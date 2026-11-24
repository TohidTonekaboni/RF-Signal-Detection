import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getExperiment, getExperimentStats } from '@/api/experiments.js'
import { Loading, ErrorState } from '@/components/ui/States.jsx'
import { fmtNumber } from '@/lib/digits.js'

export default function DashboardPage() {
  const { t, i18n } = useTranslation()
  const { expId } = useParams()
  const rtl = i18n.language === 'fa'
  const exp = useQuery({ queryKey: ['experiment', expId], queryFn: () => getExperiment(expId) })
  const stats = useQuery({ queryKey: ['stats', expId], queryFn: () => getExperimentStats(expId) })
  if (exp.isPending || stats.isPending) return <Loading />
  if (exp.isError || stats.isError) return <ErrorState onRetry={() => { exp.refetch(); stats.refetch() }} />
  const s = stats.data
  const status = [{ name: t('images.annotated'), value: s.annotated, color: 'var(--color-accent)' }, { name: t('images.pending'), value: s.total - s.annotated, color: 'var(--color-border)' }]
  // RTL-aware: reverse the category axis and flip the value axis, so charts read right→left.
  const tick = { fill: 'var(--color-muted)', fontSize: 12, fontFamily: 'var(--font-sans)' }
  const tickFmt = (v) => fmtNumber(v)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{exp.data.name} — {t('experiments.dashboard')}</h1>
        <Link to={`/annotate/${expId}`} className="btn btn-primary">{t('experiments.annotate')}</Link>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-2 text-sm text-muted">{t('experiments.boxesPerClass')}</h2>
          <div className="h-64" dir="ltr">
            <ResponsiveContainer>
              <BarChart data={s.per_class} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="var(--color-border)" vertical={false} />
                <XAxis dataKey="name" tick={tick} reversed={rtl} />
                <YAxis tick={tick} tickFormatter={tickFmt} orientation={rtl ? 'right' : 'left'} allowDecimals={false} />
                <Tooltip formatter={(v) => fmtNumber(v)} contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-border)', fontFamily: 'var(--font-sans)' }} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>{s.per_class.map((c) => <Cell key={c.class_id} fill={c.color} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="card">
          <h2 className="mb-2 text-sm text-muted">{t('experiments.imagesStatus')}</h2>
          <div className="h-64" dir="ltr">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={status} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} stroke="none">{status.map((x) => <Cell key={x.name} fill={x.color} />)}</Pie>
                <Tooltip formatter={(v) => fmtNumber(v)} contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-border)', fontFamily: 'var(--font-sans)' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <p className="text-center text-sm">{fmtNumber(s.annotated)} / {fmtNumber(s.total)} {t('images.annotated')}</p>
        </section>
      </div>
    </div>
  )
}
