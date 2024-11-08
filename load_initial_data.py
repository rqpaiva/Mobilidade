import os
import logging
import requests
from pymongo import MongoClient
from datetime import datetime, timedelta

# Configuração de Logs
logging.basicConfig(level=logging.DEBUG)

# Configurações do MongoDB e variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")
FOGO_EMAIL = os.getenv("FOGO_EMAIL")
FOGO_PASSWORD = os.getenv("FOGO_PASSWORD")
FOGO_CRUZADO_API_URL = os.getenv("FOGO_CRUZADO_API_URL")

# Conexão com MongoDB
client = MongoClient(MONGO_URI)
db = client["mobility_data"]
collection = db["events"]

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
def fetch_data_from_api(token, initial_date, final_date, page=1, take=100):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
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
            collection.insert_many(data)
            logging.info(f"{len(data)} registros inseridos no MongoDB.")
    except Exception as e:
        logging.error(f"Erro ao salvar dados no MongoDB: {e}")

# Função de Carga Inicial
def load_initial_data():
    try:
        token = authenticate()
        if not token:
            raise Exception("Falha na autenticação")
        
        # Data inicial e final para carga histórica
        start_date = datetime(2016, 7, 1)  # Início da coleta (segundo a documentação)
        end_date = datetime.now()  # Data atual
        current_date = start_date

        # Loop para buscar dados mês a mês
        while current_date < end_date:
            next_date = current_date + timedelta(days=30)  # Dividindo por meses
            logging.info(f"Carregando dados de {current_date} a {next_date}")
            result = fetch_data_from_api(
                token, current_date.strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d")
            )
            if result and "data" in result:
                store_data_in_mongo(result["data"])
            current_date = next_date

        logging.info("Carga inicial concluída com sucesso.")
    except Exception as e:
        logging.error(f"Erro durante a carga inicial: {e}")

# Se o script for executado diretamente, inicie a carga inicial
if __name__ == "__main__":
    load_initial_data()