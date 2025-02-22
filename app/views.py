import logging
import os

import pandas as pd
from flask import render_template, request, jsonify, Blueprint

from app import app, db

# Configurações do MongoDB e variáveis de ambiente
FOGO_EMAIL = os.getenv("FOGO_EMAIL")
FOGO_PASSWORD = os.getenv("FOGO_PASSWORD")
FOGO_CRUZADO_API_URL = os.getenv("FOGO_CRUZADO_API_URL")

index_app = Blueprint("index_app", __name__)

events_collection = db["events"]

# Configurações de logs
logging.basicConfig(level=logging.DEBUG)

# Verificar se o arquivo é permitido
ALLOWED_EXTENSIONS = {'csv'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Página inicial
@index_app.route('/')
def home():
    return render_template('index.html')

# Upload de arquivos CSV
@index_app.route('/upload_csv', methods=['POST'])
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

# Rotas para páginas específicas
@index_app.route('/analise-espacial')
def analise_espacial():
    return render_template('analise_espacial.html')

@index_app.route('/analise-temporal')
def analise_temporal():
    return render_template('analise_temporal.html')

@index_app.route('/analise-pessoal')
def analise_pessoal():
    return render_template('analise_pessoal.html')

@index_app.route('/dados-correlacionados')
def dados_correlacionados():
    return render_template('dados_correlacionados.html')

@index_app.route('/mapa_ocorrencias')
def mapa_ocorrencias():
    return render_template('impacto_eventos.html')

app.register_blueprint(index_app, url_prefix="/")
