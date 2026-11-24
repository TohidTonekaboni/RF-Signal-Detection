import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import fa from './fa.json'
import en from './en.json'

const stored = (() => { try { return localStorage.getItem('lang') } catch { return null } })()

i18n.use(initReactI18next).init({
  resources: { fa: { translation: fa }, en: { translation: en } },
  lng: stored === 'en' ? 'en' : 'fa',
  fallbackLng: 'fa',
  interpolation: { escapeValue: false },
})

export const dirFor = (lng) => (lng === 'fa' ? 'rtl' : 'ltr')

/** Apply language + direction to <html>. Call on init and on change. */
export function applyDocumentLang(lng) {
  document.documentElement.lang = lng
  document.documentElement.dir = dirFor(lng)
}

export function setLanguage(lng) {
  try { localStorage.setItem('lang', lng) } catch { /* ignore */ }
  i18n.changeLanguage(lng)
  applyDocumentLang(lng)
}

export default i18n
