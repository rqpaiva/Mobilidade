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

# [Mantém todas as funções existentes para upload, carga incremental, etc.]

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

        # Chamar a função de correlação de eventos do módulo CorrelacaoEventos
        correlations = get_event_correlations(radius, date, start_time, end_time, status_filter)

        return jsonify(correlations), 200
    except Exception as e:
        logging.error(f"Erro durante análise de correlação de eventos: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)