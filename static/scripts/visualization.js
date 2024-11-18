document.addEventListener('DOMContentLoaded', () => {
    const map = L.map('map').setView([-22.9068, -43.1729], 12); // Coordenadas iniciais (Rio de Janeiro)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    document.getElementById('filterForm').addEventListener('submit', async (event) => {
        event.preventDefault();

        const date = document.getElementById('date').value;
        const start_time = document.getElementById('start_time').value;
        const end_time = document.getElementById('end_time').value;
        const status = document.getElementById('status').value;
        const radius = document.getElementById('radius').value;

        const url = new URL('https://mobilidade.onrender.com/events-near-cancellations');
        url.searchParams.append('date', date);
        url.searchParams.append('start_time', start_time);
        url.searchParams.append('end_time', end_time);
        if (status) url.searchParams.append('status', status);
        url.searchParams.append('radius', radius);

        try {
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

            const tableBody = document.querySelector('#data-table tbody');
            tableBody.innerHTML = ''; // Limpar tabela

            if (data.message) {
                alert(data.message);

                data.recent_events.forEach((event) => {
                    // Adicionar eventos recentes ao mapa
                    L.circle(event.event_location, {
                        radius: 500,
                        color: 'blue'
                    }).addTo(map)
                        .bindPopup(`Evento: ${event.event_name}<br>Endereço: ${event.event_address}<br>Bairro: ${event.event_neighborhood}`);

                    // Adicionar eventos recentes à tabela
                    const row = `
                        <tr>
                            <td>-</td>
                            <td>-</td>
                            <td>-</td>
                            <td>${event.event_address}</td>
                            <td>${event.event_neighborhood}</td>
                            <td>${event.event_name}</td>
                            <td>-</td>
                            <td>-</td>
                        </tr>
                    `;
                    tableBody.innerHTML += row;
                });

                document.getElementById('data-table').style.display = 'block';
                return;
            }

            // Adicionar dados ao mapa e à tabela
            data.forEach((item) => {
                L.marker(item.cancel_location).addTo(map)
                    .bindPopup(`Cancelamento: ${item.cancel_address}<br>Bairro: ${item.cancel_bairro}`);

                L.circle(item.event_location, {
                    radius: 500,
                    color: 'red'
                }).addTo(map)
                    .bindPopup(`Evento: ${item.event_name}<br>Endereço: ${item.event_address}<br>Bairro: ${item.event_neighborhood}`);

                const row = `
                    <tr>
                        <td>${item.cancel_id}</td>
                        <td>${item.cancel_address}</td>
                        <td>${item.cancel_bairro}</td>
                        <td>${item.event_address}</td>
                        <td>${item.event_neighborhood}</td>
                        <td>${item.event_name}</td>
                        <td>${item.distance_km.toFixed(2)}</td>
                        <td>${item.time_diff_min.toFixed(2)}</td>
                    </tr>
                `;
                tableBody.innerHTML += row;
            });

            document.getElementById('data-table').style.display = 'block';
        } catch (error) {
            console.error('Erro ao buscar dados:', error);
            alert('Erro ao buscar dados. Verifique os filtros e tente novamente.');
        }
    });
});