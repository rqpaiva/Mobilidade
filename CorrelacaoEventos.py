from flask import Flask, request, jsonify
from pymongo import MongoClient
from haversine import haversine, Unit
from datetime import datetime, timedelta

# Configurações do MongoDB e variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")

app = Flask(__name__)

# Conexão com MongoDB
client = MongoClient(MONGO_URI)
db = client["mobility_data"]

@app.route('/events-near-cancellations', methods=['GET'])
def get_events_near_cancellations():
    # Parâmetros recebidos
    radius = float(request.args.get('radius', 5))  # Raio em km
    date = request.args.get('date')  # Exemplo: '2024-11-13'
    start_time = request.args.get('start_time', '00:00')
    end_time = request.args.get('end_time', '23:59')
    status_filter = request.args.get('status', None)  # Ex.: "cancelada pelo taxista"
    
    # Convertendo data e hora
    start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
    
    # Buscar cancelamentos
    query = {"status": {"$regex": status_filter}} if status_filter else {}
    query.update({"created_at": {"$gte": start_datetime, "$lte": end_datetime}})
    cancellations = list(db.rides_original.find(query))
    
    # Buscar eventos próximos
    events = list(db.events.find())
    nearby_events = []
    
    for cancel in cancellations:
        origin = (cancel['origin_lat'], cancel['origin_lng'])
        for event in events:
            event_loc = (event['latitude'], event['longitude'])
            distance = haversine(origin, event_loc, unit=Unit.KILOMETERS)
            time_diff = abs((event['date'] - cancel['created_at']).total_seconds()) / 60  # Minutos
            if distance <= radius and time_diff <= 15:  # Ajustar tempo e raio
                nearby_events.append({
                    "cancel_id": cancel['_id'],
                    "cancel_location": origin,
                    "event_location": event_loc,
                    "event_name": event['mainReason']['name'],
                    "distance_km": distance,
                    "time_diff_min": time_diff
                })

    return jsonify(nearby_events)

if __name__ == '__main__':
    app.run(debug=True)
