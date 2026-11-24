import { describe, it, expect } from 'vitest'
import { jalaliDayToUtc, jalaliRangeToUtc, toJalaliString, utcToJalaliParts, getDaysInMonth, isLeapYear } from '@/lib/dates.js'
import { setDigitMode } from '@/lib/digits.js'

describe('dates (Jalali ↔ UTC, Asia/Tehran)', () => {
  it('1 Farvardin 1403 starts at 2024-03-19T20:30Z (Nowruz, 00:00 Tehran)', () => {
    expect(jalaliDayToUtc({ year: 1403, month: 1, day: 1 }).toISOString()).toBe('2024-03-19T20:30:00.000Z')
  })
  it('range is inclusive of the whole end day', () => {
    const r = jalaliRangeToUtc({ from: { year: 1403, month: 1, day: 1 }, to: { year: 1403, month: 1, day: 1 } })
    expect(new Date(r.to) - new Date(r.from)).toBe(86_400_000 - 1)
  })
  it('handles open-ended ranges', () => {
    expect(jalaliRangeToUtc({ from: null, to: null })).toEqual({ from: undefined, to: undefined })
  })
  it('month lengths: 1–6 have 31 days, 7–11 have 30', () => {
    const d = (m) => getDaysInMonth(jalaliDayToUtc({ year: 1403, month: m, day: 1 }))
    expect([1, 6, 7, 11].map(d)).toEqual([31, 31, 30, 30])
  })
  it('Esfand has 30 days in a leap year and 29 otherwise (1403 is leap)', () => {
    expect(isLeapYear(jalaliDayToUtc({ year: 1403, month: 12, day: 1 }))).toBe(true)
    expect(getDaysInMonth(jalaliDayToUtc({ year: 1403, month: 12, day: 1 }))).toBe(30)
    expect(getDaysInMonth(jalaliDayToUtc({ year: 1404, month: 12, day: 1 }))).toBe(29)
  })
  it('day-boundary edge: 23:59 Tehran and 00:00 Tehran fall on different Jalali days', () => {
    const a = utcToJalaliParts('2024-03-19T20:29:59.000Z'), b = utcToJalaliParts('2024-03-19T20:30:00.000Z')
    expect([a.year, a.month, a.day]).toEqual([1402, 12, 29])
    expect([b.year, b.month, b.day]).toEqual([1403, 1, 1])
  })
  it('round-trips Jalali → UTC → Jalali', () => {
    for (const j of [{ year: 1402, month: 12, day: 29 }, { year: 1403, month: 6, day: 31 }, { year: 1404, month: 7, day: 1 }]) {
      const p = utcToJalaliParts(jalaliDayToUtc(j).toISOString())
      expect([p.year, p.month, p.day]).toEqual([j.year, j.month, j.day])
    }
  })
  it('formats with Persian digits', () => {
    setDigitMode('fa')
    expect(toJalaliString('2024-03-19T20:30:00.000Z')).toBe('۱۴۰۳/۰۱/۰۱')
    setDigitMode('latin')
    expect(toJalaliString('2024-03-19T20:30:00.000Z')).toBe('1403/01/01')
    setDigitMode('fa')
  })
})
