import { useCallback, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { FolderUp, RotateCw } from 'lucide-react'
import { nanoid } from 'nanoid'
import { Dialog } from '@/components/ui/Dialog.jsx'
import { Ltr } from '@/components/ui/Ltr.jsx'
import { uploadImage } from '@/api/images.js'
import { fmtNumber } from '@/lib/digits.js'

const MAX_PARALLEL = 3

export default function UploadDrawer({ open, onOpenChange }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [items, setItems] = useState([]) // {id,file,pct,status:'queued'|'uploading'|'done'|'failed'}
  const folderRef = useRef(null)
  const patch = (id, p) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)))

  const run = useCallback(async (list) => {
    const queue = [...list]
    const worker = async () => {
      while (queue.length) {
        const it = queue.shift()
        patch(it.id, { status: 'uploading', pct: 0 })
        try {
          await uploadImage(it.file, (pct) => patch(it.id, { pct }))
          patch(it.id, { status: 'done', pct: 100 })
        } catch { patch(it.id, { status: 'failed' }) }
      }
    }
    await Promise.all(Array.from({ length: MAX_PARALLEL }, worker))
    qc.invalidateQueries({ queryKey: ['images'] })
  }, [qc])

  const add = useCallback((files) => {
    const list = files.filter((f) => f.type.startsWith('image/')).map((file) => ({ id: nanoid(6), file, pct: 0, status: 'queued' }))
    setItems((xs) => [...xs, ...list])
    run(list)
  }, [run])

  const { getRootProps, getInputProps, isDragActive, open: pick } = useDropzone({ onDrop: add, accept: { 'image/*': [] }, noClick: true })

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t('images.upload')} wide>
      <div {...getRootProps()} className={`rounded-md border-2 border-dashed p-8 text-center ${isDragActive ? 'border-accent bg-accent/10' : 'border-border'}`}>
        <input {...getInputProps()} />
        <p className="mb-3 text-muted">{t('images.dropHere')}</p>
        <div className="flex justify-center gap-2">
          <button type="button" className="btn" onClick={pick}>{t('images.uploadFiles')}</button>
          <button type="button" className="btn" onClick={() => folderRef.current?.click()}><FolderUp size={14} />{t('images.uploadFolder')}</button>
          <input ref={folderRef} type="file" className="hidden" webkitdirectory="" multiple onChange={(e) => { add([...e.target.files]); e.target.value = '' }} />
        </div>
      </div>
      <ul className="mt-4 max-h-64 space-y-2 overflow-auto">
        {items.map((it) => (
          <li key={it.id} className="text-sm">
            <div className="flex items-center justify-between gap-2">
              <Ltr className="truncate font-mono">{it.file.name}</Ltr>
              <span className="flex items-center gap-2 text-xs text-muted">
                {it.status === 'failed' ? <>{t('images.failed')}<button className="btn !p-1" aria-label={t('common.retry')} onClick={() => { patch(it.id, { status: 'queued', pct: 0 }); run([it]) }}><RotateCw size={12} /></button></>
                  : it.status === 'done' ? t('images.done') : `${fmtNumber(it.pct)}%`}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded bg-panel-2" role="progressbar" aria-valuenow={it.pct} aria-valuemin={0} aria-valuemax={100}>
              <div className={`h-full ${it.status === 'failed' ? 'bg-danger' : 'bg-accent'}`} style={{ width: `${it.pct}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Dialog>
  )
}
