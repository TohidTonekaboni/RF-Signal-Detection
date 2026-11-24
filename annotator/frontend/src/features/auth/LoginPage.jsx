import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import { useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { login } from '@/api/auth.js'
import { errorMessage } from '@/api/errors.js'
import { useAuthStore } from './authStore.js'
import { Ltr } from '@/components/ui/Ltr.jsx'

const schema = z.object({ username: z.string().min(1, 'required'), password: z.string().min(1, 'required') })

export default function LoginPage() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const loc = useLocation()
  const setSession = useAuthStore((s) => s.setSession)
  const [error, setError] = useState(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) })

  const onSubmit = async (v) => {
    setError(null)
    try {
      const data = await login(v.username, v.password)
      setSession(data.access_token, data.user)
      nav(data.user.must_change_password ? '/change-password' : loc.state?.from || '/', { replace: true })
    } catch (e) { setError(errorMessage(e, t)) }
  }

  return (
    <div className="grid min-h-full place-items-center p-4">
      <form onSubmit={handleSubmit(onSubmit)} className="card w-full max-w-sm space-y-4" noValidate>
        <h1 className="text-xl font-semibold">{t('app.name')}</h1>
        <p className="text-sm text-muted">{t('auth.title')}</p>
        <div>
          <label className="label" htmlFor="u">{t('auth.username')}</label>
          <input id="u" className="input" dir="ltr" autoComplete="username" {...register('username')} />
          {errors.username && <p className="err">{t('auth.required')}</p>}
        </div>
        <div>
          <label className="label" htmlFor="p">{t('auth.password')}</label>
          <input id="p" type="password" className="input" dir="ltr" autoComplete="current-password" {...register('password')} />
          {errors.password && <p className="err">{t('auth.required')}</p>}
        </div>
        {error && <p role="alert" className="err">{error}</p>}
        <button className="btn btn-primary w-full" disabled={isSubmitting}>{t('auth.login')}</button>
        {import.meta.env.VITE_MOCK === 'true' && <p className="text-xs text-muted">demo: <Ltr>admin / admin</Ltr> · <Ltr>annotator / password</Ltr></p>}
      </form>
    </div>
  )
}
