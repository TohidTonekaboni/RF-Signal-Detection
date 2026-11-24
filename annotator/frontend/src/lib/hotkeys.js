// Single registry: drives both the bindings and the cheat-sheet dialog.
export const HOTKEYS = [
  { keys: 'v', action: 'select', labelKey: 'hotkeys.select' },
  { keys: 'b', action: 'box', labelKey: 'hotkeys.box' },
  { keys: 'h', action: 'pan', labelKey: 'hotkeys.pan' },
  { keys: 'delete,backspace', action: 'delete', labelKey: 'hotkeys.delete', display: 'Del' },
  { keys: 'mod+z', action: 'undo', labelKey: 'hotkeys.undo', display: 'Ctrl+Z' },
  { keys: 'mod+shift+z,mod+y', action: 'redo', labelKey: 'hotkeys.redo', display: 'Ctrl+Shift+Z' },
  { keys: 'mod+s', action: 'save', labelKey: 'hotkeys.save', display: 'Ctrl+S' },
  { keys: 'mod+d', action: 'duplicate', labelKey: 'hotkeys.duplicate', display: 'Ctrl+D' },
  { keys: '1,2,3,4,5,6,7,8,9', action: 'class', labelKey: 'hotkeys.class', display: '1–9' },
  { keys: 'equal,plus', action: 'zoomIn', labelKey: 'hotkeys.zoomIn', display: '+' },
  { keys: 'minus', action: 'zoomOut', labelKey: 'hotkeys.zoomOut', display: '−' },
  { keys: '0', action: 'fit', labelKey: 'hotkeys.fit', display: '0' },
  { keys: 'right,period', action: 'next', labelKey: 'hotkeys.next', display: '→' },
  { keys: 'left,comma', action: 'prev', labelKey: 'hotkeys.prev', display: '←' },
]
