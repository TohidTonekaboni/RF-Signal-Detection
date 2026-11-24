// In-memory mock backend (VITE_MOCK=true) so the UI runs without FastAPI/MinIO.
import { nanoid } from 'nanoid'
import { ApiError } from './errors.js'

const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms))

/** Draw a synthetic spectrogram (noise + chirps + bursts) → dataURL. */
function synth(w, h, seed) {
  const c = document.createElement('canvas'); c.width = w; c.height = h
  const g = c.getContext('2d'); const img = g.createImageData(w, h)
  let s = seed * 9301 + 49297
  const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280)
  const chirps = Array.from({ length: 3 }, () => ({ x0: rnd() * w * 0.5, y0: rnd() * h, k: (rnd() - 0.5) * 0.8, len: w * (0.2 + rnd() * 0.3) }))
  const bursts = Array.from({ length: 2 }, () => ({ x: rnd() * w * 0.8, y: rnd() * h * 0.8, bw: 30 + rnd() * 60, bh: 20 + rnd() * 40 }))
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let v = 25 + rnd() * 35
    for (const ch of chirps) { const t = x - ch.x0; if (t > 0 && t < ch.len) v += 170 * Math.exp(-((y - (ch.y0 + ch.k * t)) ** 2) / 18) }
    for (const b of bursts) if (x > b.x && x < b.x + b.bw && y > b.y && y < b.y + b.bh) v += 90 * rnd()
    const i = (y * w + x) * 4; const q = Math.min(255, v)
    img.data[i] = img.data[i + 1] = img.data[i + 2] = q; img.data[i + 3] = 255
  }
  g.putImageData(img, 0, 0)
  return c.toDataURL('image/png')
}

const now = Date.now()
const db = {
  users: [
    { id: 'u1', username: 'admin', role: 'admin', active: true, must_change_password: false },
    { id: 'u2', username: 'annotator', role: 'annotator', active: true, must_change_password: false },
    { id: 'u3', username: 'reviewer', role: 'reviewer', active: true, must_change_password: false },
  ],
  images: [], experiments: [], annotations: {}, audit: [],
}
let seeded = false
function seed() {
  if (seeded) return; seeded = true
  for (let i = 0; i < 24; i++) {
    const url = synth(640, 320, i + 1)
    db.images.push({
      id: `img${i + 1}`, filename: `capture_${String(i + 1).padStart(3, '0')}.png`, url, thumb_url: url,
      width: 640, height: 320, size: 80_000 + i * 1000,
      created_at: new Date(now - i * 86_400_000 * 3).toISOString(),
      meta: { duration_s: 0.5, bandwidth_hz: 20e6, center_freq_hz: 2.437e9 },
    })
  }
  db.experiments.push({
    id: 'e1', name: 'تشخیص سیگنال‌های Wi-Fi', description: 'آزمایش نمونه', created_at: new Date(now).toISOString(),
    classes: [{ id: 'c1', name: 'Wi-Fi', color: '#E69F00' }, { id: 'c2', name: 'Bluetooth', color: '#56B4E9' }, { id: 'c3', name: 'Radar', color: '#009E73' }],
    image_ids: db.images.map((i) => i.id),
  })
}

const session = { user: null }

export async function mockUpload(file, onProgress) {
  seed(); await delay(100)
  for (const p of [20, 55, 85, 100]) { onProgress(p); await delay(80) }
  const url = URL.createObjectURL(file)
  const dims = await new Promise((res) => { const im = new Image(); im.onload = () => res({ w: im.naturalWidth, h: im.naturalHeight }); im.onerror = () => res({ w: 0, h: 0 }); im.src = url })
  const img = { id: `img_${nanoid(6)}`, filename: file.name, url, thumb_url: url, width: dims.w, height: dims.h, size: file.size, created_at: new Date().toISOString(), meta: {} }
  db.images.unshift(img)
  return img
}

/** Route table-ish dispatcher. */
export async function mockRequest(method, path, { query = {}, body, headers = {} } = {}) {
  seed(); await delay()
  const m = (re) => path.match(re)
  const need = () => { if (!session.user) throw new ApiError(401, 'unauthorized') }
  let r

  if (path === '/auth/login' && method === 'POST') {
    const u = db.users.find((x) => x.username === body.username)
    if (!u || body.password !== (u.username === 'admin' ? 'admin' : 'password')) throw new ApiError(401, 'invalid_credentials')
    session.user = u; return { access_token: `mock-${nanoid(8)}`, user: u }
  }
  if (path === '/auth/refresh') { if (!session.user) throw new ApiError(401, 'unauthorized'); return { access_token: `mock-${nanoid(8)}`, user: session.user } }
  if (path === '/auth/logout') { session.user = null; return null }
  if (path === '/auth/change-password') { need(); session.user.must_change_password = false; return null }
  if (path === '/auth/me') { need(); return session.user }
  need()

  if (path === '/images' && method === 'GET') {
    let items = db.images.filter((i) => (!query.q || i.filename.includes(query.q)) && (!query.from || i.created_at >= query.from) && (!query.to || i.created_at <= query.to))
    const page = Number(query.page || 1), size = Number(query.page_size || 12)
    return { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size }
  }
  if ((r = m(/^\/images\/([^/]+)$/))) {
    if (method === 'DELETE') { db.images = db.images.filter((i) => i.id !== r[1]); return null }
    const im = db.images.find((i) => i.id === r[1]); if (!im) throw new ApiError(404, 'not_found'); return im
  }
  if (path === '/experiments' && method === 'GET') return db.experiments.map((e) => ({ ...e, image_count: e.image_ids.length, annotated_count: e.image_ids.filter((id) => db.annotations[`${e.id}:${id}`]?.boxes.length).length }))
  if (path === '/experiments' && method === 'POST') { const e = { id: `e_${nanoid(5)}`, created_at: new Date().toISOString(), image_ids: db.images.map((i) => i.id), ...body, classes: body.classes.map((c) => ({ id: nanoid(5), ...c })) }; db.experiments.push(e); return e }
  if ((r = m(/^\/experiments\/([^/]+)\/stats$/))) {
    const e = db.experiments.find((x) => x.id === r[1]); if (!e) throw new ApiError(404, 'not_found')
    const counts = Object.fromEntries(e.classes.map((c) => [c.id, 0])); let annotated = 0
    for (const id of e.image_ids) { const a = db.annotations[`${e.id}:${id}`]; if (a?.boxes.length) annotated++; a?.boxes.forEach((b) => { counts[b.class_id] = (counts[b.class_id] || 0) + 1 }) }
    return { total: e.image_ids.length, annotated, per_class: e.classes.map((c) => ({ class_id: c.id, name: c.name, color: c.color, count: counts[c.id] })) }
  }
  if ((r = m(/^\/experiments\/([^/]+)\/images$/))) {
    const e = db.experiments.find((x) => x.id === r[1]); if (!e) throw new ApiError(404, 'not_found')
    const items = e.image_ids.map((id) => db.images.find((i) => i.id === id)).filter(Boolean)
    return { items, total: items.length }
  }
  if ((r = m(/^\/experiments\/([^/]+)\/images\/([^/]+)\/annotations$/))) {
    const key = `${r[1]}:${r[2]}`
    const cur = db.annotations[key] || { boxes: [], image_labels: [], version: 1 }
    if (method === 'GET') return cur
    if (String(cur.version) !== String(headers['If-Match'])) throw new ApiError(409, 'conflict')
    db.annotations[key] = { boxes: body.boxes, image_labels: body.image_labels, version: cur.version + 1 }
    db.audit.unshift({ id: nanoid(5), at: new Date().toISOString(), actor: session.user.username, action: `annotations.save ${r[2]}` })
    return db.annotations[key]
  }
  if ((r = m(/^\/experiments\/([^/]+)$/))) { const e = db.experiments.find((x) => x.id === r[1]); if (!e) throw new ApiError(404, 'not_found'); if (method === 'PUT') Object.assign(e, body); return e }
  if (path === '/users' && method === 'GET') return db.users
  if (path === '/users' && method === 'POST') { const u = { id: nanoid(5), active: true, must_change_password: true, ...body }; db.users.push(u); return u }
  if ((r = m(/^\/users\/([^/]+)$/)) && method === 'PATCH') { const u = db.users.find((x) => x.id === r[1]); Object.assign(u, body); return u }
  if ((r = m(/^\/users\/([^/]+)\/reset-password$/))) { db.users.find((x) => x.id === r[1]).must_change_password = true; return null }
  if (path === '/audit') return { items: db.audit, total: db.audit.length }
  throw new ApiError(404, 'not_found')
}
