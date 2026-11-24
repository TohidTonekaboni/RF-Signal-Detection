import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RequireAuth, RequireRole } from '@/features/auth/guards.jsx'
import Layout from './Layout.jsx'
import { Loading } from '@/components/ui/States.jsx'

const L = (f) => { const C = lazy(f); return <Suspense fallback={<Loading />}><C /></Suspense> }

export const router = createBrowserRouter(
  [
    { path: '/login', element: L(() => import('@/features/auth/LoginPage.jsx')) },
    {
      element: <RequireAuth />,
      children: [
        { path: '/change-password', element: L(() => import('@/features/auth/ChangePasswordPage.jsx')) },
        {
          element: <Layout />,
          children: [
            { index: true, element: <Navigate to="/images" replace /> },
            { path: '/images', element: L(() => import('@/features/images/LibraryPage.jsx')) },
            { path: '/experiments', element: L(() => import('@/features/experiments/ExperimentsPage.jsx')) },
            { path: '/experiments/new', element: L(() => import('@/features/experiments/ExperimentForm.jsx')) },
            { path: '/experiments/:expId', element: L(() => import('@/features/experiments/DashboardPage.jsx')) },
            { path: '/review', element: L(() => import('@/features/review/ReviewPage.jsx')) },
            { path: '/settings', element: L(() => import('@/features/settings/SettingsPage.jsx')) },
            { path: '/users', element: <RequireRole roles={['admin']}>{L(() => import('@/features/users/UsersPage.jsx'))}</RequireRole> },
          ],
        },
        // The workspace is full-bleed, outside the standard layout.
        { path: '/annotate/:expId/:imageId?', element: L(() => import('@/features/annotate/AnnotatePage.jsx')) },
      ],
    },
    { path: '*', element: <Navigate to="/" replace /> },
  ],
  { basename: import.meta.env.BASE_URL.replace(/\/$/, '') || undefined },
)
