import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { listUsers, createUser, updateUser, resetPassword, listAudit } from '@/api/users.js'
import { errorMessage } from '@/api/errors.js'
import { Dialog } from '@/components/ui/Dialog.jsx'
import { Loading, ErrorState, Empty } from '@/components/ui/States.jsx'
import { Ltr } from '@/components/ui/Ltr.jsx'
import { toJalaliString } from '@/lib/dates.js'

const schema = z.object({ username: z.string().trim().min(3), role: z.enum(['admin', 'annotator', 'reviewer']), password: z.string().min(8) })

function NewUser({ open, onOpenChange }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(schema), defaultValues: { role: 'annotator' } })
  const m = useMutation({ mutationFn: createUser, onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); reset(); onOpenChange(false) }, onError: (e) => toast.error(errorMessage(e, t)) })
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t('users.new')}>
      <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-3" noValidate>
        <div><label className="label" htmlFor="nu">{t('auth.username')}</label><input id="nu" dir="ltr" className="input" {...register('username')} />{errors.username && <p className="err">{t('auth.required')}</p>}</div>
        <div><label className="label" htmlFor="nr">{t('users.role')}</label>
          <select id="nr" className="input" {...register('role')}>{['admin', 'annotator', 'reviewer'].map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}</select></div>
        <div><label className="label" htmlFor="np">{t('auth.password')}</label><input id="np" type="password" dir="ltr" className="input" {...register('password')} />{errors.password && <p className="err">{t('auth.minLen')}</p>}</div>
        <div className="flex justify-end"><button className="btn btn-primary" disabled={m.isPending}>{t('common.create')}</button></div>
      </form>
    </Dialog>
  )
}

export default function UsersPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const users = useQuery({ queryKey: ['users'], queryFn: listUsers })
  const audit = useQuery({ queryKey: ['audit'], queryFn: () => listAudit({}) })
  const toggle = useMutation({ mutationFn: ({ id, active }) => updateUser(id, { active }), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
  const reset = useMutation({ mutationFn: resetPassword, onSuccess: () => toast.success(t('common.saved')) })
  const tab = 'px-4 py-2 text-sm data-[state=active]:border-b-2 data-[state=active]:border-accent data-[state=active]:text-accent'

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">{t('users.title')}</h1>
      <Tabs.Root defaultValue="users">
        <Tabs.List className="mb-4 flex border-b border-border">
          <Tabs.Trigger value="users" className={tab}>{t('users.tab.users')}</Tabs.Trigger>
          <Tabs.Trigger value="audit" className={tab}>{t('users.tab.audit')}</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="users">
          <button className="btn btn-primary mb-3" onClick={() => setOpen(true)}>{t('users.new')}</button>
          {users.isPending ? <Loading /> : users.isError ? <ErrorState onRetry={users.refetch} /> : (
            <table className="w-full text-sm">
              <thead className="text-muted"><tr><th className="p-2 text-start">{t('auth.username')}</th><th className="p-2 text-start">{t('users.role')}</th><th className="p-2 text-start">{t('users.active')}</th><th className="p-2 text-start">{t('common.actions')}</th></tr></thead>
              <tbody>{users.data.map((u) => (
                <tr key={u.id} className="border-t border-border">
                  <td className="p-2"><Ltr>{u.username}</Ltr></td><td className="p-2">{t(`roles.${u.role}`)}</td>
                  <td className="p-2"><input type="checkbox" checked={u.active} onChange={(e) => toggle.mutate({ id: u.id, active: e.target.checked })} aria-label={t('users.active')} /></td>
                  <td className="p-2"><button className="btn" onClick={() => reset.mutate(u.id)}>{t('users.resetPassword')}</button></td>
                </tr>))}</tbody>
            </table>
          )}
        </Tabs.Content>
        <Tabs.Content value="audit">
          {audit.isPending ? <Loading /> : audit.isError ? <ErrorState onRetry={audit.refetch} /> : !audit.data.items.length ? <Empty /> : (
            <table className="w-full text-sm">
              <thead className="text-muted"><tr><th className="p-2 text-start">{t('common.date')}</th><th className="p-2 text-start">{t('users.actor')}</th><th className="p-2 text-start">{t('users.action')}</th></tr></thead>
              <tbody>{audit.data.items.map((a) => <tr key={a.id} className="border-t border-border"><td className="p-2">{toJalaliString(a.at, { time: true })}</td><td className="p-2"><Ltr>{a.actor}</Ltr></td><td className="p-2"><Ltr>{a.action}</Ltr></td></tr>)}</tbody>
            </table>
          )}
        </Tabs.Content>
      </Tabs.Root>
      <NewUser open={open} onOpenChange={setOpen} />
    </div>
  )
}
