import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests', timeout: 30000, retries: 0,
  use: { baseURL: 'http://127.0.0.1:4178', headless: true },
  webServer: { command: 'npm run preview -- --port 4178 --strictPort'+(process.env.ROOMBEACON_TEST_DIST?' --outDir '+process.env.ROOMBEACON_TEST_DIST:''), url: 'http://127.0.0.1:4178', reuseExistingServer: false },
  reporter: [['list']],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
