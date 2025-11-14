// Gráfico de distribuição de scores atualizado
function initCharts(results) {
    // Gráfico de distribuição de scores
    const scoreCtx = document.getElementById('scoreDistributionChart').getContext('2d');
    new Chart(scoreCtx, {
        type: 'bar',
        data: {
            labels: ['1-2', '2-3', '3-4', '4-5'],
            datasets: [{
                label: 'Distribuição de Avaliações',
                data: [
                    results.score_distribution['1-2'],
                    results.score_distribution['2-3'],
                    results.score_distribution['3-4'],
                    results.score_distribution['4-5']
                ],
                backgroundColor: [
                    'rgba(220, 53, 69, 0.7)',
                    'rgba(255, 193, 7, 0.7)',
                    'rgba(25, 135, 84, 0.7)',
                    'rgba(13, 110, 253, 0.7)'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: `Distribuição de Avaliações dos Motoristas (Total: ${results.all_drivers_count})`
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y} motoristas (${((context.parsed.y / results.all_drivers_count) * 100).toFixed(1)}%)`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Quantidade de Motoristas'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Faixa de Avaliação'
                    }
                }
            }
        }
    });


    // Gráfico de tipos de Problemas
    const discCtx = document.getElementById('discriminationChart').getContext('2d');
    new Chart(discCtx, {
        type: 'pie',
        data: {
            labels: Object.keys(results.problem_stats),
            datasets: [{
                label: 'Tipos de Problemas Encontrados',
                data: Object.values(results.problem_stats),
                backgroundColor: [
                    '#dc3545', '#fd7e14', '#ffc107', '#198754',
                    '#0dcaf0', '#6f42c1', '#d63384', '#20c997'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Tipos de Problemas Encontrados'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const value = context.raw;
                            const percentage = Math.round((value / total) * 100);
                            return `${context.label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Inicializar o mapa de satisfação
    const mapElement = document.getElementById('map');
    if (mapElement) {
        initMap(results.bairros_stats, JSON.parse(geojsonData));
    }

    // Inicializar o mapa de problemas
    const problemMapElement = document.getElementById('problemMap');
    if (problemMapElement) {
        initProblemMap(results.bairros_stats, results.problem_stats_by_suburb, JSON.parse(geojsonData));
    }

}

function initMap(bairrosStats, geojsonData) {
    const map = L.map('map').setView([-22.9068, -43.1729], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    // Função de cor aprimorada
    function getColor(stats) {
        if (stats.total_rides === 0) return '#cccccc'; // Cinza para sem dados

        // Destaque em vermelho gradiente baseado na severidade dos problemas
        if (stats.problematic_rides > 0) {
            const severity = Math.min(1, stats.problematic_rides / stats.total_rides);
            // Escala de vermelho (claro para escuro)
            const redIntensity = Math.floor(200 + (55 * severity));
            return `rgb(${redIntensity}, 50, 50)`;
        }

        // Escala normal baseada no sentiment_score
        const score = stats.sentiment_score || 0;
        if (score >= 50) return '#198754';  // Verde
        if (score >= 0) return '#ffc107';   // Amarelo
        return '#dc3545';                  // Vermelho
    }

    // Estilo do mapa
    function style(feature) {
        const bairro = feature.properties.nome;
        const stats = bairrosStats[bairro] || {};

        return {
            fillColor: getColor(stats),
            weight: 2,
            opacity: 1,
            color: 'white',
            fillOpacity: 0.7
        };
    }

    // Adicionar GeoJSON ao mapa
    L.geoJSON(geojsonData, {
        style: style,
        onEachFeature: function(feature, layer) {
            const bairro = feature.properties.nome;
            const stats = bairrosStats[bairro] || {};

            let popupContent = `<b>${bairro}</b><br>`;

            if (stats.total_rides > 0) {
                popupContent += `
                    <b>Total de corridas:</b> ${stats.total_rides}<br>
                    <b>Avaliadas:</b> ${stats.total_rated}<br>
                    ${stats.problematic_rides > 0 ?
                       `<b style="color:#ff0000">⚠️ Corridas problemáticas: ${stats.problematic_rides} (${((stats.problematic_rides/stats.total_rides)*100).toFixed(1)}%)</b><br>` : ''}
                    <div style="margin-top:8px;">
                        <b>Avaliações:</b><br>
                        <span style="color:#198754">✓ Positivas (≥4): ${stats.percent_positivo?.toFixed(1) || 0}%</span><br>
                        <span style="color:#ffc107">○ Neutras (3-3.9): ${stats.percent_neutro?.toFixed(1) || 0}%</span><br>
                        <span style="color:#dc3545">✗ Negativas (<3): ${stats.percent_negativo?.toFixed(1) || 0}%</span><br>
                    </div>
                    <b>Índice de satisfação:</b> ${stats.sentiment_score?.toFixed(1) || 0}<br>
                    <small>(%Positivas - %Negativas)</small>
                `;
            } else {
                popupContent += `<b>Nenhuma corrida analisada</b>`;
            }

            layer.bindPopup(popupContent);
        }
    }).addTo(map);

    // Legenda atualizada
    const legend = L.control({position: 'bottomright'});
    legend.onAdd = function() {
        const div = L.DomUtil.create('div', 'info legend');
        div.innerHTML = `
            <h6>Índice de Satisfação</h6>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:#198754; margin-right:5px;"></i>
                <span>Positivo (50-100)</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:#ffc107; margin-right:5px;"></i>
                <span>Neutro (0-50)</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:#dc3545; margin-right:5px;"></i>
                <span>Negativo (-100-0)</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:#cccccc; margin-right:5px;"></i>
                <span>Sem dados suficientes</span>
            </div>
            <hr style="margin:8px 0;">
            <small>Índice = (%Positivas - %Negativas)</small>
        `;
        return div;
    };
    legend.addTo(map);
}

// Função para exibir mapa com bairros com comentários problemáticos
function initProblemMap(bairrosStats, problemStats, geojsonData) {
    const map = L.map('problemMap').setView([-22.9068, -43.1729], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    // Função de cor baseada na quantidade de problemas
    function getProblemColor(stats, totalProblems) {
        if (totalProblems === 0) return '#cccccc'; // Cinza para sem dados

        // Escala de vermelho (claro para escuro) baseado na intensidade
        const intensity = Math.min(1, totalProblems / Math.max(1, stats.total_rides));
        const redIntensity = Math.floor(200 + (55 * intensity));
        return `rgb(${redIntensity}, 50, 50)`;
    }

    // Estilo do mapa
    function style(feature) {
        const bairro = feature.properties.nome;
        const stats = bairrosStats[bairro] || {};
        const problems = problemStats[bairro] || { total_problems: 0 };

        return {
            fillColor: getProblemColor(stats, problems.total_problems),
            weight: 2,
            opacity: 1,
            color: 'white',
            fillOpacity: 0.7
        };
    }

    // Adicionar GeoJSON ao mapa
    L.geoJSON(geojsonData, {
        style: style,
        onEachFeature: function(feature, layer) {
            const bairro = feature.properties.nome;
            const stats = bairrosStats[bairro] || {};
            const problems = problemStats[bairro] || { total_problems: 0, problem_types: {}, discriminatory_problems: false };

            let popupContent = `<b>${bairro}</b><br>`;

            if (stats.total_rides > 0) {
                popupContent += `
                    <b>Total de corridas:</b> ${stats.total_rides}<br>
                    <b>Comentários problemáticos:</b> ${problems.total_problems || 0}<br>
                `;

                if (problems.total_problems > 0) {
                    popupContent += `<b>Tipos de problemas:</b><br>`;
                    for (const [ptype, count] of Object.entries(problems.problem_types)) {
                        popupContent += `- ${ptype}: ${count}<br>`;
                    }
                }

                if (problems.discriminatory_problems) {
                    popupContent += `<div style="color: red; font-weight: bold;"> 🚨 Possível comportamento discriminatório</div>`;
                }
            } else {
                popupContent += `<b>Nenhuma corrida analisada</b>`;
            }

            layer.bindPopup(popupContent);

        }
    }).addTo(map);

    // Legenda atualizada
    const legend = L.control({position: 'bottomright'});
    legend.onAdd = function() {
        const div = L.DomUtil.create('div', 'info legend');
        div.innerHTML = `
            <h6>Intensidade de Problemas</h6>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:rgb(255,50,50); margin-right:5px;"></i>
                <span>Alta incidência</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:rgb(200,50,50); margin-right:5px;"></i>
                <span>Média incidência</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:rgb(150,50,50); margin-right:5px;"></i>
                <span>Baixa incidência</span>
            </div>
            <div style="display:flex; align-items:center; margin:3px 0;">
                <i style="background:#cccccc; margin-right:5px;"></i>
                <span>Sem dados</span>
            </div>
        `;
        return div;
    };
    legend.addTo(map);
}


// Função para aplicar filtros
function applyFilters() {
    const maxScore = parseFloat(document.getElementById('maxScore').value) || 5;
    const problemType = document.getElementById('problemType').value;

    document.querySelectorAll('.driver-card').forEach(card => {
        const score = parseFloat(card.querySelector('.rating-badge').textContent.split(': ')[1]);
        const problemTypes = card.dataset.problemTypes ? card.dataset.problemTypes.split(',') : [];

        const scoreMatch = score <= maxScore;
        const typeMatch = !problemType || problemTypes.includes(problemType);

        card.style.display = (scoreMatch && typeMatch) ? 'block' : 'none';
    });
}


// Mostrar loading ao aplicar filtros
document.querySelector('form').addEventListener('submit', function() {
    document.getElementById('loadingOverlay').style.display = 'flex';
});

// Esconder loading quando a página carregar
window.addEventListener('load', function() {
    document.getElementById('loadingOverlay').style.display = 'none';
});