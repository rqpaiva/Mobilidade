from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from pymongo import MongoClient
import os
import logging
import pandas as pd

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Variáveis de ambiente e configurações
mongo_uri = os.getenv('MONGO_URI')

app = Flask(__name__)
CORS(app)

# Configuração do diretório de upload
UPLOAD_FOLDER = 'upload_files/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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

# Rota principal para a página inicial
@app.route('/')
def home():
    try:
        return render_template('index.html')  # Certifique-se de que o arquivo 'index.html' está na pasta 'templates'
    except Exception as e:
        logging.error(f"Erro ao renderizar a página inicial: {e}")
        return jsonify({'error': 'Falha ao carregar a página inicial'}), 500

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

            # Processar o CSV e armazenar no MongoDB
            data = pd.read_csv(file_path)
            json_data = data.to_dict(orient='records')
            client = get_mongo_client()
            db = client['mobility_data']
            db['rides'].insert_many(json_data)
            logging.info(f"Arquivo {file.filename} carregado com sucesso.")
            return jsonify({'success': 'Arquivo carregado e armazenado com sucesso'}), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

if __name__ == '__main__':
    app.run(debug=True)