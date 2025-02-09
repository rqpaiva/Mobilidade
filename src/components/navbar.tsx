import React from 'react';
import { Link } from 'react-router';

const Navbar = () => {
  return (
    <nav>
      <ul>
        <li><Link to="/">Home</Link></li>
        <li><Link to="/analise-espacial">Análise Espacial</Link></li>
        <li><Link to="/analise-temporal">Análise Temporal</Link></li>
        <li><Link to="/analise-pessoal">Análise Pessoal</Link></li>
        <li><Link to="/dados-correlacionados">Análise Sociodemográfica</Link></li>
        <li><Link to="/mapa_ocorrencias">Impacto dos Eventos na Cidade</Link></li>
        <li><Link to="/impacto_eventos">Impacto Eventos</Link></li>
      </ul>
    </nav>
  );
};

export default Navbar;