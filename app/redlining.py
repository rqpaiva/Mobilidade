import os
import logging
import geopandas as gpd
import re  # usado em build_query
from datetime import datetime, timedelta
from collections import defaultdict
from shapely.geometry import shape, Point, Polygon
from flask import Flask, Blueprint, request, render_template, request, jsonify, make_response
from dotenv import load_dotenv
from pymongo import MongoClient
from unidecode import unidecode
import folium
import folium.plugins
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from collections import defaultdict
import json, numpy as np, pandas as pd
import time


# Configuração de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

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


# --- Helpers de normalização de cancelamento ---
def _norm_txt(s):
    try:
        return s.astype(str).map(lambda x: unidecode(x).lower())
    except Exception:
        return pd.Series([''], index=s.index)

def ensure_cancel_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante/deriva is_driver_cancel e is_passenger_cancel a partir de:
    - Colunas já existentes (coerção para 0/1);
    - Campos estruturados (cancel_by/canceled_by/who_canceled/quem_cancelou...);
    - Texto em 'status' (driver/motorista/taxista vs passageiro + 'cancel').
    """
    if df is None or df.empty:
        return df

    # Se já existem, normaliza para 0/1
    if 'is_driver_cancel' in df.columns:
        df['is_driver_cancel'] = pd.to_numeric(df['is_driver_cancel'], errors='coerce').fillna(0).astype(int)
    else:
        df['is_driver_cancel'] = 0

    if 'is_passenger_cancel' in df.columns:
        df['is_passenger_cancel'] = pd.to_numeric(df['is_passenger_cancel'], errors='coerce').fillna(0).astype(int)
    else:
        df['is_passenger_cancel'] = 0

    # Estruturados
    for col in ['cancel_by', 'canceled_by', 'cancelled_by', 'who_canceled', 'quem_cancelou', 'quem_cancelou_corrida']:
        if col in df.columns:
            v = _norm_txt(df[col])
            df.loc[v.isin(['driver', 'motorista', 'taxista']), 'is_driver_cancel'] = 1
            df.loc[v.isin(['passenger', 'passageiro', 'passageira']), 'is_passenger_cancel'] = 1

    # Texto em 'status'
    if 'status' in df.columns:
        s = _norm_txt(df['status'])
        has_cancel = (
            s.str.contains('cancel', na=False) |
            s.str.contains('cancelou', na=False) |
            s.str.contains('cancelad', na=False)
        )
        is_driver = (
            s.str.contains('driver', na=False) |
            s.str.contains('motorist', na=False) |
            s.str.contains('motorista', na=False) |
            s.str.contains('taxista', na=False)
        )
        is_pass = (
            s.str.contains('passenger', na=False) |
            s.str.contains('passageir', na=False)
        )
        df.loc[has_cancel & is_driver, 'is_driver_cancel'] = 1
        df.loc[has_cancel & is_pass,   'is_passenger_cancel'] = 1

    # Coerção final
    df['is_driver_cancel'] = df['is_driver_cancel'].fillna(0).astype(int)
    df['is_passenger_cancel'] = df['is_passenger_cancel'].fillna(0).astype(int)
    return df





# --------------- Utils Geo/Filtros ------------------

def slugify(text):
    """Remove acentos, baixa caixa e troca não-alfanum por '_'"""
    if text is None:
        return ''
    s = unidecode(str(text)).lower().strip()
    return re.sub(r'[^a-z0-9]+', '_', s)

def carregar_bairros_geojson():
    """
    Ajuste o nome do arquivo conforme seu diretório /data.
    """
    return load_geojson("censo2022_bairros.geojson")

def carregar_favelas_geojson():
    return load_geojson("Limite_Favelas_2019.geojson")


def montar_zone_neighborhoods(bairros_geojson):
    """
    Retorna dict { 'Zona Norte': ['Méier', ...], ... }
    Usa get_zone(...) para classificar.
    """
    zone_map = defaultdict(list)
    for feat in bairros_geojson.get('features', []):
        props = feat.get('properties', {})
        bairro = (
            props.get('Bairros') or props.get('bairro') or
            props.get('BAIRRO') or props.get('NOME') or props.get('name') or 'Desconhecido'
        )
        zone = get_zone(bairro)
        zone_map[zone].append(bairro)
    return dict(zone_map)

def montar_neighborhood_favelas(favelas_geojson):
    """
    Dict { slug_bairro: [ {nome:'...', complexo:'...'}, ... ] }
    Usa a função criar_mapeamento_favelas_bairros e faz slug na chave.
    """
    raw = criar_mapeamento_favelas_bairros(favelas_geojson)
    out = {}
    for bairro, lst in raw.items():
        out[slugify(bairro)] = lst
    return out


def buscar_bairro_da_favela(nome_favela, favelas_geojson):
    """
    Retorna o bairro da favela pelo nome (primeira ocorrência).
    """
    alvo = unidecode(nome_favela).lower().strip()
    for feat in favelas_geojson.get('features', []):
        props = feat.get('properties', {})
        nome = props.get('nome') or props.get('NOME') or ''
        if unidecode(nome).lower().strip() == alvo:
            return props.get('bairro') or props.get('Bairro') or ''
    return ''

def buscar_zona_do_bairro(bairro, zone_neighborhoods):
    """
    Procura a zona do bairro usando o dict zone_neighborhoods.
    """
    alvo = unidecode(bairro).lower().strip()
    for zone, bairros in zone_neighborhoods.items():
        if any(unidecode(b).lower().strip() == alvo for b in bairros):
            return zone
    return 'Outros'



# --- Mapeamento das Favelas e seus Bairros ---

def criar_mapeamento_favelas_bairros(favelas_geojson):
    """Cria mapeamento de favelas para bairros a partir do GeoJSON"""
    mapeamento = defaultdict(list)
    for feature in favelas_geojson['features']:
        nome = feature['properties'].get('nome') or 'Desconhecida'
        complexo = feature['properties'].get('complexo') or 'N/A'
        bairro = feature['properties'].get('bairro') or 'N/A'
        mapeamento[bairro].append({
            'nome': nome,
            'complexo': complexo
        })
    return dict(mapeamento)


def get_zone(suburb):
    """Determina a zona de um bairro"""
    if not suburb:
        return 'Outros'
    key = unidecode(suburb).lower().strip()
    for zone, suburbs in ZONE_MAP.items():
        if key in suburbs:
            return zone
    return 'Outros'


def build_query(filters):
    """
    Monta o dicionário de query para MongoDB com base nos filtros.
    NÃO inclui filtro por distância (isso é feito após o cálculo).
    """
    query = {}

    # Status
    if filters.get('status'):
        status_map = {
            'completed': {'$regex': 'Finalizada', '$options': 'i'},
            'driver_cancel': {'$regex': 'Taxista|Motorista', '$options': 'i'},
            'passenger_cancel': {'$regex': 'Passageiro', '$options': 'i'}
        }
        q = status_map.get(filters['status'])
        if q:
            query['status'] = q

    # Datas
    # Campos típicos: 'request_datetime' ou 'start_time' (ajuste ao seu schema)
    date_field = 'request_datetime'
    start_date = filters.get('start_date')
    end_date   = filters.get('end_date')
    if start_date or end_date:
        query[date_field] = {}
        if start_date:
            query[date_field]['$gte'] = datetime.strptime(start_date, '%Y-%m-%d')
        if end_date:
            # incluir o último dia inteiro
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query[date_field]['$lt'] = end_dt

    # Horas
    # Supondo que você tem coluna 'hour' computada antes; se não, você pode filtrar depois em pandas
    start_time = filters.get('start_time')
    end_time   = filters.get('end_time')
    if start_time or end_time:
        # filtra depois em pandas, mais fácil
        pass

    # Zona/Bairro/Favela
    # Filtro inicial em Mongo pode reduzir o volume (se tiver esse campo já salvo)
    if filters.get('zone'):
        query['zone'] = filters['zone']
    if filters.get('neighborhood'):
        # neighborhood no DF será normalizado; aqui filtramos pelo nome original se existir no banco
        query['neighborhood'] = {'$regex': filters['neighborhood'], '$options': 'i'}
    if filters.get('favela'):
        query['favela'] = {'$regex': f"^{re.escape(filters['favela'])}$", '$options': 'i'}

    return query


def carregar_dados(db, filters):
    """
    Executa a query e devolve um DataFrame com as colunas necessárias.
    Ajuste os campos conforme seu schema em rides_original.
    """
    query = build_query(filters)
    proj = {
        '_id': 0,
        'status': 1,
        'origin_lat': 1, 'origin_lng': 1,
        'address': 1,
        'zone': 1,
        'neighborhood': 1,
        'request_datetime': 1,
        # ... inclua outros campos usados em stats (driver_id, etc.)
    }
    rides = list(db.rides_original.find(query, proj))

    if not rides:
        return pd.DataFrame()

    df = pd.DataFrame(rides)

    # Ajustes básicos
    if 'request_datetime' in df.columns:
        df['request_datetime'] = pd.to_datetime(df['request_datetime'])
        df['hour'] = df['request_datetime'].dt.hour
        df['weekday'] = df['request_datetime'].dt.dayofweek
    else:
        df['hour'] = np.nan
        df['weekday'] = np.nan

    # Normalizar bairros para slug/minúsculo se necessário
    if 'neighborhood' in df.columns:
        df['neighborhood'] = df['neighborhood'].fillna('').astype(str)

    # Filtro de hora em pandas (se enviados)
    start_time = filters.get('start_time')
    end_time   = filters.get('end_time')
    if start_time:
        h0, m0 = map(int, start_time.split(':'))
        df = df[(df['hour'] > h0) | ((df['hour'] == h0) & (df['request_datetime'].dt.minute >= m0))]
    if end_time:
        h1, m1 = map(int, end_time.split(':'))
        df = df[(df['hour'] < h1) | ((df['hour'] == h1) & (df['request_datetime'].dt.minute <= m1))]

    return df



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


def haversine(lat1, lon1, lat2, lon2):
    """Calcula distância em km entre dois pontos"""
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def atribuir_rides_favelas(rides_df, favelas_geojson, raio_km):
    """
    Atribui a cada corrida a favela mais próxima e mantém informação do bairro de origem.
    Retorna DataFrame com colunas adicionais para rastreamento.
    """
    try:
        if rides_df.empty:
            rides_df['favela'] = pd.NA
            rides_df['dist_comunidade_m'] = np.nan
            rides_df['zone'] = 'Outros'
            rides_df['origem_bairro'] = pd.NA
            return rides_df

        # Garantir que temos a coluna de bairro normalizada
        if 'neighborhood' not in rides_df.columns:
            rides_df['neighborhood'] = rides_df.get('suburb_client', 'N/A')
        rides_df['neighborhood'] = rides_df['neighborhood'].fillna('N/A').astype(str)

        def _norm_neigh(s):
            try:
                return unidecode(str(s)).strip().lower()
            except Exception:
                return str(s).strip().lower()

        rides_df['origem_bairro'] = rides_df['neighborhood'].map(_norm_neigh)

        # 1) GeoDataFrame das corridas
        rides_gdf = gpd.GeoDataFrame(
            rides_df.copy(),
            geometry=gpd.points_from_xy(rides_df.origin_lng, rides_df.origin_lat),
            crs="EPSG:4326"
        ).to_crs(3857)

        # 2) Criar mapeamento favela->bairro->zona
        favela_info = {}
        for feat in favelas_geojson.get('features', []):
            props = feat.get('properties', {})
            nome = props.get('nome') or props.get('NOME') or 'Desconhecida'
            bairro = props.get('bairro') or props.get('Bairro') or ''
            favela_info[nome] = {
                'bairro': bairro,
                'zone': get_zone(bairro)
            }

        # 3) GeoDataFrame das favelas
        feats = []
        for feat in favelas_geojson.get('features', []):
            props = feat.get('properties', {})
            feats.append({
                'nome': props.get('nome') or props.get('Nome') or 'Desconhecida',
                'bairro': props.get('bairro', ''),
                'geometry': shape(feat['geometry'])
            })
        favelas_gdf = gpd.GeoDataFrame(feats, crs="EPSG:4326").to_crs(3857)

        # 4) Calcular boundary para medir distância ao PERÍMETRO
        favelas_gdf['boundary'] = favelas_gdf.geometry.boundary

        sindex = favelas_gdf.sindex
        max_m = float(raio_km) * 1000.0

        dist_list, idx_list, favela_list = [], [], []
        for idx, pt in enumerate(rides_gdf.geometry):
            # candidatos dentro de um buffer aproximado
            cand_idx = list(sindex.query(pt.buffer(max_m)))
            if not cand_idx:
                dist_list.append(np.nan)
                idx_list.append(-1)
                favela_list.append(pd.NA)
                continue

            dseries = favelas_gdf.iloc[cand_idx].boundary.distance(pt)
            j = dseries.idxmin()
            dmin = float(dseries.loc[j])

            if dmin <= max_m:
                dist_list.append(dmin)
                idx_list.append(j)
                favela_list.append(favelas_gdf.loc[j, 'nome'])
            else:
                dist_list.append(np.nan)
                idx_list.append(-1)
                favela_list.append(pd.NA)

        out = rides_gdf.drop(columns='geometry').copy()
        out['dist_comunidade_m'] = dist_list
        out['favela'] = favela_list
        out['zone'] = out['favela'].map(lambda x: favela_info.get(x, {}).get('zone', 'Outros'))

        return out

    except Exception:
        logger.exception("Erro ao atribuir favelas")
        rides_df['favela'] = pd.NA
        rides_df['dist_comunidade_m'] = np.nan
        rides_df['zone'] = 'Outros'
        rides_df['origem_bairro'] = pd.NA
        return rides_df


def processar_estatisticas(rides_df, favelas_geojson):
    """
    Calcula estatísticas gerais e específicas (favela/bairro) para o dashboard.

    Mantém a lógica original:
      - near_mask: corridas associadas a alguma favela (proximidade ao boundary da favela).
      - neighborhood_stats_all: estatística por bairro considerando APENAS corridas 'near'.
      - favela_stats_all: estatística por favela considerando APENAS corridas 'near'.
      - hourly_stats: estatística temporal considerando APENAS corridas 'near'.
      - neighborhood_stats_all_raw: estatística por bairro SEM correlação com favela (todas as corridas, "raw").
      - top_*: seleciona maior taxa (com filtro de volume) para motorista e passageiro.

    Adições:
      - normalização canônica de bairro (sem acento, minúscula) para dicionários *_raw / *_excl_favela.
      - neighborhood_near_by_origin: corridas 'near' agregadas por bairro de ORIGEM (chave canônica).
      - neighborhood_stats_excl_favela: raw − near_by_origin (por bairro canônico), com clamp a zero.

    Retorna um dicionário com as mesmas chaves já usadas no frontend, acrescido das novas chaves.
    """
    try:
        import numpy as np
        import pandas as pd
        from unidecode import unidecode
    except Exception:
        pass

    try:
        df = rides_df.copy() if rides_df is not None else pd.DataFrame()
        if df.empty:
            return {
                'total': 0, 'near_favela': 0, 'near_pct': 0.0,
                'driver': 0, 'passenger': 0, 'driver_pct': 0.0, 'passenger_pct': 0.0,
                'avg_distance': 0.0,
                'top_driver_neighborhood': None, 'top_passenger_neighborhood': None,
                'top_driver_favela': None, 'top_passenger_favela': None,
                'top_driver_hour': None, 'top_passenger_hour': None,
                'neighborhood_stats': {'top_driver': [], 'top_passenger': []},
                'favela_stats': {'top_driver': [], 'top_passenger': []},
                'hourly_stats': {'top_driver': [], 'top_passenger': []},
                'neighborhood_stats_all': {},
                'neighborhood_stats_all_raw': {},
                'neighborhood_near_by_origin': {},
                'neighborhood_stats_excl_favela': {},
                'favela_stats_all': {},
                'top_addresses': []
            }

        # --- Garantias mínimas de colunas
        if 'favela' not in df.columns:
            df['favela'] = pd.NA
        if 'zone' not in df.columns:
            df['zone'] = 'Outros'

        # Bairro de origem
        if 'neighborhood' not in df.columns:
            df['neighborhood'] = df.get('suburb_client', 'N/A')
        df['neighborhood'] = df['neighborhood'].fillna('N/A').astype(str)

        # Flags de cancelamento (sua função auxiliar já existente)
        df = ensure_cancel_flags(df)

        # Hora (0..23)
        if 'hour' not in df.columns:
            df['hour'] = 0
        df['hour'] = pd.to_numeric(df['hour'], errors='coerce').fillna(0).astype(int).clip(0, 23)

        # Distância média
        if 'dist_comunidade_m' not in df.columns:
            df['dist_comunidade_m'] = np.nan

        # --- Máscara de corridas associadas a alguma favela (near)
        near_mask = df['favela'].notna() & df['favela'].astype(str).str.strip().ne('')

        # --- Totais gerais
        total_all = int(len(df))
        near_total = int(near_mask.sum())
        driver_near = int(df.loc[near_mask, 'is_driver_cancel'].sum()) if near_total else 0
        passenger_near = int(df.loc[near_mask, 'is_passenger_cancel'].sum()) if near_total else 0

        near_pct = float((near_total / total_all) * 100) if total_all else 0.0
        driver_rate_near = float((driver_near / near_total) * 100) if near_total else 0.0
        passenger_rate_near = float((passenger_near / near_total) * 100) if near_total else 0.0
        avg_distance = float(df.loc[near_mask, 'dist_comunidade_m'].mean()) if near_total else 0.0

        # --- Helpers
        def _rate_cols(g):
            if g.empty:
                g['driver_rate'] = 0.0
                g['passenger_rate'] = 0.0
                return g
            g['driver_rate'] = (g['driver'] / g['total']).fillna(0.0)
            g['passenger_rate'] = (g['passenger'] / g['total']).fillna(0.0)
            return g

        def stats_by_group(_df, group_col, use_near_mask=True):
            """Agrupa e calcula total/driver/passenger e taxas."""
            mask = near_mask if use_near_mask else pd.Series(True, index=_df.index)
            if group_col not in _df.columns:
                return ([], [], {})
            g = (
                _df.loc[mask]
                .groupby(group_col, observed=False)
                .agg(total=('status', 'count'),
                     driver=('is_driver_cancel', 'sum'),
                     passenger=('is_passenger_cancel', 'sum'))
            )
            g = _rate_cols(g)
            if g.empty:
                return ([], [], {})

            vol_min = max(1, int(0.05 * int(g['total'].sum())))  # 5% do volume do agrupamento
            gf = g[g['total'] >= vol_min] if (g['total'] >= vol_min).any() else g

            # top listas no formato [[chave, taxa]]
            top_driver = gf.nlargest(1, 'driver_rate')[['driver_rate']].reset_index().values.tolist()
            top_pass = gf.nlargest(1, 'passenger_rate')[['passenger_rate']].reset_index().values.tolist()

            stats_all = {
                str(idx): {
                    'total': int(row['total']),
                    'driver': int(row['driver']),
                    'passenger': int(row['passenger']),
                    'driver_rate': float(row['driver_rate']),
                    'passenger_rate': float(row['passenger_rate']),
                }
                for idx, row in g.reset_index().set_index(group_col).iterrows()
            }
            return (top_driver, top_pass, stats_all)

        # --- Estatísticas por FAVELA (apenas near)
        tdf_fav, tpf_fav, favela_stats_all = stats_by_group(df, 'favela', use_near_mask=True)

        # --- Estatísticas por BAIRRO (apenas near)
        tdn_bai, tpn_bai, neighborhood_stats_all = stats_by_group(df, 'neighborhood', use_near_mask=True)

        # --- Estatísticas por HORA (apenas near)
        hourly_stats = {'top_driver': [], 'top_passenger': []}
        if near_total > 0 and 'hour' in df.columns:
            hg = (
                df.loc[near_mask]
                .groupby('hour', observed=False)
                .agg(total=('status', 'count'),
                     driver=('is_driver_cancel', 'sum'),
                     passenger=('is_passenger_cancel', 'sum'))
            )
            hg = _rate_cols(hg)
            if not hg.empty:
                vol_min = max(1, int(0.05 * near_total))
                hfil = hg[hg['total'] >= vol_min] if (hg['total'] >= vol_min).any() else hg
                td = hfil.nlargest(1, 'driver_rate')[['driver_rate']].reset_index().values.tolist()
                tp = hfil.nlargest(1, 'passenger_rate')[['passenger_rate']].reset_index().values.tolist()
                # Mantém para gráficos:
                hourly_stats['top_driver'] = [[int(float(x[0])), float(x[1])] for x in td] if td else []
                hourly_stats['top_passenger'] = [[int(float(x[0])), float(x[1])] for x in tp] if tp else []

        # ============================================================
        #               BLOCO "RAW" + NORMALIZAÇÃO DE BAIRRO
        # ============================================================

        def _norm_neigh(s):
            try:
                return unidecode(str(s)).strip().lower()
            except Exception:
                return str(s).strip().lower()

        df['neighborhood_key'] = df['neighborhood'].map(_norm_neigh)

        # --- neighborhood_stats_all_raw: TODAS as corridas por bairro (SEM correlação com favela)
        g_raw = (
            df.groupby('neighborhood_key', observed=False)
            .agg(total=('status', 'count'),
                 driver=('is_driver_cancel', 'sum'),
                 passenger=('is_passenger_cancel', 'sum'))
        )
        g_raw = _rate_cols(g_raw)
        neighborhood_stats_all_raw = {
            k: {
                'total': int(r['total']),
                'driver': int(r['driver']),
                'passenger': int(r['passenger']),
                'driver_rate': float(r['driver_rate']),
                'passenger_rate': float(r['passenger_rate'])
            }
            for k, r in g_raw.reset_index().set_index('neighborhood_key').iterrows()
        }

        # --- NEAR BY ORIGIN com detalhamento por bairro de origem ---
        # Agora agrupamos por favela E bairro de origem
        g_near_origin_detail = (
            df.loc[near_mask]
            .groupby(['favela', 'neighborhood_key'], observed=False)
            .agg(total=('status', 'count'),
                 driver=('is_driver_cancel', 'sum'),
                 passenger=('is_passenger_cancel', 'sum'))
            .reset_index()
        )

        # Estrutura para armazenar detalhes por favela
        favela_origin_details = defaultdict(lambda: defaultdict(lambda: {
            'total': 0, 'driver': 0, 'passenger': 0
        }))

        for _, row in g_near_origin_detail.iterrows():
            favela = row['favela']
            bairro_key = row['neighborhood_key']

            favela_origin_details[favela][bairro_key] = {
                'total': row['total'],
                'driver': row['driver'],
                'passenger': row['passenger']
            }

        # --- neighborhood_near_by_origin: corridas NEAR agregadas por bairro de ORIGEM ---
        g_near_origin = (
            df.loc[near_mask]
            .groupby('neighborhood_key', observed=False)
            .agg(total=('status', 'count'),
                 driver=('is_driver_cancel', 'sum'),
                 passenger=('is_passenger_cancel', 'sum'))
            .reset_index()
        )

        neighborhood_near_by_origin = {}
        for _, row in g_near_origin.iterrows():
            bairro_key = row['neighborhood_key']
            neighborhood_near_by_origin[bairro_key] = {
                'total': row['total'],
                'driver': row['driver'],
                'passenger': row['passenger']
            }

        # --- neighborhood_stats_excl_favela: RAW − NEAR(ORIGEM) por chave canônica ---
        neighborhood_stats_excl_favela = {}
        for key, raw in (neighborhood_stats_all_raw or {}).items():
            base_tot = int(raw.get('total', 0))
            base_drv = int(raw.get('driver', 0))
            base_pas = int(raw.get('passenger', 0))

            near_loc = neighborhood_near_by_origin.get(key, {'total': 0, 'driver': 0, 'passenger': 0})

            rem_tot = max(0, base_tot - int(near_loc['total']))
            rem_drv = max(0, base_drv - int(near_loc['driver']))
            rem_pas = max(0, base_pas - int(near_loc['passenger']))

            dr_rate = (rem_drv / rem_tot) if rem_tot > 0 else 0.0
            ps_rate = (rem_pas / rem_tot) if rem_tot > 0 else 0.0

            neighborhood_stats_excl_favela[key] = {
                'total': rem_tot,
                'driver': rem_drv,
                'passenger': rem_pas,
                'driver_rate': float(dr_rate),
                'passenger_rate': float(ps_rate),
            }

        # --- Montagem dos "tops" com EXTRAÇÃO SOMENTE DA CHAVE ---
        def _top_key(lst):
            # recebe [[chave, taxa]] e devolve apenas a chave; se vazio, None
            try:
                return lst[0][0] if lst and len(lst[0]) >= 1 else None
            except Exception:
                return None

        # Para horas, a chave é int (0..23)
        top_driver_hour_key = _top_key(hourly_stats.get('top_driver', []))
        top_passenger_hour_key = _top_key(hourly_stats.get('top_passenger', []))

        neighborhood_stats = {
            'top_driver': tdn_bai or [],
            'top_passenger': tpn_bai or []
        }
        favela_stats = {
            'top_driver': tdf_fav or [],
            'top_passenger': tpf_fav or []
        }

        # --- Resultado final (top_* como CHAVE) ---
        result = {
            'total': total_all,
            'near_favela': near_total,
            'near_pct': near_pct,
            'driver': driver_near,
            'passenger': passenger_near,
            'driver_pct': driver_rate_near,
            'passenger_pct': passenger_rate_near,
            'avg_distance': avg_distance,

            # ATENÇÃO: top_* agora são APENAS as chaves (não listas)
            'top_driver_neighborhood': _top_key(tdn_bai),
            'top_passenger_neighborhood': _top_key(tpn_bai),
            'top_driver_favela': _top_key(tdf_fav),
            'top_passenger_favela': _top_key(tpf_fav),
            'top_driver_hour': top_driver_hour_key,
            'top_passenger_hour': top_passenger_hour_key,

            'neighborhood_stats': neighborhood_stats,  # listas completas ainda disponíveis
            'favela_stats': favela_stats,
            'hourly_stats': hourly_stats,

            # OBS:
            # neighborhood_stats_all e favela_stats_all indexados pelo NOME ORIGINAL
            # *_raw / *_near_by_origin / *_excl_favela por chave canônica (sem acento/minúscula)
            'neighborhood_stats_all': neighborhood_stats_all,
            'favela_stats_all': favela_stats_all,

            'neighborhood_stats_all_raw': neighborhood_stats_all_raw,
            'neighborhood_near_by_origin': neighborhood_near_by_origin,
            'neighborhood_stats_excl_favela': neighborhood_stats_excl_favela,
            'favela_origin_details': dict(favela_origin_details),  # NOVO: detalhes por favela e bairro
            'top_addresses': []  # mantenha/complete conforme sua lógica original
        }

        return result

    except Exception as e:
        import logging
        logging.exception("Erro em processar_estatisticas: %s", e)
        return {
            'total': 0, 'near_favela': 0, 'near_pct': 0.0,
            'driver': 0, 'passenger': 0, 'driver_pct': 0.0, 'passenger_pct': 0.0,
            'avg_distance': 0.0,
            'top_driver_neighborhood': None, 'top_passenger_neighborhood': None,
            'top_driver_favela': None, 'top_passenger_favela': None,
            'top_driver_hour': None, 'top_passenger_hour': None,
            'neighborhood_stats': {'top_driver': [], 'top_passenger': []},
            'favela_stats': {'top_driver': [], 'top_passenger': []},
            'hourly_stats': {'top_driver': [], 'top_passenger': []},
            'neighborhood_stats_all': {},
            'neighborhood_stats_all_raw': {},
            'neighborhood_near_by_origin': {},
            'neighborhood_stats_excl_favela': {},
            'favela_stats_all': {},
            'top_addresses': []
        }




def gerar_bins_distancia(rides_df, raio_km, n_bins=10):
    """
    Retorna lista de dicts: [{label,total,driver,passenger}, ...]
    Usada no gráfico 'Taxa de Cancelamento por Distância Média'.
    """
    import numpy as np
    if rides_df is None or rides_df.empty:
        return []

    df = ensure_cancel_flags(rides_df.copy())
    if 'dist_comunidade_m' not in df.columns:
        df['dist_comunidade_m'] = np.nan
    df = df[df['dist_comunidade_m'].notna()].copy()
    if df.empty:
        max_m = max(1, int(raio_km * 1000))
        bins = np.linspace(0, max_m, n_bins + 1)
        labels = [f"{int(bins[i])}-{int(bins[i+1])} m" for i in range(n_bins)]
        return [{'label': lab, 'total': 0, 'driver': 0, 'passenger': 0} for lab in labels]

    max_m = max(1, int(raio_km * 1000))
    bins = np.linspace(0, max_m, n_bins + 1)
    labels = [f"{int(bins[i])}-{int(bins[i+1])} m" for i in range(n_bins)]
    df['dist_bin'] = pd.cut(df['dist_comunidade_m'].astype(float), bins=bins, labels=labels, include_lowest=True)

    agg = (
        df.groupby('dist_bin', observed=False)
          .agg(total=('status', 'count'),
               driver=('is_driver_cancel', 'sum'),
               passenger=('is_passenger_cancel', 'sum'))
          .reset_index()
    )

    # Preenche bins faltantes para manter eixo consistente
    have = set(agg['dist_bin'].astype(str))
    for lab in labels:
        if lab not in have:
            agg = pd.concat([agg, pd.DataFrame([{'dist_bin': lab, 'total': 0, 'driver': 0, 'passenger': 0}])], ignore_index=True)

    agg = agg.sort_values('dist_bin')

    return [
        {'label': str(r['dist_bin']), 'total': int(r['total']), 'driver': int(r['driver']), 'passenger': int(r['passenger'])}
        for _, r in agg.iterrows()
    ]


def gerar_top_enderecos(rides_df, top_n=20):
    """
    Retorna lista de dicionários com:
    [{address,total,driver,passenger,driver_rate,passenger_rate,dist_mean,zone,favela},...]
    Apenas corridas com favela atribuída.
    Observações:
    - Considera APENAS corridas com favela atribuída (near).
    - Mantém mínimo de ocorrências por endereço para relevância estatística.
    - Ordena por distância (asc), depois taxa do motorista (desc), depois total (desc).
    """
    try:
        # ---------- Verificações iniciais ----------
        if rides_df is None or rides_df.empty:
            return []

        # O original exigia colunas de coordenadas como pré-condição
        if 'origin_lat' not in rides_df.columns or 'origin_lng' not in rides_df.columns:
            return []

        df = rides_df.copy()

        # ---------- Garantir colunas essenciais ----------
        required_cols = ['road_client', 'suburb_client', 'status', 'origin_lat', 'origin_lng']
        for col in required_cols:
            if col not in df.columns:
                df[col] = None

        # Coluna de distância usada na agregação
        if 'dist_comunidade_m' not in df.columns:
            df['dist_comunidade_m'] = pd.NA

        # Favela e zona
        if 'favela' not in df.columns:
            df['favela'] = pd.NA
        if 'zone' not in df.columns:
            df['zone'] = 'Outros'

        # Neighborhood (para tooltip comparativa no front)
        if 'neighborhood' not in df.columns:
            # Usar suburb_client como melhor proxy quando não houver 'neighborhood' consolidado
            df['neighborhood'] = df['suburb_client'].fillna('N/A').astype(str)
        else:
            df['neighborhood'] = df['neighborhood'].fillna('N/A').astype(str)

        # ---------- Compor endereço ----------
        df['address'] = (
            df['road_client'].fillna('').astype(str).str.strip() + ', ' +
            df['suburb_client'].fillna('').astype(str).str.strip()
        ).str.strip(', ').replace('', pd.NA)

        # ---------- Flags de cancelamento ----------
        # (Mantém a detecção textual padrão usada no módulo)
        if 'is_driver_cancel' not in df.columns:
            df['is_driver_cancel'] = df['status'].astype(str).str.contains(
                'Taxista|Motorista', case=False, na=False
            ).astype(int)
        else:
            df['is_driver_cancel'] = df['is_driver_cancel'].fillna(0).astype(int)

        if 'is_passenger_cancel' not in df.columns:
            df['is_passenger_cancel'] = df['status'].astype(str).str.contains(
                'Passageiro', case=False, na=False
            ).astype(int)
        else:
            df['is_passenger_cancel'] = df['is_passenger_cancel'].fillna(0).astype(int)

        # ---------- Filtro: apenas corridas com favela atribuída ----------
        df = ensure_cancel_flags(df)

        near = df[df['favela'].notna()].copy()
        if near.empty:
            return []

        # Remover linhas sem address (após composição)
        near = near[near['address'].notna()].copy()
        if near.empty:
            return []

        # ---------- Agregação ----------
        agg = (
            near.groupby(['address', 'favela', 'zone', 'neighborhood'], as_index=False)
                .agg(
                    total=('status', 'count'),
                    driver=('is_driver_cancel', 'sum'),
                    passenger=('is_passenger_cancel', 'sum'),
                    distance=('dist_comunidade_m', 'mean')  # média em metros
                )
        )

        # Calcular taxas
        agg['driver_rate'] = (agg['driver'] / agg['total']).astype(float)
        agg['passenger_rate'] = (agg['passenger'] / agg['total']).astype(float)

        # ---------- Mínimo de ocorrências ----------
        # (Mantém o critério original de robustez estatística)
        agg = agg[agg['total'] >= 5]
        if agg.empty:
            return []

        # ---------- Ordenação solicitada ----------
        # 1) distância (asc)  2) driver_rate (desc)  3) total (desc)
        agg = agg.sort_values(
            by=['distance', 'driver_rate', 'total'],
            ascending=[True, False, False]
        ).head(int(top_n))

        # ---------- Conversão para estrutura esperada ----------
        result = []
        for _, row in agg.iterrows():
            result.append({
                'address': str(row['address']) if pd.notna(row['address']) else '',
                'favela': str(row['favela']) if pd.notna(row['favela']) else '',
                'zone': str(row['zone']) if pd.notna(row['zone']) else 'Outros',
                'neighborhood': str(row['neighborhood']) if pd.notna(row['neighborhood']) else 'N/A',  # NOVO
                'distance': float(row['distance']) if pd.notna(row['distance']) else 0.0,
                'total': int(row['total']) if pd.notna(row['total']) else 0,
                'driver': int(row['driver']) if pd.notna(row['driver']) else 0,
                'passenger': int(row['passenger']) if pd.notna(row['passenger']) else 0,
                'driver_rate': float(row['driver_rate']) if pd.notna(row['driver_rate']) else 0.0,
                'passenger_rate': float(row['passenger_rate']) if pd.notna(row['passenger_rate']) else 0.0,
            })

        return result

    except Exception as e:
        # Mantém o padrão original de logging/retorno
        try:
            logger.error(f"Erro em gerar_top_enderecos: {str(e)}")
        except Exception:
            pass
        return []


def gerar_top_favelas(rides_df, top_n=5):
    """
    Retorna [{favela,total,driver,passenger,driver_rate,passenger_rate},...]
    Considera apenas corridas próximas a favelas
    """
    if rides_df.empty or 'favela' not in rides_df.columns:
        return []

    # Filtra apenas corridas próximas a favelas
    df = rides_df[rides_df['favela'].notna()].copy()
    if df.empty:
        return []

    # Garantir flags de cancelamento
    df = ensure_cancel_flags(df)

    agg = df.groupby('favela').agg(
        total=('status', 'count'),
        driver=('is_driver_cancel', 'sum'),
        passenger=('is_passenger_cancel', 'sum')
    ).reset_index()

    # Calcular taxas com proteção contra divisão por zero
    agg['driver_rate'] = agg.apply(lambda x: x['driver'] / x['total'] if x['total'] > 0 else 0, axis=1)
    agg['passenger_rate'] = agg.apply(lambda x: x['passenger'] / x['total'] if x['total'] > 0 else 0, axis=1)

    # Filtra favelas com pelo menos 5 corridas para relevância estatística
    agg = agg[agg['total'] >= 5]
    if agg.empty:
        return []

    top = agg.sort_values(['total', 'driver_rate', 'passenger_rate'], ascending=[False, False, False]).head(top_n)

    return [
        {
            'favela': r['favela'],
            'total': int(r['total']),
            'driver': int(r['driver']),
            'passenger': int(r['passenger']),
            'driver_rate': float(r['driver_rate']),
            'passenger_rate': float(r['passenger_rate'])
        }
        for _, r in top.iterrows()
    ]



def criar_grafico_taxa_distancia(rides_df, raio_km):
    """
    Linha(s) de taxa de cancelamento por faixa de distância (0 até raio_km).
    Gera HTML Plotly (fig.to_html(full_html=False)).
    """
    try:
        # Garantir colunas
        for col in ['is_driver_cancel', 'is_passenger_cancel', 'dist_comunidade_m']:
            if col not in rides_df:
                rides_df[col] = 0

        # Apenas corridas com distância válida
        df = rides_df.copy()
        df['dist_comunidade_m'] = pd.to_numeric(df['dist_comunidade_m'], errors='coerce')
        df = df[df['dist_comunidade_m'].notna()]

        # Bins
        max_m = int(raio_km * 1000)
        n_bins = 10
        bins = np.linspace(0, max_m, n_bins + 1)
        labels = [f"{int(bins[i])}-{int(bins[i+1])} m" for i in range(n_bins)]

        df['dist_bin'] = pd.cut(df['dist_comunidade_m'], bins=bins, labels=labels, include_lowest=True)

        grp = df.groupby('dist_bin').agg(
            total=('status', 'count'),
            driver=('is_driver_cancel', 'sum'),
            passenger=('is_passenger_cancel', 'sum')
        ).reset_index()

        grp['driver_rate'] = grp['driver'] / grp['total']
        grp['passenger_rate'] = grp['passenger'] / grp['total']

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=grp['dist_bin'],
            y=grp['driver_rate'],
            name='Taxa Cancel. Motorista',
            mode='lines+markers',
            line=dict(width=2),
            customdata=np.stack((grp['total'], grp['driver']), axis=-1),
            hovertemplate="<b>%{x}</b><br>Taxa Motorista: %{y:.1%}<br>Total: %{customdata[0]}<br>Cancelamentos: %{customdata[1]}<extra></extra>"
        ))

        fig.add_trace(go.Scatter(
            x=grp['dist_bin'],
            y=grp['passenger_rate'],
            name='Taxa Cancel. Passageiro',
            mode='lines+markers',
            line=dict(width=2),
            customdata=np.stack((grp['total'], grp['passenger']), axis=-1),
            hovertemplate="<b>%{x}</b><br>Taxa Passageiro: %{y:.1%}<br>Total: %{customdata[0]}<br>Cancelamentos: %{customdata[1]}<extra></extra>"
        ))

        fig.update_layout(
            title="Taxa de Cancelamento por Faixa de Distância ao Perímetro da Favela",
            xaxis_title="Faixa de distância (m)",
            yaxis_title="Taxa de cancelamento",
            yaxis_tickformat=".0%",
            legend=dict(orientation='h', y=-0.2),
            margin=dict(l=40, r=20, t=40, b=80),
            template="plotly_white"
        )

        return fig.to_html(full_html=False)

    except Exception:
        logger.exception("Erro ao criar gráfico de taxa por distância")
        return ""


def criar_grafico_enderecos(rides_df):
    """Cria visualização de endereços com tratamento completo de dados incluindo distância média."""
    try:
        # 1. Garantir colunas necessárias
        for col in ['road_client', 'suburb_client', 'favela', 'zone', 'status', 'dist_comunidade_m']:
            if col not in rides_df.columns:
                rides_df[col] = 0.0 if col == 'dist_comunidade_m' else ''

        # 2. Montar endereço completo
        rides_df["address"] = (
                rides_df["road_client"].fillna("") + ", " +
                rides_df["suburb_client"].fillna("")
        ).str.strip().str.rstrip(',').str.strip()

        # 3. Filtrar apenas corridas próximas a favelas
        df_cancel = rides_df[rides_df["favela"].notna()].copy()

        if df_cancel.empty:
            fig = go.Figure()
            fig.update_layout(
                title="Sem dados de cancelamentos próximos a favelas",
                xaxis={"visible": False}, yaxis={"visible": False}
            )
            return fig, []

        # 4. Criar flags de cancelamento
        df_cancel['is_driver_cancel'] = df_cancel['status'].str.contains('Taxista|Motorista', case=False,
                                                                         na=False).astype(int)
        df_cancel['is_passenger_cancel'] = df_cancel['status'].str.contains('Passageiro', case=False, na=False).astype(
            int)

        # 5. Agrupar por endereço, favela e zona, computando estatísticas
        grouped = df_cancel.groupby(
            ["address", "favela", "zone"], as_index=False
        ).agg({
            "is_driver_cancel": "sum",
            "is_passenger_cancel": "sum",
            "status": "count",
            "dist_comunidade_m": "mean"
        }).rename(columns={
            "status": "total",
            "dist_comunidade_m": "distance"
        })

        # 6. Calcular taxas de cancelamento
        grouped["driver_rate"] = grouped["is_driver_cancel"] / grouped["total"]
        grouped["passenger_rate"] = grouped["is_passenger_cancel"] / grouped["total"]

        # 7. Selecionar top 20 por volume total
        top20 = grouped.nlargest(20, "total")

        # 8. Montar o gráfico de barras
        fig = go.Figure()

        # Barras para cancelamentos por motorista
        fig.add_trace(go.Bar(
            x=top20["address"],
            y=top20["driver_rate"],
            name="Taxista",
            text=top20.apply(lambda x: f"{x['favela']}<br>Dist: {x['distance']:.0f}m", axis=1),
            customdata=top20[["total", "driver_rate", "passenger_rate", "distance"]],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Favela: %{text}<br>"
                "Taxa Motorista: %{customdata[1]:.1%}<br>"
                "Taxa Passageiro: %{customdata[2]:.1%}<br>"
                "Distância: %{customdata[3]:.0f}m<br>"
                "Total corridas: %{customdata[0]}"
                "<extra></extra>"
            ),
            marker_color='#d62728'
        ))

        # Barras para cancelamentos por passageiro
        fig.add_trace(go.Bar(
            x=top20["address"],
            y=top20["passenger_rate"],
            name="Passageiro",
            text=top20.apply(lambda x: f"{x['favela']}<br>Dist: {x['distance']:.0f}m", axis=1),
            customdata=top20[["total", "driver_rate", "passenger_rate", "distance"]],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Favela: %{text}<br>"
                "Taxa Motorista: %{customdata[1]:.1%}<br>"
                "Taxa Passageiro: %{customdata[2]:.1%}<br>"
                "Distância: %{customdata[3]:.0f}m<br>"
                "Total corridas: %{customdata[0]}"
                "<extra></extra>"
            ),
            marker_color='#1f77b4'
        ))

        fig.update_layout(
            title="Top 20 Endereços com Maior Taxa de Cancelamento",
            xaxis_title="Endereço",
            yaxis_title="Taxa de Cancelamento",
            barmode="group",
            hovermode="x unified",
            height=600,
            xaxis={'categoryorder': 'total descending'},
            yaxis={'tickformat': '.0%'}
        )

        return fig, top20.to_dict("records")

    except Exception as e:
        logger.error(f"Erro ao criar gráfico de endereços: {e}")
        fig = go.Figure()
        fig.update_layout(title="Erro ao gerar gráfico de endereços")
        return fig, []



def criar_mapa(rides_df, bairros_geojson, favelas_geojson, filters):
    """Cria mapa interativo com zonas, bairros e favelas"""
    try:
        # Determina centro do mapa
        avg_lat = rides_df["origin_lat"].mean()
        avg_lon = rides_df["origin_lng"].mean()

        # Cria mapa base
        m = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=12,
            tiles="cartodbpositron"
        )

        # Adiciona zonas/bairros (com tratamento especial)
        if bairros_geojson["features"]:
            first_feature = bairros_geojson["features"][0]
            properties = first_feature.get("properties", {})

            # Encontra a propriedade que contém o nome do bairro
            bairro_property = None
            for possible in ["Bairros", "bairro", "BAIRRO", "NOME", "nome", "name"]:
                if possible in properties:
                    bairro_property = possible
                    break

            if not bairro_property:
                available = list(properties.keys())
                raise ValueError(f"Propriedade do bairro não encontrada. Chaves disponíveis: {available}")

            folium.GeoJson(
                bairros_geojson,
                name="Bairros",
                style_function=lambda feature: {
                    "fillColor": "#4daf4a" if get_zone(feature["properties"].get(bairro_property, "")) == filters.get(
                        "zone", "") else "#ffffcc",
                    "color": "#555555",
                    "weight": 1,
                    "fillOpacity": 0.6
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=[bairro_property],
                    aliases=["Bairro:"],
                    localize=True
                )
            ).add_to(m)

        # Adiciona favelas (com estrutura diferente)
        favela_stats = defaultdict(lambda: {"total": 0, "driver": 0, "passenger": 0})
        for _, row in rides_df.iterrows():
            if pd.notna(row["favela"]):
                favela = row["favela"]
                favela_stats[favela]["total"] += 1
                favela_stats[favela]["driver"] += row['is_driver_cancel']
                favela_stats[favela]["passenger"] += row['is_passenger_cancel']

        for feature in favelas_geojson["features"]:
            properties = feature.get("properties", {})
            nome = properties.get("nome") or properties.get("NOME") or "Desconhecida"
            stats = favela_stats.get(nome, {"total": 0, "driver": 0, "passenger": 0})

            driver_rate = stats["driver"] / stats["total"] if stats["total"] > 0 else 0
            passenger_rate = stats["passenger"] / stats["total"] if stats["total"] > 0 else 0

            feature_color = "#d73027" if driver_rate > passenger_rate else "#4575b4" if passenger_rate > driver_rate else "#999999"

            folium.GeoJson(
                feature,
                name="Favelas",
                style_function=lambda f, cor=feature_color: {
                    "fillColor": cor,
                    "color": "#555555",
                    "weight": 1,
                    "fillOpacity": 0.7
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["nome", "bairro", "complexo"],
                    aliases=["Favela:", "Bairro:", "Complexo:"],
                    localize=True
                )
            ).add_to(m)

        # Adiciona controle de camadas
        folium.LayerControl().add_to(m)

        return m
    except Exception as e:
        logger.error(f"Erro ao criar mapa: {e}")
        raise


def debug_neighborhood_stats(bairro_nome, stats):
    """Função auxiliar para debug das estatísticas de bairro"""
    from unidecode import unidecode

    bairro_key = unidecode(bairro_nome).lower().strip()

    print(f"\n=== DEBUG DETALHADO: {bairro_nome} ({bairro_key}) ===")

    # Estatísticas raw (todas as corridas do bairro)
    raw = stats.get('neighborhood_stats_all_raw', {}).get(bairro_key, {})
    print(f"📊 RAW (Todas corridas do bairro):")
    print(f"   Total: {raw.get('total', 0)}")
    print(f"   Driver: {raw.get('driver', 0)}")
    print(f"   Passenger: {raw.get('passenger', 0)}")
    print(f"   Driver Rate: {raw.get('driver_rate', 0):.3f}")
    print(f"   Passenger Rate: {raw.get('passenger_rate', 0):.3f}")

    # Corridas near por origem
    near_origin = stats.get('neighborhood_near_by_origin', {}).get(bairro_key, {})
    print(f"\n📍 NEAR (Corridas próximas à favela COM ORIGEM neste bairro):")
    print(f"   Total: {near_origin.get('total', 0)}")
    print(f"   Driver: {near_origin.get('driver', 0)}")
    print(f"   Passenger: {near_origin.get('passenger', 0)}")

    # Detalhe por favela (se disponível)
    if 'favelas' in near_origin:
        print(f"   📍 Detalhe por favela:")
        for favela, dados in near_origin['favelas'].items():
            print(
                f"      {favela}: Total={dados.get('total', 0)}, Driver={dados.get('driver', 0)}, Passenger={dados.get('passenger', 0)}")

    # Estatísticas excluindo favelas
    excl = stats.get('neighborhood_stats_excl_favela', {}).get(bairro_key, {})
    print(f"\n➖ EXCL (RAW - NEAR):")
    print(f"   Total: {excl.get('total', 0)}")
    print(f"   Driver: {excl.get('driver', 0)}")
    print(f"   Passenger: {excl.get('passenger', 0)}")
    print(f"   Driver Rate: {excl.get('driver_rate', 0):.3f}")
    print(f"   Passenger Rate: {excl.get('passenger_rate', 0):.3f}")

    # Debug detalhado para entender o cálculo
    if raw and near_origin:
        rem_tot = max(0, raw.get('total', 0) - near_origin.get('total', 0))
        rem_drv = max(0, raw.get('driver', 0) - near_origin.get('driver', 0))
        rem_pas = max(0, raw.get('passenger', 0) - near_origin.get('passenger', 0))

        print(f"\n🧮 CÁLCULO DETALHADO:")
        print(f"   Total: {raw.get('total', 0)} - {near_origin.get('total', 0)} = {rem_tot}")
        print(f"   Driver: {raw.get('driver', 0)} - {near_origin.get('driver', 0)} = {rem_drv}")
        print(f"   Passenger: {raw.get('passenger', 0)} - {near_origin.get('passenger', 0)} = {rem_pas}")

        # Verificar consistência
        if rem_tot != excl.get('total', 0):
            print(f"   ❌ INCONSISTÊNCIA: Total calculado ({rem_tot}) ≠ Total excl ({excl.get('total', 0)})")
        if rem_drv != excl.get('driver', 0):
            print(f"   ❌ INCONSISTÊNCIA: Driver calculado ({rem_drv}) ≠ Driver excl ({excl.get('driver', 0)})")
        if rem_pas != excl.get('passenger', 0):
            print(f"   ❌ INCONSISTÊNCIA: Passenger calculado ({rem_pas}) ≠ Passenger excl ({excl.get('passenger', 0)})")

    # Verificar se há dados de corridas near para este bairro
    near_stats_all = stats.get('neighborhood_stats_all', {})
    near_for_this_bairro = None
    for bairro_name, data in near_stats_all.items():
        if unidecode(bairro_name).lower().strip() == bairro_key:
            near_for_this_bairro = data
            break

    if near_for_this_bairro:
        print(f"\n📈 NEAR STATS (corridas próximas atribuídas a este bairro):")
        print(f"   Total: {near_for_this_bairro.get('total', 0)}")
        print(f"   Driver: {near_for_this_bairro.get('driver', 0)}")
        print(f"   Passenger: {near_for_this_bairro.get('passenger', 0)}")


def debug_detalhado_favela_origem(stats, favela_nome):
    """Debug detalhado para uma favela específica"""
    from unidecode import unidecode

    favela_origin_details = stats.get('favela_origin_details', {})
    detalhes = favela_origin_details.get(favela_nome, {})

    print(f"\n=== DEBUG DETALHADO ORIGEM: {favela_nome} ===")
    print(f"Total de bairros de origem: {len(detalhes)}")

    total_geral = 0
    for bairro_origem, dados in detalhes.items():
        total_bairro = dados.get('total', 0)
        total_geral += total_bairro
        print(f"   {bairro_origem}: {total_bairro} corridas")

    print(f"Total geral confirmado: {total_geral}")

    # Verificar consistência com favela_stats_all
    favela_stats = stats.get('favela_stats_all', {}).get(favela_nome, {})
    total_stats = favela_stats.get('total', 0)

    if total_geral != total_stats:
        print(f"❌ INCONSISTÊNCIA: Total por origem ({total_geral}) ≠ Total stats ({total_stats})")
    else:
        print(f"✅ Consistente: Total por origem = Total stats")


# Blueprint Flask
favelas_app = Blueprint('favelas_app', __name__)


@favelas_app.route('/', methods=['GET'])
def index():
    """
    Rota principal da página de análise de redlining (favelas).
    Garante retorno válido em todos os caminhos.
    """
    try:
        start_time = time.time()

        # -------- 1) Filtros --------
        def _parse_float(v, default):
            try:
                return float(v)
            except Exception:
                return default

        filters = {
            'zone':         request.args.get('zone', ''),
            'neighborhood': request.args.get('neighborhood', ''),
            'favela':       request.args.get('favela', ''),
            'status':       request.args.get('status', ''),
            'start_date':   request.args.get('start_date', ''),
            'end_date':     request.args.get('end_date', ''),
            'start_time':   request.args.get('start_time', ''),
            'end_time':     request.args.get('end_time', ''),
            'raio':         _parse_float(request.args.get('raio', 1.0), 1.0),  # km
        }

        # -------- 2) Dados base (Mongo) --------
        query = build_query(filters)
        raw = list(db.rides_original.find(query, {
            "origin_lat": 1, "origin_lng": 1,
            "status": 1, "suburb_client": 1, "road_client": 1
        }))
        df = pd.json_normalize(raw)

        # -------- Helpers JSON --------
        def _js_clean(o):
            if isinstance(o, np.generic):
                return o.item()
            raise TypeError()

        # ========= CAMINHO SEM DADOS =========
        if df.empty:
            # GeoJSONs para mapa e para popular listas
            bairros_geo = load_geojson("censo2022_bairros.geojson")
            favelas_geo = load_geojson("Limite_Favelas_2019.geojson")

            # Stats vazios com TODAS as chaves esperadas no template/JS
            empty_stats = {
                'total': 0, 'near_favela': 0, 'near_pct': 0.0,
                'driver': 0, 'passenger': 0,
                'driver_pct': 0.0, 'passenger_pct': 0.0,
                'avg_distance': 0.0,
                'top_driver_neighborhood': None, 'top_passenger_neighborhood': None,
                'top_driver_favela': None, 'top_passenger_favela': None,
                'top_driver_hour': None, 'top_passenger_hour': None,
                'neighborhood_stats': {'top_driver': [], 'top_passenger': []},
                'favela_stats': {'top_driver': [], 'top_passenger': []},
                'hourly_stats': {'top_driver': [], 'top_passenger': []},
                'neighborhood_stats_all': {},
                'favela_stats_all': {},
                'top_addresses': []
            }

            zones = sorted(ZONE_MAP.keys())
            zone_neighborhoods = {z: sorted(list(s)) for z, s in ZONE_MAP.items()}

            # Para o <select> Favela o front espera lista de objetos {nome, complexo}
            neighborhood_favelas = montar_neighborhood_favelas(favelas_geo)

            html = render_template(
                'favelas.html',
                zones=zones,
                zone_neighborhoods=zone_neighborhoods,
                neighborhood_favelas=neighborhood_favelas,
                bairros_geo=bairros_geo,
                favelas_geo=favelas_geo,
                stats=empty_stats,
                spatial={'avg_distance': 0.0},
                filters=filters,
                distance_bins=[],
                top_addresses=[],
                top_favelas=[],
                html_fig_dist=None,
                html_fig_address=None,
                mapa=None
            )
            return make_response(html, 200)

        # ========= CAMINHO COM DADOS =========
        # 3) GeoJSONs / mapeamentos
        bairros_geo = load_geojson("censo2022_bairros.geojson")
        favelas_geo = load_geojson("Limite_Favelas_2019.geojson")

        # 4) Distâncias / associação favela
        df = atribuir_rides_favelas(df, favelas_geo, filters['raio'])

        # 5) Estatísticas
        stats = processar_estatisticas(df, favelas_geo)

        # DEBUG DETALHADO - Para investigar o problema
        print("\n" + "=" * 80)
        print("DEBUG DETALHADO DAS ESTATÍSTICAS")
        print("=" * 80)

        debug_neighborhood_stats('Méier', stats)
        debug_neighborhood_stats('Todos os Santos', stats)
        debug_neighborhood_stats('Lins de Vasconcelos', stats)

        debug_detalhado_favela_origem(stats, 'Joaquim Méier')
        debug_detalhado_favela_origem(stats, 'Santos Titara')
        debug_detalhado_favela_origem(stats, 'Morro do Céu')

        # Debug adicional: listar todas as favelas encontradas
        print(f"\n🎯 FAVELAS ENCONTRADAS:")
        for favela_name, favela_data in stats.get('favela_stats_all', {}).items():
            if favela_data.get('total', 0) > 0:
                print(f"   {favela_name}: {favela_data.get('total', 0)} corridas")

        spatial = {'avg_distance': stats.get('avg_distance', 0.0)}

        # 6) Gráficos / tops
        distance_bins = gerar_bins_distancia(df, filters['raio'])
        html_fig_dist = criar_grafico_taxa_distancia(df, filters['raio'])
        html_fig_addr, top_addresses = criar_grafico_enderecos(df)
        top_favelas = gerar_top_favelas(df, top_n=5)

        # 7) Mapa (se sua função retorna HTML, guarde em `mapa`)
        mapa = criar_mapa(df, bairros_geo, favelas_geo, filters)

        # 8) Dados de selects
        zones = sorted(ZONE_MAP.keys())
        zone_neighborhoods = {z: sorted(list(s)) for z, s in ZONE_MAP.items()}
        neighborhood_favelas = montar_neighborhood_favelas(favelas_geo)

        # 9) Limpeza de tipos numpy para JSON
        stats         = json.loads(json.dumps(stats, default=_js_clean))
        spatial       = json.loads(json.dumps(spatial, default=_js_clean))
        top_addresses = json.loads(json.dumps(top_addresses, default=_js_clean))

        html = render_template(
            'favelas.html',
            zones=zones,
            zone_neighborhoods=zone_neighborhoods,
            neighborhood_favelas=neighborhood_favelas,
            bairros_geo=bairros_geo,
            favelas_geo=favelas_geo,
            stats=stats,
            spatial=spatial,
            filters=filters,
            distance_bins=distance_bins,
            top_addresses=top_addresses,
            top_favelas=top_favelas,
            html_fig_dist=html_fig_dist,
            html_fig_address=html_fig_addr,
            mapa=mapa
        )
        return make_response(html, 200)

    except Exception as e:
        logger.exception("Erro no index de favelas")
        # sempre retorna uma Response válida no except também
        return make_response(render_template('error.html', error=str(e)), 500)





@favelas_app.route('/api/favelas', methods=['GET'])
def api_favelas():
    """Endpoint para obter favelas de um bairro específico"""
    try:
        neighborhood = request.args.get('neighborhood', '').lower()
        if not neighborhood:
            return jsonify({"error": "Parâmetro 'neighborhood' é obrigatório"}), 400

        # Carrega GeoJSON das favelas
        favelas_geojson = load_geojson("Limite_Favelas_2019.geojson")

        # Filtra favelas pelo bairro
        favelas = []
        for feature in favelas_geojson['features']:
            bairro_favela = feature['properties'].get('bairro', '').lower()
            if bairro_favela == neighborhood:
                nome = feature['properties'].get('nome') or 'Desconhecida'
                complexo = feature['properties'].get('complexo') or 'N/A'
                favelas.append({
                    'nome': nome,
                    'complexo': complexo
                })

        return jsonify({
            "neighborhood": neighborhood,
            "favelas": favelas
        })
    except Exception as e:
        logger.error(f"Erro na API de favelas: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app = Flask(__name__)
    app.config['DEBUG'] = True
    app.register_blueprint(favelas_app, url_prefix='/favelas')
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
