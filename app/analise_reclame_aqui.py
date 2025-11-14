from flask import Blueprint, render_template, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
from collections import defaultdict
import re
from typing import Tuple, Optional
from itertools import combinations


# Matplotlib: backend "Agg" para ambiente headless
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # importa após setar backend

# NLTK é opcional
NLTK_OK = False
try:
    import nltk  # noqa
    from nltk.corpus import stopwords  # noqa
    # se tiver dados, ótimo; se não tiver, só seguimos sem
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('corpora/stopwords')
        NLTK_OK = True
    except LookupError:
        # Não tenta baixar aqui. Apenas registra e prossigue.
        pass
except Exception:
    pass

from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from io import BytesIO
import base64
import pandas as pd

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente
load_dotenv()

# Conexão com MongoDB
try:
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["mobility_data"]
    collection = db["reclame_aqui_complaints"]
    logger.info("Conexão com MongoDB estabelecida")
except Exception as e:
    logger.error(f"Falha na conexão com MongoDB: {str(e)}")
    raise

# Configuração do Blueprint
reclame_aqui_app = Blueprint('reclame_aqui_app', __name__)


# Registrar filtro personalizado para o blueprint
@reclame_aqui_app.app_template_filter('datetimeformat')
def datetimeformat(value, format='%d/%m/%Y'):
    """Filtro para formatar objetos datetime no template"""
    if value is None:
        return ""

    if isinstance(value, str):
        try:
            # Tentar converter string para datetime
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                value = datetime.strptime(value, '%d/%m/%Y')
            except (ValueError, AttributeError):
                return value  # Retornar o valor original se não conseguir converter

    try:
        return value.strftime(format)
    except (AttributeError, ValueError):
        return str(value)  # Fallback para string



# Inicializar analisador de sentimentos leve
vader_analyzer = SentimentIntensityAnalyzer()

# Palavras-chave para categorização de problemas
PROBLEM_KEYWORDS = {
    "funcionamento_app": [
        # Termos específicos do aplicativo do usuário:
        "login", "cadastro", "instalação", "aplicativo", "conta", "acesso",
        "sistema", "atualização", "bug", "erro", "tela", "carregando",
        "app", "aplicativo", "congelou", "travou", "instalar", "desinstalar",
        "reinicializar", "reiniciar",
        # Termos específicos da plataforma:
        "bloqueio", "bloqueado",  "conta bloqueada", "plataforma ruim",
        "dados pessoais", "vazamento dados", "lentidão", "distribuição", "aceite", "plataforma",
        "fora do ar", "indisponível", "recuperar senha"
    ],
    "problemas_servico": [
        # Termos específicos de tarifa:
        "tarifa", "preço", "valor", "cobrança", "desconto", "troco",
        "pagamento", "cartão", "dinheiro", "valor diferença",
        "devolução", "reembolso", "estorno",
        # Termos específicos de veículo:
        "veículo", "carro", "moto", "limpeza", "cheiro", "conforto",
        # Termos específicos da rota:
        "rota", "percurso", "trajeto", "desvio",
        # Termos específicos do prestador do serviço (motorista):
        "motorista", "condutor", "comportamento", "embarque", "desembarque", "direção",
        "cancelamento", "tempo de espera", "atraso", "problema viagem",
        "reclamação passageira", "acordado passageira",
        "reclamação passageiro", "acordado passageiro"
    ],
    "discriminacao": [
        # Termos específicos de discriminação racial
        "racismo", "racial", "negro", "preto", "branco", "cor da pele",
        "discriminação racial", "preconceito racial", "pardo", "mulato",

        # Termos específicos de gênero
        "machismo", "sexismo", "assédio sexual", "assedio sexual",
        "mulher", "gênero", "feminismo",

        # Termos específicos de forma física
        "gordo", "gorda", "obeso", "obesa", "magrelo", "magricelo",
        "raquítico", "raquitico",

        # Termos específicos de etarismo
        "velho", "velha", "idoso", "idosa", "fedelho", "pirralho",
        "avô", "avó", "novinho", "novinha",

        # Termos específicos de LGBTfobia
        "homofobia", "lgbtfobia", "transfobia", "orientação sexual",
        "homossexual", "gay", "lésbica", "trans", "travesti", "sapatão",
        "sapatao", "sapata", "viado", "viadinho",

        # Termos de assédio explícito
        "assediar", "agredir", "xingar", "ofender", "humilhar", "abusar",

        # Termos de discriminação por localidade (contexto específico)
        "favela", "periferia", "comunidade", "zona norte",

        # Termos de discriminação politico-religioso
        "crente", "religião", "carola", "política", "bolsonaro", "lula", "macumba", "macumbeiro",
        "hino", "bíblia", "louvor", "evangélico", "evangélica", "fanático",

        # Excluir termos ambíguos como "preto" (pode ser cor) e "gênero" (pode ser tipo)
    ]
}

# --- Subtipos específicos dentro das macro-categorias ---
SUBTYPE_KEYWORDS = {
    "discriminacao": {
        "racial": [
            r"\bracis", r"\bnegro\b", r"\bpreto\b", r"cor da pele", r"\bpardo\b", r"\bmulat"
        ],
        "genero": [
            r"machism", r"sexism", r"g[eê]nero", r"\bmulher(es)?\b"
        ],
        "lgbtfobia": [
            r"homofob", r"lgbtfob", r"transfob", r"\bgay\b", r"l[eé]sbic", r"\btrans\b", r"\btravest", r"viad", r"sapat(a|ã)o"
        ],
        "etarismo": [
            r"\bidos[oa]\b", r"\bvelh", r"novinh", r"pirralh", r"fedelh"
        ],
        "redlining_bairro": [
            r"(favela|comunidade|periferia).*(discrimin|preconceit)",
            r"(discrimin|preconceit).*(favela|comunidade|periferia)",
            r"\b(bairro|zona)\b.*(recus|negou)"
        ],
        "assedio_agressao": [
            r"ass[eé]di", r"agress[ãa]o", r"\bhumilh", r"\bxing", r"\bofend", r"\babus", r"amea[çc]"
        ]
    },
    "funcionamento_app": {
        "login_acesso": [
            r"\blogin\b", r"\bacesso\b", r"recuperar senha", r"\bcadastro"
        ],
        "instalacao_atualizacao": [
            r"instal", r"atualiza", r"desinstal", r"reinicia"
        ],
        "bloqueio_conta": [
            r"\bbloque", r"conta bloqueada"
        ],
        "bug_erro_crash": [
            r"\bbug\b", r"\berro\b", r"trav", r"congel"
        ],
        "performance_conexao": [
            r"fora do ar", r"indispon[ií]vel", r"lent", r"\bqueda\b", r"\bconex"
        ]
    },
    "problemas_servico": {
        "cobranca_tarifa": [
            r"tarifa", r"pre[çc]o", r"valor", r"cobran", r"taxa", r"troco"
        ],
        "cancelamento_recusa": [
            r"cancel", r"\brecus", r"n[aã]o aceitou", r"n[aã]o quis", r"n[aã]o pegou"
        ],
        "atraso_espera": [
            r"atras", r"tempo de espera", r"demor"
        ],
        "comportamento_motorista": [
            r"mal educad", r"grosseir", r"\bxing", r"\bofend", r"\bhumilh", r"mau atendimento", r"atendimento ruim"
        ],
        "condicoes_veiculo": [
            r"carro suj", r"sem ar", r"ar.?condicionado", r"carro velho", r"pneu", r"quebrad"
        ],
        "rota_valor": [
            r"\brota\b", r"caminho", r"desvi", r"cobrou a mais", r"km a mais"
        ],
        "seguranca": [
            r"seguran", r"roub", r"assalt", r"perig"
        ]
    }
}


def analyze_sentiment(text):
    """Analisa o sentimento do texto usando VADER (mais leve)"""
    if not text:
        return {"label": "NEUTRO", "score": 0}

    try:
        # Usar VADER para análise de sentimentos em português
        scores = vader_analyzer.polarity_scores(text)

        # Mapear para categorias em português
        if scores['compound'] >= 0.05:
            return {"label": "POSITIVO", "score": scores['compound']}
        elif scores['compound'] <= -0.05:
            return {"label": "NEGATIVO", "score": scores['compound']}
        else:
            return {"label": "NEUTRO", "score": scores['compound']}

    except Exception as e:
        logger.error(f"Erro na análise de sentimento: {str(e)}")
        return {"label": "NEUTRO", "score": 0}


def determine_severity(complaint):
    """Determina a severidade da reclamação com base no conteúdo"""
    text = f"{complaint.get('title', '')} {complaint.get('description', '')}".lower()

    # Verificar problemas críticos
    critical_keywords = PROBLEM_KEYWORDS["discriminacao"] + ["assédio", "agressão", "redlining"]
    if any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in critical_keywords):
        return "crítica"

    # Verificar problemas de serviço
    service_keywords = PROBLEM_KEYWORDS["problemas_servico"]
    if any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in service_keywords):
        return "alta"

    # Verificar problemas operacionais
    operational_keywords = PROBLEM_KEYWORDS["funcionamento_app"]
    if any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in operational_keywords):
        return "média"

    # Default baseado na avaliação
    rating = complaint.get('rating', 5)
    if rating <= 2:
        return "alta"
    elif rating <= 4:
        return "média"
    else:
        return "baixa"


def categorize_problems(complaint):
    """Categoriza os problemas mencionados na reclamação com contexto melhorado"""
    try:
        text = f"{complaint.get('title', '')} {complaint.get('description', '')}"
        if not isinstance(text, str):
            return []

        text_lower = text.lower()
        categories = set()

        # Verificar problemas de serviço primeiro (mais comuns)
        service_keywords = PROBLEM_KEYWORDS["problemas_servico"]
        for keyword in service_keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                # Verificar contexto para evitar falsos positivos
                if keyword in ["motorista", "condutor"]:
                    # "motorista" só é problema de serviço se não for o reclamante
                    user_type = complaint.get('user_type', '')
                    if user_type != 'motorista':  # Se quem reclama não é motorista
                        categories.add("problemas_servico")
                else:
                    categories.add("problemas_servico")
                break  # Uma keyword é suficiente para categorizar como problema de serviço

        # Verificar outras categorias
        for category, keywords in PROBLEM_KEYWORDS.items():
            if category == "problemas_servico":
                continue  # Já verificamos acima

            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                    # Verificações de contexto para evitar falsos positivos
                    if category == "discriminacao":
                        if keyword == "preto" and re.search(r'(preto de|cor preta|bloco.*preto)', text_lower):
                            continue
                        if keyword == "gênero" and not re.search(r'(discriminação.*gênero|gênero.*discriminação)',
                                                                 text_lower):
                            continue
                    categories.add(category)

        return list(categories)
    except Exception:
        return []


def extract_problem_subtypes(complaint):
    """
    Retorna uma lista de pares (categoria, subtipo) detectados no texto.
    Evita duplicidades por (categoria, subtipo).
    """
    text = f"{complaint.get('title','')} {complaint.get('description','')}"
    if not isinstance(text, str):
        return []
    tl = text.lower()

    found = set()
    for cat, submap in SUBTYPE_KEYWORDS.items():
        for subtype, patterns in submap.items():
            for pat in patterns:
                try:
                    if re.search(pat, tl):
                        found.add((cat, subtype))
                        break  # evita contar o mesmo subtipo várias vezes no mesmo item
                except re.error:
                    # em caso de regex malformada, apenas ignora esse padrão
                    continue
    return list(found)


def _format_subtype_label(cat: str, sub: str) -> str:
    cat_map = {
        "discriminacao": "Discriminação",
        "funcionamento_app": "Funcionamento do App",
        "problemas_servico": "Problemas do Serviço"
    }
    sub_map = {
        "racial": "Racial",
        "genero": "Gênero",
        "lgbtfobia": "LGBTfobia",
        "etarismo": "Etarismo",
        "redlining_bairro": "Redlining/Bairro",
        "assedio_agressao": "Assédio/Agressão",
        "login_acesso": "Login/Acesso",
        "instalacao_atualizacao": "Instalação/Atualização",
        "bloqueio_conta": "Bloqueio de Conta",
        "bug_erro_crash": "Bug/Erro/Crash",
        "performance_conexao": "Performance/Conexão",
        "cobranca_tarifa": "Cobrança/Tarifa",
        "cancelamento_recusa": "Cancelamento/Recusa",
        "atraso_espera": "Atraso/Espera",
        "comportamento_motorista": "Comportamento do Motorista",
        "condicoes_veiculo": "Condições do Veículo",
        "rota_valor": "Rota/Valor",
        "seguranca": "Segurança",
    }
    return f"{cat_map.get(cat, cat)}: {sub_map.get(sub, sub.replace('_',' ').title())}"

def compute_subtype_cooccurrence(complaints, top_n=15, min_count_for_lift=2):
    """
    Calcula coocorrências entre subtipos (pares dentro da MESMA reclamação).
    Retorna top pares por contagem e por lift, com métricas auxiliares.
    """
    N = len(complaints)
    if N == 0:
        return {"pairs_by_count": [], "pairs_by_lift": [], "node_counts": {}, "N": 0}

    # 1) Contagem por subtipo e por par
    node_counts = {}          # key="cat:sub" -> count de ocorrências em itens
    pair_counts = {}          # key=(a,b) (ordenado) -> count conjunto
    pair_intra = {}           # mesmo macro? True/False

    for c in complaints:
        # subtipos únicos neste item
        st = extract_problem_subtypes(c)  # [(cat, sub), ...]
        if not st:
            continue
        # normaliza em "cat:sub"
        uniq = sorted({f"{cat}:{sub}" for (cat, sub) in st})
        # aumenta contagem de cada nó
        for key in uniq:
            node_counts[key] = node_counts.get(key, 0) + 1
        # combinações 2 a 2 para coocorrência
        for a, b in combinations(uniq, 2):
            k = (a, b) if a < b else (b, a)
            pair_counts[k] = pair_counts.get(k, 0) + 1
            # intra-categoria?
            a_cat = a.split(':', 1)[0]
            b_cat = b.split(':', 1)[0]
            pair_intra[k] = (a_cat == b_cat)

    if not pair_counts:
        return {"pairs_by_count": [], "pairs_by_lift": [], "node_counts": node_counts, "N": N}

    # 2) Métricas
    def metrics_for_pair(k, cnt):
        a, b = k
        a_cnt = node_counts.get(a, 0)
        b_cnt = node_counts.get(b, 0)
        # probabilidades
        p_a = a_cnt / N if N else 0
        p_b = b_cnt / N if N else 0
        p_ab = cnt / N if N else 0
        # métricas
        jaccard = cnt / (a_cnt + b_cnt - cnt) if (a_cnt + b_cnt - cnt) > 0 else 0
        lift = (p_ab / (p_a * p_b)) if (p_a > 0 and p_b > 0) else 0
        conf_a_b = cnt / a_cnt if a_cnt > 0 else 0
        conf_b_a = cnt / b_cnt if b_cnt > 0 else 0

        a_cat, a_sub = a.split(':', 1)
        b_cat, b_sub = b.split(':', 1)

        return {
            "a": a, "b": b,
            "a_label": _format_subtype_label(a_cat, a_sub),
            "b_label": _format_subtype_label(b_cat, b_sub),
            "pair_label": f"{_format_subtype_label(a_cat, a_sub)} × {_format_subtype_label(b_cat, b_sub)}",
            "count": cnt,
            "support": round(p_ab, 4),
            "jaccard": round(jaccard, 4),
            "lift": round(lift, 4),
            "confidence_a_to_b": round(conf_a_b, 4),
            "confidence_b_to_a": round(conf_b_a, 4),
            "intra": pair_intra.get(k, False)
        }

    rows = [metrics_for_pair(k, cnt) for k, cnt in pair_counts.items()]

    # 3) Rankings
    # Top por contagem
    pairs_by_count = sorted(rows, key=lambda r: r["count"], reverse=True)[:top_n]

    # Top por lift (evita ruído exigindo contagem mínima)
    rows_for_lift = [r for r in rows if r["count"] >= min_count_for_lift]
    pairs_by_lift = sorted(rows_for_lift, key=lambda r: r["lift"], reverse=True)[:top_n]

    return {
        "pairs_by_count": pairs_by_count,
        "pairs_by_lift": pairs_by_lift,
        "node_counts": node_counts,
        "N": N
    }



def analyze_context(text):
    """Analisa o contexto linguístico para determinar o tipo de usuário"""
    score = {'passageiro': 0, 'motorista': 0}

    # Análise de pronomes e perspectiva
    if re.search(r'\b(eu|minha|meu)\s+motorista\b', text):
        score['motorista'] += 3

    if re.search(r'\b(o|a)\s+motorista\s+(me|minha)\b', text):
        score['passageiro'] += 3

    # Verificar perspectiva narrativa
    if re.search(r'\bmotorista\s+fez\b', text) or re.search(r'\bmotorista\s+disse\b', text):
        score['passageiro'] += 2

    if re.search(r'\bpassageiro\s+fez\b', text) or re.search(r'\bpassageiro\s+disse\b', text):
        score['motorista'] += 2

    # Verificar se fala sobre "meu carro" vs "o carro"
    if re.search(r'\bmeu\s+carro\b', text) or re.search(r'\bmeu\s+ve[ií]culo\b', text):
        score['motorista'] += 2

    if re.search(r'\bo\s+carro\s+do\s+motorista\b', text):
        score['passageiro'] += 2

    return score


def determine_user_type_manual(text, context):
    """Validação manual baseada em casos específicos identificados"""
    text_lower = text.lower()

    # CASOS ESPECÍFICOS IDENTIFICADOS NOS EXEMPLOS

    # Casos que são CLARAMENTE motoristas (classificados errado como passageiros)
    motorista_cases = [
        # Padrão: reclama sobre bloqueio de conta, comissão, etc.
        (r'bloqueado.*motorista', 5),
        (r'conta.*bloqueada.*motorista', 5),
        (r'comiss[ãa]o.*n[aã]o.*creditada', 4),
        (r'taxi\.rio.*bloqueia.*motorista', 5),
        (r'recebimento.*pendente', 4),
        (r'fui\s+bloqueado.*motorista', 5),

        # Padrão: fala sobre passageiros problematicos
        (r'passageira.*queria.*ar\s+ligado', 4),
        (r'passageiro.*n[aã]o.*pagou', 4),
        (r've[ií]culo.*danificado.*passageiro', 4),
    ]

    # Casos que são CLARAMENTE passageiros (classificados errado como motoristas)
    passageiro_cases = [
        # Padrão: experiência como usuário do serviço
        (r'chamei.*t[áa]xi', 5),
        (r'solicitei.*corrida', 5),
        (r'motorista.*n[aã]o.*chegou', 5),
        (r'motorista.*cancelou', 5),
        (r'taxista.*foi.*embora', 4),
        (r'deixou.*esperando', 4),

        # Padrão: problemas com motoristas específicos
        (r'motorista.*mal\s+educado', 4),
        (r'taxista.*grosso', 4),
        (r'motorista.*agressivo', 4),

        # Padrão: insegurança como passageiro
        (r'dados.*placa.*n[aã]o.*aparecem', 4),
        (r've[ií]culo.*sem.*identifica[çc][aã]o', 4),
        (r'inseguran[çc]a.*corrida', 4),
    ]

    # Verificar casos de motorista
    for pattern, score in motorista_cases:
        if re.search(pattern, text_lower):
            return 'motorista'

    # Verificar casos de passageiro
    for pattern, score in passageiro_cases:
        if re.search(pattern, text_lower):
            return 'passageiro'

    # Heurística baseada em palavras-chave contextuais
    palavras_motorista = [
        'comissão', 'ganhos', 'conta bloqueada', 'recebimento',
        'passageiro não pagou', 'veículo danificado', 'combustível'
    ]

    palavras_passageiro = [
        'chamei táxi', 'solicitei corrida', 'motorista não chegou',
        'taxista foi embora', 'valor corrida', 'cobrança indevida'
    ]

    for palavra in palavras_motorista:
        if palavra in text_lower:
            return 'motorista'

    for palavra in palavras_passageiro:
        if palavra in text_lower:
            return 'passageiro'

    return None


def determine_user_type(text, title=""):
    """Determina se a reclamação é de passageiro ou motorista com análise contextual"""
    if not text:
        return 'desconhecido'

    text_combined = f"{title} {text}".lower()

    # Primeiro: verificar validação manual para casos conhecidos
    manual_type = determine_user_type_manual(text_combined, "auto")
    if manual_type:
        return manual_type

    # Sistema de pontuação contextual
    passenger_score = 0
    driver_score = 0

    # ===== PADRÕES FORTES PARA MOTORISTAS =====
    driver_strong_patterns = [
        # Identificação explícita
        (r'\b(sou|somos)\s+motorista', 5),
        (r'\btrabalho\s+como\s+motorista', 5),
        (r'\bminha\s+conta\s+motorista', 5),
        (r'\bapp\s+motorista', 4),
        (r'\bplataforma\s+motorista', 4),

        # Questões financeiras/profissionais
        (r'\brecebimento\s+corrida', 4),
        (r'\bcomiss[ãa]o\s+n[aã]o\s+creditada', 4),
        (r'\bganhos\s+motorista', 4),
        (r'\brenda\s+motorista', 4),
        (r'\bconta\s+bloqueada\s+motorista', 4),
        (r'\bbloqueio\s+conta\s+motorista', 4),

        # Problemas com passageiros
        (r'\bpassageiro\s+n[aã]o\s+compareceu', 3),
        (r'\bcancelamento\s+passageiro', 3),
        (r'\bpassageiro\s+mal\s+educado', 3),
        (r'\bpassageiro\s+agressivo', 3),
        (r'\bpassageiro\s+n[aã]o\s+pagou', 3),

        # Veículo e manutenção
        (r'\bve[ií]culo\s+danificado\s+passageiro', 4),
        (r'\bcarro\s+danificado\s+passageiro', 4),
        (r'\bcombust[ií]vel\s+gasto', 3),
        (r'\bkm\s+rodado', 3),
        (r'\bmanuten[çc][aã]o\s+ve[ií]culo', 3),
    ]

    # ===== PADRÕES FORTES PARA PASSAGEIROS =====
    passenger_strong_patterns = [
        # Uso do serviço como cliente
        (r'\bchamei\s+t[áa]xi', 4),
        (r'\bsolicitei\s+corrida', 4),
        (r'\bpeguei\s+t[áa]xi', 4),
        (r'\bminha\s+corrida', 4),
        (r'\bpaguei\s+corrida', 4),
        (r'\bvalor\s+corrida', 4),

        # Problemas com motoristas
        (r'\bmotorista\s+n[aã]o\s+chegou', 4),
        (r'\bmotorista\s+cancelou', 4),
        (r'\bmotorista\s+mal\s+educado', 4),
        (r'\btaxista\s+grosso', 4),
        (r'\bmotorista\s+agressivo', 4),

        # Experiência do cliente
        (r'\bve[ií]culo\s+sujo', 3),
        (r'\bcarro\s+sujo', 3),
        (r'\bass[eé]dio', 5),
        (r'\bdiscrimina[çc][aã]o', 5),
        (r'\bfui\s+cobrad[oa]\s+indevidamente', 4),

        # Reclamações sobre app (como usuário)
        (r'\bapp\s+n[aã]o\s+funciona', 3),
        (r'\baplicativo\s+com\s+problema', 3),
    ]

    # ===== PADRÕES EXCLUSIVOS (evitam falsos positivos) =====
    exclusive_driver_patterns = [
        r'\bsou\s+motorista',
        r'\btrabalho\s+como\s+motorista',
        r'\bminha\s+conta\s+motorista',
        r'\bcomiss[ãa]o\s+retida',
        r'\bganhos\s+motorista'
    ]

    exclusive_passenger_patterns = [
        r'\bchamei\s+um\s+t[áa]xi',
        r'\bsolicitei\s+uma\s+corrida',
        r'\bpeguei\s+um\s+t[áa]xi',
        r'\bmotorista\s+me\s+deixou',
        r'\bfui\s+assediad[oa]'
    ]

    # ===== VERIFICAÇÃO DE PADRÕES EXCLUSIVOS =====
    for pattern in exclusive_driver_patterns:
        if re.search(pattern, text_combined, re.IGNORECASE):
            return 'motorista'

    for pattern in exclusive_passenger_patterns:
        if re.search(pattern, text_combined, re.IGNORECASE):
            return 'passageiro'

    # ===== PONTUAÇÃO POR PADRÕES FORTES =====
    for pattern, score in driver_strong_patterns:
        if re.search(pattern, text_combined, re.IGNORECASE):
            driver_score += score

    for pattern, score in passenger_strong_patterns:
        if re.search(pattern, text_combined, re.IGNORECASE):
            passenger_score += score

    # ===== ANÁLISE DE CONTEXTO E PRONOMES =====
    context_score = analyze_context(text_combined)
    passenger_score += context_score.get('passageiro', 0)
    driver_score += context_score.get('motorista', 0)

    # ===== DECISÃO FINAL =====
    if driver_score >= 5 and driver_score > passenger_score:
        return 'motorista'
    elif passenger_score >= 5 and passenger_score > driver_score:
        return 'passageiro'
    else:
        # Se ainda ambíguo, usar validação manual de fallback
        return determine_user_type_manual(text_combined, "fallback") or 'passageiro'


def extract_rating(text):
    """Tenta extrair uma avaliação numérica do texto"""
    if not text or not isinstance(text, str):
        return 3  # Default neutro

    patterns = [
        r'(nota|avaliação|rating)[\s:]*(\d+)',
        r'(\d+)[\s]*estrelas',
        r'avaliar[\s]*em[\s]*(\d+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                # Grupo 2 se existir, senão grupo 1
                rating_str = match.group(2) if match.lastindex >= 2 else match.group(1)
                rating = int(rating_str)
                return max(1, min(5, rating))
            except (ValueError, IndexError):
                continue

    # Se não encontrar rating explícito, inferir do sentimento
    sentiment = analyze_sentiment(text)
    if sentiment['label'] == 'NEGATIVO':
        return 1
    elif sentiment['label'] == 'POSITIVO':
        return 5
    else:
        return 3

def _parse_date_range(date_range_field) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Aceita 'DD/MM/YYYY - DD/MM/YYYY' vindo do form (como string ou lista) e
    devolve (start, end) como datetime (end no fim do dia).
    """
    if not date_range_field:
        return None, None
    if isinstance(date_range_field, list):
        date_str = date_range_field[0] if date_range_field else ''
    else:
        date_str = date_range_field or ''
    parts = [p.strip() for p in date_str.split('-')]
    if len(parts) != 2:
        return None, None
    try:
        start = datetime.strptime(parts[0].strip(), '%d/%m/%Y')
        end   = datetime.strptime(parts[1].strip(), '%d/%m/%Y')
        # considerar final do dia
        end   = end.replace(hour=23, minute=59, second=59)
        return start, end
    except Exception:
        return None, None

def analyze_complaints(filters=None):
    """Analisa as reclamações com base nos filtros do formulário."""
    filters = filters or {}
    query = {}

    # (1) Filtro de serviço: hoje só temos Taxi.Rio no dataset
    if filters.get('service'):
        if filters['service'] != 'taxi-rio':
            # Não há dados de outros serviços nesta coleção
            return []
        # Mantemos query em branco porque os campos de data/serviço na coleção são strings livres

    # Buscar tudo e filtrar em memória (campos vêm heterogêneos)
    try:
        complaints = list(collection.find(query))
    except Exception as e:
        logger.error(f"Erro ao buscar reclamações: {str(e)}")
        return []

    processed = []
    for complaint in complaints:
        data_hora = complaint.get('data-hora', '')
        if isinstance(data_hora, (float, int)): data_hora = str(data_hora)

        titulo = complaint.get('titulo_da_reclamacao', '')
        if isinstance(titulo, (float, int)): titulo = str(titulo)

        comentarios = complaint.get('comentarios', '')
        if isinstance(comentarios, (float, int)): comentarios = str(comentarios)

        local = complaint.get('local', '')
        if isinstance(local, (float, int)): local = str(local)

        status = complaint.get('status', '')
        if isinstance(status, (float, int)): status = str(status)

        item = {
            'id': str(complaint.get('_id')),
            'id_reclamacao': complaint.get('id_reclamacao'),
            'title': titulo or '',
            'description': comentarios or '',
            'location': local or '',
            'status': status or '',
            'date_str': data_hora or '',
            'service': 'taxi-rio',
            'raw_data': complaint
        }

        # Extrair data dd/mm/yyyy com robustez
        date_obj = None
        ds = item['date_str']
        if isinstance(ds, str) and ds:
            try:
                date_part = ds.split(' ')[0]
                date_obj = datetime.strptime(date_part, '%d/%m/%Y')
            except Exception:
                try:
                    if '/' in ds:
                        date_obj = datetime.strptime(ds, '%d/%m/%Y')
                except Exception:
                    date_obj = None
        item['date'] = date_obj

        # Tipo de usuário, severidade, categorias, sentimento, rating
        text_all = f"{item['title']} {item['description']}".lower()
        item['user_type'] = determine_user_type(text_all)
        item['severity'] = determine_severity(item)
        item['problem_categories'] = categorize_problems(item)
        item['sentiment'] = analyze_sentiment(text_all)
        item['rating'] = extract_rating(text_all)

        processed.append(item)

    # (2) Aplicar filtros do formulário em memória
    start, end = _parse_date_range(filters.get('date_range'))
    if start and end:
        processed = [c for c in processed if c.get('date') and start <= c['date'] <= end]

    if filters.get('user_type'):
        processed = [c for c in processed if c.get('user_type') == filters['user_type']]

    if filters.get('severity'):
        processed = [c for c in processed if c.get('severity') == filters['severity']]

    return processed



def is_critical_complaint(complaint):
    """
    Determina se é reclamação crítica de PASSAGEIRO:
    - conteúdo com indícios de assédio/agressão/discriminação/redlining, OU
    - severidade já classificada como 'crítica', OU
    - categoria 'discriminacao' detectada.
    (Não exige sentimento NEGATIVO para não descartar relatos objetivos.)
    """
    if complaint.get('user_type') != 'passageiro':
        return False

    severity = (complaint.get('severity') or '').lower()
    categories = complaint.get('problem_categories', [])
    text = f"{complaint.get('title','')} {complaint.get('description','')}".lower()

    # Termos críticos (acentos/variações cobertos)
    critical_terms = [
        r'ass[eé]dio', r'agress[aã]o', r'viol[eê]ncia',
        r'discrimina[çc][aã]o', r'racismo', r'homofobia', r'transfobia',
        r'redlining', r'favela.*discrimina[çc][aã]o', r'periferia.*preconceito'
    ]

    # Critério 1: termos explícitos
    for pat in critical_terms:
        if re.search(pat, text):
            return True

    # Critério 2: categoria semântica
    if 'discriminacao' in categories:
        return True

    # Critério 3: severidade classificada como crítica
    if severity == 'crítica':
        return True

    return False



def generate_stats(complaints):
    """Gera estatísticas agregadas das reclamações"""
    if not complaints:
        return {}

    # Estatísticas básicas
    stats = {
        'total_complaints': len(complaints),
        'services': defaultdict(int),
        'user_types': defaultdict(int),
        'severities': defaultdict(int),
        'problem_categories': defaultdict(int),
        'sentiments': defaultdict(int),
        'statuses': defaultdict(int),
        'by_year': defaultdict(lambda: defaultdict(int)),
        'by_month': defaultdict(lambda: defaultdict(int))
    }

    # Processar cada reclamação
    for complaint in complaints:
        # Contagem por serviço
        stats['services'][complaint['service']] += 1

        # Contagem por tipo de usuário
        stats['user_types'][complaint.get('user_type', 'desconhecido')] += 1

        # Contagem por severidade
        stats['severities'][complaint.get('severity', 'desconhecida')] += 1

        # Contagem por status
        stats['statuses'][complaint.get('status', 'desconhecido')] += 1

        # Contagem por categoria de problema
        for category in complaint.get('problem_categories', []):
            stats['problem_categories'][category] += 1

        # Contagem por sentimento
        stats['sentiments'][complaint.get('sentiment', {}).get('label', 'NEUTRO')] += 1

        # Contagem por ano e mês
        if complaint.get('date'):
            date = complaint['date']
            try:
                year = date.year
                month_year = f"{date.year}-{date.month:02d}"

                stats['by_year'][year]['total'] += 1
                stats['by_year'][year][complaint.get('severity', 'desconhecida')] += 1

                stats['by_month'][month_year]['total'] += 1
                stats['by_month'][month_year][complaint.get('severity', 'desconhecida')] += 1
            except AttributeError:
                # Se date não for um objeto datetime válido
                continue

    return stats


def generate_time_series_plot(stats, complaints):
    """Gera um gráfico de barras das reclamações por mês com tooltips e melhor visual"""
    if not stats.get('by_month'):
        return None

    try:
        # Preparar dados
        df = pd.DataFrame.from_dict(stats['by_month'], orient='index')

        if df.empty:
            return None

        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Preencher meses faltantes com zero
        date_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq='MS')
        df = df.reindex(date_range, fill_value=0)

        # Garantir que todas as severidades existam no DataFrame
        severities = ['baixa', 'média', 'alta', 'crítica']
        for severity in severities:
            if severity not in df.columns:
                df[severity] = 0

        # Calcular estatísticas para tooltips
        total_complaints = stats.get('total_complaints', 0)
        critical_count = stats.get('severities', {}).get('crítica', 0)
        critical_percentage = (critical_count / total_complaints * 100) if total_complaints > 0 else 0

        # Calcular distribuição por tipo de reclamante
        user_type_distribution = defaultdict(int)
        for complaint in complaints:
            user_type = complaint.get('user_type', 'desconhecido')
            user_type_distribution[user_type] += 1

        # Configuração de estilo profissional
        plt.style.use('default')
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 12

        # Criar figura com tamanho adequado
        fig, ax = plt.subplots(figsize=(16, 10))

        # Cores profissionais
        colors = ['#4CAF50', '#FFC107', '#FF9800', '#F44336']  # Verde, Amarelo, Laranja, Vermelho
        severities_ordered = ['baixa', 'média', 'alta', 'crítica']
        severity_labels = ['Baixa', 'Média', 'Alta', 'Crítica']

        # Calcular valores totais para tooltips
        total_values = df[severities_ordered].sum(axis=1)

        # Criar barras empilhadas
        bottom = None
        bars = []

        for i, severity in enumerate(severities_ordered):
            values = df[severity].values
            if bottom is None:
                bar = ax.bar(range(len(df)), values,
                             label=severity_labels[i],
                             color=colors[i],
                             alpha=0.85,
                             edgecolor='white',
                             linewidth=0.5,
                             width=0.8)
                bottom = values
            else:
                bar = ax.bar(range(len(df)), values, bottom=bottom,
                             label=severity_labels[i],
                             color=colors[i],
                             alpha=0.85,
                             edgecolor='white',
                             linewidth=0.5,
                             width=0.8)
                bottom += values
            bars.append(bar)

        # Configurações do gráfico
        title_text = (f'Evolução Temporal das Reclamações - Taxi.Rio\n'
                      f'Total: {total_complaints} reclamações | '
                      f'Críticas: {critical_count} ({critical_percentage:.1f}%)')

        ax.set_title(title_text, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Período', fontsize=14, fontweight='bold')
        ax.set_ylabel('Quantidade de Reclamações', fontsize=14, fontweight='bold')

        # Configurar eixo X com datas formatadas
        x_positions = range(len(df))
        x_labels = [date.strftime('%b/%Y') for date in df.index]
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, rotation=45, ha='right')

        # Adicionar grid
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_axisbelow(True)

        # Adicionar legenda
        ax.legend(title='Nível de Severidade', title_fontsize=12, fontsize=11,
                  loc='upper left', bbox_to_anchor=(1, 1))

        # Adicionar valores totais no topo das barras
        for i, total in enumerate(total_values):
            if total > 0:
                ax.text(i, total + 0.1, f'{int(total)}',
                        ha='center', va='bottom', fontsize=10, fontweight='bold')

        # Adicionar informações de tooltip como texto adicional
        user_type_text = " | ".join([f"{k.capitalize()}: {v}" for k, v in user_type_distribution.items()])

        # Adicionar caixa de informações
        info_text = (f"Distribuição: {user_type_text}\n"
                     f"Período: {df.index.min().strftime('%b/%Y')} - {df.index.max().strftime('%b/%Y')}")

        ax.text(0.02, 0.98, info_text, transform=ax.transAxes, fontsize=9,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        # Ajustar layout para acomodar a legenda
        plt.tight_layout(rect=[0, 0, 0.85, 1])  # Deixa espaço para legenda à direita

        # Salvar gráfico em alta qualidade
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight')
        buffer.seek(0)
        plt.close()

        return base64.b64encode(buffer.read()).decode('utf-8')

    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de linha do tempo: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def generate_time_series_data(complaints):
    """Gera dados para o gráfico de série temporal por severidade e tipo de reclamante"""
    time_series_data = {
        'labels': [],
        'passenger_baixa': [], 'passenger_media': [], 'passenger_alta': [], 'passenger_critica': [],
        'motorista_baixa': [], 'motorista_media': [], 'motorista_alta': [], 'motorista_critica': []
    }

    # Agrupar reclamações por mês
    monthly_data = defaultdict(lambda: {
        'passenger_baixa': 0, 'passenger_media': 0, 'passenger_alta': 0, 'passenger_critica': 0,
        'motorista_baixa': 0, 'motorista_media': 0, 'motorista_alta': 0, 'motorista_critica': 0
    })

    for complaint in complaints:
        if not complaint.get('date'):
            continue

        # Formatar chave do mês (YYYY-MM)
        month_key = complaint['date'].strftime('%Y-%m')
        user_type = complaint.get('user_type', 'desconhecido')
        severity = complaint.get('severity', 'baixa')

        # Contabilizar por tipo e severidade
        if user_type == 'passageiro':
            if severity == 'baixa':
                monthly_data[month_key]['passenger_baixa'] += 1
            elif severity == 'média':
                monthly_data[month_key]['passenger_media'] += 1
            elif severity == 'alta':
                monthly_data[month_key]['passenger_alta'] += 1
            elif severity == 'crítica':
                monthly_data[month_key]['passenger_critica'] += 1
        elif user_type == 'motorista':
            if severity == 'baixa':
                monthly_data[month_key]['motorista_baixa'] += 1
            elif severity == 'média':
                monthly_data[month_key]['motorista_media'] += 1
            elif severity == 'alta':
                monthly_data[month_key]['motorista_alta'] += 1
            elif severity == 'crítica':
                monthly_data[month_key]['motorista_critica'] += 1

    # Ordenar por mês e preparar dados para o gráfico
    sorted_months = sorted(monthly_data.keys())
    for month in sorted_months:
        time_series_data['labels'].append(month)
        data = monthly_data[month]
        time_series_data['passenger_baixa'].append(data['passenger_baixa'])
        time_series_data['passenger_media'].append(data['passenger_media'])
        time_series_data['passenger_alta'].append(data['passenger_alta'])
        time_series_data['passenger_critica'].append(data['passenger_critica'])
        time_series_data['motorista_baixa'].append(data['motorista_baixa'])
        time_series_data['motorista_media'].append(data['motorista_media'])
        time_series_data['motorista_alta'].append(data['motorista_alta'])
        time_series_data['motorista_critica'].append(data['motorista_critica'])

    return time_series_data


def generate_problem_category_plot(complaints, user_type=None):
    """Gera um gráfico de categorias de problemas baseado nas reclamações"""
    if not complaints:
        return None

    # Filtrar por tipo de usuário se especificado
    categories = defaultdict(int)
    for complaint in complaints:
        if user_type and complaint.get('user_type') != user_type:
            continue

        for category in complaint.get('problem_categories', []):
            categories[category] += 1

    if not categories:
        return None

    # Criar gráfico
    plt.figure(figsize=(10, 6))
    plt.bar(categories.keys(), categories.values())
    plt.title(f'Categorias de Problemas{" - " + user_type.capitalize() if user_type else ""}')
    plt.xlabel('Categoria')
    plt.ylabel('Número de Reclamações')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # Salvar gráfico em buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close()

    return base64.b64encode(buffer.read()).decode('utf-8')


def generate_user_type_plot(complaints):
    """Gera gráfico de pizza para distribuição por tipo de reclamante"""
    if not complaints:
        return None

    try:
        user_types = defaultdict(int)
        for complaint in complaints:
            user_type = complaint.get('user_type', 'desconhecido')
            user_types[user_type] += 1

        # Se só há um tipo, não vale a pena mostrar o gráfico
        if len(user_types) <= 1:
            return None

        # Configurar estilo
        plt.style.use('default')
        plt.rcParams['font.family'] = 'DejaVu Sans'

        fig, ax = plt.subplots(figsize=(10, 8))

        # Cores e labels
        labels = []
        sizes = []
        for ut, count in user_types.items():
            labels.append(f"{ut.capitalize()} ({count})")
            sizes.append(count)

        colors = ['#FF6B6B', '#4ECDC4', '#FFE66D', '#C7C7C7']

        # Gráfico de pizza
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors[:len(labels)],
                                          autopct='%1.1f%%', startangle=90,
                                          textprops={'fontsize': 12})

        ax.set_title('Distribuição por Tipo de Reclamante', fontsize=16, fontweight='bold', pad=20)
        ax.axis('equal')

        # Melhorar aparência
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')

        plt.tight_layout()

        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        plt.close()

        return base64.b64encode(buffer.read()).decode('utf-8')

    except Exception as e:
        logger.error(f"Erro ao gerar gráfico de tipos de reclamante: {str(e)}")
        return None


@reclame_aqui_app.route('/', methods=['GET', 'POST'])
def show_analysis():
    """Rota principal para exibir a análise"""
    try:
        # 1) Filtros do formulário
        filters = {
            'service'   : request.form.get('service'),
            'date_range': request.form.getlist('date_range'),
            'user_type' : request.form.get('user_type'),
            'severity'  : request.form.get('severity')
        }

        # 2) Buscar e preparar dados
        complaints = analyze_complaints(filters)
        stats = generate_stats(complaints)

        # 3) Problemas por tipo de reclamante (para os gráficos de barras)
        from collections import defaultdict
        passenger_problems = defaultdict(int)
        driver_problems = defaultdict(int)

        for c in complaints:
            user_type = c.get('user_type', 'desconhecido')
            for category in c.get('problem_categories', []):
                if user_type == 'passageiro':
                    passenger_problems[category] += 1
                elif user_type == 'motorista':
                    driver_problems[category] += 1

        # 3b) Agregação por SUBTIPOS (total — somando todos os reclamantes)
        problem_subtypes_total = {
            "discriminacao": defaultdict(int),
            "funcionamento_app": defaultdict(int),
            "problemas_servico": defaultdict(int),
        }
        # --- NOVO: resumo de multiclasse ---
        macro_hist = {0: 0, 1: 0, 2: 0, 3: 0}
        cooc_pairs = {
            "discriminacao_funcionamento_app": 0,
            "discriminacao_problemas_servico": 0,
            "funcionamento_app_problemas_servico": 0,
            "todos_tres": 0
        }
        multi_macro_count = 0
        multi_subtype_count = 0
        total_subtypes = 0
        max_subtypes_per_complaint = 0

        for c in complaints:
            # subtipos encontrados neste item
            subtypes = extract_problem_subtypes(c)
            total_subtypes += len(subtypes)
            if len(subtypes) >= 2:
                multi_subtype_count += 1
            max_subtypes_per_complaint = max(max_subtypes_per_complaint, len(subtypes))

            # distribuição por macro-categorias
            macros = set(c.get('problem_categories', []))  # já vem de categorize_problems
            n = len(macros)
            macro_hist[n] = macro_hist.get(n, 0) + 1
            if n >= 2:
                multi_macro_count += 1

            # coocorrências (pares e tripla)
            has_disc = 'discriminacao' in macros
            has_app  = 'funcionamento_app' in macros
            has_srv  = 'problemas_servico' in macros
            if has_disc and has_app:
                cooc_pairs["discriminacao_funcionamento_app"] += 1
            if has_disc and has_srv:
                cooc_pairs["discriminacao_problemas_servico"] += 1
            if has_app and has_srv:
                cooc_pairs["funcionamento_app_problemas_servico"] += 1
            if has_disc and has_app and has_srv:
                cooc_pairs["todos_tres"] += 1

            # alimentar totais por subtipo (para os gráficos 3B)
            for (cat, subtype) in subtypes:
                if cat in problem_subtypes_total:
                    problem_subtypes_total[cat][subtype] += 1

        avg_subtypes = (total_subtypes / len(complaints)) if complaints else 0.0

        multi_class_summary = {
            "macro_hist": {str(k): v for k, v in macro_hist.items()},  # stringify chaves p/ JSON
            "multi_macro_count": multi_macro_count,
            "cooc_pairs": cooc_pairs,
            "multi_subtype_count": multi_subtype_count,
            "avg_subtypes_per_item": round(avg_subtypes, 2),
            "max_subtypes_per_item": max_subtypes_per_complaint,
            "total_items": len(complaints)
        }

        # >>> NOVO: coocorrência entre subtipos
        subtype_cooccurrence = compute_subtype_cooccurrence(complaints, top_n=15, min_count_for_lift=2)

        # 4) Série temporal
        time_series_data = generate_time_series_data(complaints)

        # 5) Listas dos cards
        critical_passenger_complaints = [
            c for c in complaints
            if c.get('user_type') == 'passageiro' and is_critical_complaint(c)
        ]
        driver_complaints = [
            c for c in complaints
            if c.get('user_type') == 'motorista'
        ]

        # 6) Ordenação por gravidade + data
        severity_rank = {'baixa': 0, 'média': 1, 'media': 1, 'alta': 2, 'crítica': 3, 'critica': 3}
        def _rank(c):
            sev = (c.get('severity') or '').lower()
            if sev == 'media': sev = 'média'
            d = c.get('date') or datetime.min
            return (severity_rank.get(sev, -1), d)

        critical_passenger_complaints.sort(key=_rank, reverse=True)
        driver_complaints.sort(key=_rank, reverse=True)

        # 7) Render
        return render_template(
            'analise_reclame_aqui.html',
            stats=stats,
            filters=filters,
            passenger_problems=dict(passenger_problems),
            driver_problems=dict(driver_problems),
            time_series_data=time_series_data,
            user_type_data=stats.get('user_types', {}),
            problem_subtypes_total={k: dict(v) for k, v in problem_subtypes_total.items()},
            multi_class_summary=multi_class_summary,
            subtype_cooccurrence=subtype_cooccurrence,
            critical_passenger_complaints=critical_passenger_complaints[:10],
            driver_complaints=driver_complaints[:10]
        )

    except Exception as e:
        logger.error(f"Erro na rota de análise: {str(e)}")
        return render_template('error.html', error=f"Erro ao analisar reclamações: {str(e)}"), 500



@reclame_aqui_app.route('/debug_fields')
def debug_fields():
    """Debug detalhado dos campos e tipos"""
    try:
        sample_complaints = list(collection.find().limit(5))
        field_analysis = {}

        for complaint in sample_complaints:
            for field, value in complaint.items():
                if field not in field_analysis:
                    field_analysis[field] = {
                        'types': defaultdict(int),
                        'values': [],
                        'count': 0
                    }
                field_analysis[field]['types'][type(value).__name__] += 1
                field_analysis[field]['values'].append(str(value)[:100])  # Limitar tamanho
                field_analysis[field]['count'] += 1

        return jsonify({
            'field_analysis': field_analysis,
            'sample_count': len(sample_complaints)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500