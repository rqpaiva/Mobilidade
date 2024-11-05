from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import pandas as pd
import json
import os

app = Flask(__name__)
CORS(app)

# Configuração do MongoDB Atlas
mongo_uri = "mongodb+srv://raquelpaiva:f1smsz0f0ov5rJad@projetounirio.jizft.mongodb.net/?retryWrites=true&w=majority&appName=ProjetoUnirio"
client = MongoClient(mongo_uri)
db = client['mobility_data']

# Caminho para a pasta de upload dos arquivos CSV
UPLOAD_FOLDER = 'upload_files/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Carregar os dados GeoJSON
def load_geojson_to_mongo(file_path, collection_name):
    with open(file_path) as f:
        geojson_data = json.load(f)
    db[collection_name].insert_many(geojson_data['features'])

# Carregar arquivos GeoJSON ao iniciar o app
@app.before_first_request
def load_initial_geojson():
    # Confirme que os arquivos estão no diretório correto antes de rodar o app
    load_geojson_to_mongo('data/Limite_Favelas_2019.geojson', 'geo_data')
    load_geojson_to_mongo('data/Censo_2022__População_e_domicílios_por_bairros_(dados_preliminares).geojson', 'geo_data')