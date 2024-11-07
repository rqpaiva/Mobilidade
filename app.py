import os
from flask import Flask, request, jsonify, render_template, g
from pymongo import MongoClient
import logging
import json

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Variáveis de ambiente e configurações
mongo_uri = os.getenv('MONGO_URI')

app = Flask(__name__)

# Função para obter o cliente MongoDB no contexto atual
def get_mongo_client():
    if 'mongo_client' not in g:
        g.mongo_client = MongoClient(mongo_uri)
    return g.mongo_client

# Encerrar o cliente MongoDB ao finalizar a requisição
@app.teardown_appcontext
def teardown_mongo_client(exception):
    mongo_client = g.pop('mongo_client', None)
    if mongo_client is not None:
        mongo_client.close()

# Função para carregar GeoJSON no MongoDB
def load_geojson_to_mongo(file_path, collection_name):
    try:
        logging.info(f"Carregando arquivo GeoJSON: {file_path}")
        with open(file_path, encoding='utf-8') as f:
            geojson_data = json.load(f)
        client = get_mongo_client()
        db = client['mobility_data']

        # Verificar se a coleção está vazia antes de inserir os dados
        if db[collection_name].count_documents({}) == 0:
            db[collection_name].insert_many(geojson_data['features'])
            logging.info(f"GeoJSON {file_path} carregado com sucesso na coleção {collection_name}.")
        else:
            logging.info(f"GeoJSON {collection_name} já possui dados. Nenhuma ação realizada.")
    except Exception as e:
        logging.error(f"Erro ao carregar GeoJSON {file_path}: {e}")
        raise

# Carregar GeoJSONs ao iniciar o servidor
@app.before_first_request
def initialize_geojson_data():
    try:
        load_geojson_to_mongo('data/Limite_Favelas_2019.geojson', 'geo_favelas')
        load_geojson_to_mongo('data/Censo_2022__População_e_domicílios_por_bairros_(dados_preliminares).geojson', 'geo_censo')
    except Exception as e:
        logging.error(f"Erro ao inicializar dados GeoJSON: {e}")

# Rota para carregar GeoJSONs sob demanda
@app.route('/upload_geojson/<collection_name>', methods=['POST'])
def upload_geojson(collection_name):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Nome do arquivo inválido'}), 400

        if file and file.filename.endswith('.geojson'):
            geojson_data = json.load(file)
            client = get_mongo_client()
            db = client['mobility_data']

            # Limpar dados antigos e inserir novos
            db[collection_name].delete_many({})
            db[collection_name].insert_many(geojson_data['features'])
            logging.info(f"GeoJSON enviado e carregado na coleção {collection_name}.")
            return jsonify({'success': f'GeoJSON carregado na coleção {collection_name} com sucesso'}), 200
        else:
            return jsonify({'error': 'Formato de arquivo inválido. Envie um arquivo .geojson'}), 400
    except Exception as e:
        logging.error(f"Erro ao carregar GeoJSON na coleção {collection_name}: {e}")
        return jsonify({'error': str(e)}), 500

# Exemplo de rota para verificar os dados GeoJSON carregados
@app.route('/get_geojson/<collection_name>', methods=['GET'])
def get_geojson(collection_name):
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        geojson_data = list(db[collection_name].find())
        return jsonify(geojson_data), 200
    except Exception as e:
        logging.error(f"Erro ao consultar GeoJSON da coleção {collection_name}: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)