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
  const overlay = await windowFor(run.app, '')
  const layout = await layoutOf(overlay)
  expect(layout.notch.hasNotch).toBe(true)
  expect(layout.notch.place).toBe('notch')
  await expect(overlay.locator('[data-island-layer]').first()).toBeAttached()
  expect(run.errors).toEqual([])
})

test('Home, Library and Settings open in the app window', async () => {
  run = await launch(SET_UP)
  const overlay = await windowFor(run.app, '')
  await openWindow(overlay, 'library', { page: 'home' })
  const lib = await windowFor(run.app, 'library')
  await expect(lib.locator('h1, [role=heading]').first()).toBeVisible()
  const pages: Array<Record<string, string>> = [{ page: 'lessons' }, { page: 'skills' }, { page: 'progress' }, { page: 'settings', section: 'general' }, { page: 'settings', section: 'privacy' }]
  for (const q of pages) {
    await openWindow(overlay, 'library', q)
    await lib.waitForTimeout(600)
    await expect(lib.locator('h1, [role=heading]').first(), JSON.stringify(q)).toBeVisible()
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
  run = await launch({ ...SET_UP, SCENARIO: 'signincard' })
  const overlay = await windowFor(run.app, '')
  await expect(overlay.locator('[data-signincard]')).toHaveCount(0)
  // The mock plays a lesson build that the cloud refuses (cloud.notice signin_required), like a signed-out learner.
  await overlay.evaluate(() => (window as unknown as { tut: { send(c: unknown): void } }).tut.send({ type: 'dev.signincard.signin', payload: {} }))
  await expect(overlay.locator('[data-signincard="signin"]')).toBeVisible({ timeout: 30_000 })
  expect(run.errors).toEqual([])
})
