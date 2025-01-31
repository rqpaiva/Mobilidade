from flask import Flask
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient
import os
import secrets
from app.Impacto_eventos import app as impacto_eventos_app

# Configurações gerais do Flask
app = Flask(__name__)
CORS(app)

# Registro do blueprint
app.register_blueprint(impacto_eventos_app)


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
