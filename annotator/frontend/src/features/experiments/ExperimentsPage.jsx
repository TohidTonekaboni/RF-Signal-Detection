import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import { listExperiments } from '@/api/experiments.js'
import { Loading, ErrorState, Empty } from '@/components/ui/States.jsx'
import { fmtNumber } from '@/lib/digits.js'
import { toJalaliString } from '@/lib/dates.js'
import { useCan } from '@/features/auth/guards.jsx'

export default function ExperimentsPage() {
  const { t } = useTranslation()
  const can = useCan('experiments.create')
  const q = useQuery({ queryKey: ['experiments'], queryFn: listExperiments })
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t('experiments.title')}</h1>
        {can && <Link to="/experiments/new" className="btn btn-primary"><Plus size={16} />{t('experiments.new')}</Link>}
      </div>
      {q.isPending ? <Loading /> : q.isError ? <ErrorState onRetry={q.refetch} /> : !q.data.length ? <Empty /> : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.map((e) => {
            const pct = e.image_count ? Math.round((e.annotated_count / e.image_count) * 100) : 0
            return (
              <li key={e.id} className="card space-y-3">
                <div>
                  <Link to={`/experiments/${e.id}`} className="font-semibold hover:text-accent">{e.name}</Link>
                  <p className="text-xs text-muted">{toJalaliString(e.created_at)}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {e.classes.map((c) => <span key={c.id} className="inline-flex items-center gap-1 rounded bg-panel-2 px-2 py-0.5 text-xs"><i className="size-2 rounded-full" style={{ background: c.color }} />{c.name}</span>)}
                </div>
                <div>
                  <div className="mb-1 flex justify-between text-xs text-muted"><span>{t('experiments.progress')}</span><span>{fmtNumber(e.annotated_count)} / {fmtNumber(e.image_count)}</span></div>
                  <div className="h-1.5 overflow-hidden rounded bg-panel-2"><div className="h-full bg-accent" style={{ width: `${pct}%` }} /></div>
                </div>
                <Link to={`/annotate/${e.id}`} className="btn w-full">{t('experiments.annotate')}</Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
