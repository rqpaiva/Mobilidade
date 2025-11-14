// favelas_main.js

/* ===================== GLOBAL EXPORTS ===================== */

/**
 * Remove acentos/diacríticos e normaliza para comparação.
 * toLower=true retorna minúsculas; passe false para manter o caso original.
 */
window.unidecode = function(str, toLower = true) {
  if (str == null) return '';
  let s = String(str).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  return toLower ? s.toLowerCase().trim() : s.trim();
};

window.slug = function(str) {
  return window.unidecode(str).replace(/[^a-z0-9]+/g, '_');
};

/** Remove todas as opções exceto a primeira (placeholder) */
function clearSelect(selectEl) {
  while (selectEl.options.length > 1) {
    selectEl.remove(1);
  }
}

/** Adiciona uma lista de opções (value=txtDefault) a um <select> */
function addOptions(selectEl, values, selectedValue = '') {
  values.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v.value ?? v;  // aceita {value,text}
    opt.textContent = v.text ?? v;
    if (selectedValue && selectedValue === opt.value) opt.selected = true;
    selectEl.appendChild(opt);
  });
}

/**
 * Descobre zona a partir do bairro usando o mapa zone_neighborhoods
 * (array de bairros por zona). Usa comparação sem acento.
 */
window.getZoneForNeighborhood = function(bairro, zoneMap) {
  const sBairro = window.unidecode(bairro);
  for (const [zone, bairros] of Object.entries(zoneMap)) {
    if (bairros.map(b => window.unidecode(b)).includes(sBairro)) return zone;
  }
  return 'Outros';
};

/* ===================== Core ===================== */

window.ZONE_COLORS = {
  'Zona Norte': '#1f77b4',
  'Zona Sul': '#ff7f0e',
  'Zona Oeste': '#2ca02c',
  'Zona Central': '#d62728',
  'Outros': '#7f7f7f'
};

/**
 * Inicializa os selects e eventos do dashboard de favelas.
 * Requer:
 *  - form id="filters-form"
 *  - selects: #zone-select, #neighborhood-select, #favela-select
 *  - botão aplicar: id="apply-filters"
 * appData precisa conter:
 *  - zone_neighborhoods: { zona: [bairros...] }
 *  - neighborhood_favelas: { slug_bairro: [{nome: 'Favela X', ...}, ...] }
 *  - filters: { zone, neighborhood, favela, ... } (valores atuais)
 */
window.initFavelasDashboard = function(appData) {
  try {
    const zoneSelect = document.getElementById('zone-select');
    const neighborhoodSelect = document.getElementById('neighborhood-select');
    const favelaSelect = document.getElementById('favela-select');
    const applyBtn = document.getElementById('apply-filters');
    const form = document.getElementById('filters-form');

    if (!zoneSelect || !neighborhoodSelect || !favelaSelect || !form) {
      console.error('Elementos de filtro não encontrados.');
      return;
    }

    /* ---------- Preenchimento inicial ---------- */
    function fillZones() {
      clearSelect(zoneSelect);
      addOptions(zoneSelect, [{value: '', text: 'Todas as zonas'}]);

      // Get zones from ZONE_COLORS to maintain consistency
      const zones = Object.keys(ZONE_COLORS).filter(z => z !== 'Outros');
      addOptions(zoneSelect, zones, appData.filters.zone || '');
    }

    function fillNeighborhoods() {
      clearSelect(neighborhoodSelect);
      addOptions(neighborhoodSelect, [{value: '', text: 'Todos os bairros'}]);

      const selectedZone = zoneSelect.value;
      let neighborhoods = [];

      if (selectedZone && appData.zone_neighborhoods[selectedZone]) {
        neighborhoods = [...appData.zone_neighborhoods[selectedZone]];
      } else {
        // All neighborhoods from all zones
        neighborhoods = Object.values(appData.zone_neighborhoods || {}).flat();
      }

      // Remove duplicates and sort
      neighborhoods = [...new Set(neighborhoods)].sort();

      // Create options with original names but slugified values
      const options = neighborhoods.map(b => ({
        value: slug(b),
        text: b
      }));

      addOptions(neighborhoodSelect, options, appData.filters.neighborhood || '');
    }

    function fillFavelas() {
      clearSelect(favelaSelect);
      addOptions(favelaSelect, [{ value: '', text: 'Todas as favelas' }]);

      const selectedNeighborhood = neighborhoodSelect.value; // slug
      let items = [];

      if (selectedNeighborhood && appData.neighborhood_favelas[selectedNeighborhood]) {
        items = [...appData.neighborhood_favelas[selectedNeighborhood]];
      } else {
        items = Object.values(appData.neighborhood_favelas || {}).flat();
      }

      // Aceita tanto strings quanto objetos {nome,...}
      const names = [...new Set(
        items
          .map(f => typeof f === 'string' ? f : (f.nome || f.NOME || f.name || ''))
          .filter(Boolean)
      )].sort((a, b) => a.localeCompare(b, 'pt-BR'));

      const options = names.map(n => ({ value: n, text: n }));
      addOptions(favelaSelect, options, appData.filters.favela || '');
    }


    /* ---------- Eventos ---------- */
    zoneSelect.addEventListener('change', () => {
      fillNeighborhoods();
      fillFavelas();
    });

    neighborhoodSelect.addEventListener('change', fillFavelas);

    if (applyBtn) {
      applyBtn.addEventListener('click', e => {
        e.preventDefault();
        form.submit();
      });
    }

    /* ---------- Execução inicial ---------- */
    fillZones();
    fillNeighborhoods();
    fillFavelas();

  } catch (err) {
    console.error('Erro em initFavelasDashboard:', err);
  }
};


