/**
 * The real Electron app, end to end (MIC-11): Home, Library, Settings, first-run, the overlay in a (simulated) notch,
 * and the sign-in card on a cloud.notice from the mock engine. Every test also fails on console errors we own.
 */
import { expect, test } from '@playwright/test'
import { launch, layoutOf, openWindow, windowFor, type Launched } from './app'

let run: Launched | undefined
test.afterEach(async () => {
  await run?.app.close().catch(() => undefined)
  run = undefined
})

const SET_UP = { MIYAGI_SKIP_ONBOARDING: '1', MIYAGI_SKIP_LOGIN: '1', MIYAGI_QUIET_LAUNCH: '1' }

test('the overlay sits in the notch on a notched Mac', async () => {
  run = await launch(SET_UP)
  const overlay = await windowFor(run.app, 'overlay')
  const layout = await layoutOf(overlay)
  expect(layout.notch.hasNotch).toBe(true)
  expect(layout.notch.place).toBe('notch')
  await expect(overlay.locator('[data-island-layer]').first()).toBeAttached()
  expect(run.errors).toEqual([])
})

test('Home, Library and Settings open in the app window', async () => {
  run = await launch(SET_UP)
  const overlay = await windowFor(run.app, 'overlay')
  await openWindow(overlay, 'library', { page: 'home' })
  const lib = await windowFor(run.app, 'library')
  // Home has no page title by design (v4 home: sections only, no greeting), so Home is its own marker; every other
  // page keeps its h1.
  await expect(lib.locator('[data-home]:visible').first()).toBeVisible()
  const title = lib.locator('main h1:visible').first()
  const pages: Array<Record<string, string>> = [{ page: 'lessons' }, { page: 'skills' }, { page: 'progress' }, { page: 'settings', section: 'general' }, { page: 'settings', section: 'privacy' }]
  for (const q of pages) {
    await openWindow(overlay, 'library', q)
    await lib.waitForTimeout(600)
    await expect(title, JSON.stringify(q)).toBeVisible()
  }
  expect(run.errors).toEqual([])
})

test('first run: the home window opens on setup', async () => {
  run = await launch({ MIYAGI_SKIP_LOGIN: '1' }) // no MIYAGI_SKIP_ONBOARDING: a brand-new Mac
  const deadline = Date.now() + 30_000
  let seen = ''
  while (Date.now() < deadline) {
    for (const w of run.app.windows()) {
      if (await w.locator('[data-onb-primary], [data-onb-row], [data-onb-welcome]').count().catch(() => 0)) seen = w.url().split('#')[1] ?? '/'
    }
    if (seen) break
    await new Promise((r) => setTimeout(r, 500))
  }
  expect(seen, `windows: ${run.app.windows().map((w) => w.url().split('#')[1] ?? '/').join(', ')}`).not.toBe('')
  expect(run.errors).toEqual([])
})

test('the sign-in card shows on a cloud.notice', async () => {
  // mock/scenarios/e2e-signin.json: on connect the mock starts a lesson build that the cloud refuses (cloud.notice
  // signin_required, status 401), as for a signed-out learner. Commands like dev.* never pass main's allowlist.
  run = await launch({ ...SET_UP, SCENARIO: 'e2e-signin' })
  const overlay = await windowFor(run.app, 'overlay')
  await expect(overlay.locator('[data-signincard="signin"]')).toBeVisible({ timeout: 30_000 })
  await expect(overlay.getByRole('dialog')).toContainText(/sign in/i)
  expect(run.errors).toEqual([])
})
