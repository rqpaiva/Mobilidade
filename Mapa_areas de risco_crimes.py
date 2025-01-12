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
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
import json

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

# Carregar os dados das coleções do MongoDB
logger.info("Carregando dados das coleções do MongoDB...")
rides_data = pd.DataFrame(list(db['rides_original'].find()))
events_data = pd.DataFrame(list(db['events'].find()))

# Carregar dados das áreas de risco (favelas) de um arquivo GeoJSON
with open('Limite_Favelas_2019.geojson', 'r', encoding='utf-8') as f:
    favelas_data_raw = json.load(f)

# Filtrar apenas polígonos válidos (com pelo menos 3 coordenadas)
valid_favelas = []
for feature in favelas_data_raw["features"]:
    try:
        polygon = Polygon(feature["geometry"]["coordinates"][0])
        if polygon.is_valid and len(polygon.exterior.coords) >= 3:
            valid_favelas.append(polygon)
    except Exception as e:
        continue

# Criar uma árvore de busca espacial (STRtree) para os polígonos das áreas de risco
favelas_tree = STRtree(valid_favelas)

# Inicializar o app Flask
app = Flask(__name__)

# Rota principal para exibir o mapa e a tabela
@app.route('/', methods=['GET', 'POST'])
def index():
    distancia_maxima_km = request.form.get('distancia', 5)
    janela_temporal_horas = request.form.get('tempo', 2)

    distancia_maxima_km = float(distancia_maxima_km)
    janela_temporal_horas = float(janela_temporal_horas)

    # Converter os locais de embarque das corridas canceladas em pontos
    cancelled_rides_points = [Point(xy) for xy in zip(rides_data['origin_lng'], rides_data['origin_lat'])]

    # Verificar quantos pontos estão dentro das áreas de risco usando STRtree
    cancelled_in_favelas = sum([len(favelas_tree.query(point)) > 0 for point in cancelled_rides_points])

    # Realizar a análise de cancelamentos relacionados a eventos de criminalidade
    resultados = []
    mapa_cancelamentos = folium.Map(location=[-22.9068, -43.1729], zoom_start=12)

    for bairro, total_cancelamentos in rides_data.groupby('suburb_client').size().items():
        cancelamentos_bairro = rides_data[rides_data['suburb_client'] == bairro]
        events_bairro = events_data[events_data['neighborhood'].apply(lambda x: x.get('name', '')) == bairro]

        if not events_bairro.empty:
            kdtree = KDTree(np.radians(events_bairro[['longitude', 'latitude']].dropna().values))
            coords_cancelamentos = cancelamentos_bairro[['origin_lat', 'origin_lng']].dropna().values

            relacionados = 0
            tipos_eventos_relacionados = {}

            if len(coords_cancelamentos) > 0:
                dist, idx = kdtree.query(np.radians(coords_cancelamentos), k=min(10, len(events_bairro)), return_distance=True)
                dist = dist * 6371.0  # Converter para km

                for i, dists in enumerate(dist):
                    for d, j in zip(dists, idx[i]):
                        if d <= distancia_maxima_km:
                            evento = events_bairro.iloc[j]
                            intervalo_tempo = abs(
                                (pd.to_datetime(cancelamentos_bairro.iloc[i]['created_at']) - pd.to_datetime(evento['created_at'])).total_seconds() / 3600
                            )
                            if intervalo_tempo <= janela_temporal_horas:
                                relacionados += 1
                                tipo_evento = evento.get('contextInfo', {}).get('mainReason', {}).get('name', 'Não identificado')
                                if tipo_evento not in tipos_eventos_relacionados:
                                    tipos_eventos_relacionados[tipo_evento] = 0
                                tipos_eventos_relacionados[tipo_evento] += 1

            percentual_relacionados = (relacionados / total_cancelamentos) * 100 if total_cancelamentos > 0 else 0

            resultados.append({
                'Bairro': bairro,
                'Total Cancelamentos': total_cancelamentos,
                'Cancelamentos Relacionados': relacionados,
                'Percentual Relacionados (%)': percentual_relacionados,
                'Tipos de Eventos Relacionados': tipos_eventos_relacionados
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
        <title>Dashboard de Cancelamentos Relacionados a Crimes</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    </head>
    <body>
        <div class="container">
            <h1 class="mt-4">Dashboard de Cancelamentos Relacionados a Crimes</h1>
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