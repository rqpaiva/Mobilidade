document.addEventListener('DOMContentLoaded', () => {
    // Inicializar mapa
    const map = L.map('map').setView([-22.9068, -43.1729], 12); // Coordenadas iniciais (Rio de Janeiro)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Evento de submissão do formulário
    document.getElementById('filterForm').addEventListener('submit', async (event) => {
        event.preventDefault();

        // Obter valores dos filtros
        const date = document.getElementById('date').value;
        const start_time = document.getElementById('start_time').value;
        const end_time = document.getElementById('end_time').value;
        const status = document.getElementById('status').value;
        const radius = document.getElementById('radius').value;

        // Construir URL para o backend
        const url = new URL('https://mobilidade.onrender.com/events-near-cancellations');
        url.searchParams.append('date', date);
        url.searchParams.append('start_time', start_time);
        url.searchParams.append('end_time', end_time);
        if (status) url.searchParams.append('status', status);
        url.searchParams.append('radius', radius);

        try {
            // Fazer a requisição ao backend
            const response = await fetch(url);
            const data = await response.json();

            // Limpar camadas anteriores do mapa
            map.eachLayer((layer) => {
                if (!!layer.toGeoJSON) {
                    map.removeLayer(layer);
                }
            });

            // Adicionar novamente o OpenStreetMap
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);

            // Adicionar dados ao mapa
            if (data.length === 0) {
                alert('Nenhum dado encontrado para os filtros aplicados.');
                return;
            }

            data.forEach((item) => {
                // Local do cancelamento
                L.marker(item.cancel_location).addTo(map)
                    .bindPopup(`Cancelamento: ${item.distance_km.toFixed(2)} km do evento`);

                // Local do evento
                L.circle(item.event_location, {
                    radius: 500, // Raio em metros
                    color: 'red'
                }).addTo(map)
                    .bindPopup(`Evento: ${item.event_name}`);
            });
        } catch (error) {
            console.error('Erro ao buscar dados:', error);
            alert('Erro ao buscar dados. Verifique os filtros e tente novamente.');
        }
    });
});