// Okabe–Ito colorblind-safe palette (+ extensions), used for class colors.
export const CLASS_COLORS = [
  '#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7', '#FFFFFF',
  '#999999', '#A6761D',
]

export function colorForIndex(i) { return CLASS_COLORS[i % CLASS_COLORS.length] }

function lum(hex) {
  const n = parseInt(hex.slice(1), 16)
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
}
export function contrastRatio(a, b) {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

// Representative mid-tones of the thumbnails' colormaps; a class color must stay distinguishable on them.
const BACKGROUNDS = { viridis: '#21918c', magma: '#b73779', turbo: '#a4fc3c' }
/** Validate a user-picked class color against minimum contrast on each colormap's typical colors. */
export function validateClassColor(hex, min = 1.5) {
  const failing = Object.entries(BACKGROUNDS).filter(([, bg]) => contrastRatio(hex, bg) < min).map(([k]) => k)
  return { ok: failing.length === 0, failing }
}
