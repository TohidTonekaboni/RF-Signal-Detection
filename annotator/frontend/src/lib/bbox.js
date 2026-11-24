/**
 * Boxes are stored normalized (0–1) relative to the image: {x, y, w, h} top-left origin.
 * @typedef {{x:number,y:number,w:number,h:number}} NBox
 * @typedef {{x:number,y:number,width:number,height:number}} PxRect
 */

export const MIN_SIZE = 0.004 // minimum normalized width/height

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

/** Normalized → stage pixels. @param {NBox} b @param {{width:number,height:number}} img */
export function denormalize(b, img) {
  return { x: b.x * img.width, y: b.y * img.height, width: b.w * img.width, height: b.h * img.height }
}

/** Stage pixels → normalized. @param {PxRect} r @param {{width:number,height:number}} img */
export function normalize(r, img) {
  return { x: r.x / img.width, y: r.y / img.height, w: r.width / img.width, h: r.height / img.height }
}

/** Clamp a box inside [0,1] and enforce a minimum size. @param {NBox} b @returns {NBox} */
export function clampBox(b, min = MIN_SIZE) {
  let w = clamp(Math.abs(b.w), min, 1)
  let h = clamp(Math.abs(b.h), min, 1)
  const x = clamp(b.x, 0, 1 - w)
  const y = clamp(b.y, 0, 1 - h)
  return { x, y, w, h }
}

/** Build a box from two corner points (any drag direction). */
export function boxFromPoints(a, b) {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) }
}

/** Screen point → image-normalized point, given viewport {scale,x,y} and image pixel size. */
export function screenToNorm(p, vp, img) {
  return { x: (p.x - vp.x) / vp.scale / img.width, y: (p.y - vp.y) / vp.scale / img.height }
}

export function isTooSmall(b, min = MIN_SIZE) {
  return b.w < min || b.h < min
}
