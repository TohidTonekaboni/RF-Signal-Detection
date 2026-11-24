import { create } from 'zustand'
import { enablePatches, produceWithPatches, applyPatches } from 'immer'
import { nanoid } from 'nanoid'
import { clampBox } from '@/lib/bbox.js'

enablePatches()

export const DEFAULT_DISPLAY = { brightness: 0, contrast: 0, gamma: 1, colormap: 'gray', invert: false }
const MAX_HISTORY = 200
const doc = (s) => ({ boxes: s.boxes, imageLabels: s.imageLabels })

/**
 * Workspace state. Document edits (boxes, imageLabels) go through `commit`, which records immer
 * patches for undo/redo. Boxes are normalized (0–1): {id, class_id, x, y, w, h}.
 */
export const useWorkspaceStore = create((set, get) => ({
  // document
  boxes: [],
  imageLabels: [],
  // ui
  selection: [],
  tool: 'select', // 'select' | 'box' | 'pan'
  activeClass: null,
  viewport: { scale: 1, x: 0, y: 0 },
  display: { ...DEFAULT_DISPLAY },
  // history
  history: { past: [], future: [] },
  // persistence
  dirty: false,
  version: 0,
  saveStatus: 'saved', // 'saved' | 'dirty' | 'saving' | 'error'
  conflict: false,

  /** Load a server snapshot. Resets history and selection. */
  load({ boxes = [], image_labels = [], version = 1 }) {
    set({ boxes, imageLabels: image_labels, version, selection: [], history: { past: [], future: [] }, dirty: false, saveStatus: 'saved', conflict: false })
  },

  commit(recipe) {
    const [next, patches, inverse] = produceWithPatches(doc(get()), recipe)
    if (!patches.length) return
    set((s) => ({
      ...next,
      history: { past: [...s.history.past, { patches, inverse }].slice(-MAX_HISTORY), future: [] },
      dirty: true,
      saveStatus: 'dirty',
    }))
  },

  undo() {
    const { history } = get()
    const last = history.past.at(-1)
    if (!last) return
    const next = applyPatches(doc(get()), last.inverse)
    set((s) => ({ ...next, history: { past: s.history.past.slice(0, -1), future: [last, ...s.history.future] }, dirty: true, saveStatus: 'dirty', selection: s.selection.filter((id) => next.boxes.some((b) => b.id === id)) }))
  },

  redo() {
    const [first, ...rest] = get().history.future
    if (!first) return
    const next = applyPatches(doc(get()), first.patches)
    set((s) => ({ ...next, history: { past: [...s.history.past, first], future: rest }, dirty: true, saveStatus: 'dirty' }))
  },

  addBox(box) {
    const id = nanoid(8)
    const { activeClass } = get()
    const b = { id, class_id: box.class_id ?? activeClass, ...clampBox(box) }
    get().commit((d) => { d.boxes.push(b) })
    set({ selection: [id] })
    return id
  },
  updateBox(id, patch) {
    get().commit((d) => {
      const b = d.boxes.find((x) => x.id === id)
      if (!b) return
      Object.assign(b, patch.x !== undefined ? clampBox({ ...b, ...patch }) : patch)
    })
  },
  deleteSelected() {
    const sel = get().selection
    if (!sel.length) return
    get().commit((d) => { d.boxes = d.boxes.filter((b) => !sel.includes(b.id)) })
    set({ selection: [] })
  },
  duplicateSelected() {
    const sel = get().selection
    const copies = get().boxes.filter((b) => sel.includes(b.id)).map((b) => ({ ...b, id: nanoid(8), ...clampBox({ ...b, x: b.x + 0.01, y: b.y + 0.01 }) }))
    if (!copies.length) return
    get().commit((d) => { d.boxes.push(...copies) })
    set({ selection: copies.map((c) => c.id) })
  },
  setBoxClass(id, class_id) { get().updateBox(id, { class_id }) },
  toggleImageLabel(label) {
    get().commit((d) => { const i = d.imageLabels.indexOf(label); if (i >= 0) d.imageLabels.splice(i, 1); else d.imageLabels.push(label) })
  },

  select(ids) { set({ selection: ids }) },
  setTool(tool) { set({ tool }) },
  setActiveClass(id) {
    set({ activeClass: id })
    const { selection } = get()
    if (selection.length === 1) get().setBoxClass(selection[0], id)
  },
  setViewport(v) { set((s) => ({ viewport: { ...s.viewport, ...v } })) },
  setDisplay(p) { set((s) => ({ display: { ...s.display, ...p } })) },
  resetDisplay() { set({ display: { ...DEFAULT_DISPLAY } }) },

  // persistence
  setSaving() { set({ saveStatus: 'saving' }) },
  markSaved(version, snapshotBoxes) {
    // If the user edited while the request was in flight, stay dirty.
    const stillSame = get().boxes === snapshotBoxes
    set({ version, dirty: !stillSame, saveStatus: stillSame ? 'saved' : 'dirty' })
  },
  setSaveError() { set({ saveStatus: 'error' }) },
  setConflict(conflict) { set({ conflict, saveStatus: conflict ? 'error' : get().saveStatus }) },
}))

/** Payload for PUT …/annotations */
export function toPayload(s) {
  return { boxes: s.boxes.map(({ id, class_id, x, y, w, h }) => ({ id, class_id, x, y, w, h })), image_labels: s.imageLabels, version: s.version }
}
