from flask import Flask, request, jsonify, render_template, g 
from flask_cors import CORS
from pymongo import MongoClient
import os
import logging
import pandas as pd
from bson.json_util import dumps
from datetime import datetime, timedelta
import requests
from CorrelacaoEventos import get_event_correlations  # Importa a funcionalidade de correlação de eventos

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Configurações do MongoDB e variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")
FOGO_EMAIL = os.getenv("FOGO_EMAIL")
FOGO_PASSWORD = os.getenv("FOGO_PASSWORD")
FOGO_CRUZADO_API_URL = os.getenv("FOGO_CRUZADO_API_URL")

app = Flask(__name__)
CORS(app)

# Diretório de upload
UPLOAD_FOLDER = 'upload_files/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Conexão com MongoDB
client = MongoClient(MONGO_URI)
db = client["mobility_data"]
events_collection = db["events"]

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

# Função para buscar dados da API
def fetch_data_from_api(token, state_id, city_ids, initial_date, final_date, page=1, take=100):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "idState": state_id,
            "idCities": ",".join(city_ids) if city_ids else None,
            "initialdate": initial_date,
            "finaldate": final_date,
            "page": page,
            "take": take,
        }
        response = requests.get(f"{FOGO_CRUZADO_API_URL}/occurrences", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Erro ao buscar dados da API Fogo Cruzado: {e}")
        return None

# Função para carregar dados no MongoDB
def store_data_in_mongo(data):
    try:
        if data:
            for record in data:
                record["inserido_em"] = datetime.now()
            events_collection.insert_many(data)
            logging.info(f"{len(data)} registros inseridos no MongoDB.")
    except Exception as e:
        logging.error(f"Erro ao salvar dados no MongoDB: {e}")

# Endpoint para carga incremental
@app.route('/load_incremental_data', methods=['POST'])
def load_incremental_data():
    try:
        token = authenticate()
        if not token:
            return jsonify({"error": "Falha na autenticação"}), 500

        # Dados fornecidos na requisição
        data = request.json
        state_id = data.get("state_id")
        city_ids = data.get("city_ids", [])
        last_date = data.get("last_date", None)

        if not state_id:
            return jsonify({"error": "State ID é obrigatório"}), 400

        # Determinar a última data registrada no MongoDB ou a data fornecida
        if not last_date:
            last_entry = events_collection.find_one(sort=[("date", -1)])
            last_date = last_entry["date"] if last_entry else "2016-07-01"

        start_date = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
        end_date = datetime.now()
        current_date = start_date

        # Loop para buscar dados mês a mês
        while current_date < end_date:
            next_date = current_date + timedelta(days=30)
            logging.info(f"Carregando dados de {current_date.strftime('%Y-%m-%d')} a {next_date.strftime('%Y-%m-%d')}")
            result = fetch_data_from_api(
                token,
                state_id,
                city_ids,
                current_date.strftime("%Y-%m-%d"),
                next_date.strftime("%Y-%m-%d"),
            )
            if result and "data" in result:
                store_data_in_mongo(result["data"])
                if not result.get("pageMeta", {}).get("hasNextPage", False):
                    break
            current_date = next_date

        return jsonify({"message": "Carga incremental concluída com sucesso"}), 200
    except Exception as e:
        logging.error(f"Erro durante a carga incremental: {e}")
        return jsonify({"error": str(e)}), 500

# Função para obter o cliente MongoDB
def get_mongo_client():
    if 'mongo_client' not in g:
        logging.debug("Conectando ao MongoDB.")
        g.mongo_client = MongoClient(MONGO_URI)
    return g.mongo_client

# Encerrar o cliente MongoDB ao finalizar a requisição
@app.teardown_appcontext
def teardown_mongo_client(exception):
    mongo_client = g.pop('mongo_client', None)
    if mongo_client is not None:
        logging.debug("Fechando conexão com o MongoDB.")
        mongo_client.close()

# Página inicial
@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Erro ao renderizar a página inicial: {e}")
        return jsonify({'error': 'Página inicial não encontrada'}), 404

# Upload de arquivos CSV
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
            db['rides_original'].insert_many(json_data)
            logging.info(f"Arquivo {file.filename} carregado com sucesso.")
            return jsonify({'success': 'Arquivo CSV carregado e armazenado com sucesso'}), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

# Consulta de dados CSV no MongoDB
@app.route('/get_rides', methods=['GET'])
def get_rides():
    logging.debug("Recebendo requisição para consultar dados de corridas.")
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        rides = list(db['rides_original'].find())
        return dumps(rides), 200
    except Exception as e:
        logging.error(f"Erro ao consultar dados CSV: {e}")
        return jsonify({'error': str(e)}), 500

# Consulta de ocorrências da API no MongoDB
@app.route('/get_occurrences', methods=['GET'])
def get_occurrences():
    logging.debug("Recebendo requisição para consultar ocorrências.")
    try:
        client = get_mongo_client()
        db = client['mobility_data']
        occurrences = list(db['events'].find())
        return dumps(occurrences), 200
    except Exception as e:
        logging.error(f"Erro ao consultar ocorrências: {e}")
        return jsonify({'error': str(e)}), 500

# Novo endpoint para análise de eventos correlacionados
@app.route('/events-near-cancellations', methods=['GET'])
def events_near_cancellations():
    try:
        # Obter parâmetros da requisição
        radius = float(request.args.get('radius', 5))  # Raio em km
        date = request.args.get('date')  # Exemplo: '2024-11-13'
        start_time = request.args.get('start_time', '00:00')
        end_time = request.args.get('end_time', '23:59')
        status_filter = request.args.get('status', None)  # Exemplo: 'cancelada pelo taxista'

        if not date:
            return jsonify({'error': 'O parâmetro "date" é obrigatório.'}), 400

        # Chamar a função de correlação de eventos
        correlations = get_event_correlations(radius, date, start_time, end_time, status_filter)

        if "message" in correlations:  # Fallback
            return jsonify(correlations), 200

        return jsonify(correlations), 200
    except Exception as e:
        logging.error(f"Erro durante análise de correlação de eventos: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)