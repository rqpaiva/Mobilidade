import os
import re
import json
import logging
import traceback
from collections import defaultdict
from textblob import TextBlob
from pymongo import MongoClient
from unidecode import unidecode
from dotenv import load_dotenv
from flask import Blueprint, render_template, current_app, request, jsonify
from shapely.geometry import shape, Point
from datetime import datetime
import nltk
from nltk import download as nltk_download
from transformers import pipeline
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from collections import Counter
import pandas as pd
from copy import deepcopy

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente
load_dotenv()

# Conexão com MongoDB
try:
    client = MongoClient(os.getenv("MONGO_URI"))
    client.server_info()  # Força uma conexão para testar
    db = client["mobility_data"]
    logger.info("Conexão com MongoDB estabelecida")
except Exception as e:
    logger.error(f"Falha na conexão com MongoDB: {str(e)}", exc_info=True)
    raise

# Configuração dos recursos do NLTK
NLTK_RESOURCES = [
    'punkt',
    'averaged_perceptron_tagger',
    'movie_reviews',
    'wordnet',
    'stopwords'
]

# Mapeamento de variáveis
GENDER_MAP = {2: 'Feminino', 1: 'Masculino'}
RACE_MAP = {-1: 'Asiático', 0: 'Branco', 1: 'Pardo', 2: 'Negro'}
AGE_RANGE_MAP = {0: 'Jovem (abaixo de 30)', 1: 'Adulto (30 a 60)', 2: 'Sênior (acima de 60)'}
FITNESS_MAP = {-1: 'Magro', 0: 'Normal', 1: 'Acima do peso'}

# Status de corrida
STATUS_FINALIZADA = "Finalizada"
STATUS_CANCELADA_MOTORISTA = "Cancelada pelo Taxista"
STATUS_CANCELADA_PASSAGEIRO = "Cancelada pelo Passageiro"


def setup_nltk():
    """Configura os recursos do NLTK com tratamento de erros"""
    try:
        for resource in NLTK_RESOURCES:
            try:
                nltk.data.find(f'tokenizers/{resource}')
            except LookupError:
                nltk_download(resource, quiet=True)
    except Exception as e:
        logger.error(f"Erro ao configurar NLTK: {str(e)}")

setup_nltk()

# Configuração do Blueprint
analise_comentarios_app = Blueprint('analise_comentarios_app', __name__)

# Carregar modelo BERT para análise de sentimentos em português
try:
    sentiment_analyzer = pipeline("text-classification", model="neuralmind/bert-base-portuguese-cased",
                                  tokenizer="neuralmind/bert-base-portuguese-cased")
except Exception as e:
    sentiment_analyzer = None
    logger.warning(f"Modelo BERT não pôde ser carregado, usando TextBlob como fallback. Erro: {str(e)}")

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



def analyze_sentiment(text, score=None):
    """Analisa o sentimento usando BERT ou fallback para TextBlob"""
    if not text or str(text).strip().lower() in ['', 'nan', 'comentarios opcional']:
        return {"polarity": 0, "label": "Neutro"}

    try:
        if sentiment_analyzer:
            result = sentiment_analyzer(text[:512])
            return {
                "polarity": result[0]['score'] if result[0]['label'] == 'POSITIVE' else -result[0]['score'],
                "label": result[0]['label']
            }
        else:
            # Fallback usando score da corrida se disponível
            if score is not None:
                if score >= 4:
                    return {"polarity": 0.8, "label": "Positivo"}
                elif score <= 2:
                    return {"polarity": -0.8, "label": "Negativo"}
                else:
                    return {"polarity": 0.2, "label": "Neutro"}
            blob = TextBlob(str(text))
            polarity = blob.sentiment.polarity
            label = "Positivo" if polarity > 0.1 else "Negativo" if polarity < -0.1 else "Neutro"
            return {"polarity": polarity, "label": label}
    except Exception as e:
        logger.error(f"Erro na análise de sentimento: {str(e)}")
        return {"polarity": 0, "label": "Neutro"}


def detect_problems(text):
    """Detecta tipos de problemas no texto com categorização mais precisa"""
    if not text:
        return []

    text_lower = unidecode(str(text).lower())
    problem_types = set()

    # Padrões melhorados para cada tipo de problema
    patterns = {
        "racial": {
            'keywords': ['racismo', 'cor', 'raça', 'negro', 'branco', 'preto', 'pardo', 'asiático', 'indio', 'mulato',
                         'crioulo'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'ofensa']
        },
        "gênero": {
            'keywords': ['gênero', 'mulher', 'homem', 'feminino', 'masculino', 'moça', 'senhora', 'garota', 'menina'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'assédio', 'assedio']
        },
        "etarismo": {
            'keywords': ['idade', 'velho', 'jovem', 'idoso', 'velha', 'jovenzinho', 'senhor', 'senhora', 'avó', 'avo',
                         'idosos', 'terceira idade'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'maltrat', 'desrespeito']
        },
        "físico": {
            'keywords': ['peso', 'gordo', 'magro', 'forma física', 'gordinho', 'magrelo', 'barrigudo', 'obeso',
                         'deficiente'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'piada']
        },
        "homofobia": {
            'keywords': ['homossexual', 'gay', 'lésbica', 'lgbt', 'bicha', 'sapatão', 'viado', 'traveco', 'sapata',
                         'boiola', 'viadinho'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'homofob']
        },
        "regional": {
            'keywords': ['bairro', 'favela', 'comunidade', 'zona', 'periferia', 'subúrbio', 'morro', 'asfalto'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'perigoso', 'marginal']
        },
        "tarifa": {
            'keywords': ['preço', 'caro', 'valor', 'tarifa', 'dinheiro', 'conta', 'lucro', 'roubo', 'golpe',
                         'desonesto', 'cobrança', 'cobranca', 'cobrou'],
            'context': ['abusivo', 'injusto', 'errado', 'fraude', 'mentira', 'enganou', 'explor', 'alto']
        },
        "político-religioso": {
            'keywords': ['religião', 'política', 'partido', 'crente', 'ateu', 'bolsonaro', 'lula', 'deus', 'crente',
                         'evangélico', 'católico'],
            'context': ['discrimina', 'ofende', 'xingou', 'preconceito', 'briga', 'discussão']
        },
        "veículo": {
            'keywords': ['carro', 'veículo', 'cheiro', 'odor', 'cigarro', 'sujo', 'velho', 'quebrado', 'mal cuidado',
                         'banco', 'assento', 'porta', 'lataria'],
            'context': ['condição', 'estado', 'limpeza', 'conservação', 'higiene', 'problema', 'quebrado', 'sujo',
                        'fedido'],
            'exclude': ['entrar no carro', 'sair do carro', 'dentro do carro']  # Contextos neutros
        }
    }

    # Verificação de problemas baseada em contexto
    for ptype, config in patterns.items():
        # Verifica se há palavras-chave
        has_keywords = any(re.search(r'\b' + re.escape(kw) + r'\b', text_lower) for kw in config['keywords'])

        # Verifica contexto relevante
        has_context = any(re.search(r'\b' + re.escape(ctx) + r'\b', text_lower) for ctx in config.get('context', []))

        # Verifica contextos a excluir (especialmente para veículo)
        exclude_context = False
        if 'exclude' in config:
            exclude_context = any(phrase in text_lower for phrase in config['exclude'])

        # Lógica de classificação
        if has_keywords and not exclude_context:
            # Para alguns tipos, a palavra-chave sozinha já é suficiente
            if ptype in ["homofobia", "racial", "gênero"]:
                problem_types.add(ptype)
            # Para outros, requeremos contexto adicional
            elif has_context or ptype in ["tarifa", "etarismo", "veículo"]:
                problem_types.add(ptype)

    # Casos especiais - quando certas frases indicam claramente um problema
    special_cases = {
        "tarifa": [
            r'come[cç]ou a corrida antes',
            r'iniciou a corrida antes',
            r'cobrou a mais',
            r'valor errado',
            r'golpe|fraude|engano',
            r'desonest[ao]\s+(na|com)\s+(corrida|tarifa)'
        ],
        "etarismo": [
            r'av[oó]|idos[ao]',
            r'terceira idade',
            r'pessoa mais velha',
            r'idos[ao]'
        ],
        "veículo": [
            r've[ií]culo\s+(sujo|quebrado|mal cuidado)',
            r'carro\s+(fedido|com mau cheiro|sujo)',
            r'banco\s+(rasgado|quebrado|sujo)',
            r'porta\s+(não fecha|quebrada)'
        ]
    }

    for ptype, cases in special_cases.items():
        if any(re.search(pattern, text_lower) for pattern in cases):
            problem_types.add(ptype)

    return list(problem_types)


def get_bairros_stats(filters=None):
    """Obtém estatísticas de ocorrências por bairro com tratamento robusto"""
    try:
        collection = db["rides_original"]
        geojson_data = load_geojson()

        # Query base para todas as corridas
        query_total = {
            "$or": [{"finalizada": 1}, {"canceled_by_driver": 1}, {"canceled_by_client": 1}],
            "suburb_client": {"$exists": True, "$ne": None, "$ne": ""}
        }

        # Aplicar filtros se existirem
        if filters:
            if filters.get('date_range') and len(filters['date_range']) == 2:
                start_date = datetime.strptime(filters['date_range'][0], '%d/%m/%Y')
                end_date = datetime.strptime(filters['date_range'][1], '%d/%m/%Y')
                query_total["date"] = {"$gte": start_date, "$lte": end_date}

            if filters.get('suburb'):
                query_total["suburb_client"] = filters['suburb']

        # Pipeline para estatísticas básicas
        pipeline_stats = [
            {"$match": query_total},
            {"$group": {
                "_id": "$suburb_client",
                "total_rides": {"$sum": 1},
                "canceled_by_driver": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_MOTORISTA]}, 1, 0]
                    }
                },
                "canceled_by_client": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_PASSAGEIRO]}, 1, 0]
                    }
                },
                "finalized_rides": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_FINALIZADA]}, 1, 0]
                    }
                }
            }}
        ]

        # Pipeline para comentários problemáticos
        pipeline_problems = [
            {"$match": {
                **query_total,
                "finalizada": 1,
                "rating_comment": {
                    "$exists": True,
                    "$nin": [None, "", "comentarios opcional"]
                },
                "problems": {"$exists": True, "$ne": []}
            }},
            {"$group": {
                "_id": "$suburb_client",
                "problematic_rides": {"$sum": 1}
            }}
        ]

        # Pipeline para estatísticas de avaliação
        pipeline_ratings = [
            {"$match": {
                **query_total,
                "finalizada": 1,
                "rating_score": {"$exists": True}
            }},
            {"$group": {
                "_id": "$suburb_client",
                "total_rated": {"$sum": 1},
                "avg_score": {"$avg": "$rating_score"},
                "positive_ratings": {
                    "$sum": {
                        "$cond": [{"$gte": ["$rating_score", 4]}, 1, 0]
                    }
                },
                "negative_ratings": {
                    "$sum": {
                        "$cond": [{"$lt": ["$rating_score", 3]}, 1, 0]
                    }
                },
                "neutral_ratings": {
                    "$sum": {
                        "$cond": [
                            {"$and": [
                                {"$gte": ["$rating_score", 3]},
                                {"$lt": ["$rating_score", 4]}
                            ]},
                            1, 0
                        ]
                    }
                }
            }}
        ]

        # Executar consultas
        total_results = list(collection.aggregate(pipeline_stats))
        problem_results = list(collection.aggregate(pipeline_problems))
        rating_results = list(collection.aggregate(pipeline_ratings))

        # Processar resultados
        bairros_stats = {}
        for feature in geojson_data['features']:
            bairro = feature['properties']['nome']
            total = next((t for t in total_results if t['_id'] == bairro), None)
            problems = next((p for p in problem_results if p['_id'] == bairro), None)
            ratings = next((r for r in rating_results if r['_id'] == bairro), None)

            stats = {
                'total_rides': total['total_rides'] if total else 0,
                'problematic_rides': problems['problematic_rides'] if problems else 0,
                'has_problems': problems is not None,
                'total_rated': ratings['total_rated'] if ratings else 0,
                'avg_score': ratings['avg_score'] if ratings else None
            }

            # Calcular percentuais de avaliação
            if stats['total_rated'] > 0:
                stats['percent_positivo'] = (
                    (ratings['positive_ratings'] / stats['total_rated']) * 100 if ratings else 0
                )
                stats['percent_negativo'] = (
                    (ratings['negative_ratings'] / stats['total_rated']) * 100 if ratings else 0
                )
                stats['percent_neutro'] = (
                    (ratings['neutral_ratings'] / stats['total_rated']) * 100 if ratings else 0
                )

                # Cálculo corrigido do sentiment_score
                positive_weight = stats['percent_positivo'] * 1
                neutral_weight = stats['percent_neutro'] * 0.5
                negative_weight = stats['percent_negativo'] * 1
                stats['sentiment_score'] = positive_weight + neutral_weight - negative_weight

                # Normalização para a escala -100 a 100
                stats['sentiment_score'] = (stats['sentiment_score'] / 100) * 100
            else:
                stats['percent_positivo'] = 0
                stats['percent_negativo'] = 0
                stats['percent_neutro'] = 0
                stats['sentiment_score'] = 0

            bairros_stats[bairro] = stats

        return bairros_stats

    except Exception as e:
        logger.error(f"Erro ao obter estatísticas por bairro: {str(e)}")
        logger.error(traceback.format_exc())
        return {}



def filters_to_query(filters):
    """Converte filtros do formulário para query do MongoDB"""
    query = {}

    if filters.get('date_range') and len(filters['date_range']) == 2:
        query["date"] = {
            "$gte": datetime.strptime(filters['date_range'][0], '%d/%m/%Y'),
            "$lte": datetime.strptime(filters['date_range'][1], '%d/%m/%Y')
        }

    if filters.get('suburb'):
        query["suburb_client"] = filters['suburb']

    if filters.get('score_range'):
        query["rating_score"] = {
            "$gte": filters['score_range'][0],
            "$lte": filters['score_range'][1]
        }

    if filters.get('problem_type'):
        keywords = get_keywords_for_problem_type(filters['problem_type'])
        query["rating_comment"] = {
            "$regex": "|".join(keywords),
            "$options": "i"
        }

    return query


# Função para obter estatísticas do motorista - VERSÃO CORRIGIDA
def get_driver_stats(driver_id, filters=None):
    """Estatísticas completas considerando TODAS as corridas"""
    try:
        base_query = {"driver_id": driver_id}
        if filters:
            if filters.get('date_range'):
                base_query["date"] = {
                    "$gte": datetime.strptime(filters['date_range'][0], '%d/%m/%Y'),
                    "$lte": datetime.strptime(filters['date_range'][1], '%d/%m/%Y')
                }
            if filters.get('suburb'):
                base_query["suburb_client"] = filters['suburb']

        pipeline = [
            {"$match": base_query},
            {"$group": {
                "_id": "$driver_id",
                "total_rides": {"$sum": 1},
                "canceled_by_driver": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_MOTORISTA]}, 1, 0]
                    }
                },
                "canceled_by_client": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_PASSAGEIRO]}, 1, 0]
                    }
                },
                "finalized_rides": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_FINALIZADA]}, 1, 0]
                    }
                },
                "avg_score": {
                    "$avg": {
                        "$cond": [
                            {"$eq": ["$status", STATUS_FINALIZADA]},
                            "$rating_score",
                            None
                        ]
                    }
                },
                "profile": {
                    "$first": {
                        "race": "$race",
                        "gender": "$gender",
                        "age_Range": "$age_Range",
                        "fitness": "$fitness",
                        "car_type": "$car_type"
                    }
                },
                "suburbs": {"$addToSet": "$suburb_client"}
            }}
        ]

        result = list(db["rides_original"].aggregate(pipeline))
        if not result:
            return None

        stats = result[0]
        total_rides = stats["total_rides"]

        # Verificação de consistência
        calculated_cancels = total_rides - stats["finalized_rides"]
        recorded_cancels = stats["canceled_by_driver"] + stats["canceled_by_client"]

        if calculated_cancels != recorded_cancels:
            logger.warning(f"Inconsistência em cancelamentos para motorista {driver_id}: "
                           f"Calculado={calculated_cancels} vs Registrado={recorded_cancels}")
            # Ajusta os cancelamentos pelo motorista para a diferença
            stats["canceled_by_driver"] = calculated_cancels - stats["canceled_by_client"]

        return {
            "driver_id": stats["_id"],
            "total_rides": total_rides,
            "canceled_by_driver": stats["canceled_by_driver"],
            "canceled_by_client": stats["canceled_by_client"],
            "finalized_rides": stats["finalized_rides"],
            "cancel_rate_driver": (stats["canceled_by_driver"] / total_rides) * 100 if total_rides > 0 else 0,
            "cancel_rate_client": (stats["canceled_by_client"] / total_rides) * 100 if total_rides > 0 else 0,
            "avg_score": stats["avg_score"] or 0,
            "profile": stats["profile"],
            "top_suburbs": [s for s in stats["suburbs"] if s]
        }
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas do motorista {driver_id}: {str(e)}")
        return None


# Função para buscar estatísticas completas dos motoristas
def get_driver_complete_stats(driver_id, filters=None):
    """Obtém estatísticas completas de um motorista considerando TODAS as corridas"""
    try:
        base_query = {"driver_id": driver_id}
        if filters:
            if filters.get('date_range') and len(filters['date_range']) == 2:
                base_query["date"] = {
                    "$gte": datetime.strptime(filters['date_range'][0], '%d/%m/%Y'),
                    "$lte": datetime.strptime(filters['date_range'][1], '%d/%m/%Y')
                }
            if filters.get('suburb'):
                base_query["suburb_client"] = filters['suburb']

        pipeline = [
            {"$match": base_query},
            {"$group": {
                "_id": "$driver_id",
                "total_rides": {"$sum": 1},
                "canceled_by_driver": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_MOTORISTA]}, 1, 0]
                    }
                },
                "canceled_by_client": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_PASSAGEIRO]}, 1, 0]
                    }
                },
                "finalized_rides": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_FINALIZADA]}, 1, 0]
                    }
                },
                "avg_score": {
                    "$avg": {
                        "$cond": [
                            {"$eq": ["$status", STATUS_FINALIZADA]},
                            "$rating_score",
                            None
                        ]
                    }
                },
                "suburbs": {"$addToSet": "$suburb_client"},
                "profile": {
                    "$first": {
                        "race": "$race",
                        "gender": "$gender",
                        "age_Range": "$age_Range",
                        "fitness": "$fitness",
                        "car_type": "$car_type"
                    }
                }
            }}
        ]

        result = list(db["rides_original"].aggregate(pipeline))
        if not result:
            return None

        stats = result[0]
        total_rides = stats["total_rides"]

        # Verificação de consistência
        calculated_cancels = total_rides - stats["finalized_rides"]
        recorded_cancels = stats["canceled_by_driver"] + stats["canceled_by_client"]

        # Se houver diferença, distribuímos proporcionalmente
        if calculated_cancels != recorded_cancels:
            if recorded_cancels > 0:
                ratio_driver = stats["canceled_by_driver"] / recorded_cancels
                stats["canceled_by_driver"] = int(calculated_cancels * ratio_driver)
                stats["canceled_by_client"] = calculated_cancels - stats["canceled_by_driver"]
            else:
                # Se não há registros, assume que foram canceladas pelo motorista
                stats["canceled_by_driver"] = calculated_cancels
                stats["canceled_by_client"] = 0

        return {
            "driver_id": stats["_id"],
            "total_rides": total_rides,
            "finalized_rides": stats.get("finalized_rides", 0),
            "canceled_by_driver": stats.get("canceled_by_driver", 0),
            "canceled_by_client": stats.get("canceled_by_client", 0),
            "cancel_rate_driver": (stats.get("canceled_by_driver", 0) / total_rides) * 100 if total_rides > 0 else 0,
            "cancel_rate_client": (stats.get("canceled_by_client", 0) / total_rides) * 100 if total_rides > 0 else 0,
            "avg_score": stats.get("avg_score", 0),
            "profile": stats.get("profile", {}),
            "top_suburbs": [s for s in stats.get("suburbs", []) if s]
        }
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas completas do motorista {driver_id}: {str(e)}")
        return None


# Função principal atualizada
def analyze_driver_comments(filters=None):
    """Analisa comentários e avaliações para identificar padrões de problemas"""
    try:
        filters = filters or {}
        collection = db["rides_original"]
        geojson_data = load_geojson()

        # 1. Definir queries base - considerar TODAS as corridas
        base_query = {}

        # Aplicar filtros comuns
        if filters.get('date_range') and len(filters['date_range']) == 2:
            start_date = datetime.strptime(filters['date_range'][0], '%d/%m/%Y')
            end_date = datetime.strptime(filters['date_range'][1], '%d/%m/%Y')
            base_query["date"] = {"$gte": start_date, "$lte": end_date}

        if filters.get('suburb'):
            base_query["suburb_client"] = filters['suburb']

        # Query específica para comentários (apenas corridas finalizadas com comentários)
        query_comments = {
            "finalizada": 1,
            "rating_score": {"$exists": True},
            "rating_comment": {
                "$exists": True,
                "$nin": [None, "", "comentarios opcional", "Comentarios (opcional)"]
            }
        }
        query_comments.update(base_query)  # Aplica os filtros comuns

        # 2. Pipeline para estatísticas GERAIS (incluindo cancelamentos)
        pipeline_all_drivers = [
            {"$match": base_query},
            {"$group": {
                "_id": "$driver_id",
                "total_rides": {"$sum": 1},
                "canceled_by_driver": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_MOTORISTA]}, 1, 0]
                    }
                },
                "canceled_by_client": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_PASSAGEIRO]}, 1, 0]
                    }
                },
                "finalized_rides": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_FINALIZADA]}, 1, 0]
                    }
                },
                "total_score": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", STATUS_FINALIZADA]},
                            "$rating_score",
                            0
                        ]
                    }
                },
                "has_comments": {
                    "$sum": {
                        "$cond": [
                            {"$and": [
                                {"$eq": ["$status", STATUS_FINALIZADA]},
                                {"$ne": ["$rating_comment", None]},
                                {"$ne": ["$rating_comment", ""]},
                                {"$ne": ["$rating_comment", "comentarios opcional"]}
                            ]},
                            1, 0
                        ]
                    }
                }
            }},
            {"$group": {
                "_id": None,
                "total_drivers": {"$sum": 1},
                "total_rides_all": {"$sum": "$total_rides"},
                "total_cancel_driver": {"$sum": "$canceled_by_driver"},
                "total_cancel_client": {"$sum": "$canceled_by_client"},
                "total_finalized": {"$sum": "$finalized_rides"},
                "total_score_all": {"$sum": "$total_score"},
                "total_with_comments": {"$sum": "$has_comments"},
                "avg_rides": {"$avg": "$total_rides"},
                "avg_cancel_rate_driver": {
                    "$avg": {
                        "$cond": [
                            {"$gt": ["$total_rides", 0]},
                            {"$divide": ["$canceled_by_driver", "$total_rides"]},
                            None
                        ]
                    }
                },
                "avg_cancel_rate_client": {
                    "$avg": {
                        "$cond": [
                            {"$gt": ["$total_rides", 0]},
                            {"$divide": ["$canceled_by_client", "$total_rides"]},
                            None
                        ]
                    }
                }
            }},
            {"$addFields": {
                "avg_score_all": {
                    "$cond": [
                        {"$gt": ["$total_finalized", 0]},
                        {"$divide": ["$total_score_all", "$total_finalized"]},
                        0
                    ]
                }
            }}
        ]

        # EXECUTAR o pipeline de estatísticas gerais
        stats_all_drivers = list(collection.aggregate(pipeline_all_drivers))
        if stats_all_drivers:
            stats_all_drivers = stats_all_drivers[0]
            # Garantir valores padrão
            stats_all_drivers["avg_cancel_rate_driver"] = stats_all_drivers.get("avg_cancel_rate_driver", 0) or 0
            stats_all_drivers["avg_cancel_rate_client"] = stats_all_drivers.get("avg_cancel_rate_client", 0) or 0
        else:
            stats_all_drivers = {
                "total_drivers": 0,
                "total_rides_all": 0,
                "total_cancel_driver": 0,
                "total_cancel_client": 0,
                "total_finalized": 0,
                "total_with_comments": 0,
                "avg_rides": 0,
                "avg_cancel_rate_driver": 0,
                "avg_cancel_rate_client": 0,
                "avg_score_all": 0
            }

        # 3. Pipeline para estatísticas por motorista
        pipeline_driver_stats = [
            {"$match": base_query},
            {"$group": {
                "_id": "$driver_id",
                "total_rides": {"$sum": 1},
                "finalized_rides": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_FINALIZADA]}, 1, 0]
                    }
                },
                "canceled_by_driver": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_MOTORISTA]}, 1, 0]
                    }
                },
                "canceled_by_client": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", STATUS_CANCELADA_PASSAGEIRO]}, 1, 0]
                    }
                },
                "avg_score": {
                    "$avg": {
                        "$cond": [
                            {"$eq": ["$status", STATUS_FINALIZADA]},
                            "$rating_score",
                            None
                        ]
                    }
                },
                "profile": {
                    "$first": {
                        "race": "$race",
                        "gender": "$gender",
                        "age_Range": "$age_Range",
                        "fitness": "$fitness",
                        "car_type": "$car_type"
                    }
                },
                "suburbs": {"$addToSet": "$suburb_client"}
            }}
        ]

        all_drivers_stats = list(collection.aggregate(pipeline_driver_stats))


        # 4. Obter corridas com comentários
        rides_with_comments = list(collection.find(query_comments, {
            "driver_id": 1,
            "rating_score": 1,
            "rating_comment": 1,
            "suburb_client": 1,
            "race": 1,
            "gender": 1,
            "age_Range": 1,
            "fitness": 1,
            "car_type": 1,
            "date": 1,
            "canceled_by_driver": 1,
            "canceled_by_client": 1
        }))

        # 5. Processar comentários problemáticos
        problematic_drivers = set()
        comments_analysis = []
        problem_counts = defaultdict(int)
        total_comments = 0
        problematic_comments = 0
        sentiment_counts = {"Positivo": 0, "Neutro": 0, "Negativo": 0}

        for ride in rides_with_comments:
            comment = str(ride.get("rating_comment", "")).strip()
            if not comment or comment.lower() in ['nan', 'comentarios opcional', 'comentarios (opcional)']:
                continue

            total_comments += 1
            sentiment = analyze_sentiment(comment, ride.get("rating_score", 3))
            sentiment_counts[sentiment["label"]] += 1

            # Pré-processamento do comentário
            comment_lower = comment.lower()

            # Detecção inicial de problemas
            problem_types = detect_problems(comment)

            # Verificação adicional para contexto específico
            if 'avó' in comment_lower or 'avo' in comment_lower:
                # Verifica tarifa se mencionar termos relacionados
                if any(w in comment_lower for w in
                       ['corrida', 'tarifa', 'preço', 'valor', 'cobrança', 'começou', 'iniciou']):
                    if 'tarifa' not in problem_types:
                        problem_types.append('tarifa')

                # Verifica etarismo se mencionar desrespeito
                if any(w in comment_lower for w in ['desrespeito', 'maltrato', 'falta de respeito', 'abus']):
                    if 'etarismo' not in problem_types:
                        problem_types.append('etarismo')

            # Verificação adicional para desonestidade em cobrança
            if 'desonesto' in comment_lower and any(
                    w in comment_lower for w in ['cobrança', 'valor', 'preço', 'tarifa', 'corrida']):
                if 'tarifa' not in problem_types:
                    problem_types.append('tarifa')

            # Verificação adicional para problemas de veículo em contexto negativo
            if any(w in comment_lower for w in ['carro', 'veículo']) and any(
                    w in comment_lower for w in ['péssimo', 'horrível', 'quebrado', 'sujo', 'fedido']):
                if 'veículo' not in problem_types:
                    problem_types.append('veículo')

            # Considera problemático se tiver problemas e sentimento não positivo
            if problem_types and sentiment["label"] in ["Neutro", "Negativo"]:
                problematic_comments += 1
                problematic_drivers.add(ride["driver_id"])

                # Atualiza contagem de problemas
                for ptype in problem_types:
                    problem_counts[ptype] += 1

                # Obter estatísticas completas do motorista
                driver_stats = get_driver_complete_stats(ride["driver_id"])

                # Calcular diferença em relação à média dos motoristas
                avg_cancel_rate_driver = stats_all_drivers.get("avg_cancel_rate_driver", 0) * 100
                avg_cancel_rate_client = stats_all_drivers.get("avg_cancel_rate_client", 0) * 100

                driver_cancel_rate_driver = (driver_stats.get("canceled_by_driver", 0) / driver_stats.get(
                    "total_rides", 1)) * 100 if driver_stats.get("total_rides", 0) > 0 else 0
                driver_cancel_rate_client = (driver_stats.get("canceled_by_client", 0) / driver_stats.get(
                    "total_rides", 1)) * 100 if driver_stats.get("total_rides", 0) > 0 else 0

                comments_analysis.append({
                    "driver_id": ride["driver_id"],
                    "comment": comment,
                    "score": ride.get("rating_score", 3),
                    "sentiment": sentiment,
                    "driver_profile": {
                        "race": RACE_MAP.get(ride.get("race")),
                        "gender": GENDER_MAP.get(ride.get("gender")),
                        "age": AGE_RANGE_MAP.get(ride.get("age_Range")),
                        "fitness": FITNESS_MAP.get(ride.get("fitness")),
                        "car_type": ride.get("car_type")
                    },
                    "suburb_client": ride.get("suburb_client"),
                    "problem_types": problem_types,
                    "date": ride.get("created_at"),
                    "total_rides": driver_stats.get("total_rides", 0) if driver_stats else 0,
                    "finalized_rides": driver_stats.get("finalized_rides", 0) if driver_stats else 0,
                    "canceled_by_driver": driver_stats.get("canceled_by_driver", 0) if driver_stats else 0,
                    "canceled_by_client": driver_stats.get("canceled_by_client", 0) if driver_stats else 0,
                    "cancel_rate_driver": driver_cancel_rate_driver,
                    "cancel_rate_client": driver_cancel_rate_client,
                    "cancel_rate_vs_avg_driver": driver_cancel_rate_driver - avg_cancel_rate_driver,
                    "cancel_rate_vs_avg_client": driver_cancel_rate_client - avg_cancel_rate_client,
                    "avg_cancel_rate_driver": avg_cancel_rate_driver,  # Adicionado para referência
                    "avg_cancel_rate_client": avg_cancel_rate_client  # Adicionado para referência
                })

        # 6. Preparar dados dos top 10 piores motoristas
        # Filtrar motoristas com pelo menos a média de corridas
        min_rides = max(5, stats_all_drivers["avg_rides"])
        filtered_drivers = [d for d in all_drivers_stats if
                            d["total_rides"] >= min_rides and
                            d.get("avg_score") is not None]

        # Ordenar por piores avaliações
        filtered_drivers.sort(key=lambda x: x.get("avg_score", 5))
        top_worst_drivers = filtered_drivers[:10]

        # Calcular médias de cancelamento
        avg_cancel_rate_driver = stats_all_drivers["avg_cancel_rate_driver"] * 100
        avg_cancel_rate_client = stats_all_drivers["avg_cancel_rate_client"] * 100

        # Adicionar estatísticas de cancelamento
        for driver in top_worst_drivers:
            total_rides = driver["total_rides"]
            canceled_by_driver = driver["canceled_by_driver"]
            canceled_by_client = driver["canceled_by_client"]

            driver["cancel_rate_driver"] = (canceled_by_driver / total_rides) * 100 if total_rides > 0 else 0
            driver["cancel_rate_client"] = (canceled_by_client / total_rides) * 100 if total_rides > 0 else 0

            # Diferença em relação à média dos motoristas
            driver["cancel_rate_vs_avg_driver"] = driver["cancel_rate_driver"] - avg_cancel_rate_driver
            driver["cancel_rate_vs_avg_client"] = driver["cancel_rate_client"] - avg_cancel_rate_client
            driver["avg_cancel_rate_driver"] = avg_cancel_rate_driver  # Adicionado para referência
            driver["avg_cancel_rate_client"] = avg_cancel_rate_client  # Adicionado para referência


        # 7. Distribuição de scores (considerando todos os motoristas)
        score_distribution = {
            '1-2': len([d for d in all_drivers_stats
                        if isinstance(d.get("avg_score"), (int, float)) and 1 <= d["avg_score"] < 2]),
            '2-3': len([d for d in all_drivers_stats
                        if isinstance(d.get("avg_score"), (int, float)) and 2 <= d["avg_score"] < 3]),
            '3-4': len([d for d in all_drivers_stats
                        if isinstance(d.get("avg_score"), (int, float)) and 3 <= d["avg_score"] < 4]),
            '4-5': len([d for d in all_drivers_stats
                        if isinstance(d.get("avg_score"), (int, float)) and 4 <= d["avg_score"] <= 5])
        }

        # 8. Depuração dos bairros com problemas:
        # Obter estatísticas dos bairros
        bairros_stats = get_bairros_stats(filters)

        # Depuração - atualizada para as novas estatísticas
        logger.info("Verificação dos bairros:")
        for bairro, stats in bairros_stats.items():
            if stats['total_rides'] > 0:
                logger.info(f"Bairro: {bairro} - Corridas: {stats['total_rides']} "
                            f"(Avaliadas: {stats['total_rated']}, "
                            f"Problemas: {stats['problematic_rides']})")

        # Verificação específica para o Maracanã
        if 'Maracanã' in bairros_stats:
            stats = bairros_stats['Maracanã']
            logger.info(f"""
                Estatísticas detalhadas do Maracanã:
                - Total de corridas: {stats['total_rides']}
                - Corridas avaliadas: {stats['total_rated']} ({stats['total_rated'] / stats['total_rides'] * 100:.1f}%)
                - Corridas problemáticas: {stats['problematic_rides']} ({stats['problematic_rides'] / stats['total_rides'] * 100:.1f}%)
                - Avaliações positivas: {stats['percent_positivo']:.1f}%
                - Avaliações neutras: {stats['percent_neutro']:.1f}%
                - Avaliações negativas: {stats['percent_negativo']:.1f}%
                - Índice de satisfação: {stats['sentiment_score']:.1f}
            """)

        logger.info(
            f"Exemplo de comentário problemático: {comments_analysis[0] if comments_analysis else 'Nenhum comentário'}")
        logger.info(
            f"Exemplo de motorista problemático: {top_worst_drivers[0] if top_worst_drivers else 'Nenhum motorista'}")


        # 9. Calcular estatísticas de problemas por bairro
        problem_stats_by_suburb = defaultdict(lambda: {
            'total_problems': 0,
            'problem_types': defaultdict(int),
            'discriminatory_problems': False
        })

        for comment in comments_analysis:
            suburb = comment.get('suburb_client')
            if suburb:
                problem_stats_by_suburb[suburb]['total_problems'] += 1
                for ptype in comment['problem_types']:
                    problem_stats_by_suburb[suburb]['problem_types'][ptype] += 1
                    if ptype in ['racial', 'gênero', 'etarismo', 'físico', 'homofobia', 'regional',
                                 'político-religioso']:
                        problem_stats_by_suburb[suburb]['discriminatory_problems'] = True

        # Agora crie e retorne o dicionário results
        return {
            "top_worst_drivers": [{
                "driver_id": d["_id"],
                "avg_score": d.get("avg_score", 0),
                "total_rides": d.get("total_rides", 0),
                "finalized_rides": d.get("finalized_rides", 0),
                "canceled_by_driver": d.get("canceled_by_driver", 0),
                "canceled_by_client": d.get("canceled_by_client", 0),
                "cancel_rate_driver": (d.get("canceled_by_driver", 0) / d.get("total_rides", 1)) * 100 if d.get(
                    "total_rides", 0) > 0 else 0,
                "cancel_rate_client": (d.get("canceled_by_client", 0) / d.get("total_rides", 1)) * 100 if d.get(
                    "total_rides", 0) > 0 else 0,
                "cancel_rate_vs_avg_driver": d["cancel_rate_vs_avg_driver"],
                "cancel_rate_vs_avg_client": d["cancel_rate_vs_avg_client"],
                "profile": {
                    "race": RACE_MAP.get(d["profile"].get("race")),
                    "gender": GENDER_MAP.get(d["profile"].get("gender")),
                    "age_Range": AGE_RANGE_MAP.get(d["profile"].get("age_Range")),
                    "fitness": FITNESS_MAP.get(d["profile"].get("fitness")),
                    "car_type": d["profile"].get("car_type")
                },
                "top_suburbs": list(d["suburbs"])[:5] if d.get("suburbs") else []
            } for d in top_worst_drivers],
            "problematic_comments": comments_analysis,
            "problematic_drivers_count": len(problematic_drivers),
            "total_drivers_analyzed": stats_all_drivers["total_drivers"],
            "total_comments_analyzed": total_comments,
            "problematic_comments_count": problematic_comments,
            "problem_stats_by_suburb": dict(problem_stats_by_suburb),
            "problem_stats": dict(problem_counts),
            "general_stats": {
                "total_rides": stats_all_drivers["total_rides_all"],
                "total_drivers": stats_all_drivers["total_drivers"],
                "avg_rides_per_driver": stats_all_drivers["avg_rides"],
                "avg_cancel_rate_driver": stats_all_drivers["avg_cancel_rate_driver"],
                "avg_cancel_rate_client": stats_all_drivers["avg_cancel_rate_client"],
                "sentiment_stats": sentiment_counts,
                "avg_score": stats_all_drivers.get("avg_score_all", 0)  # Usando get() com valor padrão
            },
            "bairros_stats": bairros_stats,
            "score_distribution": score_distribution,
            "all_drivers_count": len(all_drivers_stats)
        }

    except Exception as e:
        logger.error(f"Erro na análise de comentários: {str(e)}")
        logger.error(traceback.format_exc())
        raise



def get_keywords_for_problem_type(ptype):
    """Retorna palavras-chave e padrões regex para um tipo específico de problema"""
    patterns = {
        "racial": {
            'keywords': ['racismo', 'cor', 'raça', 'negro', 'branco', 'preto', 'pardo', 'asiático', 'indio', 'mulato',
                         'crioulo'],
            'regex': [r'discrimin(a|o)\s+(por|pela)\s+(cor|raça)']
        },
        "gênero": {
            'keywords': ['gênero', 'mulher', 'homem', 'feminino', 'masculino', 'moça', 'senhora', 'garota', 'menina'],
            'regex': [r'ass[eé]dio\s+sexual', r'discrimin(a|o)\s+(por|pela)\s+gênero']
        },
        "etarismo": {
            'keywords': ['idade', 'velho', 'jovem', 'idoso', 'velha', 'jovenzinho', 'senhor', 'senhora', 'avó', 'avo',
                         'idosos', 'terceira idade'],
            'regex': [r'maltrat(o|ou)\s+(a|à)\s+(avó|avo|idos)', r'desrespeit(o|ou)\s+(a|à)\s+(avó|avo|idos)']
        },
        "físico": {
            'keywords': ['peso', 'gordo', 'magro', 'forma física', 'gordinho', 'magrelo', 'barrigudo', 'obeso',
                         'deficiente'],
            'regex': [r'piad(a|inha)\s+sobre\s+(peso|aparência)']
        },
        "homofobia": {
            'keywords': ['homossexual', 'gay', 'lésbica', 'lgbt', 'bicha', 'sapatão', 'viado', 'traveco', 'sapata',
                         'boiola', 'viadinho'],
            'regex': [r'discrimin(a|o)\s+(por|pela)\s+orientação']
        },
        "regional": {
            'keywords': ['bairro', 'favela', 'comunidade', 'zona', 'periferia', 'subúrbio', 'morro', 'asfalto'],
            'regex': [r'discrimin(a|o)\s+(por|pelo)\s+bairro']
        },
        "tarifa": {
            'keywords': ['preço', 'caro', 'valor', 'tarifa', 'dinheiro', 'conta', 'lucro', 'roubo', 'golpe',
                         'desonesto', 'cobrança', 'cobranca', 'cobrou'],
            'regex': [
                r'come[cç]ou\s+a\s+corrida\s+antes',
                r'cobrou\s+a\s+mais',
                r'valor\s+errado',
                r'golpe|fraude|engano',
                r'desonest(o|a)\s+(na|com)\s+(corrida|tarifa)'
            ]
        },
        "político-religioso": {
            'keywords': ['religião', 'política', 'partido', 'crente', 'ateu', 'bolsonaro', 'lula', 'deus', 'crente',
                         'evangélico', 'católico'],
            'regex': [r'discrimin(a|o)\s+(por|pela)\s+(religião|política)']
        },
        "veículo": {
            'keywords': ['carro', 'veículo', 'cheiro', 'odor', 'cigarro', 'sujo', 'velho', 'quebrado', 'mal cuidado'],
            'regex': [r'condições\s+(do|de)\s+ve[ií]culo']
        }
    }

    config = patterns.get(ptype, {})
    # Combina palavras-chave e padrões regex
    return config.get('keywords', []) + config.get('regex', [])


#Rota principal
@analise_comentarios_app.route('/', methods=['GET', 'POST'])
def show_analysis():
    try:
        # Processar filtros
        filters = {
            'date_range': request.form.getlist('date_range'),
            'suburb': request.form.get('suburb', '').strip(),
            'problem_type': request.form.get('problem_type', '').strip(),
            'score_range': [
                float(request.form.get('min_score', 1)),
                float(request.form.get('max_score', 5))
            ]
        }

        # Carregar dados
        geojson_data = load_geojson()
        results = analyze_driver_comments(filters)

        # Dados públicos para gráficos sem identificadores pessoais (LGPD)
        charts_data = deepcopy(results)
        for _c in charts_data.get('problematic_comments', []) or []:
            _c.pop('driver_id', None)
        for _d in charts_data.get('top_worst_drivers', []) or []:
            _d.pop('driver_id', None)
        # Garantir que bairros_stats seja preenchido mesmo sem filtros
        if not results.get('bairros_stats'):
            results['bairros_stats'] = get_bairros_stats()

        # Adicionar estatísticas de cancelamento para o template
        stats_all_drivers = {
            'avg_cancel_driver': results['general_stats'].get('avg_cancel_rate_driver', 0),
            'avg_cancel_client': results['general_stats'].get('avg_cancel_rate_client', 0)
        }

        return render_template(
            'analise_comentarios.html',
            results=results,
            filters=filters,
            geojson_data=json.dumps(geojson_data),
            charts_data=charts_data,
            stats_all_drivers=stats_all_drivers  # Passa as estatísticas corretamente
        )

    except Exception as e:
        logger.error(f"Erro na rota de análise de comentários: {str(e)}", exc_info=True)
        return render_template('error.html', error=f"Erro ao analisar comentários: {str(e)}"), 500


@analise_comentarios_app.route('/api/bairros')
def get_bairros_data():
    """Endpoint para obter dados de bairros para o mapa"""
    try:
        bairros_stats = get_bairros_stats()
        geojson_data = load_geojson()

        # Adicionar estatísticas ao GeoJSON
        for feature in geojson_data['features']:
            bairro = feature['properties']['nome']
            stats = bairros_stats.get(bairro, {})
            feature['properties'].update({
                'total_corridas': stats.get('total_corridas', 0),
                'corridas_com_comentarios': stats.get('corridas_com_comentarios', 0),
                'corridas_problematicas': stats.get('corridas_problematicas', 0),
                'percentual_problematico': stats.get('percentual_problematico', 0),
            })

        return jsonify(geojson_data)
    except Exception as e:
        logger.error(f"Erro ao gerar dados de bairros: {str(e)}")
        return jsonify({"error": str(e)}), 500