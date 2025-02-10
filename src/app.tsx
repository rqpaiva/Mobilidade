import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router';
import Home from './pages/home';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />

        {/* routes */}
      </Routes>
    </Router>
  );
}

export default App;