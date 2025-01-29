import os
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import pandas as pd
import numpy as np
from transformers import pipeline
from dash import Dash, dcc, html
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Obter a string de conexão do MongoDB
MONGO_URI = os.getenv("MONGO_URI")

# Conectar ao MongoDB
logger.info("Conectando ao MongoDB...")
client = MongoClient(MONGO_URI)
db = client['mobility_data']
collection = db['rides_original']

# Configurar o Dash
app = Dash(__name__)

# Carregar dados em um DataFrame
print("Conectando ao MongoDB...")
data = pd.DataFrame(list(collection.find()))

# Filtrar corridas canceladas e com comentários válidos
cancelled_rides = data[(data['finalizada'] == 0) & data['rating_comment'].notnull()]

# Configurar o pipeline de análise de sentimento com modelo acessível
def setup_sentiment_pipeline():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

sentiment_analyzer = setup_sentiment_pipeline()

# Função de análise de sentimento
def analyze_sentiment(comment):
    if isinstance(comment, str):
        result = sentiment_analyzer(comment)
        return result[0]['label']  # Retorna o rótulo do sentimento (e.g., POSITIVE, NEGATIVE, NEUTRAL)
    return 'neutral'

# Aplicar análise de sentimento nos comentários
cancelled_rides['sentiment'] = cancelled_rides['rating_comment'].apply(analyze_sentiment)

# Agrupar dados por motorista para calcular estatísticas
driver_stats = data.groupby('driver_id').agg({
    'rating_score': 'mean',
    'finalizada': ['sum', 'count'],
    'rating_comment': 'count'
}).reset_index()
driver_stats.columns = ['driver_id', 'average_rating', 'rides_completed', 'total_rides', 'comments_count']

# Calcular taxas de cancelamento
cancelled_counts = data[data['finalizada'] == 0].groupby('driver_id').size().reset_index(name='cancelled_rides')
driver_stats = driver_stats.merge(cancelled_counts, on='driver_id', how='left').fillna(0)
driver_stats['cancel_rate'] = driver_stats['cancelled_rides'] / driver_stats['total_rides']

# Análise de sentimento por motorista
sentiment_summary = cancelled_rides.groupby(['driver_id', 'sentiment']).size().unstack(fill_value=0).reset_index()

# Garantir que todas as colunas de sentimento estejam presentes
for col in ['positive', 'neutral', 'negative']:
    if col not in sentiment_summary:
        sentiment_summary[col] = 0

sentiment_summary.columns = ['driver_id', 'positive_comments', 'neutral_comments', 'negative_comments']

# Mesclar análises
driver_analysis = driver_stats.merge(sentiment_summary, on='driver_id', how='left').fillna(0)
driver_analysis['total_comments'] = driver_analysis['negative_comments'] + driver_analysis['neutral_comments'] + driver_analysis['positive_comments']

# Correlação entre sentimentos e taxas de cancelamento
correlation_matrix = driver_analysis[['average_rating', 'rides_completed', 'cancel_rate', 'negative_comments', 'positive_comments']].corr()

# Identificar bairros mais cancelados por motorista
neighborhood_cancel = data[data['finalizada'] == 0].groupby(['driver_id', 'suburb_client']).size().reset_index(name='cancel_count')
most_cancelled_neighborhoods = neighborhood_cancel.loc[neighborhood_cancel.groupby('driver_id')['cancel_count'].idxmax()]

# Layout do Dash
app.layout = html.Div([
    html.H1("Dashboard de Análise de Cancelamentos", style={'textAlign': 'center'}),

    dcc.Graph(
        id='sentiment-distribution',
        figure={
            'data': [
                go.Bar(
                    x=cancelled_rides['sentiment'].value_counts().index,
                    y=cancelled_rides['sentiment'].value_counts().values,
                    name="Sentimentos"
                )
            ],
            'layout': {
                'title': 'Distribuição de Sentimentos nos Comentários'
            }
        }
    ),

    dcc.Graph(
        id='cancel-rate',
        figure={
            'data': [
                go.Scatter(
                    x=driver_analysis['driver_id'],
                    y=driver_analysis['cancel_rate'],
                    mode='markers',
                    name='Taxa de Cancelamento'
                )
            ],
            'layout': {
                'title': 'Taxa de Cancelamento por Motorista'
            }
        }
    ),

    dcc.Graph(
        id='correlation-matrix',
        figure={
            'data': [
                go.Heatmap(
                    z=correlation_matrix.values,
                    x=correlation_matrix.columns,
                    y=correlation_matrix.index,
                    colorscale='Viridis'
                )
            ],
            'layout': {
                'title': 'Correlação de Métricas'
            }
        }
    ),

    dcc.Graph(
        id='neighborhood-cancel',
        figure={
            'data': [
                go.Bar(
                    x=most_cancelled_neighborhoods['suburb_client'],
                    y=most_cancelled_neighborhoods['cancel_count'],
                    name="Cancelamentos por Bairro"
                )
            ],
            'layout': {
                'title': 'Bairros com Mais Cancelamentos'
            }
        }
    )
])

# Rodar o servidor local
if __name__ == '__main__':
    app.run_server(debug=True, port=8050)