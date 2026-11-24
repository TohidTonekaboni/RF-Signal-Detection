/**
 * Physical units from image metadata.
 * meta: { duration_s, bandwidth_hz, center_freq_hz } — any may be missing.
 * Time runs left→right; frequency runs bottom→top and is centered on center_freq_hz.
 */

/** @returns {number|null} seconds from the left edge */
export function xToSeconds(nx, meta) {
  if (!meta?.duration_s) return null
  return nx * meta.duration_s
}

/** @returns {number|null} absolute frequency in Hz (bottom edge = center − BW/2) */
export function yToHz(ny, meta) {
  if (!meta?.bandwidth_hz) return null
  const lo = (meta.center_freq_hz ?? meta.bandwidth_hz / 2) - meta.bandwidth_hz / 2
  return lo + (1 - ny) * meta.bandwidth_hz
}

export function boxToUnits(b, meta) {
  return {
    t0: xToSeconds(b.x, meta), t1: xToSeconds(b.x + b.w, meta),
    f0: yToHz(b.y + b.h, meta), f1: yToHz(b.y, meta),
  }
}

/** Human readable frequency: Hz / kHz / MHz / GHz. Returns a Latin-digit string. */
export function formatHz(hz) {
  if (hz == null) return '—'
  const a = Math.abs(hz)
  if (a >= 1e9) return `${(hz / 1e9).toFixed(3)} GHz`
  if (a >= 1e6) return `${(hz / 1e6).toFixed(3)} MHz`
  if (a >= 1e3) return `${(hz / 1e3).toFixed(2)} kHz`
  return `${hz.toFixed(1)} Hz`
}

export function formatSeconds(s) {
  if (s == null) return '—'
  if (Math.abs(s) < 1) return `${(s * 1000).toFixed(2)} ms`
  return `${s.toFixed(3)} s`
}
