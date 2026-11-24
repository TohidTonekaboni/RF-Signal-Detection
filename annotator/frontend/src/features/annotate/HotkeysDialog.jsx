import { useTranslation } from 'react-i18next'
import { Dialog } from '@/components/ui/Dialog.jsx'
import { HOTKEYS } from '@/lib/hotkeys.js'
import { Ltr } from '@/components/ui/Ltr.jsx'

/** Cheat-sheet generated from the single hotkey registry. */
export default function HotkeysDialog({ open, onOpenChange }) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t('annotate.shortcuts')}>
      <table className="w-full text-sm"><tbody>
        {HOTKEYS.map((h) => (
          <tr key={h.action} className="border-b border-border"><td className="py-1.5">{t(h.labelKey)}</td>
            <td className="py-1.5 text-end"><kbd className="rounded bg-panel-2 px-2 py-0.5 font-mono text-xs"><Ltr>{h.display || h.keys.split(',')[0].toUpperCase()}</Ltr></kbd></td></tr>
        ))}
      </tbody></table>
    </Dialog>
  )
}
