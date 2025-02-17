import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router';
import Home from './pages/home';
import AnaliseTemporal from './pages/analise-temporal';
import AnalisePessoal from './pages/analise-pessoal';
import DadosCorrelacionados from './pages/dados-correlacionados';
import MapaOcorrencias from './pages/mapa-ocorrencias';
import ImpactoEventos from './pages/impacto-eventos';
import AnaliseEspacialEmbed from './pages/analise-espacial-embed';

function App() {
  return (
    <Router>
      <Routes>
        <Route path='/Mobilidade/' element={<Home />} />
        <Route path='/Mobilidade/analise-espacial-embed' element={<AnaliseEspacialEmbed />} />
        <Route path='/Mobilidade/analise-temporal' element={<AnaliseTemporal />} />
        <Route path='/Mobilidade/analise-pessoal' element={<AnalisePessoal />} />
        <Route path='/Mobilidade/dados-correlacionados' element={<DadosCorrelacionados />} />
        <Route path='/Mobilidade/mapa-ocorrencias' element={<MapaOcorrencias />} />
        <Route path='/Mobilidade/impacto-eventos' element={<ImpactoEventos />} />
      </Routes>
    </Router>
  );
}

export default App;