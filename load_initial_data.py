import os
import logging
import requests
from pymongo import MongoClient
from datetime import datetime, timedelta

# Configuração de Logs
logging.basicConfig(level=logging.INFO)

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
        logging.info("Autenticação realizada com sucesso!")
        return response.json()["data"]["accessToken"]
    except Exception as e:
        logging.error(f"Erro ao autenticar na API: {e}")
        return None

# Função para buscar estados
def fetch_states(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{FOGO_CRUZADO_API_URL}/states", headers=headers)
        response.raise_for_status()
        return response.json()["data"]
    except Exception as e:
        logging.error(f"Erro ao buscar estados: {e}")
        return []

# Função para buscar cidades de um estado
def fetch_cities(token, state_id):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{FOGO_CRUZADO_API_URL}/cities", headers=headers, params={"stateId": state_id}
        )
        response.raise_for_status()
        return response.json()["data"]
    except Exception as e:
        logging.error(f"Erro ao buscar cidades: {e}")
        return []

# Função para buscar dados de ocorrências
def fetch_occurrences(token, state_id, city_ids, initial_date, final_date, page=1, take=100):
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
        logging.error(f"Erro ao buscar ocorrências: {e}")
        return None

# Função para armazenar dados no MongoDB
def store_data_in_mongo(data):
    try:
        if data:
            for record in data:
                record["inserido_em"] = datetime.now()
            collection.insert_many(data)
            logging.info(f"{len(data)} registros inseridos no MongoDB.")
    except Exception as e:
        logging.error(f"Erro ao salvar dados no MongoDB: {e}")

# Função de carga inicial
def load_initial_data():
    token = authenticate()
    if not token:
        logging.error("Autenticação falhou. Encerrando script.")
        return

    # Buscar estados disponíveis
    states = fetch_states(token)
    if not states:
        logging.error("Falha ao obter estados. Encerrando script.")
        return

    # Seleção do estado pelo usuário
    logging.info("Estados disponíveis:")
    for i, state in enumerate(states):
        logging.info(f"{i + 1}. {state['name']}")
    state_index = int(input("Selecione o número do estado: ")) - 1
    state_id = states[state_index]["id"]
    state_name = states[state_index]["name"]

    # Buscar cidades disponíveis no estado
    cities = fetch_cities(token, state_id)
    logging.info(f"Cidades disponíveis no estado {state_name}:")
    for i, city in enumerate(cities):
        logging.info(f"{i + 1}. {city['name']}")
    selected_cities = input("Selecione as cidades (números separados por vírgula) ou pressione Enter para todas: ")
    if selected_cities:
        city_ids = [cities[int(i) - 1]["id"] for i in selected_cities.split(",")]
    else:
        city_ids = [city["id"] for city in cities]

    # Configuração do período de coleta
    start_date = datetime(2016, 7, 1) if state_name == "Rio de Janeiro" else \
                 datetime(2018, 4, 1) if state_name == "Pernambuco" else \
                 datetime(2022, 7, 1)
    end_date = datetime.now()
    current_date = start_date

    # Loop para buscar dados mês a mês
    while current_date < end_date:
        next_date = current_date + timedelta(days=30)
        logging.info(f"Carregando dados de {current_date.strftime('%Y-%m-%d')} a {next_date.strftime('%Y-%m-%d')}")
        result = fetch_occurrences(
            token,
            state_id,
            city_ids,
            current_date.strftime("%Y-%m-%d"),
            next_date.strftime("%Y-%m-%d"),
        )
        if result and "data" in result:
            store_data_in_mongo(result["data"])
        current_date = next_date

    logging.info("Carga inicial concluída.")

# Execução principal
if __name__ == "__main__":
    load_initial_data()