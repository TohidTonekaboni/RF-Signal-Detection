import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Image, FlaskConical, ClipboardCheck, Users, Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '@/features/auth/authStore.js'
import { logout } from '@/api/auth.js'
import { cn } from '@/lib/cn.js'

export default function Layout() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { user, clear } = useAuthStore()
  const items = [
    { to: '/images', icon: Image, label: t('nav.images') },
    { to: '/experiments', icon: FlaskConical, label: t('nav.experiments') },
    { to: '/review', icon: ClipboardCheck, label: t('nav.review') },
    ...(user?.role === 'admin' ? [{ to: '/users', icon: Users, label: t('nav.users') }] : []),
    { to: '/settings', icon: Settings, label: t('nav.settings') },
  ]
  const doLogout = async () => { try { await logout() } finally { clear(); nav('/login') } }

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-e border-border bg-panel p-3">
        <div className="mb-4 px-2 text-sm font-semibold text-accent">{t('app.name')}</div>
        <nav className="flex flex-1 flex-col gap-1">
          {items.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} className={({ isActive }) => cn('flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-panel-2', isActive && 'bg-panel-2 text-accent')}>
              <Icon size={16} />{label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border pt-3 text-xs text-muted">
          <div className="mb-2 px-2">{user?.username} · {t(`roles.${user?.role}`)}</div>
          <button className="btn w-full" onClick={doLogout}><LogOut size={14} className="rtl:-scale-x-100" />{t('nav.logout')}</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto p-6"><Outlet /></main>
    </div>
  )
}
