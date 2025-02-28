import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
import numpy as np
from math import radians, cos, sin, sqrt, atan2
import folium
from folium.plugins import MarkerCluster
from flask import Flask, Blueprint, jsonify, render_template_string, request
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
    rides_data = pd.DataFrame(
        list(db['rides_original'].find({}, {"created_at": 1, "origin_lat": 1, "origin_lng": 1, "status": 1, "suburb_client": 1})))  # Adicionando suburb_client

    ocorrencias_data = pd.DataFrame(list(db['ocorrencias'].find({}, {
        "data_inicio": 1, "data_fim": 1, "latitude": 1, "longitude": 1, "id_pop": 1, "descricao": 1  # Incluindo descricao
    })))

    procedimentos_data = pd.DataFrame(
        list(db['procedimento_operacional_padrao'].find({}, {"id_pop": 1, "pop_titulo": 1})))  # Incluindo pop_titulo

    if rides_data.empty or ocorrencias_data.empty:
        logger.warning("Um dos datasets está vazio! Verifique a conexão com o MongoDB.")

    # Converter datas para datetime
    rides_data['created_at'] = pd.to_datetime(rides_data['created_at'])
    ocorrencias_data['data_inicio'] = pd.to_datetime(ocorrencias_data['data_inicio'])
    ocorrencias_data['data_fim'] = pd.to_datetime(ocorrencias_data['data_fim'])

    # Mesclar ocorrências com procedimentos operacionais para trazer 'pop_titulo'
    ocorrencias_data = ocorrencias_data.merge(procedimentos_data, on='id_pop', how='left')

    # Garantir que 'pop_titulo' existe
    if 'pop_titulo' not in ocorrencias_data.columns:
        logger.error("A coluna 'pop_titulo' não está presente após a mesclagem.")
        ocorrencias_data['pop_titulo'] = 'Desconhecido'  # Adicionar valor padrão

    # Adicionar a coluna 'bairro' a partir do campo suburb_client nas corridas
    rides_data.rename(columns={'suburb_client': 'bairro'}, inplace=True)

    return rides_data, ocorrencias_data



# Função para calcular distância entre coordenadas geográficas (em km) de forma vetorizada
def calcular_distancia(coord1, coord2):
    lat1, lon1 = np.radians(coord1)
    lat2, lon2 = np.radians(coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0 * (2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))

# Inicializar Flask
mapa_ocorrencias_app = Blueprint("mapa_ocorrencias_app", __name__)


@mapa_ocorrencias_app.route('/', methods=['GET', 'POST'])
def index():
    rides_data, ocorrencias_data = carregar_dados()

    # Definir intervalo padrão para filtros
    min_date = rides_data['created_at'].min().strftime('%Y-%m-%d')
    max_date = rides_data['created_at'].max().strftime('%Y-%m-%d')

    distancia_maxima_km = float(request.form.get('distancia', 5))
    janela_temporal_horas = float(request.form.get('tempo', 2))
    data_inicio = request.form.get('data_inicio', min_date)
    data_fim = request.form.get('data_fim', max_date)
    tipo_evento = request.form.getlist('tipo_evento')

    # Converter filtros para datetime
    data_inicio_dt = pd.to_datetime(data_inicio)
    data_fim_dt = pd.to_datetime(data_fim)

    # Filtragem antes do processamento
    rides_filtradas = rides_data[
        (rides_data['created_at'] >= data_inicio_dt) & (rides_data['created_at'] <= data_fim_dt)]
    ocorrencias_filtradas = ocorrencias_data[
        (ocorrencias_data['data_inicio'] >= data_inicio_dt) & (ocorrencias_data['data_fim'] <= data_fim_dt)]

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

        # Se houver corridas próximas, pegar o primeiro bairro encontrado
        if not rides_proximas.empty:
            bairro_evento = rides_proximas.iloc[0]['bairro']
        else:
            bairro_evento = "Desconhecido"  # Se não houver corridas próximas, manter "Desconhecido"

        cancelamentos_taxista = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Taxista']
        cancelamentos_passageiro = rides_proximas[rides_proximas['status'] == 'Cancelada pelo Passageiro']
        total_cancelamentos = cancelamentos_taxista.shape[0] + cancelamentos_passageiro.shape[0]

        if total_cancelamentos > 0:
            percentual_cancelamento_bairro = (total_cancelamentos / rides_proximas.shape[0]) * 100 if \
                rides_proximas.shape[0] > 0 else 0

            # Criar visualização Mapa usando Marker Cluster
            folium.Marker(
                location=event_location,
                popup=f"""
                                            <b>Evento:</b> {evento['pop_titulo']}<br>
                                            <b>Bairro:</b> {bairro_evento}<br>
                                            <b>Data:</b> {evento['data_inicio'].strftime('%Y-%m-%d %H:%M:%S')}<br>
                                            <b>Raio de influência:</b> {distancia_maxima_km} km<br>
                                            <b>Cancelamentos pelo Taxista:</b> {cancelamentos_taxista.shape[0]}<br>
                                            <b>Cancelamentos pelo Passageiro:</b> {cancelamentos_passageiro.shape[0]}<br>
                                            <b>Total Cancelamentos:</b> {total_cancelamentos}
                                        """,
            ).add_to(marker_cluster)

            resultados.append({
                'Bairro': bairro_evento,
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
                'Bairro': bairro_evento,
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
