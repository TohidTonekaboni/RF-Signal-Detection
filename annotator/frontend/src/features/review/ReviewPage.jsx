import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { listExperiments } from '@/api/experiments.js'
import { Loading, ErrorState, Empty } from '@/components/ui/States.jsx'
import { fmtNumber } from '@/lib/digits.js'

/** Lists experiments with annotated images awaiting review; opens the workspace per experiment. */
export default function ReviewPage() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: ['experiments'], queryFn: listExperiments })
  if (q.isPending) return <Loading />
  if (q.isError) return <ErrorState onRetry={q.refetch} />
  const rows = q.data.filter((e) => e.annotated_count > 0)
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">{t('review.title')}</h1>
      {!rows.length ? <Empty /> : (
        <table className="w-full text-sm">
          <thead className="text-start text-muted"><tr><th className="p-2 text-start">{t('common.name')}</th><th className="p-2 text-start">{t('review.pending')}</th><th /></tr></thead>
          <tbody>{rows.map((e) => (
            <tr key={e.id} className="border-t border-border">
              <td className="p-2">{e.name}</td>
              <td className="p-2">{fmtNumber(e.annotated_count)}</td>
              <td className="p-2 text-end"><Link className="btn" to={`/annotate/${e.id}`}>{t('review.title')}</Link></td>
            </tr>))}
          </tbody>
        </table>
      )}
    </div>
  )
}
