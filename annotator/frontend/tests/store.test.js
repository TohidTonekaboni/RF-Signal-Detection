import { describe, it, expect, beforeEach } from 'vitest'
import { useWorkspaceStore as S, toPayload } from '@/features/annotate/workspaceStore.js'

const s = () => S.getState()
beforeEach(() => { s().load({ boxes: [], image_labels: [], version: 3 }); S.setState({ activeClass: 'c1', selection: [] }) })

describe('workspace store', () => {
  it('adds a box, marks dirty, and undo/redo restore it', () => {
    s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    expect(s().boxes).toHaveLength(1); expect(s().dirty).toBe(true); expect(s().boxes[0].class_id).toBe('c1')
    s().undo(); expect(s().boxes).toHaveLength(0)
    s().redo(); expect(s().boxes).toHaveLength(1)
  })
  it('a new edit clears the redo stack', () => {
    s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }); s().undo()
    s().addBox({ x: 0.5, y: 0.5, w: 0.1, h: 0.1 })
    s().redo(); expect(s().boxes).toHaveLength(1)
  })
  it('clamps updated boxes into bounds', () => {
    const id = s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    s().updateBox(id, { x: 0.95, y: 0.1, w: 0.2, h: 0.2 })
    expect(s().boxes[0].x).toBeCloseTo(0.8)
  })
  it('deletes and duplicates the selection', () => {
    const id = s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    s().duplicateSelected(); expect(s().boxes).toHaveLength(2)
    s().select([id]); s().deleteSelected(); expect(s().boxes).toHaveLength(1)
  })
  it('load() resets dirty state and history', () => {
    s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    s().load({ boxes: [], image_labels: [], version: 9 })
    expect(s().dirty).toBe(false); expect(s().history.past).toHaveLength(0); expect(s().version).toBe(9)
  })
  it('stays dirty if edited while a save was in flight', () => {
    s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    const snap = s().boxes
    s().addBox({ x: 0.5, y: 0.5, w: 0.2, h: 0.2 })
    s().markSaved(4, snap)
    expect(s().dirty).toBe(true)
  })
  it('builds the save payload with the current version (If-Match)', () => {
    s().addBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 })
    const p = toPayload(s()); expect(p.version).toBe(3); expect(Object.keys(p.boxes[0]).sort()).toEqual(['class_id', 'h', 'id', 'w', 'x', 'y'])
  })
  it('conflict flag is set and cleared', () => { s().setConflict(true); expect(s().conflict).toBe(true); expect(s().saveStatus).toBe('error'); s().setConflict(false); expect(s().conflict).toBe(false) })
})
