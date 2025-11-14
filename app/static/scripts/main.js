/**
 * Funções gerais e helpers para a aplicação
 */

// Mostrar/ocultar loading
function showLoading() {
  document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
  document.getElementById('loadingOverlay').style.display = 'none';
}

// Menu hamburguer
function initMenu() {
  const menu = document.getElementById('sideMenu');
  const hamburger = document.querySelector('.hamburger');
  const content = document.querySelector('.main-content');

  function toggleMenu() {
    menu.classList.toggle('open');
    content.classList.toggle('shifted');
    hamburger.classList.toggle('is-active');

    if (menu.classList.contains('open')) {
      document.addEventListener('click', closeMenuOnClickOutside);
    } else {
      document.removeEventListener('click', closeMenuOnClickOutside);
    }
  }

  function closeMenuOnClickOutside(e) {
    if (!menu.contains(e.target) && e.target !== hamburger) {
      toggleMenu();
    }
  }

  hamburger.addEventListener('click', toggleMenu);
}

// Helper para normalizar strings
function unidecode(str) {
  if (!str) return '';
  return str.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

// Helper para determinar a zona de um bairro
function getZoneForNeighborhood(neighborhoodName, zoneMap) {
  if (!neighborhoodName) return 'Outros';
  const normalized = unidecode(neighborhoodName);
  for (const [zone, neighborhoods] of Object.entries(zoneMap)) {
    if (neighborhoods.includes(normalized)) return zone;
  }
  return 'Outros';
}

export {
  showLoading,
  hideLoading,
  initMenu,
  unidecode,
  getZoneForNeighborhood
};