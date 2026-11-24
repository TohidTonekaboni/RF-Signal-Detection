import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:4173' },
  webServer: { command: 'VITE_MOCK=true pnpm build && pnpm preview --port 4173', port: 4173, reuseExistingServer: true },
  projects: [{ name: 'fa', use: { locale: 'fa-IR' } }, { name: 'en', use: { locale: 'en-US' } }],
})
