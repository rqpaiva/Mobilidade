import React from 'react';
import Navbar from '../components/navbar';
import UploadSection from '../components/uploadSection';

import '../styles/menu.css'
import '../styles/index.css'

const Home = () => {
  return (
    <div className='v1_17'>
      <span className='v5_3'>Visão Estratégica de Cancelamentos em Apps de Mobilidade</span>
      <div className='container-content'>
        <Navbar />
        <div className='v15_30'>
          <img src='/Mobilidade/eccb17e445d1417595732e3a62df4f28.jpg' alt='' />
        </div>
      </div>
      <UploadSection />
    </div>
  );

};

export default Home;