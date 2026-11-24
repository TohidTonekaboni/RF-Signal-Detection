import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function Spinner() { return <Loader2 className="animate-spin text-muted" size={20} aria-hidden /> }

export function Loading() {
  const { t } = useTranslation()
  return <div className="flex items-center gap-2 p-6 text-muted" role="status"><Spinner />{t('app.loading')}</div>
}

export function ErrorState({ onRetry }) {
  const { t } = useTranslation()
  return <div className="p-6 text-danger" role="alert">{t('common.loadError')} <button className="btn ms-2" onClick={onRetry}>{t('common.retry')}</button></div>
}

export function Empty({ children }) {
  const { t } = useTranslation()
  return <div className="p-8 text-center text-muted">{children || t('common.empty')}</div>
}
