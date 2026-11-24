const FA = '۰۱۲۳۴۵۶۷۸۹'

/** Replace Latin digits with Persian digits. @param {string|number} v */
export function toPersianDigits(v) {
  return String(v).replace(/\d/g, (d) => FA[Number(d)])
}

/** Replace Persian/Arabic-Indic digits with Latin digits (for parsing input). @param {string} s */
export function toLatinDigits(s) {
  return String(s)
    .replace(/[۰-۹]/g, (d) => String(FA.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
}

let digitMode = 'fa' // 'fa' | 'latin'
export function setDigitMode(mode) { digitMode = mode === 'latin' ? 'latin' : 'fa' }
export function getDigitMode() { return digitMode }

/**
 * Format a number respecting the user's digit setting.
 * @param {number} n
 * @param {Intl.NumberFormatOptions & {forceLatin?: boolean}} [opts]
 */
export function fmtNumber(n, opts = {}) {
  if (n == null || Number.isNaN(n)) return '—'
  const { forceLatin, ...rest } = opts
  const latin = forceLatin || digitMode === 'latin'
  return new Intl.NumberFormat(latin ? 'en-US' : 'fa-IR', rest).format(n)
}

/** Format an arbitrary string containing digits. */
export function fmtDigits(s) {
  return digitMode === 'fa' ? toPersianDigits(s) : String(s)
}
