from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from pymongo import MongoClient
import os
import logging
import pandas as pd
import requests
from bson.json_util import dumps

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

# Função para obter o cliente MongoDB
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

# Página inicial
@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Erro ao renderizar a página inicial: {e}")
        return jsonify({'error': 'Página inicial não encontrada'}), 404

# Upload de arquivo CSV
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
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)

            # Processar o CSV e armazenar no MongoDB
            data = pd.read_csv(file_path)
            json_data = data.to_dict(orient='records')
            client = get_mongo_client()
            db = client['mobility_data']
            db['rides'].insert_many(json_data)
            logging.info(f"Arquivo {file.filename} carregado com sucesso.")
            return jsonify({'success': 'Arquivo CSV carregado e armazenado com sucesso'}), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

# Carregar dados da API Fogo Cruzado
@app.route('/update_occurrences', methods=['POST'])
def update_occurrences():
    try:
        # Autenticar na API Fogo Cruzado
        response = requests.post(f"{FOGO_CRUZADO_API_URL}/auth", json={"email": FOGO_EMAIL, "password": FOGO_PASSWORD})
        if response.status_code != 200:
            logging.error("Falha na autenticação na API Fogo Cruzado.")
            return jsonify({'error': 'Falha na autenticação na API Fogo Cruzado'}), 500

        access_token = response.json().get('access_token')
        headers = {"Authorization": f"Bearer {access_token}"}

        # Buscar ocorrências
        occurrences_url = f"{FOGO_CRUZADO_API_URL}/occurrences"
        params = {"page": 1, "take": 100}
        all_data = []

        while True:
            response = requests.get(occurrences_url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                all_data.extend(data['data'])
                if not data['pageMeta']['hasNextPage']:
                    break
                params['page'] += 1
            else:
                logging.error("Falha ao buscar dados da API Fogo Cruzado.")
                return jsonify({'error': 'Falha ao buscar dados da API Fogo Cruzado'}), 500

        # Armazenar os dados no MongoDB
        client = get_mongo_client()
        db = client['mobility_data']
        db['occurrences'].insert_many(all_data)
        logging.info(f"{len(all_data)} ocorrências atualizadas com sucesso.")
        return jsonify({'success': f'{len(all_data)} ocorrências atualizadas com sucesso'}), 200
    except Exception as e:
        logging.error(f"Erro ao atualizar ocorrências: {e}")
        return jsonify({'error': str(e)}), 500

# Consulta de dados CSV no MongoDB
@app.route('/get_rides', methods=['GET'])
def get_rides():
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        rides = list(db['rides'].find())
        return dumps(rides), 200
    except Exception as e:
        logging.error(f"Erro ao consultar dados CSV: {e}")
        return jsonify({'error': str(e)}), 500

# Consulta de ocorrências da API no MongoDB
@app.route('/get_occurrences', methods=['GET'])
def get_occurrences():
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        occurrences = list(db['occurrences'].find())
        return dumps(occurrences), 200
    except Exception as e:
        logging.error(f"Erro ao consultar ocorrências: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)