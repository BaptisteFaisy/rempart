import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

// GitHub Pages sert le site sous /<repo>/ : le routeur doit connaître ce
// préfixe, sinon `/fleet` est interprété à la racine du domaine et tout 404.
// En local, BASE_URL vaut '/' et le basename est neutre.
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
