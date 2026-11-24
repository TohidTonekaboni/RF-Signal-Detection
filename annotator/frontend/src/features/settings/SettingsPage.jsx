import { useTranslation } from 'react-i18next'
import { useSettings } from './settingsStore.js'
import { setLanguage } from '@/i18n/index.js'
import { fmtNumber } from '@/lib/digits.js'

function Row({ label, children }) {
  return <div className="flex items-center justify-between gap-4 border-b border-border py-3"><span>{label}</span>{children}</div>
}

export default function SettingsPage() {
  const { t, i18n } = useTranslation()
  const s = useSettings()
  return (
    <div className="card mx-auto max-w-lg">
      <h1 className="mb-2 text-xl font-semibold">{t('settings.title')}</h1>
      <Row label={t('settings.language')}>
        <select className="input !w-auto" value={i18n.language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="fa">فارسی</option><option value="en">English</option>
        </select>
      </Row>
      <Row label={t('settings.theme')}>
        <select className="input !w-auto" value={s.theme} onChange={(e) => s.setTheme(e.target.value)}>
          <option value="dark">{t('settings.dark')}</option><option value="light">{t('settings.light')}</option>
        </select>
      </Row>
      <Row label={t('settings.digits')}>
        <select className="input !w-auto" value={s.digits} onChange={(e) => s.setDigits(e.target.value)}>
          <option value="fa">{t('settings.digitsFa')}</option><option value="latin">{t('settings.digitsLatin')}</option>
        </select>
      </Row>
      <Row label={t('settings.hudDigits')}>
        <select className="input !w-auto" value={s.hudDigits} onChange={(e) => s.setHudDigits(e.target.value)}>
          <option value="latin">{t('settings.digitsLatin')}</option><option value="fa">{t('settings.digitsFa')}</option>
        </select>
      </Row>
      <Row label={t('settings.autosave')}>
        <input type="checkbox" className="size-5 accent-[var(--color-accent)]" checked={s.autosave} onChange={(e) => s.setAutosave(e.target.checked)} aria-label={t('settings.autosave')} />
      </Row>
      <p className="mt-3 text-xs text-muted">{fmtNumber(1234567)}</p>
    </div>
  )
}
