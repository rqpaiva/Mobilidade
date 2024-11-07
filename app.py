from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from pymongo import MongoClient
import os
import logging
import pandas as pd
import json

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Variáveis de ambiente e configurações
mongo_uri = os.getenv('MONGO_URI', "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority&ssl=true")
FOGO_EMAIL = os.getenv('FOGO_EMAIL')
FOGO_PASSWORD = os.getenv('FOGO_PASSWORD')
FOGO_CRUZADO_API_URL = os.getenv('FOGO_CRUZADO_API_URL')

app = Flask(__name__)
CORS(app)

# Configuração do diretório de upload
UPLOAD_FOLDER = 'upload_files/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Função para obter o cliente MongoDB no contexto atual
def get_mongo_client():
    if 'mongo_client' not in g:
        g.mongo_client = MongoClient(mongo_uri, ssl=True, tlsAllowInvalidCertificates=False)
    return g.mongo_client

# Encerrar o cliente MongoDB ao finalizar a requisição
@app.teardown_appcontext
def teardown_mongo_client(exception):
    mongo_client = g.pop('mongo_client', None)
    if mongo_client is not None:
        mongo_client.close()

# Rota principal para a página inicial
@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Erro ao renderizar a página inicial: {e}")
        return jsonify({'error': 'Falha ao carregar a página inicial'}), 500

# Função para inserir dados em lotes no MongoDB
def insert_in_batches(data, collection_name, batch_size=500):
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        collection = db[collection_name]
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            collection.insert_many(batch)
            logging.info(f"Lote de {len(batch)} documentos inserido com sucesso.")
    except Exception as e:
        logging.error(f"Erro ao inserir dados em lotes: {e}")
        raise

# Rota para upload de arquivo CSV
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        logging.warning("Nenhum arquivo enviado.")
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if file.filename == '':
        logging.warning("Nome do arquivo inválido.")
        return jsonify({'error': 'Nome do arquivo inválido'}), 400

    if file and file.filename.endswith('.csv'):
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)

            # Processar o CSV e armazenar no MongoDB em lotes
            data = pd.read_csv(file_path)
            json_data = data.to_dict(orient='records')
            insert_in_batches(json_data, 'rides')
            logging.info(f"Arquivo {file.filename} carregado e processado com sucesso.")
            return jsonify({'success': 'Arquivo carregado e armazenado com sucesso'}), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

# Função para carregar GeoJSON no MongoDB
def load_geojson_to_mongo(file_path, collection_name):
    try:
        logging.info(f"Carregando arquivo GeoJSON: {file_path}")
        with open(file_path) as f:
            geojson_data = json.load(f)
        insert_in_batches(geojson_data['features'], collection_name)
        logging.info(f"GeoJSON {file_path} carregado com sucesso na coleção {collection_name}.")
    except Exception as e:
        logging.error(f"Erro ao carregar GeoJSON {file_path}: {e}")
        raise

# Rota para carregar dados GeoJSON sob demanda
@app.route('/load_geojson', methods=['POST'])
def load_geojson():
    try:
        load_geojson_to_mongo('data/Limite_Favelas_2019.geojson', 'geo_data')
        load_geojson_to_mongo('data/Censo_2022__População_e_domicílios_por_bairros_(dados_preliminares).geojson', 'geo_data')
        return jsonify({'success': 'GeoJSON carregado com sucesso!'}), 200
    except Exception as e:
        logging.error(f"Erro ao carregar GeoJSON: {e}")
        return jsonify({'error': str(e)}), 500

# Rotas para consulta de dados
@app.route('/get_rides', methods=['GET'])
def get_rides():
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        rides = list(db['rides'].find())
        logging.info("Consulta de rides realizada com sucesso.")
        return jsonify(rides), 200
    except Exception as e:
        logging.error(f"Erro ao consultar rides: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_geo_data', methods=['GET'])
def get_geo_data():
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        geo_data = list(db['geo_data'].find())
        logging.info("Consulta de geo_data realizada com sucesso.")
        return jsonify(geo_data), 200
    except Exception as e:
        logging.error(f"Erro ao consultar geo_data: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)