import logging
import os
import secrets
import pandas as pd
from flask import render_template, request, jsonify, Blueprint, current_app
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient


# Definição do Blueprint principal
index_app = Blueprint("index_app", __name__)

# ---------------------------------------------------------
# Extensões permitidas
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------------------------------------------------
# Rotas
@index_app.route("/")
def home():
    """Página inicial."""
    return render_template('index.html')

# ---------------------------------------------------------
# Upload de arquivos CSV
@index_app.route('/upload_csv', methods=['POST'])
def upload_csv():
    """Rota que recebe um CSV e insere no MongoDB."""
    if 'file' not in request.files:
        logging.warning("Nenhum arquivo enviado.")
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if file.filename == '':
        logging.warning("Nome do arquivo inválido.")
        return jsonify({'error': 'Nome do arquivo inválido'}), 400

    if file and file.filename.endswith('.csv'):
        try:
            # Salva localmente
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)

            # Processa CSV
            data = pd.read_csv(file_path)
            json_data = data.to_dict(orient='records')

            # Conecta ao MongoDB sob demanda
            MONGO_URI = os.getenv("MONGO_URI")
            client = MongoClient(MONGO_URI)
            db = client['mobility_data']
            db['rides_original'].insert_many(json_data)
            logging.info(f"Arquivo {file.filename} carregado com sucesso.")
            return jsonify({'success': 'Arquivo CSV carregado e armazenado com sucesso'}), 201
        except Exception as e:
            logging.error(f"Erro ao processar o arquivo CSV: {e}")
            return jsonify({'error': str(e)}), 500

    logging.warning("Tipo de arquivo não suportado.")
    return jsonify({'error': 'Tipo de arquivo não suportado. Envie um CSV'}), 400

# ---------------------------------------------------------
# Rotas para páginas específicas
#@index_app.route('/analise-espacial')
#def analise_espacial():
#    return render_template('analise_espacial.html')

#@index_app.route('/analise-temporal')
#def analise_temporal():
#    return render_template('analise_temporal.html')

#@index_app.route('/analise-pessoal')
#def analise_pessoal():
#    return render_template('analise_pessoal.html')

#@index_app.route('/dados-correlacionados')
#def dados_correlacionados():
#    return render_template('dados_correlacionados.html')

