import { useHotkeys } from 'react-hotkeys-hook'
import { HOTKEYS } from '@/lib/hotkeys.js'

const keys = (action) => HOTKEYS.find((h) => h.action === action).keys
const opts = { preventDefault: true }

/** All workspace shortcuts, scoped to the workspace page. Bindings come from the single registry. */
export function useWorkspaceHotkeys(h) {
  useHotkeys(keys('select'), () => h.tool('select'), opts, [h])
  useHotkeys(keys('box'), () => h.tool('box'), opts, [h])
  useHotkeys(keys('pan'), () => h.tool('pan'), opts, [h])
  useHotkeys(keys('delete'), () => h.remove(), opts, [h])
  useHotkeys(keys('undo'), () => h.undo(), opts, [h])
  useHotkeys(keys('redo'), () => h.redo(), opts, [h])
  useHotkeys(keys('save'), () => h.save(), { ...opts, enableOnFormTags: true }, [h])
  useHotkeys(keys('duplicate'), () => h.duplicate(), opts, [h])
  useHotkeys(keys('class'), (e) => h.pickClass(Number(e.key) - 1), opts, [h])
  useHotkeys(keys('zoomIn'), () => h.zoom(1.25), opts, [h])
  useHotkeys(keys('zoomOut'), () => h.zoom(0.8), opts, [h])
  useHotkeys(keys('fit'), () => h.fit(), opts, [h])
  useHotkeys(keys('next'), () => h.next(), opts, [h])
  useHotkeys(keys('prev'), () => h.prev(), opts, [h])
}
