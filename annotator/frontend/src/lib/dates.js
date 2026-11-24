import { format, newDate, parseISO, getDaysInMonth, isLeapYear } from 'date-fns-jalali'
import { faIR } from 'date-fns-jalali/locale'
import { fmtDigits } from './digits.js'

// Iran has had a fixed UTC+03:30 offset since 2022 (no DST).
export const TEHRAN_OFFSET_MIN = 210

/**
 * Convert a Jalali calendar day to the UTC instant of that day's start in Asia/Tehran.
 * Independent of the runtime's timezone.
 * @param {{year:number, month:number, day:number}} j month is 1-12
 * @param {boolean} [endOfDay] return the last millisecond of the day
 * @returns {Date}
 */
export function jalaliDayToUtc(j, endOfDay = false) {
  const g = newDate(j.year, j.month - 1, j.day) // Jalali → local Date at midnight
  const ms = Date.UTC(g.getFullYear(), g.getMonth(), g.getDate()) - TEHRAN_OFFSET_MIN * 60_000
  return new Date(endOfDay ? ms + 86_400_000 - 1 : ms)
}

/**
 * Inclusive day boundaries in Asia/Tehran → UTC ISO strings (for the API query string).
 * @param {{from?: {year:number,month:number,day:number}|null, to?: {year:number,month:number,day:number}|null}} r
 */
export function jalaliRangeToUtc({ from, to }) {
  return {
    from: from ? jalaliDayToUtc(from).toISOString() : undefined,
    to: to ? jalaliDayToUtc(to, true).toISOString() : undefined,
  }
}

/** UTC ISO → Jalali parts in Asia/Tehran. @param {string} iso */
export function utcToJalaliParts(iso) {
  const shifted = new Date(new Date(iso).getTime() + TEHRAN_OFFSET_MIN * 60_000)
  // Build a local Date with the Tehran wall-clock fields, then read it in the Jalali calendar.
  const local = new Date(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate(),
    shifted.getUTCHours(), shifted.getUTCMinutes(), shifted.getUTCSeconds())
  return {
    local,
    year: Number(format(local, 'yyyy')),
    month: Number(format(local, 'M')),
    day: Number(format(local, 'd')),
  }
}

/**
 * UTC ISO → Persian display string, e.g. «۱۴۰۴/۰۸/۲۳ ۱۴:۳۰».
 * @param {string} iso
 * @param {{time?: boolean, long?: boolean}} [o]
 */
export function toJalaliString(iso, { time = false, long = false } = {}) {
  if (!iso) return '—'
  const { local } = utcToJalaliParts(iso)
  const pattern = long ? 'EEEE d MMMM yyyy' : 'yyyy/MM/dd'
  const out = format(local, pattern, { locale: faIR }) + (time ? ' ' + format(local, 'HH:mm') : '')
  return fmtDigits(out)
}

export { getDaysInMonth, isLeapYear, parseISO }
