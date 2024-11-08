from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.utils import secure_filename
import os
import logging
import pandas as pd
import requests
from bson.json_util import dumps
from datetime import datetime, timedelta
import json

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Configurações do MongoDB e variáveis de ambiente
mongo_uri = os.getenv('MONGO_URI')
FOGO_EMAIL = os.getenv('FOGO_EMAIL')
FOGO_PASSWORD = os.getenv('FOGO_PASSWORD')
FOGO_CRUZADO_API_URL = os.getenv('FOGO_CRUZADO_API_URL')

app = Flask(__name__)
CORS(app)

# Diretório de upload
UPLOAD_FOLDER = 'upload_files/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Conexão com MongoDB
client = MongoClient(mongo_uri)
db = client["mobility_data"]

# Função para autenticação na API
def authenticate():
    try:
        response = requests.post(
            f"{FOGO_CRUZADO_API_URL}/auth/login",
            json={"email": FOGO_EMAIL, "password": FOGO_PASSWORD},
        )
        response.raise_for_status()
        return response.json()["data"]["accessToken"]
    except Exception as e:
        logging.error(f"Erro ao autenticar na API Fogo Cruzado: {e}")
        return None

# Função para carregar dados no MongoDB
def store_data_in_mongo(collection_name, data):
    try:
        collection = db[collection_name]
        if data:
            collection.insert_many(data, ordered=False)
            logging.info(f"{len(data)} registros inseridos na coleção {collection_name}.")
    except Exception as e:
        logging.error(f"Erro ao salvar dados no MongoDB: {e}")

# Conversão de CSV para GeoJSON
def csv_to_geojson(data):
    geojson_records = []

    # Identificar padrões de coordenadas
    for col in data.columns:
        if "_lat" in col or "_lng" in col:
            lat_col = col if "_lat" in col else col.replace("_lng", "_lat")
            lng_col = col if "_lng" in col else col.replace("_lat", "_lng")
            
            if lat_col in data.columns and lng_col in data.columns:
                for _, row in data.iterrows():
                    if not pd.isnull(row[lat_col]) and not pd.isnull(row[lng_col]):
                        geojson_records.append({
                            "type": "Point",
                            "coordinates": [row[lng_col], row[lat_col]],
                            "properties": row.drop([lat_col, lng_col]).to_dict()
                        })

        elif "location" in col or "coordinates" in col:
            # Lida com coordenadas combinadas no formato JSON
            for _, row in data.iterrows():
                try:
                    location_data = json.loads(row[col])
                    if isinstance(location_data, list) and len(location_data) == 2:
                        geojson_records.append({
                            "type": "Point",
                            "coordinates": location_data,
                            "properties": row.drop(col).to_dict()
                        })
                except (ValueError, TypeError):
                    logging.warning(f"Dados de coordenadas inválidos na coluna {col} para a linha {row.to_dict()}")

    return geojson_records

# Upload de arquivo CSV (dois formatos)
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        logging.warning("Nenhum arquivo enviado.")
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if file.filename == '':
        logging.warning("Nome do arquivo inválido.")
        return jsonify({'error': 'Nome do arquivo inválido'}), 400

    if file and file.filename.endswith('.csv'):
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(file_path)

            data = pd.read_csv(file_path)

            # 1. Inserir dados no formato GeoJSON
            geojson_data = csv_to_geojson(data)
            store_data_in_mongo("rides_geojson", geojson_data)

            # 2. Inserir dados preservando as variáveis originais
            original_data = data.to_dict(orient="records")
            store_data_in_mongo("rides_original", original_data)

            logging.info(f"Arquivo {file.filename} carregado com sucesso em ambos os formatos.")
            return jsonify({
                'success': 'Arquivo CSV carregado e armazenado com sucesso em ambos os formatos'
            }), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

# Consulta de dados CSV no MongoDB (dois formatos)
@app.route('/get_rides_geojson', methods=['GET'])
def get_rides_geojson():
    try:
        data = list(db["rides_geojson"].find())
        return dumps(data), 200
    except Exception as e:
        logging.error(f"Erro ao consultar dados GeoJSON: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_rides_original', methods=['GET'])
def get_rides_original():
    try:
        data = list(db["rides_original"].find())
        return dumps(data), 200
    except Exception as e:
        logging.error(f"Erro ao consultar dados originais: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)