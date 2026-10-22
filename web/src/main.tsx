import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { upgradeLegacyLink } from './app/router';
import { AppProvider } from './app/store';
import './styles/tokens.css';
import './styles/base.css';
import './styles/ui.css';
import './styles/shell.css';
import './styles/pages.css';
import './styles/lesson.css';
import './styles/chat.css';
import './styles/states.css';
import './styles/create.css';
import './styles/screens.css';
import './styles/motion.css';
import './styles/together.css';

upgradeLegacyLink();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
);
