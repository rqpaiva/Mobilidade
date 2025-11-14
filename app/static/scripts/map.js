import { getZoneForNeighborhood } from './main.js';

export function initMap(appData) {
  try {
    const container = document.getElementById('map');
    if (!container) {
      throw new Error('Elemento do mapa não encontrado');
    }

    // Limpa mapa anterior se houver
    container._leaflet_id = null;
    container.innerHTML = '';

    // Cria mapa
    const map = L.map('map', { preferCanvas: true, zoomControl: false })
      .setView([-22.9068, -43.1729], 11);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    // Valida GeoJSON
    if (!appData.bairrosGeo?.features?.length) {
      throw new Error('Dados GeoJSON inválidos ou vazios');
    }

    // Paleta por taxa
    function getColorByCancelRate(rate) {
      return rate > 0.5   ? '#800026' :
             rate > 0.3   ? '#BD0026' :
             rate > 0.2   ? '#E31A1C' :
             rate > 0.1   ? '#FC4E2A' :
             rate > 0.05  ? '#FD8D3C' :
             rate > 0.02  ? '#FEB24C' :
                              '#FFEDA0';
    }

    // Cores por zona (quando não há filtro)
    const zoneColors = {
      'Zona Norte': '#1f77b4',
      'Zona Sul':   '#ff7f0e',
      'Zona Oeste': '#2ca02c',
      'Zona Central':'#d62728',
      'Outros':     '#7f7f7f'
    };

    const zoneFilter = appData.filters?.zone || '';

    // Destaque de seleção
    let selectedLayer = null;
    function highlight(layer) {
      if (selectedLayer) {
        bairrosLayer.resetStyle(selectedLayer);
      }
      selectedLayer = layer;
      layer.setStyle({ weight: 2, color: '#222' });
      if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
        layer.bringToFront();
      }
    }

    // Adiciona GeoJSON
    const bairrosLayer = L.geoJson(appData.bairrosGeo, {
      style: feature => {
        const name = feature.properties.Bairros || feature.properties.nome || '';
        const zone = getZoneForNeighborhood(name, appData.zoneMap);

        if (!zoneFilter) {
          return {
            fillColor:   zoneColors[zone] || zoneColors['Outros'],
            weight:      1,
            color:       '#fff',
            fillOpacity: 0.7
          };
        } else {
          const stats = appData.stats.neighborhood_stats.all[name] || { total:0, driver_cancel:0, passenger_cancel:0 };
          const rate  = stats.total
                        ? (stats.driver_cancel + stats.passenger_cancel) / stats.total
                        : 0;

          if (zone !== zoneFilter) {
            return {
              fillColor:   '#ccc',
              weight:      1,
              color:       '#fff',
              fillOpacity: 0.3
            };
          }
          return {
            fillColor:   getColorByCancelRate(rate),
            weight:      1,
            color:       '#fff',
            fillOpacity: 0.7
          };
        }
      },
      onEachFeature: (feature, layer) => {
        const name = feature.properties.Bairros || feature.properties.nome || '';
        const zone = getZoneForNeighborhood(name, appData.zoneMap);
        const stats = appData.stats.neighborhood_stats.all[name] || { total:0, driver_cancel:0, passenger_cancel:0 };
        const totalCancels = stats.driver_cancel + stats.passenger_cancel;
        const ratePct = stats.total ? ((totalCancels / stats.total) * 100).toFixed(1) : '0';

        // Conteúdo do popup
        const popupContent = (!zoneFilter)
          ? `<strong>${name}</strong><br>Zona: ${zone}`
          : `
              <strong>${name}</strong><br>
              Zona: ${zone}<br>
              Total corridas: ${stats.total}<br>
              Cancel. motorista: ${stats.driver_cancel}<br>
              Cancel. passageiro: ${stats.passenger_cancel}<br>
              Taxa total: ${ratePct}%<br>
              Cancelamentos: ${totalCancels}
            `;

        layer.bindPopup(popupContent, { closeOnClick: false, autoClose: false });

        // >>> NÃO submetemos o formulário ao clicar. Mantemos popup e damos um zoom suave na área.
        layer.on('click', (e) => {
          highlight(layer);
          layer.openPopup(e.latlng || layer.getBounds().getCenter());
          map.fitBounds(layer.getBounds(), { padding: [15,15], maxZoom: 14 });

          // Preenche selects para o usuário aplicar quando quiser
          const zoneSel = document.getElementById('zone-select');
          const neighSel = document.getElementById('neighborhood-select');
          if (zoneSel) zoneSel.value = zone;
          if (neighSel) neighSel.value = name;
        });
      }
    }).addTo(map);

    // Ajusta para enquadrar a cidade (somente na carga inicial)
    map.fitBounds(bairrosLayer.getBounds(), { padding: [20,20] });

    // Legenda
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div', 'info legend');
      if (!zoneFilter) {
        div.innerHTML = '<h4>Zonas do Rio</h4>';
        for (const z of Object.keys(zoneColors).filter(z=>z!=='Outros')) {
          div.innerHTML += `
            <i style="background:${zoneColors[z]}; width:18px; height:18px; float:left; margin-right:8px;"></i>
            ${z}<br>
          `;
        }
      } else {
        div.innerHTML = '<h4>Taxa de Cancelamento</h4>';
        const grades = [0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5];
        for (let i = 0; i < grades.length; i++) {
          const from = grades[i];
          const to   = grades[i+1];
          const color = getColorByCancelRate(from + 0.001);
          div.innerHTML += `
            <i style="background:${color}; width:18px; height:18px; float:left; margin-right:8px;"></i>
            ${(from*100).toFixed(1)}${to ? '&ndash;' + (to*100).toFixed(1) : '+'}%<br>
          `;
        }
      }
      return div;
    };
    legend.addTo(map);

  } catch (error) {
    console.error('Erro ao inicializar o mapa:', error);
    const mapContainer = document.getElementById('map');
    if (mapContainer) {
      mapContainer.innerHTML = `
        <div class="map-error">
          <p>Erro ao carregar o mapa. Recarrregue a página.</p>
          <p>${error.message}</p>
        </div>
      `;
    }
  }
}
