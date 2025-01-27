import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
from math import radians
from datetime import timedelta
import folium
from flask import Flask, render_template_string, request
import numpy as np
from sklearn.neighbors import KDTree
from shapely.geometry import Point
import json

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

# Carregar os dados das coleções do MongoDB
logger.info("Carregando dados das coleções do MongoDB...")
rides_data = pd.DataFrame(list(db['rides_original'].find()))
events_data = pd.DataFrame(list(db['events'].find()))

# Converter coordenadas e datas
rides_data['origin_coordinates'] = rides_data['location'].apply(lambda x: x['coordinates'] if pd.notnull(x) else None)
events_data['event_coordinates'] = events_data['location'].apply(lambda x: x['coordinates'] if pd.notnull(x) else None)

# Ajustar a conversão de datas para lidar com diferentes formatos
def convert_to_datetime(date_value):
    if isinstance(date_value, dict) and '$date' in date_value:
        return pd.to_datetime(date_value['$date'], errors='coerce')
    return pd.to_datetime(date_value, errors='coerce')

rides_data['created_at'] = rides_data['created_at'].apply(convert_to_datetime)
events_data['date'] = events_data['date'].apply(convert_to_datetime)

# Inicializar o app Flask
app = Flask(__name__)

# Rota principal
@app.route('/', methods=['GET', 'POST'])
def index():
    distancia_maxima_km = float(request.form.get('distancia', 10))
    janela_temporal_horas = float(request.form.get('tempo', 24))

    cancelled_rides = rides_data[rides_data['status'] == "Cancelada pelo Taxista"].dropna(subset=['origin_coordinates'])
    events = events_data.dropna(subset=['event_coordinates'])

    cancelled_coords = np.radians(np.array(cancelled_rides['origin_coordinates'].tolist()))
    event_coords = np.radians(np.array(events['event_coordinates'].tolist()))

    kdtree = KDTree(event_coords)
    dist, idx = kdtree.query(cancelled_coords, k=10, return_distance=True)
    dist_km = dist * 6371.0

    related_events = []
    for ride_idx, distances in enumerate(dist_km):
        for d, event_idx in zip(distances, idx[ride_idx]):
            if d <= distancia_maxima_km:
                ride_time = cancelled_rides.iloc[ride_idx]['created_at']
                event_time = events.iloc[event_idx]['date']
                if abs((ride_time - event_time).total_seconds()) / 3600 <= janela_temporal_horas:
                    related_events.append({
                        "Ride ID": cancelled_rides.iloc[ride_idx]['_id']['$oid'],
                        "Event ID": events.iloc[event_idx]['_id']['$oid'],
                        "Distance (km)": d,
                        "Time Difference (hours)": abs((ride_time - event_time).total_seconds()) / 3600
                    })

    resultados_df = pd.DataFrame(related_events)

    tabela_html = resultados_df.to_html(index=False, classes='table table-striped') if not resultados_df.empty else "<p>Nenhuma correlação encontrada dentro dos parâmetros especificados.</p>"

    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard de Cancelamentos Relacionados a Crimes</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" />
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
            <h2 class="mt-4">Resultados da Correlação</h2>
            {tabela_html}
        </div>
    </body>
    </html>
    """

    return render_template_string(template)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
