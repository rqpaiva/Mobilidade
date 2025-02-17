import React from 'react';
import { Link } from 'react-router';

const Navbar = () => {
  return (
    <nav>
      <ul>
        <li><Link to='/Mobilidade'>Home</Link></li>
        <li><Link to='/Mobilidade/analise-espacial-embed'>Análise Espacial (Embed)</Link></li>
        <li><Link to='/Mobilidade/analise-temporal'>Análise Temporal</Link></li>
        <li><Link to='/Mobilidade/analise-pessoal'>Análise Pessoal</Link></li>
        <li><Link to='/Mobilidade/dados-correlacionados'>Análise Sociodemográfica</Link></li>
        <li><Link to='/Mobilidade/mapa-ocorrencias'>Impacto dos Eventos na Cidade</Link></li>
        <li><Link to='/Mobilidade/impacto-eventos'>Impacto Eventos</Link></li>
      </ul>
    </nav>
  );
};

export default Navbar;
