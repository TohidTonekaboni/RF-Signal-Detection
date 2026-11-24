import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fmtNumber } from '@/lib/digits.js'

export function Pagination({ page, pageSize, total, onChange }) {
  const { t } = useTranslation()
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav className="mt-4 flex items-center justify-center gap-3 text-sm" aria-label="pagination">
      <button className="btn" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        <ChevronLeft size={16} className="rtl:-scale-x-100" />{t('common.prev')}
      </button>
      <span>{t('common.page')} {fmtNumber(page)} {t('common.of')} {fmtNumber(pages)}</span>
      <button className="btn" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        {t('common.next')}<ChevronRight size={16} className="rtl:-scale-x-100" />
      </button>
    </nav>
  )
}
