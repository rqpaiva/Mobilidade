import { showLoading, hideLoading, unidecode, getZoneForNeighborhood, initMenu } from './main.js';
import { initMap } from './map.js';
import { initCharts } from './charts.js';

/**
 * Inicializa todo o dashboard
 */
export function initDashboard(appData) {
  initMenu();
  initMap(appData);
  initFilters(appData);
  initCharts(appData);

  // Ajusta alturas após render e também em redimensionamentos
  syncHeights();
  window.addEventListener('resize', syncHeights);

  // Insere rodapés de fonte de dados
  injectDataSources();

  hideLoading();
}

/**
 * Configura filtros de zona e bairro
 */
export function initFilters(appData) {
  const zoneSelect = document.getElementById('zone-select');
  const neighborhoodSelect = document.getElementById('neighborhood-select');

  zoneSelect.addEventListener('change', () => {
    updateNeighborhoodOptions(zoneSelect.value, appData.zoneMap, neighborhoodSelect);
  });

  if (appData.filters.zone) {
    updateNeighborhoodOptions(appData.filters.zone, appData.zoneMap, neighborhoodSelect);
  }

  setupInteractiveElements(appData);
  setupFormSubmit();
}

function updateNeighborhoodOptions(zone, zoneMap, neighborhoodSelect) {
  neighborhoodSelect.innerHTML = '<option value="">Todos os bairros</option>';
  if (zone && zoneMap[zone]) {
    zoneMap[zone].forEach(bairro => {
      const opt = document.createElement('option');
      opt.value = bairro;
      opt.textContent = bairro.charAt(0).toUpperCase() + bairro.slice(1);
      neighborhoodSelect.appendChild(opt);
    });
  }
}

function setupInteractiveElements(appData) {
  document.querySelectorAll('.top-neighborhood').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      showTopItems('neighborhood', el.dataset.type, appData);
    });
  });
  document.querySelectorAll('.top-hour').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      showTopItems('hour', el.dataset.type, appData);
    });
  });
}

function showTopItems(type, cancelType, appData) {
  const isDriver = cancelType === 'driver';
  const title = type === 'neighborhood' ? 'Bairros' : 'Horários';
  const dataKey = (type === 'neighborhood') ? 'neighborhood_stats' : 'hourly_stats';
  const topData = isDriver
    ? appData.stats[dataKey].top_driver
    : appData.stats[dataKey].top_passenger;

  if (!topData?.length) {
    Swal.fire({ title:'Sem dados', text:`Não há dados de ${title.toLowerCase()}`, icon:'info' });
    return;
  }

  const maxItems = type === 'neighborhood' ? 5 : 10;
  const items = topData.slice(0, maxItems);
  const content = document.createElement('div');
  content.innerHTML = `
    <div style="max-height:60vh;overflow:auto">
      <h4>Top ${items.length} ${title.toLowerCase()} com maior taxa de cancelamento por ${isDriver?'motorista':'passageiro'}</h4>
      <ol style="text-align:left;padding-left:1.5rem">
        ${items.map(item => {
          const key = item[0];
          const pct = (item[1]*100).toFixed(1);
          const stats = appData.stats[dataKey].all[key] || { total:0, driver_cancel:0, passenger_cancel:0 };
          const cancels = stats.driver_cancel + stats.passenger_cancel;
          return `
            <li style="margin-bottom:0.8rem">
              <strong>${key}</strong><br>
              Taxa: ${pct}%<br>
              Cancelamentos: ${cancels} de ${stats.total}
            </li>
          `;
        }).join('')}
      </ol>
    </div>
  `;

  Swal.fire({
    title: `${title} com maior taxa`,
    html: content,
    width: 650,
    confirmButtonText: 'Fechar'
  });
}

function setupFormSubmit() {
  const form = document.getElementById('filters-form');
  if (!form) return;
  form.addEventListener('submit', e => {
    const start = form.elements.start_date.value;
    const end   = form.elements.end_date.value;
    if (start && end && new Date(start) > new Date(end)) {
      e.preventDefault();
      Swal.fire({ title:'Erro', text:'Data início maior que data fim', icon:'error' });
      return;
    }
    showLoading();
  });
}

/* --------- Ajustes visuais utilitários --------- */

/* Faz .container-map ter ao menos a mesma altura do card de passageiros.
   (Em grid, as duas colunas já têm a MESMA altura de linha; este ajuste
   garante que o #map cresça junto e evita "pulos" em alguns navegadores.) */
function syncHeights() {
  const mapBox = document.querySelector('.container-map');
  const passBox = document.querySelector('.container-passengers');
  const mapEl = document.getElementById('map');
  if (!mapBox || !passBox || !mapEl) return;

  const h = passBox.getBoundingClientRect().height;
  mapBox.style.minHeight = `${Math.max(360, Math.round(h))}px`;
  mapEl.style.minHeight  = `${Math.max(360, Math.round(h))}px`;
}

/* Insere as fontes de dados no fim dos containers */
function injectDataSources() {
  const mapBox = document.querySelector('.container-map');
  const passBox = document.querySelector('.container-passengers');

  if (mapBox && !mapBox.querySelector('.data-source.map-source')) {
    mapBox.insertAdjacentHTML(
      'beforeend',
      `<p class="data-source map-source">
        <strong>Fonte do mapa:</strong> IBGE — “Censo 2022: População e domicílios por bairros (dados preliminares)”.
      </p>`
    );
  }
  if (passBox && !passBox.querySelector('.data-source.pass-source')) {
    passBox.insertAdjacentHTML(
      'beforeend',
      `<p class="data-source pass-source">
        <strong>Fonte dos dados socioeconômicos:</strong> Instituto Pereira Passos (IPP), Data.Rio — Armazém de Dados,
        conjunto “Domicílios particulares permanentes por rendimento médio e mediano domiciliar, segundo AP/RA/Bairros — 2010 (IBGE)”.
      </p>`
    );
  }
}

