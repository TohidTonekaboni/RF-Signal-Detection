import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Upload, Trash2, Search } from 'lucide-react'
import { toast } from 'sonner'
import { listImages, deleteImage } from '@/api/images.js'
import { errorMessage } from '@/api/errors.js'
import { jalaliRangeToUtc, toJalaliString } from '@/lib/dates.js'
import { fmtNumber } from '@/lib/digits.js'
import { JalaliRangePicker } from '@/components/ui/JalaliRangePicker.jsx'
import { Pagination } from '@/components/ui/Pagination.jsx'
import { Loading, ErrorState, Empty } from '@/components/ui/States.jsx'
import { Ltr } from '@/components/ui/Ltr.jsx'
import { useCan } from '@/features/auth/guards.jsx'
import UploadDrawer from './UploadDrawer.jsx'

const PAGE_SIZE = 12

export default function LibraryPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canUpload = useCan('images.upload')
  const canDelete = useCan('images.delete')
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [range, setRange] = useState({ from: null, to: null }) // Jalali parts
  const [uploadOpen, setUploadOpen] = useState(false)

  // Jalali state → UTC instants at the API boundary only.
  const { from, to } = jalaliRangeToUtc(range)
  const query = useQuery({
    queryKey: ['images', { page, q, from, to }],
    queryFn: () => listImages({ page, page_size: PAGE_SIZE, q, from, to }),
    placeholderData: keepPreviousData,
  })
  const remove = useMutation({
    mutationFn: deleteImage,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['images'] }),
    onError: (e) => toast.error(errorMessage(e, t)),
  })

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-semibold">{t('images.title')}</h1>
        {canUpload && <button className="btn btn-primary" onClick={() => setUploadOpen(true)}><Upload size={16} />{t('images.upload')}</button>}
      </div>

      <div className="card mb-4 grid gap-3 sm:grid-cols-3">
        <div className="relative">
          <label className="label" htmlFor="q">{t('common.search')}</label>
          <Search size={14} className="pointer-events-none absolute end-3 top-9 text-muted" />
          <input id="q" className="input pe-8" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} dir="auto" />
        </div>
        <div className="sm:col-span-2">
          <span className="label">{t('images.filterFrom')} – {t('images.filterTo')}</span>
          <div className="flex gap-2">
            <JalaliRangePicker value={range} onChange={(r) => { setRange(r); setPage(1) }} />
            {range.from && <button className="btn" onClick={() => setRange({ from: null, to: null })}>{t('images.clearFilter')}</button>}
          </div>
        </div>
      </div>

      {query.isPending ? <Loading /> : query.isError ? <ErrorState onRetry={query.refetch} /> : !query.data.items.length ? <Empty /> : (
        <>
          <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {query.data.items.map((im) => (
              <li key={im.id} className="card overflow-hidden !p-0">
                <img src={im.thumb_url} alt={im.filename} loading="lazy" className="aspect-[2/1] w-full bg-black object-cover" />
                <div className="space-y-1 p-3 text-xs">
                  <div className="truncate font-mono text-sm"><Ltr>{im.filename}</Ltr></div>
                  <div className="text-muted">{toJalaliString(im.created_at, { time: true })}</div>
                  <div className="flex items-center justify-between text-muted">
                    <span><Ltr>{fmtNumber(im.width, { useGrouping: false })}×{fmtNumber(im.height, { useGrouping: false })}</Ltr></span>
                    {canDelete && (
                      <button className="btn btn-danger !p-1" aria-label={t('common.delete')}
                        onClick={() => window.confirm(t('images.deleteConfirm')) && remove.mutate(im.id)}><Trash2 size={14} /></button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onChange={setPage} />
        </>
      )}
      <UploadDrawer open={uploadOpen} onOpenChange={setUploadOpen} />
    </div>
  )
}
