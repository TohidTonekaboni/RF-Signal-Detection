import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DirectionProvider } from '@radix-ui/react-direction'
import { TooltipProvider } from '@radix-ui/react-tooltip'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { router } from './router.jsx'
import { dirFor } from '@/i18n/index.js'
import { refreshSession } from '@/api/client.js'
import { useAuthStore } from '@/features/auth/authStore.js'
import { ApiError } from '@/api/errors.js'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2 },
  },
})

export default function App() {
  const { i18n } = useTranslation()
  const dir = dirFor(i18n.language)

  // Restore the session from the refresh cookie on load.
  useEffect(() => {
    refreshSession().finally(() => useAuthStore.getState().setReady())
  }, [])

  return (
    <DirectionProvider dir={dir}>
      <TooltipProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <Toaster dir={dir} position={dir === 'rtl' ? 'bottom-left' : 'bottom-right'} theme="system" richColors />
        </QueryClientProvider>
      </TooltipProvider>
    </DirectionProvider>
  )
}
