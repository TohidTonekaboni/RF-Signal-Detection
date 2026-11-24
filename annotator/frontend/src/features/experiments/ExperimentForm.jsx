import { useForm, useFieldArray } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { createExperiment } from '@/api/experiments.js'
import { errorMessage } from '@/api/errors.js'
import { colorForIndex, validateClassColor, CLASS_COLORS } from '@/lib/classColors.js'

// Mirrors backend validation.
const schema = z.object({
  name: z.string().trim().min(2).max(100),
  description: z.string().max(500).optional(),
  classes: z.array(z.object({ name: z.string().trim().min(1).max(50), color: z.string().regex(/^#[0-9a-fA-F]{6}$/) })).min(1)
    .refine((cs) => new Set(cs.map((c) => c.name.toLowerCase())).size === cs.length, 'duplicate'),
})

export default function ExperimentForm() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { register, control, handleSubmit, watch, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { name: '', description: '', classes: [{ name: '', color: colorForIndex(0) }] },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'classes' })
  const classes = watch('classes')
  const m = useMutation({
    mutationFn: createExperiment,
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ['experiments'] }); nav(`/experiments/${e.id}`) },
    onError: (e) => toast.error(errorMessage(e, t)),
  })

  return (
    <form onSubmit={handleSubmit((v) => m.mutate(v))} className="card mx-auto max-w-2xl space-y-4" noValidate>
      <h1 className="text-xl font-semibold">{t('experiments.new')}</h1>
      <div>
        <label className="label" htmlFor="name">{t('common.name')}</label>
        <input id="name" className="input" {...register('name')} />
        {errors.name && <p className="err">{t('auth.required')}</p>}
      </div>
      <div>
        <label className="label" htmlFor="desc">{t('experiments.description')}</label>
        <textarea id="desc" rows={2} className="input" {...register('description')} />
      </div>
      <fieldset className="space-y-2">
        <legend className="label">{t('experiments.classes')}</legend>
        {fields.map((f, i) => {
          const v = validateClassColor(classes[i]?.color || '#000000')
          return (
            <div key={f.id} className="flex items-center gap-2">
              <input type="color" aria-label={t('common.color')} list="class-colors" className="size-9 shrink-0 cursor-pointer rounded border border-border bg-transparent" {...register(`classes.${i}.color`)} />
              <input className="input" placeholder={t('experiments.className')} aria-label={t('experiments.className')} {...register(`classes.${i}.name`)} />
              {!v.ok && <span className="text-xs text-warn" title={v.failing.join(', ')}>⚠ {t('experiments.colorLow')}</span>}
              <button type="button" className="btn btn-danger !p-2" disabled={fields.length === 1} onClick={() => remove(i)} aria-label={t('common.delete')}><Trash2 size={14} /></button>
            </div>
          )
        })}
        <datalist id="class-colors">{CLASS_COLORS.map((c) => <option key={c} value={c} />)}</datalist>
        {errors.classes && <p className="err">{t('errors.validation_error')}</p>}
        <button type="button" className="btn" onClick={() => append({ name: '', color: colorForIndex(fields.length) })}><Plus size={14} />{t('experiments.addClass')}</button>
      </fieldset>
      <div className="flex justify-end gap-2">
        <button type="button" className="btn" onClick={() => nav(-1)}>{t('common.cancel')}</button>
        <button className="btn btn-primary" disabled={m.isPending}>{t('common.create')}</button>
      </div>
    </form>
  )
}
