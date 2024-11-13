from pymongo import MongoClient
from haversine import haversine, Unit
from datetime import datetime, timedelta
import logging

# Configuração do MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

def get_event_correlations(radius, date, start_time, end_time, status_filter):
    """
    Função para correlacionar eventos com cancelamentos de corridas.
    """
    try:
        # Formatar data e hora
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

        # Consultar cancelamentos no MongoDB
        query = {"created_at": {"$gte": start_datetime, "$lte": end_datetime}}
        if status_filter:
            query["status"] = {"$regex": status_filter}

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
                        "event_location": event_loc,
                        "event_name": event['mainReason']['name'],
                        "distance_km": distance,
                        "time_diff_min": time_diff
                    })
        return nearby_events
    except Exception as e:
        logging.error(f"Erro na função de correlação de eventos: {e}")
        raise