import os
import pandas as pd
import numpy as np
import pymongo
import folium
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.ensemble import IsolationForest
from folium.plugins import MarkerCluster
import plotly.graph_objects as go
import tempfile
import plotly.express as px

# 🔹 Carregar variáveis de ambiente
load_dotenv()

# 🔹 Conectar ao MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = pymongo.MongoClient(MONGO_URI)
db = client["mobility_data"]
collection = db["rides_original"]

# 🔹 Buscar os dados da coleção
cursor = collection.find({}, {
    "_id": 0,
    "status": 1,
    "driver_distance": 1,
    "route_distance": 1,
    "origin_lat": 1,
    "origin_lng": 1,
    "created_at": 1,
    "turno": 1
})

# 🔹 Converter para DataFrame
df = pd.DataFrame(list(cursor))

# 🔹 Processar dados
df.dropna(subset=["driver_distance", "route_distance", "origin_lat", "origin_lng"], inplace=True)
df["driver_distance"] = df["driver_distance"].astype(np.float32)
df["route_distance"] = df["route_distance"].astype(np.float32)

# 🔹 Criar colunas de cancelamento
df["canceled_by_driver"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Taxista" in x else 0)
df["canceled_by_passenger"] = df["status"].apply(lambda x: 1 if "Cancelada pelo Passageiro" in x else 0)
df["completed"] = df["status"].apply(lambda x: 1 if "Finalizada" in x else 0)

# 🔹 Padronizar dados para KMeans
features = ["driver_distance", "route_distance", "canceled_by_driver", "canceled_by_passenger", "completed"]
scaler = StandardScaler()
df_scaled = scaler.fit_transform(df[features])

# 🔹 Determinar o número ideal de clusters
wcss = []
silhouette_scores = []
k_values = range(2, 10)

for k in k_values:
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(df_scaled)
    wcss.append(kmeans.inertia_)
    silhouette_scores.append(silhouette_score(df_scaled, labels))

# 🔹 Escolher melhor número de clusters
optimal_k = k_values[np.argmax(silhouette_scores)]
df["cluster"] = KMeans(n_clusters=optimal_k, random_state=42, n_init=10).fit_predict(df_scaled)

# 🔹 Aplicar Isolation Forest para detectar outliers
iso_forest = IsolationForest(contamination=0.05, random_state=42)
df["outlier"] = iso_forest.fit_predict(df_scaled)


# 🔹 Criar mapa interativo com agrupamento por cluster
def generate_folium_map(df):
    map_center = [-22.9068, -43.1729]  # Rio de Janeiro
    folium_map = folium.Map(location=map_center, zoom_start=11)

    # Criando grupos separados para cada cluster e para outliers
    cluster_groups = {i: MarkerCluster(name=f"Cluster {i}") for i in range(optimal_k)}
    outlier_group = MarkerCluster(name="Outliers")

    # Definir cores para os clusters
    cluster_colors = ["blue", "green", "purple", "orange", "darkred", "pink", "cadetblue"]

    for _, row in df.iterrows():
        if row["outlier"] == -1:
            color = "red"
            popup_text = f"🚨 OUTLIER 🚨<br>Distância do Motorista: {row['driver_distance']}m"
            folium.CircleMarker(
                location=[row["origin_lat"], row["origin_lng"]],
                radius=4,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.6,
                popup=popup_text
            ).add_to(outlier_group)
        else:
            color = cluster_colors[row["cluster"] % len(cluster_colors)]
            popup_text = f"Cluster {row['cluster']}<br>Distância do Motorista: {row['driver_distance']}m"
            folium.CircleMarker(
                location=[row["origin_lat"], row["origin_lng"]],
                radius=4,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.6,
                popup=popup_text
            ).add_to(cluster_groups[row["cluster"]])

    # Adicionar os grupos ao mapa
    for group in cluster_groups.values():
        folium_map.add_child(group)
    folium_map.add_child(outlier_group)

    # Adicionar controle de camadas
    folium.LayerControl().add_to(folium_map)

    # Salvar o mapa como HTML temporário
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    folium_map.save(temp_file.name)

    with open(temp_file.name, "r", encoding="utf-8") as f:
        return f.read()


# 🔹 Criar estrutura para Circle Packing com Status das Corridas
def generate_circle_packing():
    cluster_summary = df.groupby("cluster")[["driver_distance", "route_distance",
                                             "canceled_by_driver", "canceled_by_passenger",
                                             "completed"]].mean()
    cluster_summary["total_rides"] = df.groupby("cluster").size()

    # Contar o número de ocorrências de cada status por cluster
    status_counts = df.groupby(["cluster", "status"]).size().unstack(fill_value=0)

    # Criar estrutura de dados para Circle Packing
    data = [{"id": "Clusters", "parent": "", "value": 0}]

    for cluster, row in cluster_summary.iterrows():
        data.append({"id": f"Cluster {cluster}", "parent": "Clusters", "value": row["total_rides"]})
        data.append({"id": f"Distância {cluster}", "parent": f"Cluster {cluster}", "value": row["driver_distance"]})
        data.append({"id": f"Rota {cluster}", "parent": f"Cluster {cluster}", "value": row["route_distance"]})
        data.append({"id": f"Cancelado Motorista {cluster}", "parent": f"Cluster {cluster}",
                     "value": row["canceled_by_driver"]})
        data.append({"id": f"Cancelado Passageiro {cluster}", "parent": f"Cluster {cluster}",
                     "value": row["canceled_by_passenger"]})
        data.append({"id": f"Finalizadas {cluster}", "parent": f"Cluster {cluster}", "value": row["completed"]})

        # Adicionar os status das corridas dentro de cada cluster
        if cluster in status_counts.index:
            for status, count in status_counts.loc[cluster].items():
                data.append({"id": f"{status} {cluster}", "parent": f"Cluster {cluster}", "value": count})

    return px.treemap(pd.DataFrame(data), path=["parent", "id"], values="value",
                      title="Perfil dos Clusters com Status das Corridas")

# 🔹 Criar a aplicação Dash
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Análise do comportamento das corridas em relação a distância do motorista até passageiro"),

    # 🔸 Boxplot das corridas por distância do motorista
    dcc.Graph(id="boxplot-distancia"),

    # 🔸 Gráfico combinado de WCSS e Silhouette Score com dois eixos Y
    dcc.Graph(id="combined-clustering-chart"),

    # 🔸 Perfil dos Clusters
    dcc.Graph(id="circle-packing-clusters"),

    # 🔸 Mapa com Marker Clustering por Cluster
    html.Iframe(id="mapa-clusters", width="100%", height="600")
])


# 🔹 Callback para atualizar os gráficos e o mapa
@app.callback(
    [Output("boxplot-distancia", "figure"),
     Output("combined-clustering-chart", "figure"),
     Output("circle-packing-clusters", "figure"),
     Output("mapa-clusters", "srcDoc")],
    Input("mapa-clusters", "id")
)
def update_visuals(_):
    mapa_html = generate_folium_map(df)

    # 🔸 Gráfico combinado de WCSS e Silhouette Score com eixos Y separados
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=list(k_values), y=wcss, mode="lines+markers",
                             name="WCSS", yaxis="y1"))

    fig.add_trace(go.Scatter(x=list(k_values), y=silhouette_scores, mode="lines+markers",
                             name="Silhouette Score", yaxis="y2"))

    fig.add_vline(x=optimal_k, line_dash="dash", line_color="red",
                  annotation_text=f"Melhor K = {optimal_k}")

    fig.update_layout(
        title="WCSS e Silhouette Score para Diferentes Números de Clusters",
        xaxis_title="Número de Clusters",
        yaxis=dict(title="WCSS", side="left"),
        yaxis2=dict(title="Silhouette Score", overlaying="y", side="right"),
        legend_title="Métrica"
    )

    # 🔸 Boxplot da distância do motorista
    boxplot_fig = go.Figure()
    for status in df["status"].unique():
        subset = df[df["status"] == status]
        boxplot_fig.add_trace(go.Box(y=subset["driver_distance"], name=status))

    boxplot_fig.update_layout(title="Distribuição da Distância do Motorista até o Passageiro por Status da Corrida",
                              yaxis_title="Distância (metros)")

    return boxplot_fig, fig, generate_circle_packing(), mapa_html


# 🔹 Rodar a aplicação
if __name__ == "__main__":
    app.run_server(debug=True)

