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
        # Formatar data e hora
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

        # Consultar cancelamentos no MongoDB
        query = {"created_at": {"$gte": start_datetime, "$lte": end_datetime}}
        if status_filter:
            query["status"] = {"$regex": status_filter, "$options": "i"}

        cancellations = list(db.rides_original.find(query))
        events = list(db.events.find())

        nearby_events = []
        for cancel in cancellations:
            origin = (cancel['origin_lat'], cancel['origin_lng'])
            for event in events:
                event_loc = (event['latitude'], event['longitude'])
                distance = haversine(origin, event_loc, unit=Unit.KILOMETERS)
                time_diff = abs((event['date'] - cancel['created_at']).total_seconds()) / 60  # Em minutos

                if distance <= radius and time_diff <= 15:  # 15 minutos de intervalo
                    nearby_events.append({
                        "cancel_id": cancel['_id'],
                        "cancel_location": origin,
                        "cancel_address": cancel.get('road_client', 'Desconhecido'),
                        "cancel_bairro": cancel.get('suburb_client', 'Desconhecido'),
                        "event_location": event_loc,
                        "event_address": event.get('address', 'Desconhecido'),
                        "event_neighborhood": event.get('neighborhood', 'Desconhecido'),
                        "event_locality": event.get('locality', 'Desconhecido'),
                        "event_name": event['mainReason']['name'],
                        "distance_km": distance,
                        "time_diff_min": time_diff
                    })

        # Caso nenhum evento seja encontrado, buscar eventos nos últimos 7 dias
        if not nearby_events:
            seven_days_ago = start_datetime - timedelta(days=7)
            recent_events_query = {"date": {"$gte": seven_days_ago, "$lte": start_datetime}}
            recent_events = list(db.events.find(recent_events_query))

            return {
                "message": "Nenhum evento identificado na data e horário da corrida. Seguem eventos dos últimos 7 dias.",
                "recent_events": [
                    {
                        "event_location": (event['latitude'], event['longitude']),
                        "event_address": event.get('address', 'Desconhecido'),
                        "event_neighborhood": event.get('neighborhood', 'Desconhecido'),
                        "event_locality": event.get('locality', 'Desconhecido'),
                        "event_name": event['mainReason']['name'],
                        "event_date": event['date']
                    }
                    for event in recent_events
                ]
            }

        return nearby_events
    except Exception as e:
        logging.error(f"Erro na função de correlação de eventos: {e}")
        raise