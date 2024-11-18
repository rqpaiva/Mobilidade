import os
from pymongo import MongoClient
from haversine import haversine
from datetime import datetime, timedelta
import logging
import traceback


# Configuração do MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

def get_event_correlations(radius, date, start_time, end_time, status_filter):
    try:
        # Conversão de tipos
        radius = float(radius)
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

        logging.info(f"Parâmetros recebidos: radius={radius}, date={date}, start_time={start_time}, end_time={end_time}, status={status_filter}")

        # Consulta para cancelamentos
        query = {
            "created_at": {"$gte": start_datetime, "$lte": end_datetime}
        }
        if status_filter:
            query["status"] = {"$regex": status_filter, "$options": "i"}

        cancellations = list(db.rides_original.find(query))
        logging.info(f"Número de cancelamentos encontrados: {len(cancellations)}")

        # Consulta para eventos
        event_query = {
            "date": {"$gte": start_datetime, "$lte": end_datetime}
        }
        events = list(db.events.find(event_query))
        logging.info(f"Número de eventos encontrados: {len(events)}")

        # Caso nenhum evento seja encontrado, buscar eventos recentes (últimos 7 dias)
        if not events:
            recent_date = start_datetime - timedelta(days=7)
            recent_events_query = {
                "date": {"$gte": recent_date, "$lte": start_datetime}
            }
            recent_events = list(db.events.find(recent_events_query))
            logging.info(f"Número de eventos recentes encontrados: {len(recent_events)}")
            return {
                "message": "Nenhum evento identificado na data e horário da corrida. Seguem eventos dos últimos 7 dias na região.",
                "recent_events": [
                    {
                        "event_address": event["address"],
                        "event_neighborhood": event.get("neighborhood", "-"),
                        "event_name": event.get("name", "-"),
                        "event_location": [event.get("latitude"), event.get("longitude")]
                    } for event in recent_events
                ]
            }

        # Correlacionar cancelamentos com eventos
        correlations = []
        for cancel in cancellations:
            origin = (cancel['origin_lat'], cancel['origin_lng'])
            for event in events:
                event_loc = (event['latitude'], event['longitude'])
                distance = haversine(origin, event_loc)  # Distância em km
                time_diff = abs((event['date'] - cancel['created_at']).total_seconds()) / 60  # Diferença em minutos

                if distance <= radius:
                    correlations.append({
                        "cancel_id": str(cancel["_id"]),
                        "cancel_address": cancel.get("road_client", "-"),
                        "cancel_bairro": cancel.get("suburb_client", "-"),
                        "event_address": event.get("address", "-"),
                        "event_neighborhood": event.get("neighborhood", "-"),
                        "event_name": event.get("name", "-"),
                        "distance_km": distance,
                        "time_diff_min": time_diff
                    })

        return correlations if correlations else {"message": "Nenhum evento correlacionado encontrado."}

    except Exception as e:
        logging.error(f"Erro ao buscar correlações: {e}")
        logging.error(traceback.format_exc())  # Adicionar rastreamento detalhado
        return {"error": f"Erro interno no servidor: {e}"}