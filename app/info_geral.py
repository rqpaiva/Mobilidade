import os
import json
import re
import logging
import traceback
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, Blueprint, render_template, request, jsonify, current_app
from pymongo import MongoClient
from unidecode import unidecode
from collections import defaultdict

# --- Configuração Inicial ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# --- Conexão com MongoDB ---
try:
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["mobility_data"]
    logger.info("Conexão com MongoDB estabelecida")
except Exception as e:
    logger.error(f"Falha na conexão com MongoDB: {str(e)}")
    raise

# --- Mapeamentos ---
CAR_TYPE_MAPPING = {
    'siena': 'Básico', 'logan': 'Básico', 'etios': 'Básico', 'voyage': 'Básico',
    'idea': 'Básico', 'zafira': 'Básico', 'cobalt': 'Comfort', 'spin': 'Comfort',
    'prisma': 'Comfort', 'virtus': 'Comfort', 'hrv': 'Premium', 'civic': 'Premium',
    'kicks': 'Premium', 'renegade': 'Premium', 'compass': 'Premium', 'duster': 'Premium',
    'sentra': 'Premium'
}

TURNO_MAP = {
    0: '0h as 6h',
    1: '7h as 10h',
    2: '11h as 14h',
    3: '15h as 16h',
    4: '17h as 20h',
    5: '21h as 23h'
}

WEEK_DAY_MAP = {
    0: 'Segunda',
    1: 'Terça',
    2: 'Quarta',
    3: 'Quinta',
    4: 'Sexta',
    5: 'Sábado',
    6: 'Domingo',
    None: 'Desconhecido'
}

# --- Mapeamento das Zonas e seus Bairros ---
ZONE_MAP = {
    "Zona Norte": {unidecode(s.lower().strip()) for s in [
        'Abolição', 'Acari', 'Água Santa', 'Alto da Boa Vista', 'Anchieta', 'Andaraí',
        'Bancários', 'Barros Filho', 'Bento Ribeiro', 'Bonsucesso', 'Brás de Pina', 'Cachambi', 'Cacuia',
        'Campinho', 'Cascadura', 'Cavalcanti', 'Cidade Universitária', 'Cocotá', 'Coelho Neto', 'Colégio',
        'Complexo do Alemão', 'Cordovil', 'Costa Barros', 'Del Castilho', 'Encantado', 'Engenheiro Leal',
        'Engenho da Rainha', 'Engenho de Dentro', 'Engenho Novo', 'Freguesia (Ilha do Governador)',
        'Galeão', 'Guadalude', 'Grajaú', 'Higienópolis', 'Honório Gurgel', 'Inhaúma', 'Irajá', 'Jacaré',
        'Jacarezinho', 'Jardim América', 'Jardim Carioca', 'Jardim Guanabara', 'Lins de Vasconcelos',
        'Madureira', 'Manguinhos', 'Maracanã', 'Maré', 'Marechal Hermes', 'Maria da Graça', 'Méier',
        'Moneró', 'Olaria', 'Oswaldo Cruz', 'Osvaldo Cruz', 'Parada de Lucas', 'Parque Anchieta',
        'Parque Colúmbia', 'Pavuna', 'Penha', 'Penha Circular', 'Piedade', 'Pilares', 'Pitangueiras',
        'Portuguesa', 'Praça da Bandeira', 'Praia da Bandeira', 'Quintino Bocaiúva', 'Ramos', 'Riachuelo',
        'Rocha', 'Rocha Miranda', 'Sampaio', 'São Francisco Xavier', 'Tijuca', 'Todos os Santos',
        'Tomás Coelho', 'Turiaçu', 'Vaz Lobo', 'Vicente de Carvalho', 'Vila da Penha', 'Vila Kosmos',
        'Vigário Geral', 'Vista Alegre', 'Vila Isabel'
    ]},
    "Zona Sul": {unidecode(s.lower().strip()) for s in [
        'Botafogo', 'Catete', 'Copacabana', 'Cosme Velho', 'Flamengo', 'Gávea', 'Humaitá', 'Ipanema',
        'Jardim Botânico', 'Lagoa', 'Laranjeiras', 'Leblon', 'Leme', 'Rocinha', 'São Conrado', 'Urca', 'Vidigal'
    ]},
    "Zona Oeste": {unidecode(s.lower().strip()) for s in [
        'Anil', 'Bangu', 'Barra da Tijuca', 'Barra de Guaratiba', 'Barra Olímpica', 'Camorim',
        'Campo dos Afonsos', 'Campo Grande', 'Cidade de Deus', 'Cosmos', 'Curicica', 'Deodoro',
        'Freguesia (Jacarepaguá)', 'Gardênia Azul', 'Gericinó', 'Grumari', 'Guaratiba', 'Inhoaíba',
        'Itanhangá', 'Jacarepaguá', 'Jardim Sulacap', 'Joá', 'Magalhães Bastos', 'Paciência', 'Padre Miguel',
        'Pechincha', 'Pedra de Guaratiba', 'Praça Seca', 'Realengo', 'Recreio dos Bandeirantes', 'Santa Cruz',
        'Santíssimo', 'Senador Camará', 'Senador Vasconcelos', 'Sepetiba', 'Tanque', 'Taquara', 'Vargem Grande',
        'Vargem Pequena', 'Vila Kennedy', 'Vila Militar', 'Vila Valqueire'
    ]},
    "Zona Central": {unidecode(s.lower().strip()) for s in [
        'Benfica', 'Caju', 'Catumbi', 'Centro', 'Cidade Nova', 'Estácio', 'Gamboa', 'Glória', 'Lapa',
        'Mangueira', 'Paquetá', 'Rio Comprido', 'Santa Teresa', 'Santo Cristo', 'Santos Dumont',
        'São Cristóvão', 'Saúde', 'Vasco da Gama'
    ]}
}

# --- Funções Auxiliares ---
def normalize_model_name(model):
    """Normaliza nomes de veículos para classificação"""
    model = unidecode(model).lower().strip()
    model = re.sub(r'\b(tetrafuel|flex|ev|hybrid|\d\.\d)\b', '', model)
    return re.sub(r'[^\w\s]', '', model).strip()

def get_car_category(raw_model):
    """Classifica veículos em Básico/Comfort/Premium"""
    normalized = normalize_model_name(raw_model)
    for model, category in CAR_TYPE_MAPPING.items():
        if model in normalized:
            return category
    if any(kw in normalized for kw in ['suv', '4x4']): return 'Premium'
    if any(kw in normalized for kw in ['sedan', 'turbo']): return 'Comfort'
    return 'Básico'

def get_zone(suburb):
    """Determina a zona de um bairro"""
    if not suburb:
        return 'Outros'
    key = unidecode(suburb).lower().strip()
    for zone, suburbs in ZONE_MAP.items():
        if key in suburbs:
            return zone
    return 'Outros'

def count_attributes(items, field, mapping):
    """Conta ocorrências de atributos com mapeamento personalizado"""
    counts = defaultdict(int)
    for item in items:
        value = item.get(field)
        key = mapping.get(value, 'Desconhecido')
        counts[key] += 1
    return dict(counts)

def load_geojson():
    """Carrega o GeoJSON para verificação de erros"""
    try:
        possible_paths = [
            os.path.join(current_app.root_path, 'data', 'censo2022_bairros.geojson'),
            '/home/raquel/mobilidade/data/censo2022_bairros.geojson'
        ]

        geojson_path = None
        for path in possible_paths:
            if os.path.isfile(path):
                geojson_path = os.path.abspath(path)
                break

        if not geojson_path:
            raise FileNotFoundError(f"Nenhum caminho válido encontrado para o GeoJSON. Tentados: {possible_paths}")

        logger.info(f"Carregando GeoJSON de: {geojson_path}")

        with open(geojson_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                raise ValueError("Arquivo GeoJSON está vazio")

            data = json.loads(content)

        if data.get('type') != 'FeatureCollection':
            raise ValueError("Tipo GeoJSON inválido. Esperado FeatureCollection")

        if not isinstance(data.get('features'), list):
            raise ValueError("Features deve ser uma lista")

        logger.info(f"GeoJSON carregado com sucesso. {len(data['features'])} features encontradas")
        return data

    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao carregar GeoJSON: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def build_query(filters):
    """Constrói query para MongoDB baseada nos filtros"""
    query = {}

    # Filtro de data
    if filters['start_date'] or filters['end_date']:
        date_range = {}
        if filters['start_date']:
            date_range['$gte'] = datetime.strptime(filters['start_date'], "%Y-%m-%d")
        if filters['end_date']:
            date_range['$lte'] = datetime.strptime(filters['end_date'], "%Y-%m-%d")
        query['created_at'] = date_range

    # Filtro de status
    if filters['status'] == 'driver_cancel':
        query['finalizada'] = 0
        query['status'] = {'$regex': 'Taxista'}
    elif filters['status'] == 'passenger_cancel':
        query['finalizada'] = 0
        query['status'] = {'$regex': 'Passageiro'}

    return query

def analyze_neighborhoods(rides):
    """Calcula estatísticas por bairro"""
    neighborhoods = defaultdict(lambda: {
        'total': 0,
        'driver_cancel': 0,
        'passenger_cancel': 0
    })

    for ride in rides:
        neighborhood = ride.get('suburb_client', 'Desconhecido')
        neighborhoods[neighborhood]['total'] += 1
        if ride.get('finalizada', 1) == 0:
            if 'Taxista' in ride.get('status', ''):
                neighborhoods[neighborhood]['driver_cancel'] += 1
            else:
                neighborhoods[neighborhood]['passenger_cancel'] += 1

    filtered = {k: v for k, v in neighborhoods.items() if v['total'] >= 10}

    top_driver = sorted(
        [(k, v['driver_cancel'] / v['total']) for k, v in filtered.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    top_passenger = sorted(
        [(k, v['passenger_cancel'] / v['total']) for k, v in filtered.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    return {
        'all': neighborhoods,
        'top_driver': top_driver,
        'top_passenger': top_passenger
    }

def process_turno_data(rides):
    """Processa dados por turno"""
    turno_stats = defaultdict(lambda: {'completed': 0, 'driver_cancel': 0, 'passenger_cancel': 0})

    for ride in rides:
        turno = TURNO_MAP.get(ride.get('turno'), 'Desconhecido')
        if ride.get('finalizada', 1) == 1:
            turno_stats[turno]['completed'] += 1
        elif 'Taxista' in ride.get('status', ''):
            turno_stats[turno]['driver_cancel'] += 1
        else:
            turno_stats[turno]['passenger_cancel'] += 1

    return dict(turno_stats)

def process_weekday_data(rides):
    """Processa dados por dia da semana"""
    weekday_stats = defaultdict(lambda: {'completed': 0, 'driver_cancel': 0, 'passenger_cancel': 0})

    for ride in rides:
        weekday = WEEK_DAY_MAP.get(ride.get('week_day'), 'Desconhecido')
        if ride.get('finalizada', 1) == 1:
            weekday_stats[weekday]['completed'] += 1
        elif 'Taxista' in ride.get('status', ''):
            weekday_stats[weekday]['driver_cancel'] += 1
        else:
            weekday_stats[weekday]['passenger_cancel'] += 1

    return dict(weekday_stats)

def process_hourly_data(rides):
    """Processa dados por hora do dia"""
    hourly_stats = defaultdict(lambda: {'completed': 0, 'driver_cancel': 0, 'passenger_cancel': 0})

    for ride in rides:
        if 'created_at' in ride:
            hour = ride['created_at'].hour
            hour_key = f"{hour}h-{hour + 1}h"

            if ride.get('finalizada', 1) == 1:
                hourly_stats[hour_key]['completed'] += 1
            elif 'Taxista' in ride.get('status', ''):
                hourly_stats[hour_key]['driver_cancel'] += 1
            else:
                hourly_stats[hour_key]['passenger_cancel'] += 1

    sorted_hours = sorted(hourly_stats.items(), key=lambda x: int(x[0].split('h')[0]))
    return dict(sorted_hours)

def analyze_car_types(rides):
    """Analisa tipos de veículos"""
    car_types = {'Básico': 0, 'Comfort': 0, 'Premium': 0}
    for r in rides:
        if 'car_type' in r:
            car_types[get_car_category(r['car_type'])] += 1
    return car_types

# Análise de horários
def analyze_hourly(rides):
    """Calcula estatísticas por hora do dia"""
    hourly_stats = defaultdict(lambda: {
        'total': 0,
        'driver_cancel': 0,
        'passenger_cancel': 0
    })

    for ride in rides:
        if 'created_at' in ride:
            hour = ride['created_at'].hour
            hourly_stats[hour]['total'] += 1
            if ride.get('finalizada', 1) == 0:
                if 'Taxista' in ride.get('status', ''):
                    hourly_stats[hour]['driver_cancel'] += 1
                else:
                    hourly_stats[hour]['passenger_cancel'] += 1

    # Top horas para cancelamento por motorista
    top_driver = sorted(
        [(h, data['driver_cancel']/data['total'])
         for h, data in hourly_stats.items() if data['total'] > 0],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    # Top horas para cancelamento por passageiro
    top_passenger = sorted(
        [(h, data['passenger_cancel']/data['total'])
         for h, data in hourly_stats.items() if data['total'] > 0],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    return {
        'all': hourly_stats,
        'top_driver': top_driver,
        'top_passenger': top_passenger
    }

# 8) Perfil dos Motoristas (calculado por motorista único)
def count_driver_attributes(rides, field, mapping):
    """Count attributes per unique driver"""
    drivers = {}
    for ride in rides:
        if 'driver_id' in ride:
            driver_id = ride['driver_id']
            if driver_id not in drivers:
                drivers[driver_id] = ride.get(field)

    counts = defaultdict(int)
    for value in drivers.values():
        key = mapping.get(value, 'Desconhecido')
        counts[key] += 1
    return dict(counts)

# --- Blueprint e Rotas ---
info_geral_app = Blueprint('info_geral_app', __name__)

@info_geral_app.route('/', methods=['GET'])
def info_geral():
    try:
        # 1) Coleta filtros
        filters = {
            'zone': request.args.get('zone', ''),
            'neighborhood': request.args.get('neighborhood', ''),
            'status': request.args.get('status', ''),
            'start_date': request.args.get('start_date', ''),
            'end_date': request.args.get('end_date', ''),
            'start_time': request.args.get('start_time', ''),
            'end_time': request.args.get('end_time', '')
        }

        # 2) Query e projection
        query = build_query(filters)
        projection = {
            'finalizada': 1, 'status': 1, 'suburb_client': 1, 'turno': 1,
            'week_day': 1, 'driver_distance': 1, 'route_distance': 1,
            'driver_id': 1, 'race': 1, 'gender': 1, 'age_Range': 1,
            'fitness': 1, 'car_type': 1, 'rating_score': 1, 'created_at': 1,
            'income_range': 1
        }
        rides = list(db.rides_original.find(query, projection))

        # 3) Filtros adicionais de zona/bairro
        if filters['zone']:
            rides = [r for r in rides if get_zone(r.get('suburb_client', '')) == filters['zone']]
        if filters['neighborhood']:
            target = unidecode(filters['neighborhood'].lower().strip())
            rides = [r for r in rides if unidecode(r.get('suburb_client', '').lower().strip()) == target]

        # 4) Estatísticas Gerais
        stats = {
            'total': len(rides),
            'unique_drivers': len({r['driver_id'] for r in rides if 'driver_id' in r}),
            'driver': sum(1 for r in rides if r.get('finalizada', 1) == 0 and 'Taxista' in r.get('status', '')),
            'passenger': sum(1 for r in rides if r.get('finalizada', 1) == 0 and 'Passageiro' in r.get('status', ''))
        }
        stats.update({
            'driver_pct': (stats['driver']/stats['total']*100) if stats['total'] else 0,
            'passenger_pct': (stats['passenger']/stats['total']*100) if stats['total'] else 0
        })

        # 5) Estatísticas por Bairro e Hora
        neighborhood_stats = analyze_neighborhoods(rides)
        stats.update({
            'top_driver_neighborhood': neighborhood_stats['top_driver'][0][0] if neighborhood_stats['top_driver'] else 'N/A',
            'top_passenger_neighborhood': neighborhood_stats['top_passenger'][0][0] if neighborhood_stats['top_passenger'] else 'N/A',
            'neighborhood_stats': neighborhood_stats
        })

        hourly_stats = analyze_hourly(rides)
        stats.update({
            'top_driver_hour': f"{hourly_stats['top_driver'][0][0]}h" if hourly_stats['top_driver'] else 'N/A',
            'top_passenger_hour': f"{hourly_stats['top_passenger'][0][0]}h" if hourly_stats['top_passenger'] else 'N/A',
            'hourly_stats': hourly_stats
        })

        # 6) Dados Temporais
        temporal = {
            'turno': process_turno_data(rides),
            'week_day': process_weekday_data(rides),
            'hourly': process_hourly_data(rides)
        }

        # 7) Dados Espaciais
        dist_sum = {'d':0.0,'r':0.0,'c':0}
        for r in rides:
            dd = float(r.get('driver_distance') or 0)
            rd = float(r.get('route_distance') or 0)
            dist_sum['d'] += dd
            dist_sum['r'] += rd
            dist_sum['c'] += 1
        spatial = {
            'avg_driver_to_origin': dist_sum['d']/dist_sum['c'] if dist_sum['c'] else 0,
            'avg_route': dist_sum['r']/dist_sum['c'] if dist_sum['c'] else 0
        }

        #8) Perfil dos motoristas
        profile_drivers = {
            'race': count_driver_attributes(rides, 'race', {-1: 'Asiático', 0: 'Branco', 1: 'Pardo', 2: 'Negro'}),
            'gender': count_driver_attributes(rides, 'gender', {1: 'Masculino', 2: 'Feminino'}),
            'age': count_driver_attributes(rides, 'age_Range', {0: 'Jovem', 1: 'Adulto', 2: 'Sênior'}),
            'fitness': count_driver_attributes(rides, 'fitness', {-1: 'Magro', 0: 'Normal', 1: 'Acima do peso'}),
            'car_types': analyze_car_types(rides)
        }

        # 9) Perfil Socioeconômico dos Passageiros
        try:
            renda_data = {unidecode(r['Bairros']).lower().strip(): r for r in db.censo_renda.find({}) if 'Bairros' in r}
        except Exception as e:
            logger.error(f"Erro ao carregar dados de renda: {str(e)}")
            renda_data = {}

        renda_sum = {'mean_excl': 0, 'median_excl': 0, 'mean_incl': 0, 'median_incl': 0, 'count': 0}
        for r in rides:
            key = unidecode(r.get('suburb_client', '')).lower().strip()
            entry = renda_data.get(key)
            if entry:
                try:
                    renda_sum['mean_excl'] += float(
                        entry.get('Rendimento nominal médio (R$ - exclui sem rendimento)', 0))
                    renda_sum['median_excl'] += float(
                        entry.get('Rendimento nominal mediano (R$ - exclui sem rendimento)', 0))
                    renda_sum['mean_incl'] += float(
                        entry.get('Rendimento nominal médio (R$ - inclui sem rendimento)', 0))
                    renda_sum['median_incl'] += float(
                        entry.get('Rendimento nominal mediano (R$ - inclui sem rendimento)', 0))
                    renda_sum['count'] += 1
                except (ValueError, TypeError):
                    continue

        profile_passengers = {}
        if renda_sum['count']:
            cnt = renda_sum['count']
            profile_passengers = {
                'mean_excl': renda_sum['mean_excl'] / cnt,
                'median_excl': renda_sum['median_excl'] / cnt,
                'mean_incl': renda_sum['mean_incl'] / cnt,
                'median_incl': renda_sum['median_incl'] / cnt
            }

        # 10) Render
        return render_template(
            'info_geral.html',
            zones=sorted(ZONE_MAP.keys()),
            filters=filters,
            stats=stats,
            temporal=temporal,
            spatial=spatial,
            profile_drivers=profile_drivers,
            profile_passengers=profile_passengers,
            bairros_geo=load_geojson(),
            zone_map_js={z: sorted(list(s)) for z,s in ZONE_MAP.items()},
            turno_map=TURNO_MAP,
            week_day_map=WEEK_DAY_MAP
        )

    except Exception as e:
        logger.error(f"Erro no /info_geral: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', error="Erro no processamento"), 500

@info_geral_app.route('/test')
def test_route():
    try:
        mongo_test = db.command('ping')
        geojson = load_geojson()
        features_count = len(geojson.get('features', []))
        if features_count == 0:
            raise ValueError("GeoJSON sem features")
        return jsonify({"status":"OK","mongo":mongo_test,"geojson_features":features_count})
    except Exception as e:
        logger.exception("Falha no /test:")
        return jsonify({
            "status":"ERROR",
            "error":str(e),
            "traceback": traceback.format_exc() if current_app.debug else None
        }), 500

# Execution
if __name__ == '__main__':
    app = Flask(__name__)
    app.config['DEBUG'] = True
    app.register_blueprint(info_geral_app, url_prefix='/info_geral')
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))