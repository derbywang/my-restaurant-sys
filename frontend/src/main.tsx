import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ToastProvider } from '@ury/ui'
import './index.css'
import App from './App.tsx'
import { initI18n } from './i18n'

initI18n().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter basename="/ury">
        <App />
        <ToastProvider />
      </BrowserRouter>
    </StrictMode>,
  )
})
