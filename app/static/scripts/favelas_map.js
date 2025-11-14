// favelas_map.js
const { unidecode, getZoneForNeighborhood, ZONE_COLORS } = window;


window.initFavelasMap = function(appData = {}) {
  try {
    const container = document.getElementById('map');
    if (!container) throw new Error('Elemento #map não encontrado');

    container.innerHTML = '';
    const map = L.map('map', {
      center: [-22.9068, -43.1729],
      zoom: 11,
      zoomControl: false
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap'
    }).addTo(map);

    // Camadas
    let bairrosLayer = null;
    let favelasLayer = null;

    if (appData.bairros_geo?.features?.length) {
      bairrosLayer = addBairrosLayer(map, appData);
    } else {
      console.warn('bairros_geo vazio ou ausente.');
    }

    if (appData.favelas_geo?.features?.length) {
      favelasLayer = addFavelasLayer(map, appData);
    } else {
      console.warn('favelas_geo vazio ou ausente.');
    }

    // Ajusta bounds
    const bounds = [];
    if (bairrosLayer) bounds.push(bairrosLayer.getBounds());
    if (favelasLayer) bounds.push(favelasLayer.getBounds());
    if (bounds.length) {
      const total = bounds.reduce((acc, b) => acc.extend(b), L.latLngBounds(bounds[0]));
      map.fitBounds(total, { padding: [20, 20] });
    }

    addLegend(map);

  } catch (err) {
    console.error('Erro em initFavelasMap:', err);
    showMapError(err.message || 'Erro desconhecido');
  }
}

/* ======================= Camadas ======================= */

function addBairrosLayer(map, appData) {
  const layer = L.geoJson(appData.bairros_geo, {
    style: (feature) => getBairroStyle(feature, appData),
    onEachFeature: (feature, layer) => onEachBairro(feature, layer, appData)
  }).addTo(map);
  return layer;
}

function addFavelasLayer(map, appData) {
  const maxCancelRate = computeMaxCancelRate(appData.stats);
  const layer = L.geoJson(appData.favelas_geo, {
    style: (feature) => getFavelaStyle(feature, appData.stats, maxCancelRate),
    onEachFeature: (feature, layer) => onEachFavela(feature, layer, appData)
  }).addTo(map);
  return layer;
}


/* ======================= Estilos ======================= */

function getBairroStyle(feature, appData) {
  const bairro = feature.properties.Bairros || feature.properties.nome || feature.properties.NAME || '';
  const zone = getZoneForNeighborhood(bairro, appData.zone_neighborhoods || {});

  // Calculate stats for this neighborhood
  const stats = appData.stats?.neighborhood_stats_all?.[bairro] || { total: 0, driver: 0, passenger: 0 };
  const total = stats.total || 1; // Avoid division by zero

  // Calculate intensity based on cancellation rates
  const driverRate = stats.driver / total;
  const passengerRate = stats.passenger / total;
  const maxRate = Math.max(driverRate, passengerRate);

  // Get base color from zone
  const baseColor = ZONE_COLORS[zone] || ZONE_COLORS['Outros'];

  // Adjust opacity based on cancellation intensity
  const fillOpacity = 0.3 + (0.7 * maxRate);

  return {
    fillColor: baseColor,
    weight: 1,
    color: '#fff',
    fillOpacity: fillOpacity
  };
}

function clamp01(x){ return Math.max(0, Math.min(1, x)); }
function hexToRgb(hex){ const h = hex.replace('#',''); return { r: parseInt(h.slice(0,2),16), g: parseInt(h.slice(2,4),16), b: parseInt(h.slice(4,6),16) }; }
function rgbToHex(r,g,b){ const toHex = (v)=>v.toString(16).padStart(2,'0'); return `#${toHex(r)}${toHex(g)}${toHex(b)}`; }
function interpolateColor(hex1, hex2, t){
  const a = hexToRgb(hex1), b = hexToRgb(hex2);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return rgbToHex(r,g,bl);
}
function computeMaxCancelRate(stats){
  let max = 0;
  const all = stats?.favela_stats_all || {};
  for (const k in all){
    const s = all[k] || {};
    const total = s.total || 0;
    const d = s.driver || 0;
    const p = s.passenger || 0;
    if (total > 0){
      const tRate = (d + p) / total; // taxa total de cancelamentos (0..1)
      if (tRate > max) max = tRate;
    }
  }
  return max || 1; // evita divisão por zero
}


function getFavelaStyle(feature, stats, maxCancelRate = 1) {
  const nome = feature.properties.nome || feature.properties.NOME || 'Desconhecida';
  const st = stats?.favela_stats_all?.[nome] || { total: 0, driver: 0, passenger: 0 };

  const total = st.total || 0;
  const d = st.driver || 0;
  const p = st.passenger || 0;
  const sumCanc = d + p;

  // Paletas
  const RED_LIGHT  = '#fde0dd', RED_DARK  = '#d73027';
  const BLUE_LIGHT = '#deebf7', BLUE_DARK = '#4575b4';
  const GRAY_LIGHT = '#d9d9d9', GRAY_DARK = '#000000';
  const NO_DATA    = '#f0f0f0';

  // Sem dados / sem cancelamentos
  if (total === 0 || sumCanc === 0) {
    return { fillColor: NO_DATA, weight: 2, color: '#333', fillOpacity: 0.85 };
  }

  // Intensidade pela taxa TOTAL de cancelamentos, normalizada pelo máximo do dataset
  const totalCancelRate = sumCanc / total;        // 0..1
  const intensity = clamp01(totalCancelRate / maxCancelRate); // 0..1

  // Diferença entre motorista e passageiro ENTRE OS CANCELAMENTOS (0..1)
  const diffDominance = Math.abs(d - p) / sumCanc;

  // Limiar de "muito próximas"
  const CLOSE_THRESHOLD = 0.10; // 10 p.p. entre motorista e passageiro

  let fillColor;
  if (diffDominance < CLOSE_THRESHOLD) {
    // Próximas: cinza → preto por intensidade de cancelamentos
    fillColor = interpolateColor(GRAY_LIGHT, GRAY_DARK, intensity);
  } else {
    // Predominância: vermelho (motorista) ou azul (passageiro), intensidade pela taxa total
    const isDriverDominant = d > p;
    fillColor = isDriverDominant
      ? interpolateColor(RED_LIGHT,  RED_DARK,  intensity)
      : interpolateColor(BLUE_LIGHT, BLUE_DARK, intensity);
  }

  return { fillColor, weight: 2, color: '#333', fillOpacity: 0.85 };
}



/* ======================= Eventos Layer ======================= */

function onEachBairro(feature, layer, appData) {
  const bairro = feature.properties.Bairros || feature.properties.nome || '';
  const zone = getZoneForNeighborhood(bairro, appData.zone_neighborhoods || {});

  layer.bindPopup(`
    <strong>${bairro}</strong><br>
    Zona: ${zone}<br>
    <button class="btn-filter-zone" data-zone="${zone}">Filtrar Zona</button>
    <button class="btn-filter-neigh" data-neigh="${bairro}">Filtrar Bairro</button>
  `);


  // Delegação para os botões do popup
  layer.on('popupopen', () => {
    const btnZ = document.querySelector('.btn-filter-zone');
    const btnN = document.querySelector('.btn-filter-neigh');
    if (btnZ) btnZ.addEventListener('click', (e) => {
      e.preventDefault();
      setAndSubmitFilters({ zone: e.target.dataset.zone });
    });
    if (btnN) btnN.addEventListener('click', (e) => {
      e.preventDefault();
      setAndSubmitFilters({ neighborhood: e.target.dataset.neigh });
    });
  });
}

function onEachFavela(feature, layer, appData) {
  // --- Propriedades do GeoJSON (variação de chaves normalizada) ---
  const props = (feature && feature.properties) ? feature.properties : {};
  const nome      = props.nome      || props.NOME      || 'Desconhecida';
  const bairro    = props.bairro    || props.Bairro    || props.BAIRRO || 'N/A';
  const complexo  = props.complexo  || props.Complexo  || 'N/A';

  // --- Helpers locais de formatação ---
  const pct = (v) => `${(Number(v || 0) * 100).toFixed(1)}%`;
  const num = (v) => Number(v || 0).toLocaleString('pt-BR');

  // --- Normalização de chave de bairro (sem acento, minúscula) ---
  function normKey(s) {
    const base = (s ?? '').toString().trim().toLowerCase();
    try {
      if (window.unidecode) return window.unidecode(base);
    } catch (e) {}
    return base.normalize('NFD').replace(/\p{Diacritic}/gu, '');
  }
  const bairroKey = normKey(bairro);

  // ---------- ESTATÍSTICAS DA FAVELA (corridas PRÓXIMAS/near) ----------
  const favAll = appData?.stats?.favela_stats_all || {};
  const fRaw = favAll[nome] || {};
  const fTotal     = Number(fRaw.total || 0);
  const fDriver    = Number(fRaw.driver || 0);
  const fPassenger = Number(fRaw.passenger || 0);
  const fDriverRate    = (typeof fRaw.driver_rate === 'number') ? fRaw.driver_rate : (fTotal ? (fDriver / fTotal) : 0);
  const fPassengerRate = (typeof fRaw.passenger_rate === 'number') ? fRaw.passenger_rate : (fTotal ? (fPassenger / fTotal) : 0);

  // ---------- DETALHES DE ORIGEM POR BAIRRO PARA ESTA FAVELA ----------
  // Usa o dicionário por favela -> bairro de origem (já calculado no backend)
  // para compor a lista "Origem das corridas desta favela" e também para o
  // cálculo "bairro excluindo corridas associadas à favela".
  const origemDetailsAll = appData?.stats?.favela_origin_details || {};
  const origemDetailsFav = origemDetailsAll[nome] || {}; // { bairroKey: { total, driver, passenger } }

  let origemHtml = '';
  if (fTotal > 0 && origemDetailsFav && typeof origemDetailsFav === 'object') {
    // ordenar por total desc
    const entries = Object.entries(origemDetailsFav)
      .map(([bk, obj]) => [bk, obj?.total || 0, obj?.driver || 0, obj?.passenger || 0])
      .sort((a, b) => b[1] - a[1]);

    const top = entries.slice(0, 5);
    top.forEach(([bk, totalOrigem, driverOrigem, passengerOrigem]) => {
      // tenta mostrar o nome "bonito" do bairro; se não souber, mostra a chave
      const bairroOrigem = bk;
      const pctTotal = fTotal ? (totalOrigem / fTotal * 100).toFixed(1) : 0;

      origemHtml += `
        <div style="font-size:11px; margin-top:4px;">
          • ${bairroOrigem}: ${num(totalOrigem)} corridas (${pctTotal}%)
          <span style="color:#d73027;">${driverOrigem} motorista</span>,
          <span style="color:#4575b4;">${passengerOrigem} passageiro</span>
        </div>
      `;
    });

    if (entries.length > 5) {
      origemHtml += `<div style="font-size:11px; color:#666;">+ ${entries.length - 5} outros bairros</div>`;
    }
  }

  // ---------- ESTATÍSTICAS DO BAIRRO (SEM correlação com favela) ----------
  // ATENÇÃO: a versão 'raw' (todas as corridas) vem indexada por CHAVE CANÔNICA
  const nbRawAll = appData?.stats?.neighborhood_stats_all_raw || {};
  const nbRaw    = nbRawAll[bairroKey] || {};
  const nbTotal  = Number(nbRaw.total || 0);
  const nbDriver = Number(nbRaw.driver || 0);
  const nbPass   = Number(nbRaw.passenger || 0);
  const nbDriverRate    = (typeof nbRaw.driver_rate === 'number') ? nbRaw.driver_rate : (nbTotal ? (nbDriver / nbTotal) : 0);
  const nbPassengerRate = (typeof nbRaw.passenger_rate === 'number') ? nbRaw.passenger_rate : (nbTotal ? (nbPass / nbTotal) : 0);

  // ---------- ESTATÍSTICAS DO BAIRRO (EXCLUINDO corridas desta FAVELA) ----------
  // CORREÇÃO: subtrair APENAS as corridas near originadas neste bairro PARA ESTA favela
  // (e não o agregado de todas as favelas).
  const nearForThisFavela = origemDetailsFav?.[bairroKey] || { total: 0, driver: 0, passenger: 0 };

  const nbExTot = Math.max(0, nbTotal  - Number(nearForThisFavela.total || 0));
  const nbExDrv = Math.max(0, nbDriver - Number(nearForThisFavela.driver || 0));
  const nbExPas = Math.max(0, nbPass   - Number(nearForThisFavela.passenger || 0));

  const nbExDrvRate = (nbExTot > 0) ? (nbExDrv / nbExTot) : 0;
  const nbExPasRate = (nbExTot > 0) ? (nbExPas / nbExTot) : 0;

  // ---------- POPUP ----------
  const html = `
    <div style="font-weight:700; font-size:14px; margin-bottom:4px;">${nome}</div>
    <div><b>Bairro:</b> ${bairro}</div>
    <div><b>Complexo:</b> ${complexo}</div>

    <div style="font-weight:600; margin-top:8px">Favela (corridas próximas):</div>
    <div>• Taxa Motorista: ${pct(fDriverRate)}</div>
    <div>• Taxa Passageiro: ${pct(fPassengerRate)}</div>
    ${fTotal ? `<div>• Total: ${num(fTotal)}</div>` : ''}

    ${origemHtml}

    <div style="font-weight:600; margin-top:8px">Bairro (sem correlação com favela):</div>
    <div>• Taxa Motorista no bairro: ${pct(nbDriverRate)}</div>
    <div>• Taxa Passageiro no bairro: ${pct(nbPassengerRate)}</div>
    ${nbTotal ? `<div>• Total no bairro: ${num(nbTotal)}</div>` : ''}

    <div style="font-weight:600; margin-top:8px">Bairro (excluindo corridas associadas à <u>esta</u> favela):</div>
    <div>• Taxa Motorista no bairro (excl.): ${pct(nbExDrvRate)}</div>
    <div>• Taxa Passageiro no bairro (excl.): ${pct(nbExPasRate)}</div>
    <div>• Total no bairro (excl.): ${num(nbExTot)}</div>
  `;

  // Vincula popup a feature
  layer.bindPopup(html, { maxWidth: 420 });

  // (Opcional) foco/hover
  layer.on({
    mouseover: function (e) {
      const l = e.target;
      l.setStyle({ weight: 2, opacity: 1 });
      if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
        l.bringToFront();
      }
    },
    mouseout: function (e) {
      const l = e.target;
      l.setStyle({ weight: 1, opacity: 0.8 });
    }
  });


  // botão interno ao popup
  layer.on('popupopen', () => {
    const btn = document.querySelector('.btn-filter-favela');
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        setAndSubmitFilters({ favela: e.target.dataset.favela });
      });
    }
  });
}


/* ======================= Legenda / Erro ======================= */

function addLegend(map) {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div', 'info legend');

    // monta itens de bairros com as cores já existentes
    const zoneHtml = (window.ZONE_COLORS ? Object.entries(window.ZONE_COLORS)
      .filter(([zone]) => zone !== 'Outros') // opcional
      .map(([zone, color]) => `<div><i style="background:${color};"></i>${zone}</div>`)
      .join('') : '');

    div.innerHTML = `
      <h4>Legenda</h4>

      <div class="legend-section">
        <div class="legend-title">Bairros (por zona)</div>
        ${zoneHtml}
      </div>

      <div class="legend-section" style="margin-top:8px;">
        <div class="legend-title">Favelas</div>

        <div style="margin-bottom:2px;">Predomínio: motorista</div>
        <div style="height:12px;width:130px;border-radius:2px;margin:4px 0;background:linear-gradient(to right,#fde0dd,#d73027);"></div>
        <div class="legend-scale" style="display:flex;justify-content:space-between;font-size:.75rem;color:#666;">
          <span>baixa</span><span>alta</span>
        </div>

        <div style="margin-top:8px;margin-bottom:2px;">Predomínio: passageiro</div>
        <div style="height:12px;width:130px;border-radius:2px;margin:4px 0;background:linear-gradient(to right,#deebf7,#4575b4);"></div>
        <div class="legend-scale" style="display:flex;justify-content:space-between;font-size:.75rem;color:#666;">
          <span>baixa</span><span>alta</span>
        </div>

        <div style="margin-top:8px;margin-bottom:2px;">Taxas muito próximas</div>
        <div style="height:12px;width:130px;border-radius:2px;margin:4px 0;background:linear-gradient(to right,#d9d9d9,#000000);"></div>
        <div class="legend-scale" style="display:flex;justify-content:space-between;font-size:.75rem;color:#666;">
          <span>baixa</span><span>alta</span>
        </div>

        <div style="margin-top:8px;"><i style="background:#f0f0f0;"></i> Sem dados / sem taxas</div>
      </div>
    `;

    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);
}



function showMapError(message) {
  const container = document.getElementById('map');
  if (!container) return;
  container.innerHTML = `
    <div class="alert alert-danger">
      <h4>Erro no carregamento do mapa</h4>
      <p>${message}</p>
    </div>
  `;
}

/* ======================= Filtro Helpers ======================= */

window.setAndSubmitFilters = function({ zone, neighborhood, favela }) {
  const form = document.getElementById('filters-form');
  if (!form) return;

  if (zone !== undefined) {
    const zoneSelect = document.getElementById('zone-select');
    if (zoneSelect) zoneSelect.value = zone;
  }
  if (neighborhood !== undefined) {
    const nSelect = document.getElementById('neighborhood-select');
    if (nSelect) nSelect.value = unidecode(neighborhood.toLowerCase());
  }
  if (favela !== undefined) {
    const fSelect = document.getElementById('favela-select');
    if (fSelect) fSelect.value = favela;
  }

  form.submit();
};

