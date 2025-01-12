from flask import Flask, request
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd
import networkx as nx
from flask_session import Session
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from collections import Counter
from tabulate import tabulate
from flask_cors import CORS
import io
import secrets
import base64
import json
import gmaps
from flask_pymongo import PyMongo
app = Flask(__name__)
app.config["SECRET_KEY"] = "Q9WE9QWSALKDIOASDU092U3EKDFWF"
app.config["MONGO_URI"] = "mongodb+srv://felipepaivadev:Kv8TkdhEdR9ldeYn@cluster0.qzl2q.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session'  # Diretório onde as sessões serão salvas
app.config['SESSION_PERMANENT'] = False
app.config['SECRET_KEY'] = secrets.token_hex(16)
Session(app)



from app.views import home
