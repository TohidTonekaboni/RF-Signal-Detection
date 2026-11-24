import { useHudFmt } from './useHudFmt.js'

function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw))
  const f = raw / p
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p
}

/**
 * SVG ruler next to the stage. horizontal = time (left→right); vertical = frequency (bottom→top).
 * Falls back to pixels when image metadata is missing.
 */
export default function Ruler({ orientation, viewport, image, size, meta }) {
  const fmt = useHudFmt()
  const horiz = orientation === 'x'
  const len = horiz ? size.width : size.height
  const imgLen = horiz ? image.width : image.height
  const off = horiz ? viewport.x : viewport.y
  // visible range in image px
  const a = -off / viewport.scale, b = (len - off) / viewport.scale

  let unit, toVal, fromVal
  if (horiz && meta?.duration_s) { const ms = meta.duration_s < 1; const k = (ms ? 1000 : 1) * meta.duration_s / imgLen; unit = ms ? 'ms' : 's'; toVal = (px) => px * k; fromVal = (v) => v / k }
  else if (!horiz && meta?.bandwidth_hz) {
    const bw = meta.bandwidth_hz, lo = (meta.center_freq_hz ?? bw / 2) - bw / 2
    const mhz = bw >= 1e6; const d = mhz ? 1e6 : 1e3; unit = mhz ? 'MHz' : 'kHz'
    toVal = (px) => (lo + (1 - px / imgLen) * bw) / d; fromVal = (v) => (1 - (v * d - lo) / bw) * imgLen
  } else { unit = 'px'; toVal = (px) => (horiz ? px : imgLen - px); fromVal = (v) => (horiz ? v : imgLen - v) }

  const v0 = toVal(a), v1 = toVal(b)
  const lo = Math.min(v0, v1), hi = Math.max(v0, v1)
  const step = niceStep((hi - lo) / 8 || 1)
  const ticks = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v)
  const decimals = step < 1 ? Math.min(6, Math.ceil(-Math.log10(step))) : 0
  const screen = (v) => fromVal(v) * viewport.scale + off

  const W = horiz ? size.width : 44, H = horiz ? 22 : size.height
  return (
    <svg width={W} height={H} dir="ltr" className="shrink-0 select-none bg-panel text-muted" role="img" aria-label={horiz ? 'time ruler' : 'frequency ruler'}>
      {ticks.map((v) => {
        const p = screen(v)
        if (p < 0 || p > len) return null
        const label = fmt(v.toFixed(decimals))
        return horiz ? (
          <g key={v}><line x1={p} x2={p} y1={14} y2={22} stroke="currentColor" /><text x={p + 3} y={11} fontSize="10" fill="currentColor" fontFamily="var(--font-mono)">{label}</text></g>
        ) : (
          <g key={v}><line x1={36} x2={44} y1={p} y2={p} stroke="currentColor" /><text x={34} y={p - 3} fontSize="10" fill="currentColor" textAnchor="end" fontFamily="var(--font-mono)">{label}</text></g>
        )
      })}
      <text x={horiz ? W - 4 : 4} y={horiz ? 11 : 10} fontSize="9" fill="var(--color-accent)" textAnchor={horiz ? 'end' : 'start'} fontFamily="var(--font-mono)">{unit}</text>
    </svg>
  )
}
