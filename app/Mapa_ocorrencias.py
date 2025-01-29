import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
from math import radians, cos, sin, sqrt, atan2
from datetime import timedelta
import folium
import branca.colormap as cm
from flask import Flask, render_template_string, request
import numpy as np
from sklearn.neighbors import KDTree

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Obter a string de conexão do MongoDB
MONGO_URI = os.getenv("MONGO_URI")

# Conecta ao MongoDB
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

# Carregar os dados das coleções do MongoDB
logger.info("Carregando dados das coleções do MongoDB...")
rides_data = pd.DataFrame(list(db['rides_original'].find()))
ocorrencias_data = pd.DataFrame(list(db['ocorrencias'].find()))
ocorrencias_orgaos_data = pd.DataFrame(list(db['ocorrencias_orgaos_responsaveis'].find()))
pop_data = pd.DataFrame(list(db['procedimento_operacional_padrao'].find()))

# Realizar o join das tabelas de ocorrências e tipos de eventos
ocorrencias_com_tipo = ocorrencias_data.merge(
    pop_data[['id_pop', 'pop_titulo']],
    on='id_pop',
    how='left'
)

# Inicializar o app Flask
app = Flask(__name__)

# Rota principal para exibir o mapa e a tabela
@app.route('/', methods=['GET', 'POST'])
def index():
    distancia_maxima_km = request.form.get('distancia', 5)
    janela_temporal_horas = request.form.get('tempo', 2)

    distancia_maxima_km = float(distancia_maxima_km)
    janela_temporal_horas = float(janela_temporal_horas)

    # Realizar a análise de cancelamentos relacionados
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
                dist, idx = kdtree.query(np.radians(coords_cancelamentos), k=min(10, len(ocorrencias_bairro)), return_distance=True)
                dist = dist * 6371.0  # Converter para km

                for i, dists in enumerate(dist):
                    for d, j in zip(dists, idx[i]):
                        if d <= distancia_maxima_km:
                            evento = ocorrencias_bairro.iloc[j]
                            intervalo_tempo = abs(
                                (pd.to_datetime(cancelamentos_bairro.iloc[i]['created_at']) - evento['data_inicio']).total_seconds() / 3600
                            )
                            if intervalo_tempo <= janela_temporal_horas:
                                relacionados += 1
                                tipo_evento = evento['pop_titulo']
                                if tipo_evento not in cancelamentos_por_evento:
                                    cancelamentos_por_evento[tipo_evento] = 0
                                cancelamentos_por_evento[tipo_evento] += 1

            percentual_relacionados = (relacionados / total_cancelamentos) * 100 if total_cancelamentos > 0 else 0

            resultados.append({
                'Bairro': bairro,
                'Total Cancelamentos': total_cancelamentos,
                'Cancelamentos Relacionados': relacionados,
                'Percentual Relacionados (%)': percentual_relacionados,
                'Cancelamentos por Tipo de Evento': cancelamentos_por_evento
            })

            # Adicionar círculo ao mapa
            folium.CircleMarker(
                location=[cancelamentos_bairro['origin_lat'].mean(), cancelamentos_bairro['origin_lng'].mean()],
                radius=10,
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.6,
                popup=f"<strong>{bairro}</strong><br>Total Cancelamentos: {total_cancelamentos}<br>Relacionados: {relacionados}"
            ).add_to(mapa_cancelamentos)

    # Criar DataFrame com os resultados
    resultados_df = pd.DataFrame(resultados)

    # Gerar o HTML da tabela e do mapa
    tabela_html = resultados_df.to_html(index=False, classes='table table-striped')
    mapa_html = mapa_cancelamentos._repr_html_()

    # Template simples para exibir o formulário, mapa e a tabela
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard de Cancelamentos Relacionados</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    </head>
    <body>
        <div class="container">
            <h1 class="mt-4">Dashboard de Cancelamentos Relacionados</h1>
            <form method="POST">
                <div class="form-group">
                    <label for="distancia">Distância Máxima (km):</label>
                    <input type="number" step="0.1" name="distancia" value="{distancia_maxima_km}" class="form-control" />
                </div>
                <div class="form-group">
                    <label for="tempo">Janela Temporal (horas):</label>
                    <input type="number" step="0.1" name="tempo" value="{janela_temporal_horas}" class="form-control" />
                </div>
                <button type="submit" class="btn btn-primary">Atualizar</button>
            </form>
            <h2 class="mt-4">Estatísticas por Bairro</h2>
            {tabela_html}
            <h2 class="mt-4">Mapa de Cancelamentos</h2>
            {mapa_html}
        </div>
    </body>
    </html>
    """.format(distancia_maxima_km=distancia_maxima_km, janela_temporal_horas=janela_temporal_horas, tabela_html=tabela_html, mapa_html=mapa_html)

    return render_template_string(template)

# Executar o app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)