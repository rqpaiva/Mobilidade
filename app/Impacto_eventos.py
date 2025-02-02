from flask import Flask, Blueprint, jsonify, request
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
from math import radians, cos, sin, sqrt, atan2
import folium
import numpy as np
from sklearn.neighbors import KDTree

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Obter a string de conexão do MongoDB
MONGO_URI = os.getenv("MONGO_URI")

# Conectar ao MongoDB
logger.info("Conectando ao MongoDB...")
client = MongoClient(MONGO_URI)
db = client['mobility_data']

# Função para calcular a distância entre duas coordenadas geográficas (em km)
def calcular_distancia(coord1, coord2):
    R = 6371.0  # Raio da Terra em km
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# Carregar dados do MongoDB
logger.info("Carregando dados do MongoDB...")
rides_data = pd.DataFrame(list(db['rides_original'].find()))
ocorrencias_data = pd.DataFrame(list(db['ocorrencias'].find()))
pop_data = pd.DataFrame(list(db['procedimento_operacional_padrao'].find()))

# Unir ocorrências com tipos de eventos
ocorrencias_com_tipo = ocorrencias_data.merge(
    pop_data[['id_pop', 'pop_titulo']],
    on='id_pop',
    how='left'
)

# Inicializar Flask
impacto_eventos_app = Flask(__name__)

# Criação do blueprint
impacto_eventos_app = Blueprint("impacto_eventos_app", __name__, url_prefix="/impacto_eventos")


@impacto_eventos_app.route('/dados', methods=['GET', 'POST'])
def get_data():
    try:
        distancia_maxima_km = float(request.args.get('distancia', 5))
        janela_temporal_horas = float(request.args.get('tempo', 2))

        resultados = []
        mapa_cancelamentos = folium.Map(location=[-22.9068, -43.1729], zoom_start=12)

        for bairro, total_cancelamentos in rides_data.groupby('suburb_client').size().items():
            cancelamentos_bairro = rides_data[rides_data['suburb_client'] == bairro]
            ocorrencias_bairro = ocorrencias_com_tipo[ocorrencias_com_tipo['bairro'] == bairro]

            if not ocorrencias_bairro.empty:
                kdtree = KDTree(np.radians(ocorrencias_bairro[['latitude', 'longitude']].dropna().values))
                coords_cancelamentos = cancelamentos_bairro[['origin_lat', 'origin_lng']].dropna().values

                relacionados = 0
                cancelamentos_por_evento = {}

                if len(coords_cancelamentos) > 0:
                    dist, idx = kdtree.query(np.radians(coords_cancelamentos), k=min(10, len(ocorrencias_bairro)),
                                             return_distance=True)
                    dist = dist * 6371.0  # Converter para km

                    for i, dists in enumerate(dist):
                        for d, j in zip(dists, idx[i]):
                            if d <= distancia_maxima_km:
                                evento = ocorrencias_bairro.iloc[j]
                                intervalo_tempo = abs(
                                    (pd.to_datetime(cancelamentos_bairro.iloc[i]['created_at']) - evento[
                                        'data_inicio']).total_seconds() / 3600
                                )
                                if intervalo_tempo <= janela_temporal_horas:
                                    relacionados += 1
                                    tipo_evento = evento['pop_titulo']
                                    cancelamentos_por_evento[tipo_evento] = cancelamentos_por_evento.get(tipo_evento,
                                                                                                         0) + 1

                percentual_relacionados = (relacionados / total_cancelamentos) * 100 if total_cancelamentos > 0 else 0

                resultados.append({
                    'Bairro': bairro,
                    'Total Cancelamentos': total_cancelamentos,
                    'Cancelamentos Relacionados': relacionados,
                    'Percentual Relacionados (%)': percentual_relacionados,
                    'Cancelamentos por Tipo de Evento': cancelamentos_por_evento
                })

                folium.CircleMarker(
                    location=[cancelamentos_bairro['origin_lat'].mean(), cancelamentos_bairro['origin_lng'].mean()],
                    radius=10,
                    color='blue',
                    fill=True,
                    fill_color='blue',
                    fill_opacity=0.6,
                    popup=f"<strong>{bairro}</strong><br>Total Cancelamentos: {total_cancelamentos}<br>Relacionados: {relacionados}"
                ).add_to(mapa_cancelamentos)

        resultados_df = pd.DataFrame(resultados)

        return jsonify({
            "tabela_html": resultados_df.to_html(index=False,
                                                 classes='table table-striped table-hover table-responsive'),
            "mapa_html": mapa_cancelamentos._repr_html_()
        })

    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({"error": "Erro ao processar os dados"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

