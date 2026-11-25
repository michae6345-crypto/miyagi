/**
 * Screenshot regression for miyagi's browser stage (MIC-12): every app window page and every overlay scenario, at
 * 1024 / 1280 / 1728 wide, light and dark, against committed toHaveScreenshot baselines.
 *
 *   cd app/e2e && npm ci && npx playwright install chromium --only-shell   # once
 *   npx playwright test                       # compare (starts the stage on :5741, or reuses one already there)
 *   npx playwright test --update-snapshots    # after an intended UI change: review the diff, commit the PNGs
 *
 * Headless only, 2 workers: nothing opens on screen and the GPU stays calm (no stress testing). The stage runs the
 * mock inline (no engine), the clock is pinned and every non-localhost request is aborted, so runs are repeatable.
 * Baselines are macOS Chromium headless shell renders (CI runs on macos-latest too); other OSes will differ.
 */
import { defineConfig } from '@playwright/test'

export const PORT = Number(process.env.STAGE_PORT ?? 5741)

export default defineConfig({
  testDir: './tests',
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  fullyParallel: true,
  workers: process.env.CI ? 3 : 2,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, threshold: 0.2, animations: 'disabled', caret: 'hide', scale: 'css' }
  },
  use: { baseURL: `http://localhost:${PORT}/`, headless: true, deviceScaleFactor: 1 },
  projects: [
    { name: '1024', use: { viewport: { width: 1024, height: 700 } } },
    { name: '1280', use: { viewport: { width: 1280, height: 800 } } },
    { name: '1728', use: { viewport: { width: 1728, height: 1080 } } }
  ],
  webServer: {
    command: `npm --prefix .. run dev:web -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
})
