import { describe, it, expect } from 'vitest'
import { xToSeconds, yToHz, boxToUnits, formatHz } from '@/lib/units.js'

const meta = { duration_s: 2, bandwidth_hz: 20e6, center_freq_hz: 2.437e9 }
describe('units', () => {
  it('maps x to seconds left→right', () => { expect(xToSeconds(0.25, meta)).toBe(0.5) })
  it('maps y to Hz bottom→top', () => {
    expect(yToHz(1, meta)).toBe(2.427e9) // bottom edge
    expect(yToHz(0, meta)).toBe(2.447e9) // top edge
  })
  it('returns null without metadata (pixels only)', () => { expect(xToSeconds(0.5, {})).toBeNull(); expect(yToHz(0.5, undefined)).toBeNull() })
  it('converts a box', () => {
    const u = boxToUnits({ x: 0.5, y: 0.25, w: 0.25, h: 0.5 }, meta)
    expect(u.t0).toBe(1); expect(u.t1).toBe(1.5); expect(u.f0).toBeCloseTo(2.432e9, -3); expect(u.f1).toBeCloseTo(2.442e9, -3)
  })
  it('formats Hz', () => { expect(formatHz(2.437e9)).toBe('2.437 GHz'); expect(formatHz(1500)).toBe('1.50 kHz') })
})
