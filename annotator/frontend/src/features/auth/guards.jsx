import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from './authStore.js'

const PERMISSIONS = {
  'images.upload': ['admin', 'annotator'],
  'images.delete': ['admin'],
  'experiments.create': ['admin'],
  'annotate.edit': ['admin', 'annotator'],
  'review.decide': ['admin', 'reviewer'],
  'users.manage': ['admin'],
}

/** Cosmetic only — the backend enforces every permission. */
export function useCan(permission) {
  const role = useAuthStore((s) => s.user?.role)
  return !!role && (PERMISSIONS[permission] || []).includes(role)
}

export function RequireAuth() {
  const { user, ready } = useAuthStore()
  const loc = useLocation()
  if (!ready) return null
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  if (user.must_change_password && loc.pathname !== '/change-password') return <Navigate to="/change-password" replace />
  return <Outlet />
}

export function RequireRole({ roles, children }) {
  const role = useAuthStore((s) => s.user?.role)
  if (!roles.includes(role)) return <Navigate to="/" replace />
  return children ?? <Outlet />
}
