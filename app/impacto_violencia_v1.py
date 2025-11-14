import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
import numpy as np
from math import radians, cos, sin, sqrt, atan2
import folium
from folium.plugins import MarkerCluster
from flask import Flask, Blueprint, jsonify, render_template, render_template_string, request
import plotly.graph_objects as go

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Conectar ao MongoDB
MONGO_URI = os.getenv("MONGO_URI")
logger.info("Conectando ao MongoDB...")
client = MongoClient(MONGO_URI)
db = client['mobility_data']


# Função para carregar os DataFrames sob demanda
def carregar_dados():
    eventos = list(
        db['events'].find({}, {"date": 1, "latitude": 1, "longitude": 1, "neighborhood": 1, "contextInfo": 1}))
    corridas = list(db['rides_original'].find({}, {"created_at": 1, "origin_lat": 1, "origin_lng": 1, "status": 1,
                                                   "suburb_client": 1}))

    if not eventos or not corridas:
        logger.warning("O dataset events ou rides está vazio! Verifique a conexão com o MongoDB.")
        return pd.DataFrame(), pd.DataFrame()

    events_data = pd.json_normalize(eventos)
    rides_data = pd.json_normalize(corridas)

    # Converter datas para datetime
    events_data['date'] = pd.to_datetime(events_data['date'])
    rides_data['created_at'] = pd.to_datetime(rides_data['created_at'])
    #rides_data.rename(columns={'suburb_client': 'bairro'}, inplace=True)

    return events_data, rides_data


# Função para calcular distância entre coordenadas geográficas (em km) de forma vetorizada
def calcular_distancia(coord1, coord2):
    lat1, lon1 = np.radians(coord1)
    lat2, lon2 = np.radians(coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0 * (2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))

# Função para carregar a camada de favelas
def carregar_limite_favelas():
    geojson_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "Limite_Favelas_2019.geojson")
    try:
        with open(geojson_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Erro ao carregar o arquivo GeoJSON: {e}")
        return None

# Inicializar Flask
impacto_violencia_app = Blueprint("impacto_violencia_app", __name__)


@impacto_violencia_app.route('/', methods=['GET', 'POST'])
def index():
    events_data, rides_data = carregar_dados()

    # Definir intervalo padrão para filtros
    min_date = rides_data['created_at'].min().strftime('%Y-%m-%d')
    max_date = rides_data['created_at'].max().strftime('%Y-%m-%d')
    data_inicio = request.form.get('data_inicio', min_date)
    data_fim = request.form.get('data_fim', max_date)
    distancia_maxima_km = float(request.form.get('distancia', 5))
    janela_temporal_horas = float(request.form.get('tempo', 2))
    tipo_evento = request.form.getlist('tipo_evento')

    # Converter filtros para datetime
    data_inicio_dt = pd.to_datetime(data_inicio)
    data_fim_dt = pd.to_datetime(data_fim)

    # Filtragem antes do processamento
    events_filtrados = events_data[(events_data['date'] >= data_inicio_dt) & (events_data['date'] <= data_fim_dt)]
    rides_filtradas = rides_data[
        (rides_data['created_at'] >= data_inicio_dt) & (rides_data['created_at'] <= data_fim_dt)]

    resultados = []
    sankey_data = []

    mapa_eventos = folium.Map(location=[-22.9068, -43.1729], zoom_start=12)
    marker_cluster = MarkerCluster().add_to(mapa_eventos)
#    geojson_path = "data/Limite_Favelas_2019.geojson"
    favelas_data = carregar_limite_favelas()

    if favelas_data:
        folium.GeoJson(
            favelas_data,
            name="Comunidades e Favelas",
            style_function=lambda feature: {'fillColor': 'red', 'color': 'black', 'weight': 1, 'fillOpacity': 0.5}
        ).add_to(mapa_eventos)

    # Evitar exceção ao acessar dados
    if events_filtrados.empty or rides_filtradas.empty:
        return "<h3>Nenhum dado disponível para os filtros selecionados.</h3>"

    for _, evento in events_filtrados.iterrows():
        event_location = [evento['latitude'], evento['longitude']]
        rides_proximas = rides_filtradas.copy()
        rides_proximas['distancia'] = rides_proximas.apply(
            lambda row: calcular_distancia((row['origin_lat'], row['origin_lng']), event_location), axis=1)
        rides_proximas = rides_proximas[rides_proximas['distancia'] <= distancia_maxima_km]

        rides_proximas['tempo_diferenca'] = abs(
            (rides_proximas['created_at'] - evento['date']).dt.total_seconds() / 3600)
        rides_proximas = rides_proximas[rides_proximas['tempo_diferenca'] <= janela_temporal_horas]

        cancelamentos_taxista = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Taxista']
        cancelamentos_passageiro = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Passageiro']
        total_cancelamentos = cancelamentos_taxista.shape[0] + cancelamentos_passageiro.shape[0]

        if total_cancelamentos > 0:
            percentual_cancelamento_bairro = (total_cancelamentos / rides_proximas.shape[0]) * 100 if \
                rides_proximas.shape[0] > 0 else 0

            for _, ride in rides_proximas.iterrows():
                cor_icon = 'blue' if ride.get('status', '') == 'Cancelada pelo Taxista' else 'orange'

                # Criar visualização Mapa usando Marker Cluster
                folium.Marker(
                    location=[ride['origin_lat'], ride['origin_lng']],
                    popup=f"""
                        <b>Evento:</b> {evento['contextInfo.mainReason.name']}<br>
                        <b>Bairro:</b> {ride['suburb_client']}<br>
                        <b>Data e hora do evento:</b> {evento['date'].strftime('%Y-%m-%d %H:%M:%S')}<br>
                        <b>Data e hora da corrida:</b> {ride['created_at'].strftime('%Y-%m-%d %H:%M:%S')}<b>
                        <b>Raio de influência:</b> {distancia_maxima_km} km<br>
                        <b>Cancelamentos pelo Taxista:</b> {cancelamentos_taxista.shape[0]}<br>
                        <b>Cancelamentos pelo Passageiro:</b> {cancelamentos_passageiro.shape[0]}<br>
                        <b>Total Cancelamentos:</b> {total_cancelamentos}
                    """,
                    icon=folium.Icon(color=cor_icon)
                ).add_to(marker_cluster)

                resultados.append({
                    'Bairro': ride['suburb_client'],
                    'Data': evento['date'].strftime('%Y-%m-%d'),
                    'Horário Ocorrência': evento['date'].strftime('%H:%M:%S'),
                    'Evento': evento['contextInfo.mainReason.name'],
                    'Cancelamentos pelo Taxista': cancelamentos_taxista.shape[0],
                    'Cancelamentos pelo Passageiro': cancelamentos_passageiro.shape[0],
                    'Total Cancelamentos': total_cancelamentos,
                    'Percentual de Cancelamentos Relacionados no Bairro (%)': percentual_cancelamento_bairro,
                })

                sankey_data.append({
                    'Bairro': ride['suburb_client'],
                    'Data': evento['date'].strftime('%Y-%m-%d'),
                    'Evento': evento['contextInfo.mainReason.name'],
                    'Total Cancelamentos': total_cancelamentos,
                })

    tabela_html = pd.DataFrame(resultados).to_html(index=False, classes='table table-striped')

    # Criar visualização Sankey
    sankey_df = pd.DataFrame(sankey_data)
    nodes = list(set(sankey_df['Evento'].tolist() + sankey_df['Bairro'].tolist() + sankey_df['Data'].tolist()))
    nodes_dict = {node: i for i, node in enumerate(nodes)}

    links = {
        "source": [nodes_dict[src] for src in sankey_df['Evento']],
        "target": [nodes_dict[dest] for dest in sankey_df['Bairro']],
        "value": sankey_df['Total Cancelamentos'].tolist()
    }

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=20,
            thickness=30,
            line=dict(color="black", width=0.5),
            label=nodes
        ),
        link=dict(
            source=links['source'],
            target=links['target'],
            value=links['value']
        )
    ))
    fig.update_layout(title_text="Eventos e os bairros atingidos", font_size=16)
    sankey_html = fig.to_html(full_html=False)

    mapa_html = mapa_eventos._repr_html_()

    return render_template('impacto_violencia.html',
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           distancia_maxima_km=distancia_maxima_km,
                           janela_temporal_horas=janela_temporal_horas,
                           tipo_evento=tipo_evento,
                           sankey_html=sankey_html,
                           mapa_html=mapa_html,
                           tabela_html=tabela_html,
                           events_filtrados=events_filtrados)  # Adicionado

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
        app = Flask(__name__)
        app.register_blueprint(impacto_violencia_app, url_prefix="/impacto_violencia")
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Erro subindo Impacto Violencia separadamente: {e}")