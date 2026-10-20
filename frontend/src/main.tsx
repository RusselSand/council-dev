import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/fonts.css';
import './styles/tokens.css';
import './styles/global.css';
import { App } from './app/App';

const root = document.getElementById('root');
if (!root) throw new Error('Нет #root в index.html');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
