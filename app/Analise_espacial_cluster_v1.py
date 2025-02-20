import logging
import os
import pymongo
from tabulate import tabulate
import pandas as pd
import numpy as np
import requests
import geopandas as gpd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import gc
import scipy.spatial.distance as ssd

from dotenv import load_dotenv
from pymongo import MongoClient
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.ensemble import IsolationForest
from scipy.cluster.hierarchy import linkage, dendrogram

# 🔹 Carregar variáveis de ambiente
load_dotenv()

# 🔹 Configuração de Logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 🔹 Obter a string de conexão do MongoDB
MONGO_URI = os.getenv("MONGO_URI")

# 🔹 Conectar ao MongoDB
logger.info("Conectando ao MongoDB...")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]
collection = db["rides_original"]

# 🔹 Buscar os dados da coleção (limitando para evitar sobrecarga de memória)
cursor = collection.find({}, {
    "_id": 0,
    "status": 1,
    "driver_distance": 1,
    "route_distance": 1,
    "origin_lat": 1,
    "origin_lng": 1,
    "created_at": 1
}).limit(100000)  # Reduzindo a quantidade de dados para melhorar a performance

# 🔹 Converter os dados para um DataFrame do Pandas
df = pd.DataFrame(list(cursor))

# 🔹 Verificar nomes das colunas para evitar erros de chave ausente
print("Colunas disponíveis:", df.columns)

# 🔹 Remover valores nulos para evitar problemas na análise
df = df.dropna(subset=["driver_distance", "route_distance", "origin_lat", "origin_lng"])

# 🔹 Converter tipos numéricos para otimizar memória
df["driver_distance"] = df["driver_distance"].astype(np.float32)
df["route_distance"] = df["route_distance"].astype(np.float32)
df["origin_lat"] = df["origin_lat"].astype(np.float32)
df["origin_lng"] = df["origin_lng"].astype(np.float32)

# 🔹 Criar colunas de cancelamento pelo motorista e pelo passageiro
df["canceled_by_driver"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Taxista" in x else 0).astype(np.int8)
df["canceled_by_passenger"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Passageiro" in x else 0).astype(np.int8)
df["completed"] = df["status"].apply(lambda x: 1 if "Finalizada" in x else 0).astype(np.int8)

# 🔹 Padronizar os dados para KMeans
features = ["driver_distance", "route_distance", "canceled_by_driver", "canceled_by_passenger", "completed"]
scaler = StandardScaler()
df_scaled = scaler.fit_transform(df[features])

# Determinar o número ideal de clusters com visualizações do Cotovelo e Silhouette Score
wcss = []
silhouette_scores = []
k_values = range(2, 10)

for k in k_values:
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(df_scaled)
    wcss.append(kmeans.inertia_)
    silhouette_scores.append(silhouette_score(df_scaled, labels))

# Criar gráficos do Método do Cotovelo e Silhouette Score
plt.figure(figsize=(12, 5))
plt.subplot(1, 2, 1)
plt.plot(k_values, wcss, marker='o', linestyle='-')
plt.xlabel('Número de Clusters')
plt.ylabel('WCSS (Soma dos Quadrados das Distâncias)')
plt.title('Método do Cotovelo')

plt.subplot(1, 2, 2)
plt.plot(k_values, silhouette_scores, marker='o', linestyle='-')
plt.xlabel('Número de Clusters')
plt.ylabel('Silhouette Score')
plt.title('Silhouette Score por Número de Clusters')

plt.tight_layout()
plt.show()

# Escolher o melhor número de clusters baseado no Silhouette Score
optimal_k = k_values[np.argmax(silhouette_scores)]
print(f'Número ideal de clusters: {optimal_k}')

# Aplicar K-Means com o número ideal de clusters
kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
df["cluster"] = kmeans.fit_predict(df_scaled).astype(np.int8)

# 🔹 Aplicar Isolation Forest para detectar outliers
iso_forest = IsolationForest(contamination=0.05, random_state=42)
df["outlier"] = iso_forest.fit_predict(df_scaled).astype(np.int8)

# Contar quantos outliers foram detectados
outlier_count = df['outlier'].value_counts()
print(f"Total de Outliers Detectados: {outlier_count.get(-1, 0)}")

# Visualizar os outliers no scatterplot
plt.figure(figsize=(10, 6))
sns.scatterplot(x=df['driver_distance'], y=df['route_distance'], hue=df['outlier'], palette={1: 'blue', -1: 'red'}, alpha=0.6)
plt.xlabel('Distância do Motorista até o Local de Embarque (metros)')
plt.ylabel('Distância Estimada da Corrida (metros)')
plt.title('Identificação de Outliers com Isolation Forest')
plt.legend(title="Outlier", labels=["Normal", "Outlier"])
plt.show()

# Exibir apenas os outliers para inspeção
df_outliers = df[df['outlier'] == -1]
print("Outliers Identificados:")
print(df_outliers)

# Criar boxplot para analisar a distribuição da distância em cada cluster
plt.figure(figsize=(10, 6))
sns.boxplot(x=df['cluster'], y=df['driver_distance'], palette='viridis')
plt.xlabel('Cluster')
plt.ylabel('Distância do Motorista até o Embarque (metros)')
plt.title('Distribuição das Distâncias por Cluster')
plt.show()

# Criar boxplot para comparar outliers vs. não outliers
plt.figure(figsize=(12, 6))

# Boxplot para cancelamento pelo motorista
plt.subplot(1, 2, 1)
sns.boxplot(x=df['canceled_by_driver'], y=df['driver_distance'], palette='Blues')
plt.xlabel("Cancelado pelo Motorista (0 = Não, 1 = Sim)")
plt.ylabel("Distância do Motorista até o Passageiro (metros)")
plt.title("Distribuição da Distância do Motorista para Cancelamentos pelo Motorista")

# Boxplot para cancelamento pelo passageiro
plt.subplot(1, 2, 2)
sns.boxplot(x=df['canceled_by_passenger'], y=df['driver_distance'], palette='Reds')
plt.xlabel("Cancelado pelo Passageiro (0 = Não, 1 = Sim)")
plt.ylabel("Distância do Motorista até o Passageiro (metros)")
plt.title("Distribuição da Distância do Motorista para Cancelamentos pelo Passageiro")

plt.tight_layout()
plt.show()


# 🔹 Liberar memória após processamento
gc.collect()

# 🔹 Obter os limites dos bairros do Rio de Janeiro via API do Data.Rio
url = "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Cartografia/Limites_administrativos/MapServer/4/query"
params = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson"}
response = requests.get(url, params=params)

if response.status_code == 200:
    bairros_geojson = response.json()
    gdf_bairros = gpd.GeoDataFrame.from_features(bairros_geojson["features"])
    gdf_bairros.crs = "EPSG:4326"
else:
    print("Erro ao obter dados dos bairros:", response.status_code)
    gdf_bairros = None

# 🔹 Criar visualizações interativas com Plotly
# 🔸 Mapa de Clusters
df_sample = df.sample(n=min(1000, len(df)), random_state=42)  # Reduzindo para 1000 pontos

fig_clusters = px.scatter_mapbox(
    df_sample,
    lat="origin_lat",
    lon="origin_lng",
    color="cluster",
    mapbox_style="carto-positron",
    zoom=10,
    center={"lat": -22.9068, "lon": -43.1729},
    title="Distribuição Geográfica dos Clusters de Corridas"
)
fig_clusters.show()

# 🔸 Mapa de Outliers
df_outliers_sample = df[df["outlier"] == -1].sample(n=min(300, len(df[df["outlier"] == -1])), random_state=42)

fig_outliers = px.scatter_mapbox(
    df_outliers_sample,
    lat="origin_lat",
    lon="origin_lng",
    color="outlier",
    mapbox_style="carto-positron",
    zoom=10,
    center={"lat": -22.9068, "lon": -43.1729},
    title="Distribuição Geográfica dos Outliers de Corridas"
)
fig_outliers.show()

# 🔸 Mapa Coroplético dos Clusters
if gdf_bairros is not None:
    fig_choropleth = px.choropleth_mapbox(
        df_sample,
        geojson=gdf_bairros.geometry.__geo_interface__,
        locations=df_sample.index,
        color="cluster",
        mapbox_style="carto-positron",
        center={"lat": -22.9068, "lon": -43.1729},
        zoom=10,
        title="Distribuição Geográfica dos Clusters (Geo Choropleth)"
    )
    fig_choropleth.show()

    # Liberar memória antes de continuar
    gc.collect()

    # Reduzir a amostra do DataFrame para evitar erro de memória (1000 amostras no máximo)
    df_sample = df.sample(n=min(1000, len(df)), random_state=42).copy()

    # Converter apenas colunas necessárias para tipos otimizados
    df_sample["driver_distance"] = df_sample["driver_distance"].astype(np.float32)
    df_sample["route_distance"] = df_sample["route_distance"].astype(np.float32)
    df_sample["canceled_by_driver"] = df_sample["canceled_by_driver"].astype(np.int8)
    df_sample["canceled_by_passenger"] = df_sample["canceled_by_passenger"].astype(np.int8)
    df_sample["completed"] = df_sample["completed"].astype(np.int8)
    df_sample["cluster"] = df_sample["cluster"].astype(np.int8)

    # Criar um resumo estatístico dos clusters baseado na amostra reduzida
    cluster_summary = df_sample.groupby("cluster")[
        ["driver_distance", "route_distance", "canceled_by_driver", "canceled_by_passenger", "completed"]].mean()
    cluster_summary["total_rides"] = df_sample.groupby("cluster").size()  # Contagem de corridas por cluster

    # Converter para tipos otimizados após agrupar
    cluster_summary = cluster_summary.astype({"driver_distance": "float32", "route_distance": "float32",
                                              "canceled_by_driver": "float32", "canceled_by_passenger": "float32",
                                              "completed": "float32", "total_rides": "int32"})

    # Liberar memória após processamento
    gc.collect()

    # ------------------ Zoomable Circle Packing ------------------
    # Criar um resumo estatístico dos clusters
    cluster_summary = df.groupby("cluster")[
        ["driver_distance", "route_distance", "canceled_by_driver", "canceled_by_passenger", "completed"]].mean()
    cluster_summary["total_rides"] = df.groupby("cluster").size()
    cluster_summary["finalizadas"] = df[df["status"] == "Finalizada"].groupby("cluster").size()
    cluster_summary["canceladas_motorista"] = df[df["status"] == "Cancelada pelo Taxista"].groupby("cluster").size()
    cluster_summary["canceladas_passageiro"] = df[df["status"] == "Cancelada pelo Passageiro"].groupby("cluster").size()

    # Preencher valores nulos com 1e-6 para evitar divisão por zero
    cluster_summary = cluster_summary.fillna(1e-6)

    # Criar estrutura de dados para o Zoomable Circle Packing
    data_circle_packing = []

    # Adicionar os clusters como categorias principais
    for cluster, row in cluster_summary.iterrows():
        if row["total_rides"] > 0:  # Evita valores nulos
            data_circle_packing.append({"id": f"Cluster {cluster}", "parent": "", "value": row["total_rides"]})

            # Adicionar apenas se o valor for maior que 0
            if row["finalizadas"] > 0:
                data_circle_packing.append(
                    {"id": f"Finalizadas {cluster}", "parent": f"Cluster {cluster}", "value": row["finalizadas"]})
            if row["canceladas_motorista"] > 0:
                data_circle_packing.append({"id": f"Canceladas Motorista {cluster}", "parent": f"Cluster {cluster}",
                                            "value": row["canceladas_motorista"]})
            if row["canceladas_passageiro"] > 0:
                data_circle_packing.append({"id": f"Canceladas Passageiro {cluster}", "parent": f"Cluster {cluster}",
                                            "value": row["canceladas_passageiro"]})
            if row["driver_distance"] > 0:
                data_circle_packing.append(
                    {"id": f"Distância {cluster}", "parent": f"Cluster {cluster}", "value": row["driver_distance"]})
            if row["route_distance"] > 0:
                data_circle_packing.append(
                    {"id": f"Rota {cluster}", "parent": f"Cluster {cluster}", "value": row["route_distance"]})
            if row["canceled_by_driver"] > 0:
                data_circle_packing.append({"id": f"Cancelado Motorista {cluster}", "parent": f"Cluster {cluster}",
                                            "value": row["canceled_by_driver"]})
            if row["canceled_by_passenger"] > 0:
                data_circle_packing.append({"id": f"Cancelado Passageiro {cluster}", "parent": f"Cluster {cluster}",
                                            "value": row["canceled_by_passenger"]})
            if row["finalizadas"] > 0 and row["total_rides"] > 0:
                data_circle_packing.append({"id": f"Finalizadas % {cluster}", "parent": f"Cluster {cluster}",
                                            "value": (row["finalizadas"] / max(row["total_rides"], 1e-6)) * 100})

    # Criar gráfico Zoomable Circle Packing com Plotly
    fig_circle_packing = px.treemap(
        pd.DataFrame(data_circle_packing),
        path=['parent', 'id'],
        values='value',
        title="Características dos Clusters - Zoomable Circle Packing",
        color='value',
        color_continuous_scale='viridis'
    )

    # Exibir o gráfico interativo
    fig_circle_packing.show()

# --------- Análise da normalidade da distância do motorista até o embarque do passageiro
# 🔹 Criar colunas de cancelamento pelo motorista e pelo passageiro
df["canceled_by_driver"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Taxista" in x else 0).astype(np.int8)
df["canceled_by_passenger"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Passageiro" in x else 0).astype(np.int8)
df["completed"] = df["status"].apply(lambda x: 1 if "Finalizada" in x else 0).astype(np.int8)

# 🔹 Cálculo da média e desvio padrão da distância do motorista até o passageiro
mu = df["driver_distance"].mean()
sigma = df["driver_distance"].std()

# Definição das faixas de análise
df_in_1std = df[(df["driver_distance"] >= mu - sigma) & (df["driver_distance"] <= mu + sigma)]
df_in_2std = df[(df["driver_distance"] >= mu - 2 * sigma) & (df["driver_distance"] <= mu + 2 * sigma)]
df_outside_2std = df[(df["driver_distance"] < mu - 2 * sigma) | (df["driver_distance"] > mu + 2 * sigma)]

total_corridas = len(df)

# Cálculo das quantidades e percentuais de cancelamentos em cada faixa
cancelamentos_por_faixa = {
    "Média ± 1 DesvPad (Motorista)": [
        df_in_1std["canceled_by_driver"].sum(),
        (df_in_1std["canceled_by_driver"].sum() / total_corridas) * 100,
        len(df_in_1std)
    ],
    "Média ± 2 DesvPad (Motorista)": [
        df_in_2std["canceled_by_driver"].sum(),
        (df_in_2std["canceled_by_driver"].sum() / total_corridas) * 100,
        len(df_in_2std)
    ],
    "Fora de 2 DesvPad (Motorista)": [
        df_outside_2std["canceled_by_driver"].sum(),
        (df_outside_2std["canceled_by_driver"].sum() / total_corridas) * 100,
        len(df_outside_2std)
    ],
    "Média ± 1 DesvPad (Passageiro)": [
        df_in_1std["canceled_by_passenger"].sum(),
        (df_in_1std["canceled_by_passenger"].sum() / total_corridas) * 100,
        len(df_in_1std)
    ],
    "Média ± 2 DesvPad (Passageiro)": [
        df_in_2std["canceled_by_passenger"].sum(),
        (df_in_2std["canceled_by_passenger"].sum() / total_corridas) * 100,
        len(df_in_2std)
    ],
    "Fora de 2 DesvPad (Passageiro)": [
        df_outside_2std["canceled_by_passenger"].sum(),
        (df_outside_2std["canceled_by_passenger"].sum() / total_corridas) * 100,
        len(df_outside_2std)
    ]
}

# Criar DataFrame para visualização tabular
df_cancelamentos = pd.DataFrame.from_dict(cancelamentos_por_faixa, orient='index',
                                          columns=['Cancelamentos', 'Percentual (%)', 'Total de Corridas'])

# Adicionar informações estatísticas à tabela
df_cancelamentos.loc['Média da Distância'] = [mu, '', '']
df_cancelamentos.loc['Desvio Padrão'] = [sigma, '', '']

# Exibir a tabela formatada corretamente
print("\nTabela de Cancelamentos por Faixa de Distância:")
print(tabulate(df_cancelamentos, headers=df_cancelamentos.columns, tablefmt='pretty'))

# Liberar memória
gc.collect()
