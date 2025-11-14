// static/scripts/reclame_aqui.js
// Arquivo JS puro (sem Jinja). Gera e atualiza os gráficos da página Reclame Aqui.

// Registro global de instâncias para permitir destroy() em re-renderizações
window.__RACharts = window.__RACharts || {};

function ensureChartJs() {
  if (typeof Chart === 'undefined') {
    console.error('Chart.js não está carregado');
    return false;
  }
  return true;
}

function upsertChart(canvasId, config) {
  if (!ensureChartJs()) return;
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.warn(`Canvas #${canvasId} não encontrado`);
    return;
  }
  const ctx = canvas.getContext('2d');
  if (window.__RACharts[canvasId]) {
    try { window.__RACharts[canvasId].destroy(); } catch (e) {}
  }
  window.__RACharts[canvasId] = new Chart(ctx, config);
}

// ---------- Gráficos de Problemas (Containers 3) ----------
function initProblemChart(canvasId, data, title, color) {
  const keys = data ? Object.keys(data) : [];
  const vals = data ? Object.values(data) : [];
  if (!keys.length) {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.font = '14px sans-serif';
      ctx.fillText('Nenhum dado disponível', 16, 24);
    }
    return;
  }

  upsertChart(canvasId, {
    type: 'bar',
    data: {
      labels: keys,
      datasets: [{
        label: title,
        data: vals,
        backgroundColor: color,
        borderColor: color.replace('0.7', '1'),
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: { display: true, text: title, font: { size: 16, weight: 'bold' } },
        tooltip: {
          callbacks: {
            label: function(context) {
              const total = vals.reduce((a,b)=>a+b,0);
              const value = context.parsed.y;
              const pct = total > 0 ? ((value/total)*100).toFixed(1) : 0;
              return `${context.dataset.label}: ${value} (${pct}%)`;
            }
          }
        }
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: 'Quantidade' } },
        x: {
          ticks: { maxRotation: 45, minRotation: 45 },
          title: { display: true, text: 'Tipo de Problema' }
        }
      }
    }
  });
}

// Wrapper chamado pelo HTML com os dois dicionários
function initProblemCharts(passengerProblems, driverProblems) {
  initProblemChart(
    'passengerProblemsChart',
    passengerProblems || {},
    'Problemas Reportados por Passageiros',
    'rgba(54, 162, 235, 0.7)'
  );
  initProblemChart(
    'driverProblemsChart',
    driverProblems || {},
    'Problemas Reportados por Motoristas',
    'rgba(255, 99, 132, 0.7)'
  );
}

// ---------- Gráficos de Detalhamento por Subtipos (Container 3B) ----------
function initProblemSubtypeCharts(breakdown) {
  // Map canvas por categoria
  const canvasMap = {
    discriminacao: 'discriminacaoBreakdownChart',
    funcionamento_app: 'funcionamentoBreakdownChart',
    problemas_servico: 'servicoBreakdownChart'
  };

  // Paletas distintas por categoria (horizontal bars)
  const palette = {
    discriminacao:  ['rgba(142,68,173,0.9)','rgba(155,89,182,0.9)','rgba(176, 58, 46,0.9)','rgba(192, 57, 43,0.9)','rgba(231,76,60,0.9)','rgba(214, 48, 49,0.9)'],
    funcionamento_app: ['rgba(33,150,243,0.9)','rgba(3,169,244,0.9)','rgba(0,188,212,0.9)','rgba(0,150,136,0.9)','rgba(0,121,107,0.9)','rgba(0,105,92,0.9)'],
    problemas_servico: ['rgba(76,175,80,0.9)','rgba(139,195,74,0.9)','rgba(205,220,57,0.9)','rgba(255,235,59,0.9)','rgba(255,193,7,0.9)','rgba(255,152,0,0.9)']
  };

  const makeLabel = (subkey) => {
    // rótulos amigáveis
    const map = {
      redlining_bairro: 'Redlining/Bairro',
      bug_erro_crash: 'Bug/Erro/Crash',
      login_acesso: 'Login/Acesso',
      instalacao_atualizacao: 'Instalação/Atualização',
      bloqueio_conta: 'Bloqueio de Conta',
      performance_conexao: 'Performance/Conexão',
      cobranca_tarifa: 'Cobrança/Tarifa',
      cancelamento_recusa: 'Cancelamento/Recusa',
      atraso_espera: 'Atraso/Espera',
      comportamento_motorista: 'Comportamento do Motorista',
      condicoes_veiculo: 'Condições do Veículo',
      rota_valor: 'Rota/Valor'
    };
    return map[subkey] || (subkey.charAt(0).toUpperCase() + subkey.slice(1).replaceAll('_',' '));
  };

  Object.entries(canvasMap).forEach(([cat, canvasId]) => {
    const dataObj = (breakdown && breakdown[cat]) ? breakdown[cat] : {};
    const keys = Object.keys(dataObj);
    const vals = keys.map(k => dataObj[k]);

    if (!keys.length) {
      const canvas = document.getElementById(canvasId);
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.font = '14px sans-serif';
        ctx.fillText('Nenhum dado disponível', 16, 24);
      }
      return;
    }

    const labels = keys.map(makeLabel);
    const colors = palette[cat];
    const bg = labels.map((_, i) => colors[i % colors.length]);

    upsertChart(canvasId, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Ocorrências',
          data: vals,
          backgroundColor: bg,
          borderColor: bg.map(c => c.replace('0.9','1')),
          borderWidth: 1
        }]
      },
      options: {
        indexAxis: 'y',            // barras horizontais
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.label}: ${ctx.parsed.x}`
            }
          },
          legend: { display: false }
        },
        scales: {
          x: {
            beginAtZero: true,
            title: { display: true, text: 'Quantidade' }
          },
          y: {
            title: { display: false }
          }
        }
      }
    });
  });
}


// ---------- Gráfico: Distribuição por Nº de Macro-categorias (Container 3C) ----------
function initMultiClassificationChart(summary) {
  if (!summary || !summary.macro_hist) {
    const canvas = document.getElementById('multiClassHistogramChart');
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.font = '14px sans-serif';
      ctx.fillText('Nenhum dado disponível', 16, 24);
    }
    return;
  }

  const labels = ['0 categorias', '1 categoria', '2 categorias', '3 categorias'];
  const vals = [
    summary.macro_hist['0'] || 0,
    summary.macro_hist['1'] || 0,
    summary.macro_hist['2'] || 0,
    summary.macro_hist['3'] || 0
  ];

  const bg = [
    'rgba(160, 160, 160, 0.85)', // 0
    'rgba(100, 181, 246, 0.85)', // 1 (azul claro)
    'rgba(255, 183,  77, 0.85)', // 2 (laranja)
    'rgba(229,  57,  53, 0.85)'  // 3 (vermelho)
  ];
  const border = bg.map(c => c.replace('0.85', '1'));

  upsertChart('multiClassHistogramChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Quantidade de Reclamações',
        data: vals,
        backgroundColor: bg,
        borderColor: border,
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: 'y', // barras horizontais
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.raw} reclamações`
          }
        },
        legend: { display: false }
      },
      scales: {
        x: {
          beginAtZero: true,
          title: { display: true, text: 'Quantidade' }
        },
        y: {
          title: { display: false }
        }
      }
    }
  });
}

// ---------- Gráficos: Coocorrência entre Subcategorias (Container 3D) ----------
function initSubtypeCooccurrenceCharts(cooc) {
  const makeBar = (canvasId, rows, valueKey, title) => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const labels = rows.map(r => r.pair_label);
    const vals   = rows.map(r => r[valueKey]);

    // Cores: intra (azul) vs cross (verde)
    const bg = rows.map(r => r.intra ? 'rgba(63, 81, 181, 0.9)' : 'rgba(0, 150, 136, 0.9)');
    const bd = bg.map(c => c.replace('0.9', '1'));

    // Tooltips com métricas
    const metrics = rows.map(r => ({
      count: r.count, support: r.support, jaccard: r.jaccard, lift: r.lift,
      conf_ab: r.confidence_a_to_b, conf_ba: r.confidence_b_to_a,
      a_label: r.a_label, b_label: r.b_label, intra: r.intra
    }));

    upsertChart(canvasId, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: title,
          data: vals,
          backgroundColor: bg,
          borderColor: bd,
          borderWidth: 1,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: { display: false },
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const m = metrics[ctx.dataIndex];
                const val = ctx.raw;
                // valor principal
                const head = (valueKey === 'count') ? `Contagem: ${val}` : `Lift: ${val}`;
                // linhas extras
                const lines = [
                  head,
                  `A: ${m.a_label}`,
                  `B: ${m.b_label}`,
                  `Suporte: ${m.support}`,
                  `Jaccard: ${m.jaccard}`,
                  `Conf(A→B): ${m.conf_ab}`,
                  `Conf(B→A): ${m.conf_ba}`,
                  m.intra ? 'Intra-categoria' : 'Entre categorias'
                ];
                return lines;
              }
            }
          }
        },
        scales: {
          x: { beginAtZero: true, title: { display: true, text: (valueKey === 'count' ? 'Contagem' : 'Lift') } },
          y: { title: { display: false } }
        }
      }
    });
  };

  const byCount = (cooc && cooc.pairs_by_count) || [];
  const byLift  = (cooc && cooc.pairs_by_lift)  || [];

  if (!byCount.length && !byLift.length) {
    // mensagem mínima no canvas, se quiser
    return;
  }

  makeBar('subtypePairsCountChart', byCount, 'count', 'Top pares por contagem');
  makeBar('subtypePairsLiftChart',  byLift,  'lift',  'Top pares por lift');
}


// ---------- Gráfico de Série Temporal (Container 4) ----------
function initTimeSeriesChart(timeSeriesData) {
  const labels = (timeSeriesData && timeSeriesData.labels) || [];
  const L = labels.length;
  const arr = (a) => (Array.isArray(a) ? a : new Array(L).fill(0));

  if (!labels.length) {
    const canvas = document.getElementById('timeSeriesChart');
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.font = '14px sans-serif';
      ctx.fillText('Nenhum dado disponível para série temporal', 16, 24);
    }
    return;
  }

  // Paletas bem distintas p/ Passageiros (azuis) vs Motoristas (laranja/vermelho)
  const P1 = { bg: 'rgba(144, 202, 249, 0.85)', border: 'rgba(144, 202, 249, 1)' }; // Azul claro (baixa)
  const P2 = { bg: 'rgba( 66, 165, 245, 0.85)', border: 'rgba( 66, 165, 245, 1)' }; // Azul (média)
  const P3 = { bg: 'rgba( 30, 136, 229, 0.85)', border: 'rgba( 30, 136, 229, 1)' }; // Azul escuro (alta)
  const P4 = { bg: 'rgba( 13,  71, 161, 0.85)', border: 'rgba( 13,  71, 161, 1)' }; // Azul mais escuro (crítica)

  const M1 = { bg: 'rgba(255, 224, 130, 0.85)', border: 'rgba(255, 224, 130, 1)' }; // Amarelo/laranja claro (baixa)
  const M2 = { bg: 'rgba(255, 183,  77, 0.85)', border: 'rgba(255, 183,  77, 1)' }; // Laranja (média)
  const M3 = { bg: 'rgba(255, 112,  67, 0.85)', border: 'rgba(255, 112,  67, 1)' }; // Laranja forte (alta)
  const M4 = { bg: 'rgba(211,  47,  47, 0.85)', border: 'rgba(211,  47,  47, 1)' }; // Vermelho (crítica)

  upsertChart('timeSeriesChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [
        // PASSAGEIROS (stack "Passageiros")
        {
          label: 'Passageiros - Baixa',
          data: arr(timeSeriesData.passenger_baixa),
          stack: 'Passageiros',
          backgroundColor: P1.bg,
          borderColor: P1.border,
          borderWidth: 1,
          order: 1
        },
        {
          label: 'Passageiros - Média',
          data: arr(timeSeriesData.passenger_media),
          stack: 'Passageiros',
          backgroundColor: P2.bg,
          borderColor: P2.border,
          borderWidth: 1,
          order: 1
        },
        {
          label: 'Passageiros - Alta',
          data: arr(timeSeriesData.passenger_alta),
          stack: 'Passageiros',
          backgroundColor: P3.bg,
          borderColor: P3.border,
          borderWidth: 1,
          order: 1
        },
        {
          label: 'Passageiros - Crítica',
          data: arr(timeSeriesData.passenger_critica),
          stack: 'Passageiros',
          backgroundColor: P4.bg,
          borderColor: P4.border,
          borderWidth: 1,
          order: 1
        },

        // MOTORISTAS (stack "Motoristas")
        {
          label: 'Motoristas - Baixa',
          data: arr(timeSeriesData.motorista_baixa),
          stack: 'Motoristas',
          backgroundColor: M1.bg,
          borderColor: M1.border,
          borderWidth: 1,
          order: 2
        },
        {
          label: 'Motoristas - Média',
          data: arr(timeSeriesData.motorista_media),
          stack: 'Motoristas',
          backgroundColor: M2.bg,
          borderColor: M2.border,
          borderWidth: 1,
          order: 2
        },
        {
          label: 'Motoristas - Alta',
          data: arr(timeSeriesData.motorista_alta),
          stack: 'Motoristas',
          backgroundColor: M3.bg,
          borderColor: M3.border,
          borderWidth: 1,
          order: 2
        },
        {
          label: 'Motoristas - Crítica',
          data: arr(timeSeriesData.motorista_critica),
          stack: 'Motoristas',
          backgroundColor: M4.bg,
          borderColor: M4.border,
          borderWidth: 1,
          order: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: {
          display: true,
          text: 'Evolução Temporal das Reclamações (Barras empilhadas por severidade, 2 grupos: Passageiros x Motoristas)',
          font: { size: 16, weight: 'bold' }
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: {
            // Exibe também o total por grupo (stack) no rodapé do tooltip
            footer: (items) => {
              if (!items || !items.length) return '';
              const idx = items[0].dataIndex;
              // soma por stack
              const sumByStack = items.reduce((acc, it) => {
                const stack = it.dataset.stack || 'total';
                acc[stack] = (acc[stack] || 0) + (it.parsed.y || 0);
                return acc;
              }, {});
              const parts = Object.entries(sumByStack).map(([stack, val]) => `Total ${stack}: ${val}`);
              return parts.join(' | ');
            }
          }
        },
        legend: {
          position: 'top',
          labels: {
            // deixa a legenda mais legível
            usePointStyle: true,
            boxWidth: 12
          }
        }
      },
      scales: {
        x: {
          stacked: true,
          title: { display: true, text: 'Período' }
        },
        y: {
          stacked: true,
          beginAtZero: true,
          title: { display: true, text: 'Quantidade de Reclamações' }
        }
      },
      // Ajuste de largura para barras agrupadas
      categoryPercentage: 0.7,
      barPercentage: 0.9
    }
  });
}


// ---------- Gráfico de Distribuição por Tipo (Container 5) ----------
function initUserTypeChart(userTypeData) {
  const keys = userTypeData ? Object.keys(userTypeData) : [];
  const vals = userTypeData ? Object.values(userTypeData) : [];
  if (!keys.length) {
    const canvas = document.getElementById('userTypeChart');
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.font = '14px sans-serif';
      ctx.fillText('Nenhum dado disponível', 16, 24);
    }
    return;
  }

  const labels = keys.map(k => ({ passageiro:'Passageiro', motorista:'Motorista', desconhecido:'Desconhecido' }[k] || k));

  upsertChart('userTypeChart', {
    type: 'pie',
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: [
          'rgba(54,162,235,0.7)',
          'rgba(255,99,132,0.7)',
          'rgba(255,206,86,0.7)',
          'rgba(75,192,192,0.7)',
          'rgba(153,102,255,0.7)'
        ],
        borderColor: [
          'rgba(54,162,235,1)',
          'rgba(255,99,132,1)',
          'rgba(255,206,86,1)',
          'rgba(75,192,192,1)',
          'rgba(153,102,255,1)'
        ],
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: { display: true, text: 'Distribuição por Tipo de Reclamante', font: { size: 16, weight: 'bold' } },
        tooltip: {
          callbacks: {
            label: function(ctx){
              const total = ctx.dataset.data.reduce((a,b)=>a+b,0);
              const value = ctx.parsed;
              const pct = total>0 ? ((value/total)*100).toFixed(1) : 0;
              return `${ctx.label}: ${value} (${pct}%)`;
            }
          }
        }
      }
    }
  });
}

// Expor no escopo global para o HTML chamar
window.initProblemChart   = initProblemChart;
window.initProblemCharts  = initProblemCharts;
window.initProblemSubtypeCharts = initProblemSubtypeCharts;
window.initMultiClassificationChart = initMultiClassificationChart;
window.initSubtypeCooccurrenceCharts = initSubtypeCooccurrenceCharts;
window.initTimeSeriesChart= initTimeSeriesChart;
window.initUserTypeChart  = initUserTypeChart;
