import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
from math import radians, cos, sin, sqrt, atan2
import folium
from folium.plugins import MarkerCluster
from flask import Flask, Blueprint, jsonify, render_template_string, request
import json
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
rides_data = pd.DataFrame(list(db['rides_original'].find()))
ocorrencias_data = pd.DataFrame(list(db['ocorrencias'].find()))
procedimentos_data = pd.DataFrame(list(db['procedimento_operacional_padrao'].find()))


# Função para calcular a distância entre duas coordenadas geográficas (em km)
def calcular_distancia(coord1, coord2):
    R = 6371.0  # Raio da Terra em km
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# Converter datas para datetime
rides_data['created_at'] = pd.to_datetime(rides_data['created_at'])
ocorrencias_data['data_inicio'] = pd.to_datetime(ocorrencias_data['data_inicio'])
ocorrencias_data['data_fim'] = pd.to_datetime(ocorrencias_data['data_fim'])

# Mesclar ocorrências com procedimentos operacionais
ocorrencias_data = ocorrencias_data.merge(procedimentos_data, on='id_pop', how='left')

# Inicializar Flask
mapa_ocorrencias_app = Blueprint("mapa_ocorrencias_app", __name__)


@mapa_ocorrencias_app.route('/', methods=['GET', 'POST'])
def index():
    # Parâmetros do formulário
    min_date = rides_data['created_at'].min().strftime('%Y-%m-%d')
    max_date = rides_data['created_at'].max().strftime('%Y-%m-%d')

    distancia_maxima_km = float(request.form.get('distancia', 5))
    janela_temporal_horas = float(request.form.get('tempo', 2))
    data_inicio = request.form.get('data_inicio', min_date)
    data_fim = request.form.get('data_fim', max_date)
    tipo_evento = request.form.getlist('tipo_evento')  # Seleção múltipla de eventos

    # Filtrar os dados pelo período de análise
    rides_filtradas = rides_data[
        (rides_data['created_at'] >= data_inicio) & (rides_data['created_at'] <= data_fim)
        ]

    ocorrencias_filtradas = ocorrencias_data[
        (ocorrencias_data['data_inicio'] >= data_inicio) & (ocorrencias_data['data_fim'] <= data_fim)
        ]

    if tipo_evento:
        ocorrencias_filtradas = ocorrencias_filtradas[ocorrencias_filtradas['pop_titulo'].isin(tipo_evento)]

    resultados = []
    resultados_sankey = []
    mapa_cancelamentos = folium.Map(location=[-22.9068, -43.1729], zoom_start=12)
    marker_cluster = MarkerCluster().add_to(mapa_cancelamentos)

    for _, evento in ocorrencias_filtradas.iterrows():
        event_location = [evento['latitude'], evento['longitude']]
        event_duration = (evento['data_fim'] - evento['data_inicio']).total_seconds() / 3600

        rides_proximas = rides_filtradas.copy()
        rides_proximas['distancia'] = rides_proximas.apply(lambda row: calcular_distancia(
            (row['origin_lat'], row['origin_lng']), event_location), axis=1)
        rides_proximas = rides_proximas[rides_proximas['distancia'] <= distancia_maxima_km]

        rides_proximas['tempo_diferenca'] = abs(
            (rides_proximas['created_at'] - evento['data_inicio']).dt.total_seconds() / 3600)
        rides_proximas = rides_proximas[rides_proximas['tempo_diferenca'] <= janela_temporal_horas]

        cancelamentos_taxista = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Taxista']
        cancelamentos_passageiro = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Passageiro']
        total_cancelamentos = cancelamentos_taxista.shape[0] + cancelamentos_passageiro.shape[0]

        if total_cancelamentos > 0:
            percentual_cancelamento_bairro = (total_cancelamentos / rides_proximas.shape[0]) * 100 if \
                rides_proximas.shape[0] > 0 else 0

            folium.Marker(
                location=event_location,
                popup=f"""
                                            <b>Evento:</b> {evento['pop_titulo']}<br>
                                            <b>Bairro:</b> {evento.get('bairro', 'Desconhecido')}<br>
                                            <b>Data:</b> {evento['data_inicio'].strftime('%Y-%m-%d %H:%M:%S')}<br>
                                            <b>Raio de influência:</b> {distancia_maxima_km} km<br>
                                            <b>Cancelamentos pelo Taxista:</b> {cancelamentos_taxista.shape[0]}<br>
                                            <b>Cancelamentos pelo Passageiro:</b> {cancelamentos_passageiro.shape[0]}<br>
                                            <b>Total Cancelamentos:</b> {total_cancelamentos}
                                        """,
            ).add_to(marker_cluster)

            resultados.append({
                'Bairro': evento.get('bairro', 'Desconhecido'),
                'Data': evento['data_inicio'].strftime('%Y-%m-%d'),
                'Horário Ocorrência': evento['data_inicio'].strftime('%H:%M:%S'),
                'Duração Ocorrência (h)': round(event_duration, 2),
                'Evento': evento['pop_titulo'],
                'Cancelamentos pelo Taxista': cancelamentos_taxista.shape[0],
                'Cancelamentos pelo Passageiro': cancelamentos_passageiro.shape[0],
                'Total Cancelamentos': total_cancelamentos,
                'Percentual de Cancelamentos Relacionados no Bairro (%)': percentual_cancelamento_bairro,
            })

            resultados_sankey.append({
                'Bairro': evento.get('bairro', 'Desconhecido'),
                'Data': evento['data_inicio'].strftime('%Y-%m-%d'),
                'Evento': evento['pop_titulo'],
                'Total Cancelamentos': total_cancelamentos,
            })

    tabela_html = pd.DataFrame(resultados).to_html(index=False, classes='table table-striped')

    # Criar visualização Sankey
    sankey_df = pd.DataFrame(resultados_sankey)
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

    mapa_html = mapa_cancelamentos._repr_html_()

    return jsonify({"mapa": mapa_html, "sankey": sankey_html, "tabela": tabela_html})

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 10000))
        app = Flask(__name__)
        app.register_blueprint(mapa_ocorrencias_app, url_prefix="/mapa_ocorrencias")
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logging.error("Erro subindo Mapa Ocorrencias separadamente: ", e)
