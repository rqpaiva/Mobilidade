from app import app  # Flask app principal
import pandas as pd
from flask import render_template, request, session, redirect
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

# Configuração para arquivos permitidos
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rota principal do Flask
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'Nenhum arquivo foi enviado.'
        file = request.files['file']
        if file.filename == '':
            return 'Nenhum arquivo selecionado.'
        if file and allowed_file(file.filename):
            try:
                data = pd.read_csv(file)

                # Verificando se as colunas necessárias existem
                if 'origin_location' not in data.columns or 'Address_client_dict' not in data.columns:
                    return 'As colunas "origin_location" ou "Address_client_dict" não foram encontradas no arquivo.'

                # Extraindo as coordenadas da coluna 'origin_location' (suposto formato: "latitude, longitude")
                data[['Latitude', 'Longitude']] = data['origin_location'].apply(lambda x: pd.Series(x.split(',')))
                data['Latitude'] = data['Latitude'].astype(float)
                data['Longitude'] = data['Longitude'].astype(float)

                # Extraindo o bairro da coluna 'Address_client_dict' e atribuindo à coluna 'suburb'
                data['suburb'] = data['Address_client_dict'].apply(lambda x: eval(x).get('suburb', 'Desconhecido'))

                # Salvando os dados na sessão
                session['data'] = data.to_json(orient='split')  
                return redirect('/dashboard/')
            except Exception as e:
                return f"Erro ao processar o arquivo: {e}"
    return render_template('index.html')

# Inicialização do Dash
dash_app = Dash(
    __name__,
    server=app,
    url_base_pathname='/dashboard/',
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

# Layout do Dash
dash_app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            dcc.Tabs(id='tabs', children=[
                dcc.Tab(label='Visualização 1', children=[
                    html.Div([
                        html.H3("Filtros"),
                        dcc.Dropdown(
                            id='status-dropdown',
                            options=[
                                {'label': 'Corridas Canceladas', 'value': 'cancelada'},
                                {'label': 'Corridas Finalizadas', 'value': 'finalizada'},
                                {'label': 'Todas', 'value': 'todas'}
                            ],
                            value='todas',
                            multi=False,
                            style={'width': '100%'}
                        ),
                        html.H3("Selecione o Bairro"),
                        dcc.Dropdown(
                            id='suburb-dropdown',
                            options=[],  # Inicialmente sem opções, será preenchido após carregar os dados
                            value=None,
                            multi=False,
                            style={'width': '100%'}
                        ),
                    ], style={'marginBottom': '20px'}),  # Adicionando margem para separar os filtros

                    # Colocando o mapa e o gráfico lado a lado
                    dbc.Row([
                        dbc.Col([
                            dcc.Graph(id='map-graph'),
                        ], md=6),  # 50% da largura

                        dbc.Col([
                            dcc.Graph(id='candle-graph'),  # Gráfico de barras
                        ], md=6),  # 50% da largura
                    ]),

                    html.Div(id='data-preview')  # Exibe a tabela de dados ou outros resultados
                ]),

                dcc.Tab(label='Visualização 2', children=[
                    # Mapa vazio na Visualização 2
                    dcc.Graph(id='map-graph-2', figure={
                        'data': [],
                        'layout': go.Layout(
                            geo=dict(
                                lakecolor='rgb(255, 255, 255)',
                                projection=dict(type='mercator')
                            )
                        )
                    })
                ]),
            ])
        ], md=12),
    ])
])

# Callback para o gráfico, visualização dos dados e preenchimento do filtro de bairros
@dash_app.callback(
    [Output('map-graph', 'figure'), 
     Output('candle-graph', 'figure'),
     Output('data-preview', 'children'),
     Output('suburb-dropdown', 'options')],
    [Input('status-dropdown', 'value'),
     Input('suburb-dropdown', 'value'),
     Input('tabs', 'active_tab')]  # Verifica qual aba está ativa
)
def display_data(selected_status, selected_suburb, active_tab):
    data_json = session.get('data')

    if not data_json:
        return px.scatter_mapbox(), go.Figure(), html.P("Nenhum dado disponível. Faça o upload de um arquivo na página inicial."), []

    data = pd.read_json(data_json, orient='split')

    # Verificar se o 'Latitude' e 'Longitude' estão presentes
    if 'Latitude' not in data.columns or 'Longitude' not in data.columns:
        return px.scatter_mapbox(), go.Figure(), html.P("As colunas 'Latitude' ou 'Longitude' não foram encontradas."), []

    # Filtro baseado no status
    if selected_status == "cancelada":
        data_filtered = data[data['status'].str.contains('cancelada', case=False)]
    elif selected_status == "finalizada":
        data_filtered = data[data['status'].str.contains('finalizada', case=False)]
    else:
        data_filtered = data

    # Filtro baseado no bairro
    if selected_suburb:
        data_filtered = data_filtered[data_filtered['suburb'] == selected_suburb]

    # Atualizando o Dropdown de bairros com base nos dados filtrados
    suburb_options = [{'label': suburb, 'value': suburb} for suburb in data_filtered['suburb'].unique()]
    suburb_options = sorted(suburb_options, key=lambda x: x['label'])  # Ordena os bairros

    # Aplicar cores conforme o status
    data_filtered['color'] = data_filtered['status'].apply(
        lambda x: 'rgb(255, 0, 0)' if 'cancelada' in x.lower() 
        else 'rgb(0, 128, 0)' if 'finalizada' in x.lower() 
        else 'rgb(128, 128, 128)'  # Cinza para outras
    )

    # Criando o gráfico de mapa com bairros e coordenadas
    fig_map = px.scatter_mapbox(
        data_filtered, 
        lat='Latitude', 
        lon='Longitude', 
        color='color', 
        hover_name='suburb',
        mapbox_style='carto-positron', 
        zoom=10,
        size_max=40
    )

    fig_map.update_traces(
        customdata=data_filtered[['status']].values,
        hovertemplate="<b>Status: %{customdata[0]}</b><br><i>Bairro: %{hovertext}</i>"
    )

    # Gráfico de barras
    fig_candle = go.Figure(data=[go.Bar(
        x=data_filtered['suburb'],
        y=data_filtered.groupby('suburb').size(),
        marker_color=data_filtered['color']
    )])

    fig_candle.update_layout(
        title='Número de Corridas por Bairro',
        xaxis_title='Bairro',
        yaxis_title='Número de Corridas',
        xaxis_tickangle=-45,
        barmode='group',
        template="plotly_dark"
    )

    # Tabela de dados
    table_data = html.Table([
        html.Tr([html.Th("Bairro"), html.Th("Status")]),
        *[
            html.Tr([
                html.Td(data_filtered.iloc[i]['suburb']),
                html.Td(data_filtered.iloc[i]['status'])
            ])
            for i in range(len(data_filtered))
        ]
    ], style={'border': '1px solid black', 'borderCollapse': 'collapse'})

    return fig_map, fig_candle, table_data, suburb_options
