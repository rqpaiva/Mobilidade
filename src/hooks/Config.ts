export const baseURL = process.env.REACT_APP_BACKEND_URL;

export const endpoints = Object.freeze({
  uploadCsv: '/upload-csv',
  analiseEspacial: '/analise-espacial',
  analiseTemporal: '/analise-temporal',
  analisePessoal: '/analise-pessoal',
  dadosCorrelacionados: '/dados-correlacionados',
  impactoEventos: '/impacto-eventos',
})