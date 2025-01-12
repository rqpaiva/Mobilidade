import os
import logging
from pymongo import MongoClient
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import KNNImputer
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO)

# Obter a string de conexão do MongoDB
MONGO_URI = os.getenv("MONGO_URI")

# Conectar ao MongoDB
client = MongoClient(MONGO_URI)
db = client["mobility_data"]
collection = db["ocorrencias"]

# Carregar os dados em um DataFrame
df = pd.DataFrame(list(collection.find()))

# Filtrar registros com valores nulos
df_null = df[(df['latitude'].isnull()) | (df['longitude'].isnull())]
df_full = df.dropna(subset=['latitude', 'longitude'])

# Usar o KNN Imputer para preencher valores nulos
imputer = KNNImputer(n_neighbors=5)
df[['latitude', 'longitude']] = imputer.fit_transform(df[['latitude', 'longitude']])

# Criar o campo 'location'
df['location'] = df.apply(lambda row: {
    "type": "Point",
    "coordinates": [row['longitude'], row['latitude']]
}, axis=1)

# Atualizar o MongoDB
for _, row in df.iterrows():
    collection.update_one(
        {"_id": row["_id"]},
        {"$set": {
            "latitude": row['latitude'],
            "longitude": row['longitude'],
            "location": row['location']
        }}
    )

print("Valores nulos preenchidos com sucesso!")