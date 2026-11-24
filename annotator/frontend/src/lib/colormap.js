// Small piecewise-linear colormaps (offline, no deps). Each stop: [r,g,b] 0-255.
const MAPS = {
  gray: [[0, 0, 0], [255, 255, 255]],
  viridis: [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]],
  magma: [[0, 0, 4], [81, 18, 124], [183, 55, 121], [252, 137, 97], [252, 253, 191]],
  turbo: [[48, 18, 59], [70, 130, 250], [41, 228, 160], [164, 252, 60], [250, 186, 57], [122, 4, 3]],
}
export const COLORMAPS = Object.keys(MAPS)

export function buildLut(name) {
  const stops = MAPS[name] || MAPS.gray
  const lut = new Uint8ClampedArray(256 * 3)
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * (stops.length - 1)
    const k = Math.min(stops.length - 2, Math.floor(t))
    const f = t - k
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = stops[k][c] + (stops[k + 1][c] - stops[k][c]) * f
  }
  return lut
}

/**
 * Non-destructive display adjustment. Returns a Konva filter function bound to the settings.
 * display: {brightness(-1..1), contrast(-100..100), gamma(0.2..3), colormap, invert}
 */
export function makeDisplayFilter(display) {
  const { brightness = 0, contrast = 0, gamma = 1, colormap = 'gray', invert = false } = display
  const lut = buildLut(colormap)
  const cf = (259 * (contrast + 255)) / (255 * (259 - contrast))
  const table = new Uint8ClampedArray(256)
  for (let i = 0; i < 256; i++) {
    let v = i / 255
    v = Math.pow(v, 1 / gamma)
    v = v + brightness
    v = cf * (v * 255 - 128) + 128
    v = Math.max(0, Math.min(255, v))
    table[i] = invert ? 255 - v : v
  }
  return function filter(imageData) {
    const d = imageData.data
    for (let i = 0; i < d.length; i += 4) {
      const g = table[d[i]] // spectrograms are intensity images; use the red channel as intensity
      d[i] = lut[g * 3]; d[i + 1] = lut[g * 3 + 1]; d[i + 2] = lut[g * 3 + 2]
    }
  }
}
