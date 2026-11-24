import { describe, it, expect } from 'vitest'
import { contrastRatio, validateClassColor } from '@/lib/classColors.js'
import { toPersianDigits, toLatinDigits } from '@/lib/digits.js'

describe('class colors', () => {
  it('contrast of black vs white is 21', () => { expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0) })
  it('flags a color identical to a colormap midtone', () => { expect(validateClassColor('#21918c').ok).toBe(false) })
})
describe('digits', () => {
  it('round-trips Persian digits', () => { expect(toPersianDigits('1403/08/09')).toBe('۱۴۰۳/۰۸/۰۹'); expect(toLatinDigits('۱۴۰۳')).toBe('1403') })
})
