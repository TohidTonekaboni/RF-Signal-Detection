import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Stage, Layer, Image as KImage, Rect, Transformer, Text, Line } from 'react-konva'
import { useWorkspaceStore } from './workspaceStore.js'
import { denormalize, normalize, boxFromPoints, isTooSmall, clampBox } from '@/lib/bbox.js'
import { makeDisplayFilter } from '@/lib/colormap.js'

/** Fit viewport for an image inside a container. */
export function fitViewport(img, size, pad = 16) {
  const scale = Math.min((size.width - pad * 2) / img.width, (size.height - pad * 2) / img.height)
  return { scale, x: (size.width - img.width * scale) / 2, y: (size.height - img.height * scale) / 2 }
}

/**
 * The hero canvas. Three layers: image, boxes (+Transformer), overlay (crosshair / draft).
 * Rendered inside an explicit dir="ltr" container: time runs left→right regardless of page direction.
 */
export default function CanvasStage({ image, htmlImage, classes, size, onPointer, stageRef }) {
  const { boxes, selection, tool, viewport, display, activeClass } = useWorkspaceStore()
  const { select, addBox, updateBox, setViewport } = useWorkspaceStore.getState()
  const imgNode = useRef(null)
  const trRef = useRef(null)
  const nodes = useRef({})
  const [draft, setDraft] = useState(null) // {start:{x,y}, cur:{x,y}} in image pixels
  const [cross, setCross] = useState(null)
  const dims = useMemo(() => ({ width: image.width, height: image.height }), [image.width, image.height])
  const colorOf = useCallback((id) => classes.find((c) => c.id === id)?.color || '#ffffff', [classes])
  const nameOf = useCallback((id) => classes.find((c) => c.id === id)?.name || '', [classes])

  // Non-destructive display filter (original bytes untouched).
  useEffect(() => {
    const n = imgNode.current
    if (!n || !htmlImage) return
    n.clearCache()
    n.cache()
    n.filters([makeDisplayFilter(display)])
    n.getLayer()?.batchDraw()
  }, [display, htmlImage, size.width])

  // Attach transformer to the selected box in select tool.
  useEffect(() => {
    const tr = trRef.current
    if (!tr) return
    const target = tool === 'select' && selection.length === 1 ? nodes.current[selection[0]] : null
    tr.nodes(target ? [target] : [])
    tr.getLayer()?.batchDraw()
  }, [selection, tool, boxes])

  const pos = (stage) => stage.getRelativePointerPosition()

  const onWheel = (e) => {
    e.evt.preventDefault()
    const stage = e.target.getStage()
    const p = stage.getPointerPosition()
    const k = e.evt.deltaY < 0 ? 1.1 : 1 / 1.1
    const scale = Math.min(40, Math.max(0.05, viewport.scale * k))
    const anchor = { x: (p.x - viewport.x) / viewport.scale, y: (p.y - viewport.y) / viewport.scale }
    setViewport({ scale, x: p.x - anchor.x * scale, y: p.y - anchor.y * scale })
  }

  const onDown = (e) => {
    if (tool !== 'box' || e.evt.button !== 0) return
    const p = pos(e.target.getStage())
    setDraft({ start: p, cur: p })
  }
  const onMove = (e) => {
    const stage = e.target.getStage()
    const p = pos(stage)
    setCross(p)
    onPointer?.(p, dims)
    if (draft) setDraft({ ...draft, cur: p })
  }
  const onUp = () => {
    if (!draft) return
    const a = { x: Math.min(Math.max(draft.start.x, 0), dims.width), y: Math.min(Math.max(draft.start.y, 0), dims.height) }
    const b = { x: Math.min(Math.max(draft.cur.x, 0), dims.width), y: Math.min(Math.max(draft.cur.y, 0), dims.height) }
    const r = boxFromPoints(a, b)
    const nb = normalize({ x: r.x, y: r.y, width: r.w, height: r.h }, dims)
    setDraft(null)
    if (!isTooSmall(nb)) addBox({ ...nb, class_id: activeClass })
  }
  const onClickStage = (e) => { if (tool === 'select' && e.target === e.target.getStage()) select([]) }

  const commitRect = (id, node) => {
    const r = { x: node.x(), y: node.y(), width: node.width() * node.scaleX(), height: node.height() * node.scaleY() }
    node.scaleX(1); node.scaleY(1)
    const nb = clampBox(normalize(r, dims))
    updateBox(id, nb)
    // snap node to clamped values
    const px = denormalize(nb, dims)
    node.position({ x: px.x, y: px.y }); node.size({ width: px.width, height: px.height })
  }

  const draftRect = draft && (() => { const r = boxFromPoints(draft.start, draft.cur); return { x: r.x, y: r.y, width: r.w, height: r.h } })()
  const hl = 1 / viewport.scale // keep hairlines constant on screen

  return (
    <Stage
      ref={stageRef}
      width={size.width} height={size.height}
      x={viewport.x} y={viewport.y} scaleX={viewport.scale} scaleY={viewport.scale}
      draggable={tool === 'pan'}
      onDragEnd={(e) => e.target === e.target.getStage() && setViewport({ x: e.target.x(), y: e.target.y() })}
      onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp}
      onMouseLeave={() => { setCross(null); onPointer?.(null) }}
      onClick={onClickStage} onTap={onClickStage}
      style={{ cursor: tool === 'box' ? 'crosshair' : tool === 'pan' ? 'grab' : 'default' }}
    >
      <Layer listening={false}>
        {htmlImage && <KImage ref={imgNode} image={htmlImage} width={dims.width} height={dims.height} imageSmoothingEnabled={viewport.scale < 4} />}
      </Layer>
      <Layer>
        {boxes.map((b) => {
          const r = denormalize(b, dims)
          const sel = selection.includes(b.id)
          return (
            <Rect key={b.id} ref={(n) => { if (n) nodes.current[b.id] = n; else delete nodes.current[b.id] }}
              {...r} stroke={sel ? '#e879f9' : colorOf(b.class_id)} strokeWidth={sel ? 2.5 : 1.75} strokeScaleEnabled={false}
              fill={colorOf(b.class_id) + '26'} shadowForStrokeEnabled={false}
              draggable={tool === 'select'}
              onClick={(e) => { if (tool === 'select') { e.cancelBubble = true; select([b.id]) } }}
              onTap={() => tool === 'select' && select([b.id])}
              onDragEnd={(e) => commitRect(b.id, e.target)}
              onTransformEnd={(e) => commitRect(b.id, e.target)}
            />
          )
        })}
        {boxes.map((b) => {
          const r = denormalize(b, dims)
          const name = nameOf(b.class_id)
          return name ? <Text key={`t${b.id}`} x={r.x} y={r.y - 14 * hl} text={name} fontSize={11 * hl} fill={colorOf(b.class_id)} listening={false} fontFamily="Vazirmatn Variable, sans-serif" /> : null
        })}
        <Transformer ref={trRef} rotateEnabled={false} keepRatio={false} anchorSize={9} borderStroke="#e879f9" anchorStroke="#e879f9" anchorFill="#0b0f14"
          enabledAnchors={['top-left', 'top-center', 'top-right', 'middle-left', 'middle-right', 'bottom-left', 'bottom-center', 'bottom-right']}
          boundBoxFunc={(o, n) => (n.width < 4 || n.height < 4 ? o : n)} />
      </Layer>
      <Layer listening={false}>
        {tool === 'box' && cross && (
          <>
            <Line points={[0, cross.y, dims.width, cross.y]} stroke="#22d3ee" strokeWidth={1} strokeScaleEnabled={false} dash={[4, 4]} opacity={0.7} />
            <Line points={[cross.x, 0, cross.x, dims.height]} stroke="#22d3ee" strokeWidth={1} strokeScaleEnabled={false} dash={[4, 4]} opacity={0.7} />
          </>
        )}
        {draftRect && <Rect {...draftRect} stroke="#22d3ee" strokeWidth={1.5} strokeScaleEnabled={false} dash={[6, 3]} fill="rgba(34,211,238,0.12)" />}
      </Layer>
    </Stage>
  )
}
