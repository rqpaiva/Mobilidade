import React from 'react';
import Navbar from '../../components/navbar';
import FrameLoader from '../../components/frameLoader';
import {endpoints} from '../../hooks/Config';

const DadosCorrelacionados = () => {
  return (
    <div className='v1_17'>
      <span className='v5_3'>Análise Sociodemográfica</span>
      <div className='container-content'>
        <Navbar />
      </div>
      <FrameLoader endpoint={ endpoints.dadosCorrelacionados } />
    </div>
  );

};

export default DadosCorrelacionados;
