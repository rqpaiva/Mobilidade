from flask import Flask
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient
import os
import secrets
from app.Analise_espacial_cluster_v1 import create_analise_espacial_cluster_app
from app.Mapa_ocorrencias_v2_1 import mapa_ocorrencias_app

# Configurações gerais do Flask
app = Flask(__name__)
CORS(app)

# Registro do blueprint
# app.register_blueprint(impacto_eventos_app, url_prefix="/impacto_eventos")
app.register_blueprint(mapa_ocorrencias_app, url_prefix="/mapa_ocorrencias")

# Registro do Dash como um Blueprint dentro do Flask
create_analise_espacial_cluster_app(app)

# Configurações de upload
UPLOAD_FOLDER = 'upload_files/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurações de sessão
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session'
app.config['SESSION_PERMANENT'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)
Session(app)

# Configuração do MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

# Importar rotas do arquivo views.py
from app.views import *
# Configurações de sessão
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session'
app.config['SESSION_PERMANENT'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)
Session(app)

# Configuração do MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

# Importar rotas do arquivo views.py
from app.views import *
