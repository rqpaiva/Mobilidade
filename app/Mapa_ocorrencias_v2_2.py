import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from collections import Counter
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Blueprint, render_template, request
from pymongo import MongoClient
from unidecode import unidecode
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import folium
from folium.features import GeoJsonTooltip
import unicodedata


# ------------------------------------------------------------
# Logging e Mongo
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger("app.mapa_ocorrencias")
logging.getLogger("pymongo").setLevel(logging.WARNING)

_client = None
_db = None


def load_config():
    """Inicializa (uma única vez) o cliente do Mongo e retorna a DB."""
    global _client, _db
    if _db is not None:
        return _db
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB", "mobility_data")

    _client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=7000,
        connectTimeoutMS=5000,
        retryWrites=True,
        appname="mobilidade"
    )
    _db = _client[mongo_db]
    return _db


# --- NOVO: período global da base (min/max created_at) ---
def get_rides_global_range():
    db = load_config()
    # tenta pelos dois campos e pega min/max reais
    mins = []
    maxs = []
    for field in ("created_at", "request_datetime"):
        doc_min = db["rides_original"].find_one({field: {"$exists": True}}, {field: 1}, sort=[(field, 1)])
        doc_max = db["rides_original"].find_one({field: {"$exists": True}}, {field: 1}, sort=[(field, -1)])
        if doc_min and doc_min.get(field):
            mins.append(pd.to_datetime(doc_min[field]))
        if doc_max and doc_max.get(field):
            maxs.append(pd.to_datetime(doc_max[field]))
    if not mins or not maxs:
        now = pd.Timestamp.utcnow().normalize()
        return now - pd.Timedelta(days=30), now
    return min(mins), max(maxs)

# --- Rótulos dos bins de hora (ex.: -2h,-1h,0h,+1h...) ---
def hour_bin_labels(tempo_janela):
    # 12 bins simétricos no intervalo [-tempo, +tempo]
    edges = np.linspace(-tempo_janela, tempo_janela, 13)
    centers = (edges[:-1] + edges[1:]) / 2.0
    labels = []
    for c in centers:
        if abs(c) < 1e-9:
            labels.append("0h")
        else:
            labs = f"{c:.1f}h".replace("+", "")
            labels.append(labs)
    return labels, edges



# ------------------------------------------------------------
# Normalização e utilitários
# ------------------------------------------------------------

def strip_accents(s: str) -> str:
    if not isinstance(s, str):
        return s
    return "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_bairro(name: str) -> str:
    if not isinstance(name, str):
        return "desconhecido"
    s = strip_accents(name).lower().strip()
    # normalizações específicas comuns em bases do Rio
    replacements = {
        "ilha do governador": "ilha do governador",
        "ilha do fundao": "ilha do fundao",
        "niteroi": "niteroi",
        "centro - rio de janeiro": "centro",
        "rio de janeiro": "rio de janeiro",  # quando vem a cidade no lugar do bairro
    }
    return replacements.get(s, s)


# --- Mapeamento das Zonas e seus Bairros ---
ZONE_MAP = {
    "Zona Norte": {unidecode(s.lower().strip()) for s in [
        'Abolição', 'Acari', 'Água Santa', 'Alto da Boa Vista', 'Anchieta', 'Andaraí',
        'Bancários', 'Barros Filho', 'Bento Ribeiro', 'Bonsucesso', 'Brás de Pina', 'Cachambi', 'Cacuia',
        'Campinho', 'Cascadura', 'Cavalcanti', 'Cidade Universitária', 'Cocotá', 'Coelho Neto', 'Colégio',
        'Complexo do Alemão', 'Cordovil', 'Costa Barros', 'Del Castilho', 'Encantado', 'Engenheiro Leal',
        'Engenho da Rainha', 'Engenho de Dentro', 'Engenho Novo', 'Freguesia (Ilha do Governador)',
        'Galeão', 'Guadalude', 'Grajaú', 'Higienópolis', 'Honório Gurgel', 'Inhaúma', 'Irajá', 'Jacaré',
        'Jacarezinho', 'Jardim América', 'Jardim Carioca', 'Jardim Guanabara', 'Lins de Vasconcelos',
        'Madureira', 'Manguinhos', 'Maracanã', 'Maré', 'Marechal Hermes', 'Maria da Graça', 'Méier',
        'Moneró', 'Olaria', 'Oswaldo Cruz', 'Osvaldo Cruz', 'Parada de Lucas', 'Parque Anchieta',
        'Parque Colúmbia', 'Pavuna', 'Penha', 'Penha Circular', 'Piedade', 'Pilares', 'Pitangueiras',
        'Portuguesa', 'Praça da Bandeira', 'Praia da Bandeira', 'Quintino Bocaiúva', 'Ramos', 'Riachuelo',
        'Rocha', 'Rocha Miranda', 'Sampaio', 'São Francisco Xavier', 'Tijuca', 'Todos os Santos',
        'Tomás Coelho', 'Turiaçu', 'Vaz Lobo', 'Vicente de Carvalho', 'Vila da Penha', 'Vila Kosmos',
        'Vigário Geral', 'Vista Alegre', 'Vila Isabel'
    ]},
    "Zona Sul": {unidecode(s.lower().strip()) for s in [
        'Botafogo', 'Catete', 'Copacabana', 'Cosme Velho', 'Flamengo', 'Gávea', 'Humaitá', 'Ipanema',
        'Jardim Botânico', 'Lagoa', 'Laranjeiras', 'Leblon', 'Leme', 'Rocinha', 'São Conrado', 'Urca', 'Vidigal'
    ]},
    "Zona Oeste": {unidecode(s.lower().strip()) for s in [
        'Anil', 'Bangu', 'Barra da Tijuca', 'Barra de Guaratiba', 'Barra Olímpica', 'Camorim',
        'Campo dos Afonsos', 'Campo Grande', 'Cidade de Deus', 'Cosmos', 'Curicica', 'Deodoro',
        'Freguesia (Jacarepaguá)', 'Gardênia Azul', 'Gericinó', 'Grumari', 'Guaratiba', 'Inhoaíba',
        'Itanhangá', 'Jacarepaguá', 'Jardim Sulacap', 'Joá', 'Magalhães Bastos', 'Paciência', 'Padre Miguel',
        'Pechincha', 'Pedra de Guaratiba', 'Praça Seca', 'Realengo', 'Recreio dos Bandeirantes', 'Santa Cruz',
        'Santíssimo', 'Senador Camará', 'Senador Vasconcelos', 'Sepetiba', 'Tanque', 'Taquara', 'Vargem Grande',
        'Vargem Pequena', 'Vila Kennedy', 'Vila Militar', 'Vila Valqueire'
    ]},
    "Zona Central": {unidecode(s.lower().strip()) for s in [
        'Benfica', 'Caju', 'Catumbi', 'Centro', 'Cidade Nova', 'Estácio', 'Gamboa', 'Glória', 'Lapa',
        'Mangueira', 'Paquetá', 'Rio Comprido', 'Santa Teresa', 'Santo Cristo', 'Santos Dumont',
        'São Cristóvão', 'Saúde', 'Vasco da Gama'
    ]}
}


def get_zone(bairro: str) -> str:
    b = normalize_bairro(bairro)
    for zona, bairros in ZONE_MAP.items():
        if b in bairros:
            return zona
    return "Outro"


def get_agent(status: str) -> str:
    s = (status or "").lower()
    if "taxista" in s or "motorista" in s:
        return "Motorista"
    if "passageiro" in s:
        return "Passageiro"
    return "Outro"


def haversine_np(lat1, lon1, lat2, lon2):
    """Haversine vetorizada (km). lat1/lon1 podem ser arrays; lat2/lon2 escalares."""
    R = 6371.0088
    lat1 = np.radians(lat1).astype(float)
    lon1 = np.radians(lon1).astype(float)
    lat2 = np.radians(lat2).astype(float)
    lon2 = np.radians(lon2).astype(float)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _detect_bairro_prop(gj):
    if not gj or not gj.get("features"):
        return None
    props = gj["features"][0].get("properties", {})
    candidatos = [
        "bairro", "BAIRRO",
        "nm_bairro", "NM_BAIRRO",
        "nome_bairro", "NOME_BAIRRO",
        "nome", "NOME"
    ]
    for k in candidatos:
        if k in props:
            return k
    # fallback: primeira chave
    return next(iter(props.keys()), None)

# normaliza string de bairro para casar GeoJSON x DataFrame
def _norm_bairro(s):
    if s is None:
        return ""
    s = str(s).strip().lower()
    # se quiser, remova acentos aqui
    return s

def build_mapa_bairros(bairro_df, gj_bairros, center=(-22.906, -43.19), zoom_start=10):
    """
    Choropleth por bairro:
      - cor por taxa de cancelamentos influenciados (%)
      - cinza para 'sem impacto' (0) e 'sem dado'
      - tooltip com métricas
      - bins por quantis (melhor contraste)
    Retorna HTML do folium.
    """
    if bairro_df is None or bairro_df.empty or not gj_bairros:
        return "<div class='muted'>Sem dados para renderizar o mapa.</div>"

    # Detecta chave de bairro do GeoJSON
    key_bairro = _detect_bairro_prop(gj_bairros)
    if not key_bairro:
        return "<div class='muted'>GeoJSON sem propriedades de bairro reconhecíveis.</div>"

    # Prepara DF
    df = bairro_df.copy()
    # garante colunas
    for col in ("bairro","total_rides","influenced_cancels","rate"):
        if col not in df.columns:
            df[col] = 0

    # adiciona zona (se não tiver)
    if "zona" not in df.columns:
        df["zona"] = df["bairro"].apply(get_zone)

    # taxa em %
    df["rate_pct"] = (df["rate"].astype(float) * 100).round(2)
    # zera vira NaN -> será pintado como cinza
    df.loc[df["influenced_cancels"] <= 0, "rate_pct"] = np.nan

    # índices para o join
    df["_key"] = df["bairro"].map(_norm_bairro)

    # Mapa base claro (melhor contraste)
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="CartoDB positron")

    # Prepara bins por quantis (só em valores > 0)
    vals = df["rate_pct"].dropna()
    if len(vals) >= 5:
        qs = np.quantile(vals, [0, .2, .4, .6, .8, 1.0])
        threshold_scale = [float(round(v, 2)) for v in qs]
    else:
        # fallback estável
        maxv = float(vals.max()) if len(vals) else 1.0
        threshold_scale = [0.0, maxv*0.2, maxv*0.4, maxv*0.6, maxv*0.8, maxv]

    # Choropleth principal (pinta onde há taxa)
    folium.Choropleth(
        geo_data=gj_bairros,
        data=df,
        columns=["_key", "rate_pct"],
        key_on=f"feature.properties.{key_bairro}",
        fill_color="YlOrRd",
        nan_fill_color="#e5e7eb",      # cinza clarinho p/ sem impacto/sem dado
        fill_opacity=0.75,
        line_opacity=0.9,
        line_color="#334155",
        line_weight=1,
        threshold_scale=threshold_scale,
        legend_name="Taxa de cancelamentos influenciados (%)",
        highlight=True
    ).add_to(m)

    # GeoJson com tooltip + destaque no hover
    def style_fn(_):
        return {"fillOpacity": 0, "color": "#334155", "weight": 1}

    # monta dicionário para acesso rápido: chave normalizada -> métricas
    dmap = df.set_index("_key")[["rate_pct","influenced_cancels","total_rides","zona"]].to_dict(orient="index")

    def tooltip_fields(feature):
        nome = feature["properties"].get(key_bairro, "")
        k = _norm_bairro(nome)
        rec = dmap.get(k, None)
        if rec:
            taxa = f"{rec['rate_pct']:.2f}%"
            canc = int(rec["influenced_cancels"])
            tot  = int(rec["total_rides"])
            zona = rec["zona"] or "-"
        else:
            taxa, canc, tot, zona = "0.00%", 0, 0, "-"
        return {
            "Bairro": nome,
            "Zona": zona,
            "Cancel. infl.": canc,
            "Corridas analisadas": tot,
            "Taxa": taxa
        }

    gj_layer = folium.GeoJson(
        gj_bairros,
        name="Bairros",
        style_function=style_fn,
        highlight_function=lambda f: {"weight": 3, "color": "#0f172a"},
        tooltip=GeoJsonTooltip(
            fields=[], # ignorado; usamos `aliases` com func abaixo
            aliases=[], localize=True, sticky=False
        )
    )
    # ajusta tooltip por feature (workaround para mostrar dados calculados)
    for f in gj_layer.data["features"]:
        info = tooltip_fields(f)
        # substitui o 'tooltip' text manualmente
        f["properties"]["_tt"] = "<br>".join([f"<b>{k}:</b> {v}" for k,v in info.items()])
    gj_layer.tooltip = folium.GeoJsonTooltip(fields=["_tt"], aliases=[""], labels=False, sticky=False)
    gj_layer.add_to(m)

    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m._repr_html_()



# ------------------------------------------------------------
# Carregamento de dados
# ------------------------------------------------------------
def _pick_rides_date_field(db) -> Optional[str]:
    doc = db['rides_original'].find_one(
        {'request_datetime': {'$exists': True}}, {'request_datetime': 1}, sort=[('request_datetime', -1)]
    )
    if doc and 'request_datetime' in doc:
        return 'request_datetime'
    doc = db['rides_original'].find_one(
        {'created_at': {'$exists': True}}, {'created_at': 1}, sort=[('created_at', -1)]
    )
    if doc and 'created_at' in doc:
        return 'created_at'
    return None


def _rides_projection():
    return {
        '_id': 0,
        'origin_lat': 1, 'origin_lng': 1,
        'status': 1,
        'suburb_client': 1, 'road_client': 1,
        'request_datetime': 1, 'created_at': 1
    }


def carregar_dados(di_dt, df_dt, tempo_janela_horas=2.0, max_rides=200_000):
    """Carrega rides e eventos limitando no banco e com fallback por campo de data."""
    db = load_config()

    # Intervalo ampliado (± janela) para casar com eventos
    date_min = di_dt - timedelta(hours=tempo_janela_horas)
    date_max = df_dt + timedelta(hours=tempo_janela_horas)

    # Rides: $or request_datetime/created_at
    rides_cur = db['rides_original'].find(
        {
            '$or': [
                {'request_datetime': {'$gte': date_min, '$lt': date_max}},
                {'created_at': {'$gte': date_min, '$lt': date_max}}
            ]
        },
        _rides_projection()
    ).limit(max_rides)
    rides = pd.DataFrame(list(rides_cur))

    # Fallback: pega último período disponível se nada voltar
    if rides.empty:
        date_field = _pick_rides_date_field(db)
        if date_field:
            last_doc = list(db['rides_original'].find(
                {date_field: {'$exists': True}}, {date_field: 1, '_id': 0}
            ).sort(date_field, -1).limit(1))
            if last_doc:
                last_dt = pd.to_datetime(last_doc[0][date_field])
                date_min = last_dt - timedelta(days=30)
                date_max = last_dt + timedelta(days=1)
                rides = pd.DataFrame(list(
                    db['rides_original'].find(
                        {
                            '$or': [
                                {'request_datetime': {'$gte': date_min, '$lt': date_max}},
                                {'created_at': {'$gte': date_min, '$lt': date_max}}
                            ]
                        },
                        _rides_projection()
                    ).limit(max_rides)
                ))

    if rides.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Normalizações
    if 'created_at' not in rides.columns and 'request_datetime' in rides.columns:
        rides['created_at'] = rides['request_datetime']
    rides['created_at'] = pd.to_datetime(rides['created_at'], errors='coerce')
    rides.rename(columns={'suburb_client': 'bairro'}, inplace=True)
    rides['bairro'] = rides['bairro'].apply(normalize_bairro)

    # Janela efetiva das rides
    rides_min = pd.to_datetime(rides['created_at'].min())
    rides_max = pd.to_datetime(rides['created_at'].max())

    # Ocorrências que intersectam a janela (± tempo)
    occs_cur = db['ocorrencias'].find(
        {
            'data_inicio': {'$lt': rides_max + timedelta(hours=tempo_janela_horas)},
            'data_fim': {'$gt': rides_min - timedelta(hours=tempo_janela_horas)}
        },
        {
            '_id': 1, 'data_inicio': 1, 'data_fim': 1,
            'latitude': 1, 'longitude': 1,
            'id_pop': 1, 'descricao': 1, 'event_id': 1, 'pop_titulo': 1
        }
    )
    occs = pd.DataFrame(list(occs_cur))

    # Enriquecimentos
    procs = pd.DataFrame(list(db['procedimento_operacional_padrao'].find({}, {
        'id_pop': 1, 'pop_titulo': 1, 'pop_descricao': 1
    })))
    orgs = pd.DataFrame(list(db['ocorrencias_orgaos_responsaveis'].find({}, {
        'id_evento': 1, 'sigla': 1, 'descricao': 1
    })))

    if not occs.empty:
        if '_id' in occs.columns:
            occs.rename(columns={'_id': 'event_id'}, inplace=True)
        occs['event_id'] = occs['event_id'].astype(str)
        occs['data_inicio'] = pd.to_datetime(occs['data_inicio'], errors='coerce')
        occs['data_fim'] = pd.to_datetime(occs['data_fim'], errors='coerce')

        if not procs.empty and 'id_pop' in occs.columns and 'id_pop' in procs.columns:
            try:
                procs['id_pop'] = procs['id_pop'].astype(occs['id_pop'].dtype)
            except Exception:
                pass
            occs = occs.merge(procs, on='id_pop', how='left')

        if not orgs.empty:
            orgs = orgs.rename(columns={'id_evento': 'event_id'})
            orgs['event_id'] = orgs['event_id'].astype(str)
            agg = (orgs.groupby('event_id', as_index=False)
                   .agg({
                       'sigla': lambda x: ', '.join(sorted(set(x.dropna()))) if not x.dropna().empty else 'N/A',
                       'descricao': lambda x: ', '.join(sorted(set(x.dropna()))) if not x.dropna().empty else 'N/A'
                   }))
            occs = (occs.merge(agg, on='event_id', how='left')
                        .rename(columns={'sigla': 'orgaos_siglas', 'descricao': 'orgaos_descricoes'}))

    return rides, occs


# ------------------------------------------------------------
# Núcleo analítico
# ------------------------------------------------------------
def processar_cancelamentos(rides, occs, dist_max=2.0, tempo_janela=2.0):
    """
    Calcula estatísticas de impacto dos eventos:
    - stats: vários agregados (mapa, tabelas, gráficos)
    - canc_mot, canc_pas: totais de cancelamentos por agente
    - tot_motoristas, tot_passageiros: contagem de corridas por agente
    - bairro_df: base por bairro (total x cancelamentos influenciados x taxa)
    """
    try:
        # -------------------- Pré-processamento da base de corridas --------------------
        rides = rides.copy()
        rides['cancelada'] = rides['status'].str.contains(
            'cancelada pelo taxista|cancelada pelo passageiro', case=False, na=False
        )
        rides['agente'] = rides['status'].apply(get_agent)           # 'Motorista' | 'Passageiro' | None
        rides['zona']   = rides['bairro'].apply(get_zone)            # Zona por bairro (padrão do projeto)

        total_rides = int(len(rides))
        canc_mot = int(((rides['agente'] == 'Motorista')  & rides['cancelada']).sum())
        canc_pas = int(((rides['agente'] == 'Passageiro') & rides['cancelada']).sum())
        total_cancels = canc_mot + canc_pas

        labels, bins = hour_bin_labels(tempo_janela)  # bins para o gráfico temporal
        centers = (bins[:-1] + bins[1:]) / 2.0  # centros dos bins

        # ordem padrão das zonas
        zone_order = ['Zona Norte', 'Zona Sul', 'Zona Oeste', 'Zona Central']

        stats = {
            'total_events': int(len(occs)),
            'events_by_zone': defaultdict(int),
            'events_by_type': defaultdict(int),

            'pairs_event_zone': [],            # [( "Evento — Zona", canc_infl ) ...]
            'events_by_type_summary': [],      # [{tipo, total_periodo, com_influencia, canc_infl, mot, pass, pct_mot, pct_pass}]
            'top_bairro_by_zone': {},          # zona -> {bairro, evento, hora_pico, canc_infl}

            'zone_impact': {},                 # zona -> {top_event, avg_duration, total_cancels, motorista_rate, passageiro_rate}

            'hourly_impact': {
                'motorista':  {'num': np.zeros(len(bins)-1), 'den': np.zeros(len(bins)-1)},
                'passageiro': {'num': np.zeros(len(bins)-1), 'den': np.zeros(len(bins)-1)},
            },

            'hourly_zone': {
                z: {
                    'motorista': {'num': np.zeros(len(bins) - 1), 'den': np.zeros(len(bins) - 1)},
                    'passageiro': {'num': np.zeros(len(bins) - 1), 'den': np.zeros(len(bins) - 1)},
                } for z in zone_order
            },

            'hour_bins': {'labels': list(labels), 'centers': centers.tolist()},

            'address_impact': [],
            'influenced_total': 0,
            'influenced_cancels_total': 0,
            'events_correlated_count': 0,
            'total_rides': total_rides,
            'total_cancels': total_cancels,
        }

        # -------------------- Vetores e acumuladores auxiliares (ACRÉSCIMO a) --------------------
        lat = rides['origin_lat'].to_numpy(dtype='float64')
        lon = rides['origin_lng'].to_numpy(dtype='float64')
        tns = rides['created_at'].to_numpy(dtype='datetime64[ns]')

        is_cancel = rides['cancelada'].to_numpy()
        is_motor  = rides['agente'].eq('Motorista').to_numpy()
        is_pass   = rides['agente'].eq('Passageiro').to_numpy()

        bairros_arr = rides['bairro'].to_numpy(object)
        zonas_arr   = rides['zona'].to_numpy(object)

        # acumuladores para "Top bairros por zona"
        peak_counts = defaultdict(Counter)   # (zona,bairro) -> Counter(bin_idx)  (ACRÉSCIMO)
        tipo_counts = defaultdict(Counter)   # (zona,bairro) -> Counter(tipo)     (ACRÉSCIMO)

        # índices de todos os cancelamentos (base p/ denominador do gráfico temporal)
        idx_cancel_m = np.where(is_cancel & is_motor)[0]
        idx_cancel_p = np.where(is_cancel & is_pass)[0]

        # Índices de cancelamentos denominador por ZONA
        idx_cancel_m_by_zone = {
            z: np.where(is_cancel & is_motor & (zonas_arr == z))[0] for z in zone_order
        }
        idx_cancel_p_by_zone = {
            z: np.where(is_cancel & is_pass & (zonas_arr == z))[0] for z in zone_order
        }

        influenced = np.zeros(len(rides), dtype=bool)
        links = []             # linhas por (event_id, zona, bairro, evento)
        events_rows = []       # por evento (para pares Evento — Zona)

        # duração de cada evento
        if not occs.empty:
            occs_dur = occs.copy()
            occs_dur['duration_h'] = (occs_dur['data_fim'] - occs_dur['data_inicio']).dt.total_seconds() / 3600.0
        else:
            occs_dur = pd.DataFrame(columns=['event_id','duration_h'])

        # -------------------- Loop de eventos --------------------
        for _, ev in occs.iterrows():
            if pd.isna(ev.get('latitude')) or pd.isna(ev.get('longitude')) or pd.isna(ev.get('data_inicio')):
                continue

            ev_lat = float(ev['latitude'])
            ev_lon = float(ev['longitude'])
            t0     = np.datetime64(ev['data_inicio'].to_datetime64())

            evt_nome    = ev.get('pop_titulo') or 'Sem Título'
            zona_evento = get_zone(ev.get('descricao','')) or 'Outro'  # se houver descrição

            stats['events_by_type'][evt_nome] += 1

            # janela temporal
            mask_t = np.abs((tns - t0) / np.timedelta64(1,'h')) <= tempo_janela

            # bounding box rápido
            lat_deg = dist_max / 110.574
            lon_deg = dist_max / (111.320 * np.cos(np.radians(ev_lat)) + 1e-9)
            mask_bb = (np.abs(lat - ev_lat) <= lat_deg) & (np.abs(lon - ev_lon) <= lon_deg)

            cand_idx = np.where(mask_t & mask_bb)[0]
            if cand_idx.size == 0:
                continue

            # haversine fino
            d = haversine_np(lat[cand_idx], lon[cand_idx], ev_lat, ev_lon)
            cand_idx = cand_idx[d <= dist_max]
            if cand_idx.size == 0:
                continue

            influenced[cand_idx] = True

            # ---------- (ACRÉSCIMO b) Top bairros: contagem por bin horário e tipo ----------
            cidx_canc = cand_idx[is_cancel[cand_idx]]
            if cidx_canc.size:
                t_rel = ((tns[cidx_canc] - t0) / np.timedelta64(1,'h')).astype(float)
                bin_idx = np.digitize(t_rel, bins) - 1
                bin_idx = np.clip(bin_idx, 0, len(bins)-2)

                for z, b, bi in zip(zonas_arr[cidx_canc], bairros_arr[cidx_canc], bin_idx):
                    key = (z or 'Outro', b or '—')
                    peak_counts[key][int(bi)] += 1
                    tipo_counts[key][evt_nome] += 1

            # ---------- Impacto temporal ----------
            # Numerador: somente cancelamentos influenciados
            midx_infl = cand_idx[is_motor[cand_idx] & is_cancel[cand_idx]]
            pidx_infl = cand_idx[is_pass[cand_idx]  & is_cancel[cand_idx]]

            if midx_infl.size:
                t = ((tns[midx_infl] - t0) / np.timedelta64(1,'h')).astype(float)
                h, _ = np.histogram(t, bins=bins)
                stats['hourly_impact']['motorista']['num'] += h
            if pidx_infl.size:
                t = ((tns[pidx_infl] - t0) / np.timedelta64(1,'h')).astype(float)
                h, _ = np.histogram(t, bins=bins)
                stats['hourly_impact']['passageiro']['num'] += h

            # Denominador: todos os cancelamentos da cidade, ancorados em t0
            if idx_cancel_m.size:
                t = ((tns[idx_cancel_m] - t0) / np.timedelta64(1,'h')).astype(float)
                h, _ = np.histogram(t, bins=bins)
                stats['hourly_impact']['motorista']['den'] += h
            if idx_cancel_p.size:
                t = ((tns[idx_cancel_p] - t0) / np.timedelta64(1,'h')).astype(float)
                h, _ = np.histogram(t, bins=bins)
                stats['hourly_impact']['passageiro']['den'] += h

            # =====  Impacto temporal por ZONA =====
            if cand_idx.size:
                # zonas presentes neste evento (apenas as que têm candidatos)
                cand_zs = np.unique(zonas_arr[cand_idx])
                for z in cand_zs:
                    zmask = zonas_arr[cand_idx] == z
                    zidx = cand_idx[zmask]

                    # numerador por agente (influenciados NA zona)
                    midx_z = zidx[is_motor[zidx] & is_cancel[zidx]]
                    pidx_z = zidx[is_pass[zidx] & is_cancel[zidx]]

                    if midx_z.size:
                        t = ((tns[midx_z] - t0) / np.timedelta64(1, 'h')).astype(float)
                        h, _ = np.histogram(t, bins=bins)
                        stats['hourly_zone'][z]['motorista']['num'] += h
                    if pidx_z.size:
                        t = ((tns[pidx_z] - t0) / np.timedelta64(1, 'h')).astype(float)
                        h, _ = np.histogram(t, bins=bins)
                        stats['hourly_zone'][z]['passageiro']['num'] += h

                    # denominador por agente (TODOS os cancelamentos NA zona, ancorados em t0)
                    midx_den = idx_cancel_m_by_zone.get(z, np.array([], dtype=int))
                    pidx_den = idx_cancel_p_by_zone.get(z, np.array([], dtype=int))

                    if midx_den.size:
                        t = ((tns[midx_den] - t0) / np.timedelta64(1, 'h')).astype(float)
                        h, _ = np.histogram(t, bins=bins)
                        stats['hourly_zone'][z]['motorista']['den'] += h
                    if pidx_den.size:
                        t = ((tns[pidx_den] - t0) / np.timedelta64(1, 'h')).astype(float)
                        h, _ = np.histogram(t, bins=bins)
                        stats['hourly_zone'][z]['passageiro']['den'] += h

            # ---------- Agregações para tabelas/gráficos ----------
            bdf = rides.iloc[cand_idx][['bairro','agente','cancelada']].copy()
            canc_this_event = 0

            for bairro, grp in bdf.groupby('bairro'):
                tot  = int(len(grp))
                canc = int(grp['cancelada'].sum())
                canc_this_event += canc

                links.append({
                    'EventID': str(ev['event_id']),
                    'Zona': get_zone(bairro),
                    'Bairro': bairro,
                    'Evento': evt_nome,
                    'Total': tot,
                    'TotalCanceladas': canc,
                    'MotoristaCanceladas': int(((grp['agente']=='Motorista')  & grp['cancelada']).sum()),
                    'PassageiroCanceladas': int(((grp['agente']=='Passageiro') & grp['cancelada']).sum()),
                })

            events_rows.append({
                'EventID': str(ev['event_id']),
                'Zona': zona_evento,
                'Evento': evt_nome,
                'CancInfluenciadas': canc_this_event
            })

        # -------------------- Totais finais --------------------
        stats['influenced_total'] = int(influenced.sum())
        stats['influenced_cancels_total'] = int((influenced & rides['cancelada']).sum())
        stats['events_correlated_count'] = len({r['EventID'] for r in events_rows})

        # -------------------- Pares "Evento — Zona" (Top 5 + Outros) --------------------
        if events_rows:
            df_ev = pd.DataFrame(events_rows)
            df_pairs = df_ev.groupby(['Evento','Zona'])['CancInfluenciadas'].sum().sort_values(ascending=False)
            top = df_pairs.head(5)
            outros_val = df_pairs.iloc[5:].sum() if len(df_pairs) > 5 else 0
            stats['pairs_event_zone'] = [(f"{i[0]} — {i[1]}", int(v)) for i, v in top.items()]
            if outros_val > 0:
                stats['pairs_event_zone'].append(("Outros", int(outros_val)))

        # -------------------- Tabela por zona + Top bairro por zona --------------------
        if links:
            df_links = pd.DataFrame(links)

            # Duração média por zona (a partir dos eventos que influenciaram aquela zona)
            occs_dur_map = occs_dur.set_index('event_id')['duration_h'] if not occs_dur.empty else pd.Series(dtype=float)

            for zona in ZONE_MAP.keys():
                df_z = df_links[df_links['Zona'] == zona]
                if df_z.empty:
                    continue

                # evento mais impactante na zona (por nº de cancelamentos)
                top_event = (df_z.groupby('Evento')['TotalCanceladas']
                               .sum().sort_values(ascending=False).index[0])

                # média das durações dos eventos que influenciaram a zona
                ev_ids = df_z['EventID'].unique().tolist()
                dur_vals = [occs_dur_map.get(eid, np.nan) for eid in ev_ids]
                avg_dur = float(np.nanmean(np.array(dur_vals, dtype=float))) if len(dur_vals) else 0.0

                total_inf = int(df_z['Total'].sum())
                tot_canc  = int(df_z['TotalCanceladas'].sum())
                m_rate = df_z['MotoristaCanceladas'].sum()  / max(1, total_inf)
                p_rate = df_z['PassageiroCanceladas'].sum() / max(1, total_inf)

                stats['zone_impact'][zona] = {
                    'top_event': top_event,
                    'avg_duration': avg_dur,
                    'total_cancels': tot_canc,
                    'motorista_rate': float(m_rate),
                    'passageiro_rate': float(p_rate),
                }

            # ---- Consolida "top bairro por zona"  ----
            centers = (bins[:-1] + bins[1:]) / 2.0  # centro dos bins para rótulo
            # escolhe, em cada zona, o bairro com mais cancelamentos influenciados
            por_zona = defaultdict(lambda: {'bairro': None, 'canc': 0})
            for (zona, bairro), cnt in peak_counts.items():
                total = sum(cnt.values())
                if total > por_zona[zona]['canc']:
                    por_zona[zona] = {'bairro': bairro, 'canc': total}

            stats['top_bairro_by_zone'] = {}
            for zona, info in por_zona.items():
                if not info['bairro']:
                    continue
                key = (zona, info['bairro'])

                # hora de pico: bin de maior contagem
                if peak_counts[key]:
                    bi, _ = peak_counts[key].most_common(1)[0]
                    hora  = centers[int(bi)]
                    hora_lbl = f"{hora:+.1f}h" if abs(hora) >= 0.05 else "0h"
                else:
                    hora_lbl = "0h"

                # evento predominante no bairro/zona
                evento_pred = tipo_counts[key].most_common(1)[0][0] if tipo_counts[key] else "N/D"

                stats['top_bairro_by_zone'][zona] = {
                    'bairro': info['bairro'],
                    'evento': evento_pred,
                    'hora_pico': hora_lbl,
                    'canc_infl': int(info['canc']),
                }

            # -------------------- Resumo por tipo (mot/pass + %) p/ 2ª tabela --------------------
            # total de eventos no período por tipo (ocorrências)
            tot_periodo = (occs.groupby('pop_titulo').size()
                           .rename('total_periodo')) if not occs.empty else pd.Series(dtype=int)

            # nº de eventos com influência por tipo (eventos únicos que causaram >=1 cancelamento influenciado)
            com_infl = (pd.DataFrame(events_rows).groupby('Evento')['EventID'].nunique()
                        .rename('com_influencia')) if events_rows else pd.Series(dtype=int)

            # agregados de cancelamentos influenciados por tipo e por agente (df_links)
            agg = (df_links.groupby('Evento')
                   .agg(mot=('MotoristaCanceladas','sum'),
                        _pass=('PassageiroCanceladas','sum'),
                        canc_infl=('TotalCanceladas','sum'))
                   .rename(columns={'_pass':'pass'}))

            s = pd.concat([tot_periodo, com_infl], axis=1)
            s.index.name = 'Evento'
            summary_df = s.join(agg, how='outer').fillna(0)
            summary_df['pct_mot']  = np.where(summary_df['canc_infl']>0,
                                              (100*summary_df['mot']/summary_df['canc_infl']).round(1), 0)
            summary_df['pct_pass'] = np.where(summary_df['canc_infl']>0,
                                              (100*summary_df['pass']/summary_df['canc_infl']).round(1), 0)
            summary_df = summary_df.sort_values('canc_infl', ascending=False)

            # Top 10 + "Outros"
            if len(summary_df) > 10:
                top10_df = summary_df.head(10)
                outros_df = summary_df.iloc[10:]
                soma = outros_df[['total_periodo','com_influencia','canc_infl','mot','pass']].sum()
                pctm = (100*soma['mot']/soma['canc_infl']).round(1) if soma['canc_infl']>0 else 0.0
                pcp  = (100*soma['pass']/soma['canc_infl']).round(1) if soma['canc_infl']>0 else 0.0
                top10_df = pd.concat([top10_df, pd.DataFrame([{
                    'total_periodo': int(soma['total_periodo']),
                    'com_influencia': int(soma['com_influencia']),
                    'canc_infl': int(soma['canc_infl']),
                    'mot': int(soma['mot']),
                    'pass': int(soma['pass']),
                    'pct_mot': float(pctm),
                    'pct_pass': float(pcp),
                }], index=['Outros'])])
            else:
                top10_df = summary_df

            stats['events_by_type_summary'] = [
                {'tipo': idx,
                 'total_periodo': int(row.get('total_periodo',0)),
                 'com_influencia': int(row.get('com_influencia',0)),
                 'canc_infl': int(row.get('canc_infl',0)),
                 'mot': int(row.get('mot',0)),
                 'pass': int(row.get('pass',0)),
                 'pct_mot': float(row.get('pct_mot',0)),
                 'pct_pass': float(row.get('pct_pass',0))}
                for idx, row in top10_df.iterrows()
            ]

        # -------------------- Base para o choropleth por bairro --------------------
        df_total_bairro = rides.groupby('bairro').size().rename('total_rides').to_frame()
        df_inf_canc = rides[influenced & rides['cancelada']].groupby('bairro').size().rename('influenced_cancels')
        bairro_df = (df_total_bairro.join(df_inf_canc, how='left').fillna(0)
                     .reset_index().rename(columns={'index':'bairro'}))
        bairro_df['rate'] = bairro_df['influenced_cancels'] / bairro_df['total_rides'].clip(lower=1)

        # -------------------- Top vias/ruas --------------------
        if influenced.any():
            df_addr = (rides[influenced & rides['cancelada']]
                       .groupby(['road_client','bairro','zona'])
                       .size().reset_index(name='count')
                       .sort_values('count', ascending=False).head(10))
            stats['address_impact'] = df_addr.to_dict('records')

        # retorno final
        tot_motoristas  = int((rides['agente'] == 'Motorista').sum())
        tot_passageiros = int((rides['agente'] == 'Passageiro').sum())
        return stats, canc_mot, canc_pas, tot_motoristas, tot_passageiros, bairro_df

    except Exception as e:
        logger.error(f"Erro em processar_cancelamentos: {e}")
        empty_stats = {
            'total_events': 0, 'events_by_zone': {}, 'events_by_type': {},
            'pairs_event_zone': [], 'events_by_type_summary': [], 'top_bairro_by_zone': {},
            'zone_impact': {}, 'hourly_impact': {
                'motorista': {'num':[0]*(len(bins)-1 if 'bins' in locals() else 12), 'den':[1]*(len(bins)-1 if 'bins' in locals() else 12)},
                'passageiro': {'num':[0]*(len(bins)-1 if 'bins' in locals() else 12), 'den':[1]*(len(bins)-1 if 'bins' in locals() else 12)},
            },
            'address_impact': [], 'influenced_total': 0, 'influenced_cancels_total': 0,
            'events_correlated_count': 0, 'total_rides': 0, 'total_cancels': 0
        }
        return empty_stats, 0, 0, 0, 0, pd.DataFrame(columns=['bairro','total_rides','influenced_cancels','rate'])


# ------------------------------------------------------------
# Visualizações gráficas das estatísticas de cancelamentos por zona e por tipo
# ------------------------------------------------------------

def grafico_top5_evento_zona(stats):
    try:
        data = stats.get('pairs_event_zone', [])
        if not data: return "<div class='muted'>Sem dados para o período.</div>"
        labels = [p[0] for p in data]
        values = [p[1] for p in data]
        fig = go.Figure([go.Bar(x=values, y=labels, orientation='h', text=values, textposition='auto')])
        fig.update_layout(title='Top 5 pares "Evento — Zona" por cancelamentos influenciados (Outros agregado)',
                          margin=dict(l=10,r=10,t=50,b=10), height=300)
        return fig.to_html(full_html=False)
    except Exception as e:
        logger.error(f"Erro top5 evento-zona: {e}")
        return "<div class='alert alert-danger'>Erro ao gerar gráfico</div>"

def grafico_eventos_tipo(stats, usar_log=False):
    """
    Barras agrupadas: Total de eventos x Eventos que influenciaram
    - Sem título interno (o card do HTML já tem)
    - Botões para alternar escala: Linear (padrão) / Log
    """
    summary = stats.get('events_by_type_summary') or []
    if not summary:
        return "<div class='muted'>Sem dados para o período/ filtros selecionados.</div>"

    x = [r['tipo'] for r in summary]  # Top10 + "Outros"
    y_tot_lin = [float(r.get('total_periodo', 0)) for r in summary]
    y_inf_lin = [float(r.get('com_influencia', 0)) for r in summary]

    # Para LOG: precisa ser > 0. Usamos epsilon para zeros.
    eps = 0.5
    y_tot_log = [max(eps, v) for v in y_tot_lin]
    y_inf_log = [max(eps, v) for v in y_inf_lin]

    fig = go.Figure()

    # ---- Traces para escala LINEAR (visíveis por padrão) ----
    fig.add_bar(name='Total de eventos', x=x, y=y_tot_lin, marker_color='#4c6ef5', visible=not usar_log)
    fig.add_bar(name='Eventos que influenciaram', x=x, y=y_inf_lin, marker_color='#f2555a', visible=not usar_log)

    # ---- Traces para escala LOG (mesmas séries, com epsilon; começam escondidas) ----
    fig.add_bar(name='Total de eventos', x=x, y=y_tot_log, marker_color='#4c6ef5', visible=usar_log, showlegend=usar_log)
    fig.add_bar(name='Eventos que influenciaram', x=x, y=y_inf_log, marker_color='#f2555a', visible=usar_log, showlegend=usar_log)

    # Layout sem título interno; o card do HTML já tem o <h2>
    fig.update_layout(
        template='plotly_white',
        barmode='group',
        height=430,
        margin=dict(l=30, r=20, t=10, b=80),
        legend=dict(orientation='v')
    )
    fig.update_xaxes(tickangle=-35)

    # Eixo Y inicial (linear por padrão)
    if usar_log:
        fig.update_yaxes(type='log', title_text='Quantidade (escala log)', minexponent=0)
    else:
        fig.update_yaxes(type='linear', title_text='Quantidade')

    # ---- Botões para alternar escala ----
    fig.update_layout(
        updatemenus=[dict(
            type='buttons',
            direction='right',
            x=1.0, xanchor='right',
            y=1.15, yanchor='top',
            buttons=[
                dict(
                    label='Escala linear',
                    method='update',
                    args=[
                        {"visible": [True, True, False, False]},  # liga traces lineares
                        {"yaxis": {"type": "linear", "title": "Quantidade"}}
                    ]
                ),
                dict(
                    label='Escala log',
                    method='update',
                    args=[
                        {"visible": [False, False, True, True]},  # liga traces log
                        {"yaxis": {"type": "log", "title": "Quantidade (escala log)", "minexponent": 0}}
                    ]
                ),
            ]
        )]
    )

    return fig.to_html(include_plotlyjs='cdn', full_html=False)



# ------------------------------------------------------------
# Mapa – choropleth + camada de duração
# ------------------------------------------------------------
def load_geojson(filename):
    """Carrega arquivo GeoJSON com verificação de estrutura"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, os.pardir))
        geojson_path = os.path.join(project_root, "data", filename)
        if not os.path.exists(geojson_path):
            raise FileNotFoundError(f"Arquivo {filename} não encontrado em {geojson_path}")
        with open(geojson_path, encoding="utf-8") as f:
            gj = json.load(f)
        if gj.get("type") != "FeatureCollection":
            raise ValueError("GeoJSON inválido - não é uma FeatureCollection")
        if gj["features"]:
            first_feature = gj["features"][0]
            logger.info(f"Estrutura do GeoJSON {filename}:")
            logger.info(f"Tipo: {first_feature.get('type')}")
            logger.info(f"Propriedades: {list(first_feature.get('properties', {}).keys())}")
        return gj
    except Exception as e:
        logger.error(f"Erro ao carregar GeoJSON: {e}")
        raise


def _detect_bairro_property(gj):
    """Descobre qual propriedade do GeoJSON tem o nome do bairro."""
    candidatos = ["NOME", "Nome", "nome", "BAIRRO", "Bairro", "bairro", "name", "Name"]
    for c in candidatos:
        for f in gj.get("features", []):
            if c in f.get("properties", {}):
                return c
    # fallback: primeira propriedade string encontrada
    for f in gj.get("features", []):
        for k, v in f.get("properties", {}).items():
            if isinstance(v, str):
                return k
    return None

def _poly_centroid(coords):
    """Centroid de um polígono (lista [ [x,y], ... ]) via fórmula do sapateiro."""
    if not coords: return None
    x, y = zip(*coords)
    x = np.array(x); y = np.array(y)
    # garante fechamento do anel
    if x[0] != x[-1] or y[0] != y[-1]:
        x = np.append(x, x[0]); y = np.append(y, y[0])
    a = x[:-1]*y[1:] - x[1:]*y[:-1]
    A = a.sum()/2.0
    if abs(A) < 1e-12:
        return (float(x.mean()), float(y.mean()))
    cx = ((x[:-1] + x[1:]) * a).sum()/(6*A)
    cy = ((y[:-1] + y[1:]) * a).sum()/(6*A)
    return (float(cx), float(cy))

def _feature_centroid(feat):
    """Centroide para Polygon/MultiPolygon (lon, lat)."""
    geom = feat.get("geometry", {})
    t = geom.get("type")
    if t == "Polygon":
        rings = geom.get("coordinates", [])
        if not rings: return None
        return _poly_centroid(rings[0])
    if t == "MultiPolygon":
        polys = geom.get("coordinates", [])
        if not polys: return None
        areas, cents = [], []
        for rings in polys:
            c = _poly_centroid(rings[0]) if rings else None
            if c:
                cents.append(c)
                # área aproximada para ponderar (não precisa ser exata)
                areas.append(1.0)
        if not cents: return None
        xs, ys = zip(*cents)
        return (float(np.mean(xs)), float(np.mean(ys)))
    return None

def criar_mapa_impacto(rides, occs, dist_max, bairro_df,
                       geojson_filename=None):
    """
    Renderiza choropleth por bairro usando o loader compartilhado.
    Coloque o arquivo em app/data/<arquivo>.geojson
    ou defina GEOJSON_BAIRROS_FILENAME no .env.
    """
    try:
        filename = geojson_filename or os.getenv("GEOJSON_BAIRROS_FILENAME", "bairros_rio.geojson")
        gj = load_geojson(filename)  # <=== usa sua função
        prop_bairro = _detect_bairro_property(gj)
        if not prop_bairro:
            return "<div class='alert alert-danger'>Não foi possível detectar o campo de bairro no GeoJSON.</div>"

        # adiciona chave normalizada a cada feature
        for f in gj.get("features", []):
            props = f.get("properties", {})
            props["__key_norm__"] = normalize_bairro(props.get(prop_bairro, ""))
            f["properties"] = props

        # prepara dados (%)
        data = bairro_df.copy()
        data['bairro_key'] = data['bairro'].apply(normalize_bairro)
        data['pct'] = (data['rate'] * 100).round(2)

        m = folium.Map(location=[-22.9068, -43.1729], zoom_start=11, tiles='cartodbpositron')

        folium.Choropleth(
            geo_data=gj,
            data=data,
            columns=['bairro_key', 'pct'],
            key_on='feature.properties.__key_norm__',
            fill_color='YlOrRd',
            fill_opacity=0.85,
            line_opacity=0.3,
            nan_fill_color='lightgray',
            legend_name='% de cancelamentos influenciados por eventos'
        ).add_to(m)

        # popups com taxa e totais; marcador no centroide
        for feat in gj.get("features", []):
            props = feat.get("properties", {})
            keyv  = props.get("__key_norm__", "")
            nome  = props.get(prop_bairro, "Bairro")
            row   = data.loc[data['bairro_key'] == keyv]
            if not row.empty:
                pct = float(row['pct'].values[0])
                inf = int(row['influenced_cancels'].values[0])
                tot = int(row['total_rides'].values[0])
                html = f"<b>{nome}</b><br>Taxa infl.: {pct:.2f}%<br>Cancel. infl.: {inf} / Total: {tot}"
            else:
                html = f"<b>{nome}</b><br>Sem dados no período"

            c = _feature_centroid(feat)
            if c:
                lng, lat = c[0], c[1]  # geojson = (lon,lat)
                folium.CircleMarker(
                    location=[lat, lng],
                    radius=1, opacity=0, fill_opacity=0,
                    popup=folium.Popup(html, max_width=350)
                ).add_to(m)

        folium.LayerControl().add_to(m)
        return m._repr_html_()

    except Exception as e:
        logger.error(f"Erro ao criar mapa: {e}")
        return "<div class='alert alert-danger'>Erro ao gerar o mapa</div>"




# ------------------------------------------------------------
# Gráfico temporal (taxa por bin) e Tabela
# ------------------------------------------------------------
def criar_grafico_impacto_horario(stats, tempo_janela):
    try:
        labels, edges = hour_bin_labels(tempo_janela)
        centers = (np.array(edges[:-1]) + np.array(edges[1:])) / 2.0

        m = stats['hourly_impact']['motorista']; p = stats['hourly_impact']['passageiro']
        m_rate = np.divide(m['num'], np.maximum(m['den'], 1), where=(m['den']>0))
        p_rate = np.divide(p['num'], np.maximum(p['den'], 1), where=(p['den']>0))

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=labels, y=(m_rate*100), mode='lines+markers', name='Motorista'))
        fig.add_trace(go.Scatter(x=labels, y=(p_rate*100), mode='lines+markers', name='Passageiro'))

        zero_idx = int(np.argmin(np.abs(centers)))
        fig.add_vline(x=zero_idx, line_dash="dash", line_width=1,
                      annotation_text="Comunicado", annotation_position="top right")

        fig.update_layout(
            title='Proporção de cancelamentos influenciados ÷ total de cancelamentos (antes/depois do comunicado)',
            xaxis_title='Tempo relativo ao comunicado do evento',
            yaxis_title='Proporção (%)', hovermode='x unified',
            legend=dict(orientation='h', y=1.12),
            margin=dict(l=50,r=50,t=80,b=50)
        )
        return fig.to_html(full_html=False)
    except Exception as e:
        logger.error(f"Erro gráfico temporal: {e}")
        return "<div class='alert alert-danger'>Erro ao gerar gráfico</div>"


def grafico_impacto_temporal_por_zona(stats, tempo_janela=None):
    """
    Impacto temporal por zona (2x2), respeitando a janela temporal.
    Cores fixas: Motorista (azul) / Passageiro (vermelho).
    """
    zones = ['Zona Norte','Zona Sul','Zona Oeste','Zona Central']
    hz    = stats.get('hourly_zone', {})

    # centros/labels vindos do processamento…
    bins_info = stats.get('hour_bins', {})
    centers = np.array(bins_info.get('centers') or [], dtype=float)
    labels  = bins_info.get('labels')  or []

    # …ou recalculados pela janela passada (mantém mesma grade do gráfico geral)
    if tempo_janela is not None:
        labels, edges = hour_bin_labels(tempo_janela)
        centers = (np.asarray(edges[:-1], dtype=float) + np.asarray(edges[1:], dtype=float)) / 2.0

    if not hz or centers.size == 0:
        return "<div class='muted'>Sem dados para o período/filtros selecionados.</div>"

    n_bins = centers.size

    def safe_vec(v):
        a = np.asarray(v, dtype=float)
        if a.size == 0:
            return np.zeros(n_bins, dtype=float)
        if a.size != n_bins:
            m = min(a.size, n_bins)
            return np.pad(a[:m], (0, n_bins - m), constant_values=0.0)
        return a

    # cores padrão (iguais às outras telas)
    MOTORISTA_COLOR  = '#4c6ef5'  # azul
    PASSAGEIRO_COLOR = '#f2555a'  # vermelho

    fig = make_subplots(rows=2, cols=2, subplot_titles=zones,
                        shared_xaxes=True, shared_yaxes=True)

    def add_zone(row, col, zona, showlegend):
        z = hz.get(zona) or {}
        m = z.get('motorista', {})
        p = z.get('passageiro', {})

        num_m = safe_vec(m.get('num', []))
        den_m = np.maximum(safe_vec(m.get('den', [])), 1e-9)
        num_p = safe_vec(p.get('num', []))
        den_p = np.maximum(safe_vec(p.get('den', [])), 1e-9)

        y_m = 100.0 * (num_m / den_m)
        y_p = 100.0 * (num_p / den_p)

        # Motorista (azul)
        fig.add_trace(
            go.Scatter(
                x=centers, y=y_m, mode='lines+markers',
                name='Motorista', legendgroup='Motorista',
                line=dict(width=2, color=MOTORISTA_COLOR),
                marker=dict(color=MOTORISTA_COLOR),
                showlegend=showlegend
            ),
            row=row, col=col
        )

        # Passageiro (vermelho)
        fig.add_trace(
            go.Scatter(
                x=centers, y=y_p, mode='lines+markers',
                name='Passageiro', legendgroup='Passageiro',
                line=dict(width=2, color=PASSAGEIRO_COLOR),
                marker=dict(color=PASSAGEIRO_COLOR),
                showlegend=showlegend
            ),
            row=row, col=col
        )

        # linha vertical no "0h" (comunicado)
        fig.add_vline(x=0, line_width=1, line_dash='dot', line_color='#555',
                      row=row, col=col)

    # legenda aparece só no primeiro subplot; legendgroup faz o toggle valer p/ todos
    add_zone(1,1,zones[0], showlegend=True)
    add_zone(1,2,zones[1], showlegend=False)
    add_zone(2,1,zones[2], showlegend=False)
    add_zone(2,2,zones[3], showlegend=False)

    fig.update_layout(template='plotly_white', height=620,
                      margin=dict(l=40, r=20, t=60, b=40))
    fig.update_xaxes(tickmode='array', tickvals=centers, ticktext=labels)
    fig.update_yaxes(title_text='Proporção (%)')

    return fig.to_html(include_plotlyjs='cdn', full_html=False)


def criar_tabela_estatisticas(stats):
    """Gera duas tabelas HTML com classe .table-unirio: (1) por zona, (2) por tipo."""
    try:
        # --- Tabela 1: por Zona ---
        linhas1 = []
        for zona, d in stats.get('zone_impact', {}).items():
            linhas1.append(f"""
              <tr>
                <td>{zona}</td>
                <td>{d.get('top_event','-')}</td>
                <td>{d.get('avg_duration',0):.1f}</td>
                <td>{d.get('total_cancels',0)}</td>
                <td>{d.get('motorista_rate',0)*100:.1f}</td>
                <td>{d.get('passageiro_rate',0)*100:.1f}</td>
              </tr>
            """)

        html1 = f"""
        <table class="table-unirio" style="margin-bottom:14px">
          <thead>
            <tr>
              <th>Zona</th>
              <th>Evento Mais Impactante</th>
              <th>Duração Média (h)</th>
              <th>Total Cancel. Infl.</th>
              <th>Taxa Motorista (%)</th>
              <th>Taxa Passageiro (%)</th>
            </tr>
          </thead>
          <tbody>
            {''.join(linhas1) if linhas1 else '<tr><td colspan="6">N/D</td></tr>'}
          </tbody>
        </table>
        """

        # --- Tabela 2: Top eventos (Global) ---
        linhas2 = []
        # preferir summary com agente; se não houver, usamos contagem simples
        summary = stats.get('events_by_type_summary') or []
        if not summary and stats.get('events_by_type'):
            # fallback extremamente simples, sem % (não deve acontecer após o patch acima)
            for tipo, tot in sorted(stats['events_by_type'].items(), key=lambda x: x[1], reverse=True)[:10]:
                linhas2.append(f"<tr><td>{tipo}</td><td>{tot}</td><td>–</td><td>–</td></tr>")
        else:
            # Top 10 + "Outros"
            top = summary[:10]
            outros = summary[10:]
            for r in top:
                linhas2.append(f"""
                  <tr>
                    <td>{r['tipo']}</td>
                    <td>{r['canc_infl']}</td>
                    <td>{r['pct_mot']:.1f}</td>
                    <td>{r['pct_pass']:.1f}</td>
                  </tr>
                """)
            if outros:
                soma = sum(x['canc_infl'] for x in outros)
                mot  = sum(x['mot'] for x in outros)
                pas  = sum(x['pass'] for x in outros)
                pctm = (100*mot/soma) if soma else 0
                pctp = (100*pas/soma) if soma else 0
                linhas2.append(f"""
                  <tr>
                    <td>Outros</td>
                    <td>{soma}</td>
                    <td>{pctm:.1f}</td>
                    <td>{pctp:.1f}</td>
                  </tr>
                """)

        html2 = f"""
        <table class="table-unirio">
          <thead>
            <tr>
              <th>Top Eventos (Global)</th>
              <th>Cancel. Infl.</th>
              <th>% Motorista</th>
              <th>% Passageiro</th>
            </tr>
          </thead>
          <tbody>
            {''.join(linhas2) if linhas2 else '<tr><td colspan="4">N/D</td></tr>'}
          </tbody>
        </table>
        """

        return html1 + html2
    except Exception as e:
        logger.error(f"Erro ao gerar tabelas HTML: {e}")
        return "<div class='alert alert-danger'>Erro ao gerar tabelas</div>"



# ------------------------------------------------------------
# Blueprint / Rota
# ------------------------------------------------------------
mapa_ocorrencias_app = Blueprint("mapa_ocorrencias", __name__, url_prefix="/mapa_ocorrencias")


@mapa_ocorrencias_app.route('/', methods=['GET', 'POST'])
def index():
    try:
        # --- DEFAULT: min/max da base ---
        base_min, base_max = get_rides_global_range()
        default_end   = base_max.normalize()
        default_start = base_min.normalize()

        di  = request.form.get('data_inicio', default_start.strftime('%Y-%m-%d'))
        df_ = request.form.get('data_fim',    default_end.strftime('%Y-%m-%d'))
        dist_max      = float(request.form.get('distancia', 2.0))
        tempo_janela  = float(request.form.get('tempo', 2.0))
        tipo_evento   = request.form.getlist('tipo_evento')

        dist_max = max(0.5, min(5.0, dist_max))
        di_dt = pd.to_datetime(di)
        df_dt = pd.to_datetime(df_)

        rides, occs = carregar_dados(di_dt, df_dt, tempo_janela)

        aviso = None
        eventos_disponiveis = []
        if rides.empty:
            aviso = "Sem corridas no período selecionado. Ajuste as datas e tente novamente."
            return render_template('mapa_ocorrencias.html',
                                   data_inicio=di, data_fim=df_,
                                   distancia_maxima_km=dist_max, tempo_janela=tempo_janela,
                                   eventos_disponiveis=[], tipo_evento_selecionado=tipo_evento,
                                   mapa_html="", impacto_horario_html="", tabela_html="",
                                   stats={'events_by_zone': {}, 'events_by_type': {},
                                          'events_by_zone_detail': {}, 'top_bairro_by_zone': {},
                                          'events_by_type_summary': [], 'top_events': [],
                                          'zone_impact': {}, 'hourly_impact': {'motorista': {'num':[0]*12,'den':[1]*12},
                                                                               'passageiro': {'num':[0]*12,'den':[1]*12}},
                                          'address_impact': [], 'influenced_total':0,
                                          'influenced_cancels_total':0, 'events_correlated_count':0,
                                         },
                                   total_mot=0, total_pas=0, canc_mot=0, canc_pas=0,
                                   aviso=aviso), 200

        if not occs.empty:
            eventos_disponiveis = occs['pop_titulo'].dropna().unique().tolist()
            if tipo_evento:
                occs = occs[occs['pop_titulo'].isin(tipo_evento)]

        stats, canc_mot, canc_pas, total_mot, total_pas, bairro_df = processar_cancelamentos(
            rides, occs, dist_max, tempo_janela
        )

        gj_bairros = load_geojson("censo2022_bairros.geojson")
        mapa_html = build_mapa_bairros(bairro_df, gj_bairros, center=(-22.906, -43.19), zoom_start=10)
        impacto_horario_html = criar_grafico_impacto_horario(stats, tempo_janela)
        impacto_horario_zona_html = grafico_impacto_temporal_por_zona(stats, tempo_janela)
        tabela_html = criar_tabela_estatisticas(stats)
        graf_pares_html = grafico_top5_evento_zona(stats)
        graf_tipos_html = grafico_eventos_tipo(stats)

        return render_template('mapa_ocorrencias.html',
                               data_inicio=di, data_fim=df_,
                               distancia_maxima_km=dist_max, tempo_janela=tempo_janela,
                               eventos_disponiveis=eventos_disponiveis, tipo_evento_selecionado=tipo_evento,
                               graf_pares_html=graf_pares_html, graf_tipos_html=graf_tipos_html,
                               mapa_html=mapa_html, impacto_horario_html=impacto_horario_html,
                               impacto_horario_zona_html=impacto_horario_zona_html,
                               tabela_html=tabela_html, stats=stats,
                               total_mot=total_mot, total_pas=total_pas,
                               canc_mot=canc_mot, canc_pas=canc_pas,
                               aviso=aviso), 200
    except Exception as e:
        logger.exception("Erro no endpoint /mapa_ocorrencias:")
        return render_template('error.html', error=str(e)), 500


