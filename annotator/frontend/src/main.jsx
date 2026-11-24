import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tailwind.css'
import './i18n/index.js'
import { applyDocumentLang } from './i18n/index.js'
import i18n from './i18n/index.js'
import { applySettings, useSettings } from './features/settings/settingsStore.js'
import App from './app/App.jsx'

applyDocumentLang(i18n.language)
applySettings(useSettings.getState())
useSettings.subscribe(applySettings)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
