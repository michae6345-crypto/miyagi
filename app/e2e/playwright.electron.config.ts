/**
 * Electron E2E for the real app (MIC-11): the dev build (`npm run build` in app/ → out/) launched with Playwright's
 * _electron, mock engine in-process (DEMO=1), a fake notch helper, a fresh --user-data-dir per test.
 *
 * CI ONLY (macos-latest, .github/workflows/app-e2e.yml). Electron cannot run headless on macOS: it opens real,
 * always-on-top windows, so never run this on Michael's Mac. Locally use the stage suite (playwright.config.ts).
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './electron',
  globalSetup: './electron/global-setup.ts',
  workers: 1, // one Electron app at a time: they share the screen, the notch helper and the global shortcuts
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-electron' }]] : [['list']],
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure' }
})
