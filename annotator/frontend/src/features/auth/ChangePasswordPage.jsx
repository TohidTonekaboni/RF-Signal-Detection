import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { changePassword } from '@/api/auth.js'
import { errorMessage } from '@/api/errors.js'
import { useAuthStore } from './authStore.js'

const schema = z.object({
  current: z.string().min(1),
  next: z.string().min(8),
  confirm: z.string(),
}).refine((v) => v.next === v.confirm, { path: ['confirm'], message: 'mismatch' })

export default function ChangePasswordPage() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { user, setSession, accessToken } = useAuthStore()
  const [error, setError] = useState(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) })

  const onSubmit = async (v) => {
    try {
      await changePassword(v.current, v.next)
      setSession(accessToken, { ...user, must_change_password: false })
      nav('/', { replace: true })
    } catch (e) { setError(errorMessage(e, t)) }
  }

  return (
    <div className="grid min-h-full place-items-center p-4">
      <form onSubmit={handleSubmit(onSubmit)} className="card w-full max-w-sm space-y-4" noValidate>
        <h1 className="text-lg font-semibold">{t('auth.changePassword')}</h1>
        {user?.must_change_password && <p className="text-sm text-warn">{t('auth.mustChange')}</p>}
        <div><label className="label" htmlFor="c">{t('auth.password')}</label><input id="c" type="password" dir="ltr" className="input" {...register('current')} /></div>
        <div><label className="label" htmlFor="n">{t('auth.newPassword')}</label><input id="n" type="password" dir="ltr" className="input" {...register('next')} />{errors.next && <p className="err">{t('auth.minLen')}</p>}</div>
        <div><label className="label" htmlFor="f">{t('auth.confirmPassword')}</label><input id="f" type="password" dir="ltr" className="input" {...register('confirm')} />{errors.confirm && <p className="err">{t('auth.mismatch')}</p>}</div>
        {error && <p role="alert" className="err">{error}</p>}
        <button className="btn btn-primary w-full" disabled={isSubmitting}>{t('common.save')}</button>
      </form>
    </div>
  )
}
