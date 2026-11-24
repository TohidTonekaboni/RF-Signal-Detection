import { useTranslation } from 'react-i18next'
import { Trash2, RotateCcw } from 'lucide-react'
import { useWorkspaceStore } from './workspaceStore.js'
import { COLORMAPS, buildLut } from '@/lib/colormap.js'
import { boxToUnits, formatHz, formatSeconds } from '@/lib/units.js'
import { useHudFmt } from './useHudFmt.js'
import { Ltr } from '@/components/ui/Ltr.jsx'
import { cn } from '@/lib/cn.js'
import { fmtNumber } from '@/lib/digits.js'

export function ClassPanel({ classes, readOnly }) {
  const { t } = useTranslation()
  const { activeClass, setActiveClass, imageLabels, toggleImageLabel } = useWorkspaceStore()
  return (
    <section aria-label={t('annotate.classes')}>
      <h3 className="mb-2 text-xs uppercase text-muted">{t('annotate.classes')}</h3>
      <ul className="space-y-1">
        {classes.map((c, i) => (
          <li key={c.id}>
            <button disabled={readOnly} onClick={() => setActiveClass(c.id)}
              className={cn('flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-sm hover:bg-panel-2', activeClass === c.id && 'border-accent bg-panel-2')}>
              <i className="size-3 rounded-sm" style={{ background: c.color }} />
              <span className="flex-1 text-start">{c.name}</span>
              <kbd className="rounded bg-bg px-1.5 font-mono text-[10px] text-muted">{i + 1}</kbd>
            </button>
          </li>
        ))}
      </ul>
      <h3 className="mb-2 mt-4 text-xs uppercase text-muted">{t('annotate.imageLabels')}</h3>
      <div className="flex flex-wrap gap-1">
        {classes.map((c) => (
          <label key={c.id} className="flex cursor-pointer items-center gap-1 rounded bg-panel-2 px-2 py-0.5 text-xs">
            <input type="checkbox" disabled={readOnly} checked={imageLabels.includes(c.name)} onChange={() => toggleImageLabel(c.name)} />{c.name}
          </label>
        ))}
      </div>
    </section>
  )
}

export function BoxList({ classes, meta }) {
  const { t } = useTranslation()
  const fmt = useHudFmt()
  const { boxes, selection, select, deleteSelected } = useWorkspaceStore()
  const nameOf = (id) => classes.find((c) => c.id === id)
  return (
    <section aria-label={t('annotate.boxes')}>
      <h3 className="mb-2 text-xs uppercase text-muted">{t('annotate.boxes')} ({fmtNumber(boxes.length)})</h3>
      {!boxes.length && <p className="text-sm text-muted">{t('annotate.noBoxes')}</p>}
      <ul className="max-h-64 space-y-1 overflow-auto">
        {boxes.map((b, i) => {
          const u = boxToUnits(b, meta); const c = nameOf(b.class_id)
          return (
            <li key={b.id}>
              <button onClick={() => select([b.id])} className={cn('flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-1 text-xs hover:bg-panel-2', selection.includes(b.id) && 'border-select')}>
                <i className="size-2.5 rounded-sm" style={{ background: c?.color || '#fff' }} />
                <span>{fmtNumber(i + 1)}</span>
                <span className="flex-1 truncate text-start">{c?.name}</span>
                {u.t0 != null && <Ltr className="font-mono text-[10px] text-muted">{fmt(formatSeconds(u.t0))} · {fmt(formatHz(u.f0))}</Ltr>}
              </button>
            </li>
          )
        })}
      </ul>
      {selection.length > 0 && <button className="btn btn-danger mt-2 w-full" onClick={deleteSelected}><Trash2 size={14} />{t('common.delete')}</button>}
    </section>
  )
}

function Slider({ label, value, min, max, step, onChange }) {
  return (
    <div className="block text-xs">
      <span className="flex justify-between text-muted"><span>{label}</span><Ltr className="font-mono">{value}</Ltr></span>
      <input type="range" aria-label={label} dir="ltr" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--color-accent)]" />
    </div>
  )
}

export function DisplayPanel() {
  const { t } = useTranslation()
  const { display, setDisplay, resetDisplay } = useWorkspaceStore()
  return (
    <section className="space-y-2" aria-label={t('annotate.display')}>
      <div className="flex items-center justify-between">
        <h3 className="text-xs uppercase text-muted">{t('annotate.display')}</h3>
        <button className="btn !px-2 !py-0.5 text-xs" onClick={resetDisplay}><RotateCcw size={12} />{t('annotate.reset')}</button>
      </div>
      <Slider label={t('annotate.brightness')} value={display.brightness} min={-0.5} max={0.5} step={0.01} onChange={(v) => setDisplay({ brightness: v })} />
      <Slider label={t('annotate.contrast')} value={display.contrast} min={-100} max={100} step={1} onChange={(v) => setDisplay({ contrast: v })} />
      <Slider label={t('annotate.gamma')} value={display.gamma} min={0.2} max={3} step={0.05} onChange={(v) => setDisplay({ gamma: v })} />
      <label className="block text-xs text-muted">{t('annotate.colormap')}
        <select className="input mt-1" value={display.colormap} onChange={(e) => setDisplay({ colormap: e.target.value })}>{COLORMAPS.map((c) => <option key={c}>{c}</option>)}</select>
      </label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={display.invert} onChange={(e) => setDisplay({ invert: e.target.checked })} />{t('annotate.invert')}</label>
    </section>
  )
}

/** Vertical gradient legend for the active colormap (plain React). */
export function ColorBar() {
  const name = useWorkspaceStore((s) => s.display.colormap)
  const invert = useWorkspaceStore((s) => s.display.invert)
  const lut = buildLut(name)
  const stops = Array.from({ length: 9 }, (_, i) => { const k = Math.round((i / 8) * 255); return `rgb(${lut[k * 3]},${lut[k * 3 + 1]},${lut[k * 3 + 2]}) ${(i / 8) * 100}%` })
  return <div className="w-3 shrink-0 rounded-sm border border-border" aria-hidden style={{ background: `linear-gradient(${invert ? 'to bottom' : 'to top'}, ${stops.join(',')})` }} />
}

/** Mini-map: thumbnail with the current viewport rectangle. */
export function MiniMap({ image, viewport, size }) {
  const W = 150, H = Math.max(24, (W * image.height) / image.width)
  const k = W / image.width
  const rect = { x: (-viewport.x / viewport.scale) * k, y: (-viewport.y / viewport.scale) * k, w: (size.width / viewport.scale) * k, h: (size.height / viewport.scale) * k }
  const cx = Math.max(0, rect.x), cy = Math.max(0, rect.y)
  return (
    <div className="relative overflow-hidden rounded border border-border" dir="ltr" style={{ width: W, height: H }} aria-hidden>
      <img src={image.thumb_url} alt="" className="size-full object-fill opacity-70" />
      <div className="absolute border border-accent bg-accent/10" style={{ left: cx, top: cy, width: Math.min(W - cx, rect.w), height: Math.min(H - cy, rect.h) }} />
    </div>
  )
}
