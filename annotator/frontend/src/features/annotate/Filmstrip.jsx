import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { cn } from '@/lib/cn.js'

/** Horizontally virtualized strip of thumbnails; handles thousands of items. dir="ltr" keeps order = queue order. */
export default function Filmstrip({ images, currentId, onSelect }) {
  const ref = useRef(null)
  const v = useVirtualizer({ count: images.length, horizontal: true, getScrollElement: () => ref.current, estimateSize: () => 104, overscan: 6 })
  const idx = images.findIndex((i) => i.id === currentId)
  useEffect(() => { if (idx >= 0) v.scrollToIndex(idx, { align: 'center' }) }, [idx]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div ref={ref} dir="ltr" className="h-20 overflow-x-auto border-t border-border bg-panel">
      <div className="relative h-full" style={{ width: v.getTotalSize() }}>
        {v.getVirtualItems().map((it) => {
          const im = images[it.index]
          return (
            <button key={im.id} onClick={() => onSelect(im)} title={im.filename}
              className={cn('absolute top-1 h-[72px] w-24 overflow-hidden rounded border-2', im.id === currentId ? 'border-accent' : 'border-transparent opacity-70 hover:opacity-100')}
              style={{ left: it.start }}>
              <img src={im.thumb_url} alt={im.filename} loading="lazy" className="size-full object-cover" />
            </button>
          )
        })}
      </div>
    </div>
  )
}
