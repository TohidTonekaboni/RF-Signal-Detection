import { describe, it, expect } from 'vitest'
import { normalize, denormalize, clampBox, boxFromPoints, isTooSmall, MIN_SIZE } from '@/lib/bbox.js'

const img = { width: 640, height: 320 }
describe('bbox', () => {
  it('round-trips normalize/denormalize', () => {
    const px = { x: 64, y: 32, width: 128, height: 64 }
    const n = normalize(px, img)
    expect(n).toEqual({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    const back = denormalize(n, img)
    expect(back.x).toBeCloseTo(64); expect(back.width).toBeCloseTo(128)
  })
  it('clamps inside the image', () => {
    expect(clampBox({ x: 0.9, y: -0.2, w: 0.5, h: 0.3 })).toEqual({ x: 0.5, y: 0, w: 0.5, h: 0.3 })
  })
  it('enforces minimum size', () => {
    const b = clampBox({ x: 0.5, y: 0.5, w: 0, h: 0 })
    expect(b.w).toBe(MIN_SIZE); expect(b.h).toBe(MIN_SIZE)
  })
  it('builds a box from points in any drag direction', () => {
    expect(boxFromPoints({ x: 5, y: 9 }, { x: 1, y: 2 })).toEqual({ x: 1, y: 2, w: 4, h: 7 })
  })
  it('detects too-small boxes', () => { expect(isTooSmall({ w: 0.001, h: 0.5 })).toBe(true); expect(isTooSmall({ w: 0.1, h: 0.1 })).toBe(false) })
})
