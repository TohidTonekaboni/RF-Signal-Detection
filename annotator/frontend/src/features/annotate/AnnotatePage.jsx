import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useBlocker, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { MousePointer2, Square, Hand, Undo2, Redo2, Save, ZoomIn, ZoomOut, Maximize, Keyboard, ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { getExperiment, listExperimentImages } from '@/api/experiments.js'
import { getAnnotations, saveAnnotations } from '@/api/annotations.js'
import { errorMessage } from '@/api/errors.js'
import { useWorkspaceStore, toPayload } from './workspaceStore.js'
import { useWorkspaceHotkeys } from './useWorkspaceHotkeys.js'
import CanvasStage, { fitViewport } from './CanvasStage.jsx'
import Ruler from './Ruler.jsx'
import { ClassPanel, BoxList, DisplayPanel, ColorBar, MiniMap } from './Panels.jsx'
import Filmstrip from './Filmstrip.jsx'
import HotkeysDialog from './HotkeysDialog.jsx'
import { Dialog } from '@/components/ui/Dialog.jsx'
import { Loading, ErrorState } from '@/components/ui/States.jsx'
import { Ltr } from '@/components/ui/Ltr.jsx'
import { useSettings } from '@/features/settings/settingsStore.js'
import { useCan } from '@/features/auth/guards.jsx'
import { boxToUnits, formatHz, formatSeconds, xToSeconds, yToHz } from '@/lib/units.js'
import { useHudFmt } from './useHudFmt.js'
import { cn } from '@/lib/cn.js'
import { fmtNumber } from '@/lib/digits.js'

const AUTOSAVE_MS = 2000

/**
 * Images live on the MinIO origin (:9443). crossOrigin='anonymous' keeps the Konva canvas untainted so the
 * brightness/contrast/colormap filters can read pixels; nginx answers with a matching Access-Control-Allow-Origin.
 */
function loadImg(src, onload) {
  const im = new window.Image()
  im.crossOrigin = 'anonymous'
  if (onload) im.onload = () => onload(im)
  im.src = src
  return im
}

export default function AnnotatePage() {
  const { t } = useTranslation()
  const { expId, imageId } = useParams()
  const nav = useNavigate()
  const canEdit = useCan('annotate.edit')
  const autosave = useSettings((s) => s.autosave)
  const fmt = useHudFmt()
  const store = useWorkspaceStore
  const { dirty, saveStatus, conflict, tool, viewport, boxes, imageLabels } = useWorkspaceStore()

  const exp = useQuery({ queryKey: ['experiment', expId], queryFn: () => getExperiment(expId) })
  const imgs = useQuery({ queryKey: ['exp-images', expId], queryFn: () => listExperimentImages(expId) })
  const images = useMemo(() => imgs.data?.items ?? [], [imgs.data])
  const image = images.find((i) => i.id === imageId)
  const idx = images.findIndex((i) => i.id === imageId)
  const classes = useMemo(() => exp.data?.classes ?? [], [exp.data])

  // Default to the first image in the queue.
  useEffect(() => { if (!imageId && images.length) nav(`/annotate/${expId}/${images[0].id}`, { replace: true }) }, [imageId, images, expId, nav])
  useEffect(() => { if (classes.length && !store.getState().activeClass) store.getState().setActiveClass(classes[0].id) }, [classes, store])

  const ann = useQuery({ queryKey: ['annotations', expId, imageId], queryFn: () => getAnnotations(expId, imageId), enabled: !!imageId, staleTime: 0, gcTime: 0 })
  useEffect(() => { if (ann.data) store.getState().load(ann.data) }, [ann.data, store])

  // ---- image loading: thumbnail first, then full-size swap
  const [htmlImage, setHtmlImage] = useState(null)
  useEffect(() => {
    if (!image) return
    let cancelled = false
    setHtmlImage(null)
    loadImg(image.thumb_url, (thumb) => !cancelled && setHtmlImage((cur) => cur || thumb))
    loadImg(image.url, (full) => !cancelled && setHtmlImage(full))
    return () => { cancelled = true }
  }, [image])
  // prefetch next
  useEffect(() => { const n = images[idx + 1]; if (n) loadImg(n.url) }, [idx, images])

  // ---- container size & fit
  const wrapRef = useRef(null)
  const stageRef = useRef(null)
  const [size, setSize] = useState({ width: 800, height: 500 })
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ width: Math.max(100, e.contentRect.width), height: Math.max(100, e.contentRect.height) }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [image])
  const fit = useCallback(() => { if (image) store.getState().setViewport(fitViewport(image, size)) }, [image, size, store])
  useEffect(() => { fit() }, [image?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const zoom = (k) => {
    const v = store.getState().viewport; const c = { x: size.width / 2, y: size.height / 2 }
    const scale = Math.min(40, Math.max(0.05, v.scale * k)); const a = { x: (c.x - v.x) / v.scale, y: (c.y - v.y) / v.scale }
    store.getState().setViewport({ scale, x: c.x - a.x * scale, y: c.y - a.y * scale })
  }

  // ---- saving
  const saving = useRef(false)
  const save = useCallback(async () => {
    const s = store.getState()
    if (!imageId || saving.current || !s.dirty || !canEdit) return true
    saving.current = true; s.setSaving()
    const snapshot = s.boxes
    try {
      const res = await saveAnnotations(expId, imageId, toPayload(s))
      store.getState().markSaved(res.version, snapshot)
      return true
    } catch (e) {
      if (e.status === 409) store.getState().setConflict(true)
      else { store.getState().setSaveError(); toast.error(errorMessage(e, t)) }
      return false
    } finally { saving.current = false }
  }, [expId, imageId, canEdit, store, t])

  useEffect(() => {
    if (!autosave || !dirty || conflict) return
    const id = setTimeout(save, AUTOSAVE_MS)
    return () => clearTimeout(id)
  }, [boxes, imageLabels, dirty, autosave, conflict, save])

  // unsaved-changes guards
  useEffect(() => {
    const h = (e) => { if (store.getState().dirty) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [store])
  const blocker = useBlocker(({ currentLocation, nextLocation }) => store.getState().dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (blocker.state === 'blocked') { window.confirm(t('annotate.unsaved')) ? blocker.proceed() : blocker.reset() }
  }, [blocker, t])

  const go = useCallback(async (i) => {
    const target = images[i]
    if (!target) return
    if (!(await save())) return
    nav(`/annotate/${expId}/${target.id}`)
  }, [images, save, nav, expId])

  const resolveConflict = async (mine) => {
    const latest = await getAnnotations(expId, imageId)
    if (mine) { useWorkspaceStore.setState({ version: latest.version, conflict: false, saveStatus: 'dirty' }); await save() }
    else store.getState().load(latest)
  }

  // ---- hotkeys
  const hk = useMemo(() => ({
    tool: (x) => canEdit || x !== 'box' ? store.getState().setTool(x) : null,
    remove: () => canEdit && store.getState().deleteSelected(),
    undo: () => canEdit && store.getState().undo(),
    redo: () => canEdit && store.getState().redo(),
    save, duplicate: () => canEdit && store.getState().duplicateSelected(),
    pickClass: (i) => classes[i] && store.getState().setActiveClass(classes[i].id),
    zoom, fit, next: () => go(idx + 1), prev: () => go(idx - 1),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [canEdit, save, classes, fit, go, idx])
  useWorkspaceHotkeys(hk)

  // ---- HUD
  const [pointer, setPointer] = useState(null)
  const [help, setHelp] = useState(false)
  const meta = image?.meta
  const hud = useMemo(() => {
    if (!pointer || !image) return null
    const nx = pointer.x / image.width, ny = pointer.y / image.height
    const sec = xToSeconds(nx, meta), hz = yToHz(ny, meta)
    return sec != null || hz != null ? `${t('annotate.time')} ${formatSeconds(sec)}  ·  ${t('annotate.freq')} ${formatHz(hz)}`
      : `x ${Math.round(pointer.x)} ${t('annotate.pixels')} · y ${Math.round(pointer.y)} ${t('annotate.pixels')}`
  }, [pointer, image, meta, t])

  if (exp.isPending || imgs.isPending) return <Loading />
  if (exp.isError || imgs.isError) return <ErrorState onRetry={() => { exp.refetch(); imgs.refetch() }} />
  if (!image) return <Loading />

  const toolBtn = (id, Icon, label, disabled) => (
    <button key={id} disabled={disabled} aria-pressed={tool === id} title={label} aria-label={label}
      onClick={() => store.getState().setTool(id)} className={cn('btn !p-2', tool === id && 'border-accent text-accent')}><Icon size={16} /></button>
  )
  const statusColor = { saved: 'text-ok', dirty: 'text-warn', saving: 'text-muted', error: 'text-danger' }[saveStatus]

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-2">
        <Link to="/experiments" className="btn !p-2" aria-label={t('common.back')}><ArrowRight size={16} className="ltr:-scale-x-100" /></Link>
        <div className="me-2 min-w-0"><div className="truncate text-sm font-semibold">{exp.data.name}</div><Ltr className="text-xs text-muted">{image.filename} · {fmtNumber(idx + 1)}/{fmtNumber(images.length)}</Ltr></div>
        <div className="flex gap-1">
          {toolBtn('select', MousePointer2, t('annotate.tools.select'))}
          {toolBtn('box', Square, t('annotate.tools.box'), !canEdit)}
          {toolBtn('pan', Hand, t('annotate.tools.pan'))}
        </div>
        <div className="flex gap-1">
          <button className="btn !p-2" onClick={() => store.getState().undo()} disabled={!canEdit} aria-label={t('hotkeys.undo')} title={t('hotkeys.undo')}><Undo2 size={16} /></button>
          <button className="btn !p-2" onClick={() => store.getState().redo()} disabled={!canEdit} aria-label={t('hotkeys.redo')} title={t('hotkeys.redo')}><Redo2 size={16} /></button>
        </div>
        <div className="flex gap-1">
          <button className="btn !p-2" onClick={() => zoom(1.25)} aria-label={t('hotkeys.zoomIn')}><ZoomIn size={16} /></button>
          <button className="btn !p-2" onClick={() => zoom(0.8)} aria-label={t('hotkeys.zoomOut')}><ZoomOut size={16} /></button>
          <button className="btn !p-2" onClick={fit} aria-label={t('annotate.fit')}><Maximize size={16} /></button>
          <Ltr className="grid place-items-center px-2 font-mono text-xs text-muted">{fmt(Math.round(viewport.scale * 100))}%</Ltr>
        </div>
        <div className="ms-auto flex items-center gap-2">
          <span role="status" className={cn('text-xs', statusColor)}>{t(`annotate.saveStatus.${saveStatus}`)}</span>
          <button className="btn btn-primary" onClick={save} disabled={!dirty || !canEdit}><Save size={14} />{t('common.save')}</button>
          <button className="btn !p-2" onClick={() => setHelp(true)} aria-label={t('annotate.shortcuts')}><Keyboard size={16} /></button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-60 shrink-0 space-y-5 overflow-auto border-e border-border bg-panel p-3">
          <ClassPanel classes={classes} readOnly={!canEdit} />
          <BoxList classes={classes} meta={meta} />
        </aside>

        {/* Canvas area: explicit LTR — time runs left→right, frequency bottom→top, even inside an RTL page. */}
        <div className="flex min-w-0 flex-1 flex-col bg-bg" dir="ltr">
          <div className="flex min-h-0 flex-1">
            <div className="flex w-11 shrink-0 flex-col"><div className="h-[22px]" /><Ruler orientation="y" viewport={viewport} image={image} size={size} meta={meta} /></div>
            <div className="flex min-w-0 flex-1 flex-col">
              <Ruler orientation="x" viewport={viewport} image={image} size={size} meta={meta} />
              <div ref={wrapRef} className="relative min-h-0 flex-1 overflow-hidden">
                {!htmlImage && <div className="absolute inset-0 grid place-items-center"><Loading /></div>}
                <CanvasStage image={image} htmlImage={htmlImage} classes={classes} size={size} stageRef={stageRef} onPointer={(p) => setPointer(p)} />
                <div className="pointer-events-none absolute bottom-2 start-2 rounded bg-black/70 px-2 py-1 font-mono text-[11px] text-fg" dir="ltr">{hud ? fmt(hud) : '—'}</div>
                <div className="absolute end-2 top-2"><MiniMap image={image} viewport={viewport} size={size} /></div>
              </div>
            </div>
            <div className="flex shrink-0 py-6 pe-2 ps-1"><ColorBar /></div>
          </div>
          <Filmstrip images={images} currentId={imageId} onSelect={(im) => go(images.findIndex((i) => i.id === im.id))} />
        </div>

        <aside className="w-56 shrink-0 overflow-auto border-s border-border bg-panel p-3"><DisplayPanel /></aside>
      </div>

      <HotkeysDialog open={help} onOpenChange={setHelp} />
      <Dialog open={conflict} onOpenChange={() => {}} title={t('annotate.conflictTitle')} description={t('annotate.conflictBody')}
        footer={<><button className="btn" onClick={() => resolveConflict(false)}>{t('annotate.reloadTheirs')}</button><button className="btn btn-danger" onClick={() => resolveConflict(true)}>{t('annotate.overwriteMine')}</button></>} />
    </div>
  )
}
