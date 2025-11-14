import sys
import os
import secrets
import logging
from flask import Flask
from flask_session import Session
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)

# Inicializa o Flask
app = Flask(__name__)
CORS(app)

# Configuração de sessão
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/home/raquel/mobilidade/flask_session'
app.config['SESSION_PERMANENT'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)
Session(app)

# Configuração de uploads
UPLOAD_FOLDER = 'upload_files/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ------------------------------------------------------------------------
# Importação dos Blueprints

from app.impacto_violencia_v1 import impacto_violencia_app
from app.Mapa_ocorrencias_v2_2 import mapa_ocorrencias_app
from app.info_geral import info_geral_app
from app.redlining import favelas_app
from app.analise_comentarios import analise_comentarios_app
from app.analise_reclame_aqui import reclame_aqui_app

# Importa o blueprint principal (views.py)
from app.views import index_app


# Registro dos Blueprints
app.register_blueprint(index_app, url_prefix="/")

# Registro das demais rotas:
app.register_blueprint(impacto_violencia_app, url_prefix="/impacto_violencia")
app.register_blueprint(mapa_ocorrencias_app, url_prefix="/mapa_ocorrencias")
app.register_blueprint(favelas_app, url_prefix="/favelas")
app.register_blueprint(info_geral_app, url_prefix="/info_geral")
app.register_blueprint(analise_comentarios_app, url_prefix='/analise_comentarios')
app.register_blueprint(reclame_aqui_app, url_prefix='/analise_reclame_aqui')


# Dash para Análise Espacial:
#create_analise_espacial_cluster_app(app)
# ------------------------------------------------------------------------


