import os  # Adicione esta linha
from pymongo import MongoClient
from haversine import haversine, Unit
from datetime import datetime, timedelta
import logging

# Configuração do MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]


def get_event_correlations(radius, date, start_time, end_time, status_filter):
    try:
        # Converter data e hora para objetos datetime
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

        logging.info(f"Consultando cancelamentos entre {start_datetime} e {end_datetime}...")

        # Consulta para cancelamentos
        query = {
            "created_at": {
                "$gte": start_datetime,
                "$lte": end_datetime
            }
        }
        if status_filter:
            query["status"] = {"$regex": status_filter, "$options": "i"}

        cancellations = list(db.rides_original.find(query))
        logging.info(f"Número de cancelamentos encontrados: {len(cancellations)}")

        # Consulta para eventos
        event_query = {
            "date": {
                "$gte": start_datetime,
                "$lte": end_datetime
            }
        }
        events = list(db.events.find(event_query))
        logging.info(f"Número de eventos encontrados: {len(events)}")

        # Caso nenhum evento ou cancelamento seja encontrado
        if not cancellations and not events:
            logging.warning("Nenhum dado encontrado para os filtros aplicados.")
            return {"message": "Nenhum dado encontrado para os filtros aplicados."}

        # Lógica de correlação entre cancelamentos e eventos
        correlations = []
        for cancel in cancellations:
            origin = (cancel['origin_lat'], cancel['origin_lng'])
            for event in events:
                event_loc = (event['latitude'], event['longitude'])
                distance = haversine(origin, event_loc)  # Distância em km
                time_diff = abs((event['date'] - cancel['created_at']).total_seconds()) / 60  # Diferença em minutos

                if distance <= radius:
                    correlations.append({
                        "cancel_id": cancel["_id"],
                        "cancel_location": origin,
                        "cancel_time": cancel["created_at"],
                        "event_location": event_loc,
                        "event_time": event["date"],
                        "distance_km": distance,
                        "time_diff_min": time_diff
                    })

        return correlations if correlations else {"message": "Nenhum evento correlacionado encontrado."}

    except Exception as e:
        logging.error(f"Erro ao buscar correlações: {e}")
        raise