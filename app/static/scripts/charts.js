import { unidecode } from './main.js';

// Mapeamentos
const TURNO_MAP = {
  0: '0h as 6h', 1: '7h as 10h', 2: '11h as 14h',
  3: '15h as 16h', 4: '17h as 20h', 5: '21h as 23h'
};
const WEEK_DAY_MAP = {
  0: 'Segunda', 1: 'Terça', 2: 'Quarta',
  3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
};

// Cores
const CHART_COLORS = {
  completed: '#4e79a7',
  driverCancel: '#e15759',
  passengerCancel: '#f28e2b'
};

// Opções base
const PIE_CHART_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: ctx => {
          const label = ctx.label || '';
          const val   = ctx.raw || 0;
          const total = ctx.dataset.data.reduce((a,b)=>a+b, 0);
          return `${label}: ${val} (${Math.round((val/total)*100)}%)`;
        }
      }
    },
    title: { display:true, font:{ size:14 } }
  },
  cutout: '60%'
};
const BAR_CHART_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    x: { stacked:true },
    y: { stacked:true, beginAtZero:true }
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: ctx => {
          const label = ctx.dataset.label || '';
          const val   = ctx.raw || 0;
          const total = ctx.chart.data.datasets
            .map(d => d.data[ctx.dataIndex]).reduce((a,b)=>a+b,0);
          return `${label}: ${val} (${Math.round((val/total)*100)}%)`;
        }
      }
    },
    title: { display:true, font:{ size:14 }, text: '' }
  }
};

export function initCharts(appData) {
  initTemporalCharts(appData.temporal);
  initProfileCharts(appData.profileDrivers);
}

function initTemporalCharts(temporalData) {
  if (!temporalData) {
    console.error('Dados temporais não disponíveis');
    return;
  }
  // Turno
  const turnoLabels = Object.values(TURNO_MAP);
  const turnoData = turnoLabels.map(l =>
    temporalData.turno[l] || { completed:0, driver_cancel:0, passenger_cancel:0 }
  );
  initTurnoChart(turnoLabels, turnoData);

  // Dia da semana
  const weekLabels = Object.values(WEEK_DAY_MAP);
  const weekData = weekLabels.map(l =>
    temporalData.week_day[l] || { completed:0, driver_cancel:0, passenger_cancel:0 }
  );
  initWeekDayChart(weekLabels, weekData);

  // Horas
  if (temporalData.hourly) {
    initHourlyChart(temporalData.hourly);
  }
}

function initTurnoChart(labels, data) {
  const ctxEl = document.getElementById('chartTurno');
  if (!ctxEl) return;
  new Chart(ctxEl.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label:'Finalizadas',      data:data.map(d=>d.completed),       backgroundColor:CHART_COLORS.completed,     stack:'s' },
        { label:'Cancel. Motorista', data:data.map(d=>d.driver_cancel),   backgroundColor:CHART_COLORS.driverCancel,  stack:'s' },
        { label:'Cancel. Passageiro',data:data.map(d=>d.passenger_cancel),backgroundColor:CHART_COLORS.passengerCancel,stack:'s' }
      ]
    },
    options: {
      ...BAR_CHART_OPTIONS,
      plugins: {
        ...BAR_CHART_OPTIONS.plugins,
        title: { ...BAR_CHART_OPTIONS.plugins.title, text:'Corridas por Turno' }
      }
    }
  });
}

function initWeekDayChart(labels, data) {
  const ctxEl = document.getElementById('chartWeekDay')?.getContext('2d');
  if (!ctxEl) return;

  // Garante a ordem correta
  const order = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'];
  const filtered = order.filter(d => labels.includes(d));
  const datasets = [
    { label:'Finalizadas',      data:filtered.map(d=>data[labels.indexOf(d)].completed),       backgroundColor:CHART_COLORS.completed },
    { label:'Cancel. Motorista', data:filtered.map(d=>data[labels.indexOf(d)].driver_cancel),   backgroundColor:CHART_COLORS.driverCancel },
    { label:'Cancel. Passageiro',data:filtered.map(d=>data[labels.indexOf(d)].passenger_cancel),backgroundColor:CHART_COLORS.passengerCancel }
  ];

  new Chart(ctxEl, {
    type: 'bar',
    data: { labels:filtered, datasets },
    options: {
      ...BAR_CHART_OPTIONS,
      scales: {
        ...BAR_CHART_OPTIONS.scales,
        x: { stacked:false },
        y: { stacked:false }
      },
      plugins: {
        ...BAR_CHART_OPTIONS.plugins,
        title: { ...BAR_CHART_OPTIONS.plugins.title, text:'Corridas por Dia da Semana' }
      }
    }
  });
}

function initHourlyChart(hourlyData) {
  const ctxEl = document.getElementById('chartHourly')?.getContext('2d');
  if (!ctxEl) return;

  const hours = Object.keys(hourlyData).sort((a,b) =>
    parseInt(a.split('h')[0]) - parseInt(b.split('h')[0])
  );
  const dataset = [
    { label:'Finalizadas',      data:hours.map(h=>hourlyData[h].completed),       backgroundColor:CHART_COLORS.completed,     stack:'s' },
    { label:'Cancel. Motorista', data:hours.map(h=>hourlyData[h].driver_cancel),   backgroundColor:CHART_COLORS.driverCancel,  stack:'s' },
    { label:'Cancel. Passageiro',data:hours.map(h=>hourlyData[h].passenger_cancel),backgroundColor:CHART_COLORS.passengerCancel,stack:'s' }
  ];

  new Chart(ctxEl, {
    type:'bar',
    data:{ labels:hours, datasets:dataset },
    options:{
      ...BAR_CHART_OPTIONS,
      plugins:{
        ...BAR_CHART_OPTIONS.plugins,
        title:{ ...BAR_CHART_OPTIONS.plugins.title, text:'Corridas por Hora do Dia' }
      }
    }
  });
}

function initProfileCharts(profileData) {
  if (!profileData) {
    console.error('Dados de perfil não disponíveis');
    return;
  }
  const charts = [
    { id:'carTypeChart', data:profileData.car_types, title:'Categorias de Veículos' },
    { id:'raceChart',    data:profileData.race,      title:'Raça/Cor' },
    { id:'genderChart',  data:profileData.gender,    title:'Gênero' },
    { id:'ageChart',     data:profileData.age,       title:'Faixa Etária' },
    { id:'fitnessChart', data:profileData.fitness,   title:'Condição Física' }
  ];
  charts.forEach(c => {
    const ctxEl = document.getElementById(c.id)?.getContext('2d');
    if (!ctxEl || !c.data || !Object.keys(c.data).length) {
      document.getElementById(c.id)?.parentElement
        .insertAdjacentHTML('beforeend','<p class="no-data">Sem dados</p>');
      return;
    }
    new Chart(ctxEl, {
      type:'pie',
      data:{
        labels: Object.keys(c.data),
        datasets:[{
          data: Object.values(c.data),
          backgroundColor: Object.keys(c.data)
            .map((_,i)=>['#4e79a7','#f28e2b','#e15759','#59a14f','#8cd17d'][i%5]),
          borderWidth:1
        }]
      },
      options:{
        ...PIE_CHART_OPTIONS,
        plugins:{
          ...PIE_CHART_OPTIONS.plugins,
          title:{ ...PIE_CHART_OPTIONS.plugins.title, text:c.title }
        }
      }
    });
  });
}