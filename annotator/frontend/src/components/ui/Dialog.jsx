import * as D from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function Dialog({ open, onOpenChange, title, description, children, footer, wide }) {
  const { t } = useTranslation()
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <D.Content className={`fixed start-1/2 top-1/2 z-50 max-h-[90vh] w-[92vw] -translate-y-1/2 overflow-auto rounded-md border border-border bg-panel p-5 shadow-xl ltr:-translate-x-1/2 rtl:translate-x-1/2 ${wide ? 'max-w-2xl' : 'max-w-md'}`}>
          <div className="mb-3 flex items-start justify-between gap-4">
            <D.Title className="text-lg font-semibold">{title}</D.Title>
            <D.Close className="btn !p-1" aria-label={t('common.close')}><X size={16} /></D.Close>
          </div>
          {description ? <D.Description className="mb-3 text-sm text-muted">{description}</D.Description> : <D.Description className="sr-only">{title}</D.Description>}
          {children}
          {footer && <div className="mt-4 flex justify-end gap-2">{footer}</div>}
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}
