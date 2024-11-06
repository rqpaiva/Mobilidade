from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import requests
from datetime import datetime, timedelta
from bson.json_util import dumps
import os

mongo_uri = os.getenv('MONGO_URI')
FOGO_EMAIL = os.getenv('FOGO_EMAIL')
FOGO_PASSWORD = os.getenv('FOGO_PASSWORD')



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

@app.route('/upload', methods=['POST'])
def upload_file():
    # Verifica se o arquivo está presente na requisição
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nome do arquivo inválido'}), 400

    # Verifica se o arquivo é um CSV válido
    if file and file.filename.endswith('.csv'):
        # Salva o arquivo temporariamente
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        # Converte o CSV para JSON e armazena no MongoDB
        data = pd.read_csv(file_path)  # Lê o CSV
        json_data = data.to_dict(orient='records')  # Converte para lista de dicionários
        db['rides'].insert_many(json_data)  # Insere no MongoDB na coleção 'rides'

        return jsonify({'success': 'Arquivo carregado e armazenado com sucesso'}), 201

    # Caso o tipo de arquivo não seja suportado
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400


# Configurações da API Fogo Cruzado
FOGO_CRUZADO_API_URL = "https://api-service.fogocruzado.org.br/api/v2"
access_token = None
token_expiry = None

# Função para autenticação inicial
def authenticate():
    global access_token, token_expiry
    url = f"{FOGO_CRUZADO_API_URL}/auth/login"
    payload = {"email": FOGO_EMAIL, "password": FOGO_PASSWORD}
    response = requests.post(url, json=payload)
    if response.status_code == 201:
        data = response.json()['data']
        access_token = data['accessToken']
        token_expiry = datetime.now() + timedelta(seconds=data['expiresIn'])
    else:
        raise Exception("Falha ao autenticar com a API Fogo Cruzado")

# Função para renovação do token
def refresh_token():
    global access_token, token_expiry
    if access_token and datetime.now() < token_expiry:
        return
    url = f"{FOGO_CRUZADO_API_URL}/auth/refresh"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(url, headers=headers)
    if response.status_code == 201:
        data = response.json()['data']
        access_token = data['accessToken']
        token_expiry = datetime.now() + timedelta(seconds=data['expiresIn'])
    else:
        authenticate()

# Rota para atualizar ocorrências da API Fogo Cruzado
@app.route('/update_occurrences', methods=['GET'])
def update_occurrences():
    try:
        refresh_token()  # Garante que o token está válido
        url = f"{FOGO_CRUZADO_API_URL}/occurrences"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"page": 1, "take": 100}
        all_data = []
        while True:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                all_data.extend(data['data'])
                if not data['pageMeta']['hasNextPage']:
                    break
                params['page'] += 1
            else:
                return jsonify({'error': 'Falha ao buscar dados da API'}), 500
        db['occurrences'].insert_many(all_data)
        return jsonify({'success': f'{len(all_data)} ocorrências atualizadas com sucesso'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Rota para consultar ocorrências armazenadas
@app.route('/get_rides', methods=['GET'])
def get_rides():
    try:
        rides = list(db['rides'].find())
        return dumps(rides), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_geo_data', methods=['GET'])
def get_geo_data():
    try:
        geo_data = list(db['geo_data'].find())
        return dumps(geo_data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_occurrences', methods=['GET'])
def get_occurrences():
    try:
        occurrences = list(db['occurrences'].find())
        return dumps(occurrences), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_filtered_occurrences', methods=['GET'])
def get_filtered_occurrences():
    try:
        query = {}
        if 'state' in request.args:
            query['state.name'] = request.args['state']
        if 'city' in request.args:
            query['city.name'] = request.args['city']
        if 'start_date' in request.args and 'end_date' in request.args:
            query['date'] = {
                "$gte": request.args['start_date'],
                "$lte": request.args['end_date']
            }
        occurrences = list(db['occurrences'].find(query))
        return dumps(occurrences), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

