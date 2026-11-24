import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { setDigitMode } from '@/lib/digits.js'

/** UI preferences only (no secrets). */
export const useSettings = create(
  persist(
    (set) => ({
      theme: 'dark',
      digits: 'fa', // 'fa' | 'latin'
      hudDigits: 'latin', // canvas readouts
      autosave: true,
      setTheme: (theme) => set({ theme }),
      setDigits: (digits) => set({ digits }),
      setHudDigits: (hudDigits) => set({ hudDigits }),
      setAutosave: (autosave) => set({ autosave }),
    }),
    { name: 'annotator-settings', onRehydrateStorage: () => (s) => s && setDigitMode(s.digits) },
  ),
)

/** Apply side effects of settings (theme attribute, digit mode). */
export function applySettings(s) {
  document.documentElement.dataset.theme = s.theme
  setDigitMode(s.digits)
}
