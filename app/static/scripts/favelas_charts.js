// favelas_charts.js

/* ===================== Helpers ===================== */
function pct(num, den) {
  return den ? (num / den) : 0;
}
function fmtPct(v) {
  return (v * 100).toFixed(1) + '%';
}
function fmtNum(v) {
  return Intl.NumberFormat('pt-BR').format(v ?? 0);
}
function getCtx(id) {
  const el = document.getElementById(id);
  return el ? el.getContext('2d') : null;
}
function destroyIfExists(chartRef) {
  if (chartRef && typeof chartRef.destroy === 'function') chartRef.destroy();
}

/* ===================== State ===================== */
let distanceChart = null;
let topAddrChart = null;
let topFavChart = null;

/* ===================== Builders ===================== */
function buildDistanceDatasets(bins) {
  // bins: [{label, total, driver, passenger}]
  const labels = bins.map(b => b.label);
  const driverRates = bins.map(b => pct(b.driver, b.total));
  const passengerRates = bins.map(b => pct(b.passenger, b.total));

  return {
    labels,
    datasets: [
      {
        label: 'Taxa Cancel. Motorista',
        data: driverRates,
        tension: 0.3,
        pointRadius: 4,
        borderWidth: 2,
        borderColor: 'rgba(215, 48, 39, 1)',      // vermelho
        backgroundColor: 'rgba(215, 48, 39, 0.15)',
        pointBackgroundColor: 'rgba(215, 48, 39, 1)'
      },
      {
        label: 'Taxa Cancel. Passageiro',
        data: passengerRates,
        tension: 0.3,
        pointRadius: 4,
        borderWidth: 2,
        borderColor: 'rgba(69, 117, 180, 1)',     // azul
        backgroundColor: 'rgba(69, 117, 180, 0.15)',
        pointBackgroundColor: 'rgba(69, 117, 180, 1)'
      }
    ]
  };
}

function buildTopAddrDatasets(rows0) {
  // Ordena primeiro por distância (menor → maior),
  // depois por taxa do motorista (maior → menor), e pega o top 20
  const rows = rows0.slice().sort((a, b) => {
    const distCmp = (a.distance ?? Infinity) - (b.distance ?? Infinity);
    if (distCmp !== 0) return distCmp;
    return (b.driver_rate ?? 0) - (a.driver_rate ?? 0);
  }).slice(0, 20);

  return {
    labels: rows.map(r => `${(r.address || '').substring(0, 30)}... (${r.favela})`),
    datasets: [
      {
        label: 'Cancel. Motorista',
        data: rows.map(r => r.driver_rate),
        backgroundColor: 'rgba(215, 48, 39, 0.8)',
        borderColor: 'rgba(215, 48, 39, 1)',
        borderWidth: 1
      },
      {
        label: 'Cancel. Passageiro',
        data: rows.map(r => r.passenger_rate),
        backgroundColor: 'rgba(69, 117, 180, 0.8)',
        borderColor: 'rgba(69, 117, 180, 1)',
        borderWidth: 1
      }
    ],
    // meta precisa conter 'neighborhood' para a tooltip comparativa
    meta: rows
  };
}

function buildTopFavDatasets(rows) {
  // rows: [{favela, total, driver, passenger, driver_rate, passenger_rate}]
  const labels = rows.map(r => r.favela);

  return {
    labels,
    datasets: [
      {
        label: 'Cancel. Motorista',
        data: rows.map(r => r.driver_rate * 100), // Convertendo para porcentagem
        backgroundColor: 'rgba(215, 48, 39, 0.8)',
        borderColor: 'rgba(215, 48, 39, 1)',
        borderWidth: 1
      },
      {
        label: 'Cancel. Passageiro',
        data: rows.map(r => r.passenger_rate * 100), // Convertendo para porcentagem
        backgroundColor: 'rgba(69, 117, 180, 0.8)',
        borderColor: 'rgba(69, 117, 180, 1)',
        borderWidth: 1
      }
    ],
    meta: rows
  };
}

/* ===================== Charts ===================== */
function makeDistanceChart(canvasId, bins) {
  const ctx = getCtx(canvasId);
  if (!ctx || !bins?.length) return null;

  const { labels, datasets } = buildDistanceDatasets(bins);

  // Encontrar valor máximo para ajustar o eixo Y
  const maxValue = Math.max(
    ...datasets[0].data,
    ...datasets[1].data
  ) * 1.1; // Adiciona 10% de margem

  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: {
          ticks: {
            callback: v => fmtPct(v)
          },
          min: 0,
          max: maxValue > 0 ? maxValue : 1 // Garante que não seja zero
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const rate = ctx.parsed.y;
              const bin = bins[ctx.dataIndex];
              if (ctx.datasetIndex === 0) {
                return `${ctx.dataset.label}: ${fmtPct(rate)} (Tot: ${fmtNum(bin.total)} | Canc.: ${fmtNum(bin.driver)})`;
              }
              return `${ctx.dataset.label}: ${fmtPct(rate)} (Tot: ${fmtNum(bin.total)} | Canc.: ${fmtNum(bin.passenger)})`;
            }
          }
        },
        legend: { position: 'bottom' },
        title: { display: true, text: 'Taxa de Cancelamento por Faixa de Distância' }
      }
    }
  });
}

function makeStackedBar(canvasId, rows, type = 'address') {
  const ctx = getCtx(canvasId);
  if (!ctx || !rows?.length) return null;

  const builder = type === 'favela' ? buildTopFavDatasets : buildTopAddrDatasets;
  const built = builder(rows);

  const isFavelaChart = type === 'favela';

  return new Chart(ctx, {
    type: 'bar',
    data: { labels: built.labels, datasets: built.datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: isFavelaChart,
          ticks: {
            maxRotation: 45,
            minRotation: 45,
            autoSkip: false
          }
        },
        y: {
          stacked: isFavelaChart,
          beginAtZero: true,
          ticks: {
            callback: isFavelaChart
              ? (value) => `${value.toFixed(1)}%`  // Formato percentual para favelas
              : (value) => `${(value * 100).toFixed(0)}%`,
            stepSize: isFavelaChart ? 10 : 0.2  // Ajuste do stepSize para porcentagem
          }
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (context) => {
              const label = context.dataset.label || '';
              const value = context.raw;
              if (isFavelaChart) {
                return `${label}: ${fmtNum(value)}`;
              }
              return `${label}: ${(value * 100).toFixed(1)}%`;
            },
            afterLabel: (context) => {
              const meta = built.meta[context.dataIndex];
              const lines = [];

              if (isFavelaChart) {
                lines.push(
                  `Total corridas: ${fmtNum(meta.total)}`,
                  `Taxa Motorista: ${fmtPct(meta.driver_rate)}`,
                  `Taxa Passageiro: ${fmtPct(meta.passenger_rate)}`
                );
                return lines.join('\n');
              }

              // address chart
              lines.push(
                `Favela: ${meta.favela}`,
                `Zona: ${meta.zone || 'N/A'}`,
                `Distância: ${fmtNum(meta.distance)} m`,
                `Total corridas: ${fmtNum(meta.total)}`
              );

              // —— Comparativo do BAIRRO sem correlação com favela ——
              const bairro = meta.neighborhood || (meta.address?.split(',')[1]?.trim() || null);
              const nbAll = (window.__APP_STATS?.neighborhood_stats_all_raw || {})[bairro] || null;
              if (bairro) lines.push(`Bairro (comparativo): ${bairro}`);
              if (nbAll) {
                lines.push(
                  `• Taxa Motorista no bairro: ${fmtPct(Number(nbAll.driver_rate || (nbAll.driver / (nbAll.total||1))))}`,
                  `• Taxa Passageiro no bairro: ${fmtPct(Number(nbAll.passenger_rate || (nbAll.passenger / (nbAll.total||1))))}`
                );
              }

              return lines.join('\n');
            }
          }
        },
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 12,
            padding: 20,
            font: {
              size: 12
            }
          }
        }
      }
    }
  });
}


window.initFavelasCharts = function(appData, ids = {}) {
  window.__APP_STATS = appData?.stats || {};
  const { distance_bins = [], top_addresses = [], top_favelas = [] } = appData;
  const { dist = 'chartDist', addr = 'chartTopAddr', fav = 'chartTopFav' } = ids;

  destroyIfExists(distanceChart);
  destroyIfExists(topAddrChart);
  destroyIfExists(topFavChart);

  // Verificar se há dados válidos para favelas
  const hasFavelaData = top_favelas && top_favelas.length > 0;

  if (distance_bins.length) {
    distanceChart = makeDistanceChart(dist, distance_bins);
  }

  if (top_addresses.length) {
    topAddrChart = makeStackedBar(addr, top_addresses, 'address');
  } else {
    console.warn('Dados de endereços vazios - gráfico não renderizado');
  }

  if (hasFavelaData) {
    topFavChart = makeStackedBar(fav, top_favelas, 'favela');
    // Mostrar o container e esconder a mensagem de dados vazios
    document.getElementById('containerTopFav').style.display = 'block';
    document.getElementById('favelaEmptyMessage').classList.add('hidden');
    document.querySelector('#containerTopFav .chart-container').style.display = 'block';
  } else {
    console.warn('Dados de favelas insuficientes - gráfico não renderizado');
    // Mostrar mensagem e esconder o canvas
    document.getElementById('containerTopFav').style.display = 'block';
    document.getElementById('favelaEmptyMessage').classList.remove('hidden');
    document.querySelector('#containerTopFav .chart-container').style.display = 'none';
  }
};


/* ===================== GLOBAL EXPORTS ===================== */
window.initFavelasCharts = initFavelasCharts;
window.updateFavelasCharts = function(appData, ids) {
  window.initFavelasCharts(appData, ids);
};
window.makeDistanceChart = makeDistanceChart;
window.makeStackedBar = makeStackedBar;
window.pct = pct;
window.fmtPct = fmtPct;
window.fmtNum = fmtNum;