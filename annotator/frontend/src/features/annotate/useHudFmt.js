import { useSettings } from '@/features/settings/settingsStore.js'
import { toPersianDigits } from '@/lib/digits.js'

/** Canvas HUD digit policy: a visible, consistent setting (Latin by default for unit readouts). */
export function useHudFmt() {
  const hud = useSettings((s) => s.hudDigits)
  return (s) => (hud === 'fa' ? toPersianDigits(s) : String(s))
}
