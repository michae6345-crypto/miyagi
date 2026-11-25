/** Every app window page (library pages, settings sections, onboarding, sign-in, account, progress) on the home data. */
import { expect, test, type Page } from '@playwright/test'
import { openStage, THEMES } from './stage'

const PAGES: Array<[string, Record<string, string>]> = [
  ['library', { page: 'home' }],
  ['library', { page: 'lessons' }],
  ['library', { page: 'skills' }],
  ['library', { page: 'progress' }],
  ['library', { page: 'settings', section: 'general' }],
  ['library', { page: 'settings', section: 'permissions' }],
  ['library', { page: 'settings', section: 'privacy' }],
  ['library', { page: 'settings', section: 'account' }],
  ['library', { page: 'settings', section: 'shortcuts' }],
  ['library', { page: 'account' }],
  ['onboarding', {}],
  ['auth', {}],
  ['account', {}],
  ['progress', {}]
]

for (const [win, q] of PAGES) {
  const name = [win, q.page, q.section].filter(Boolean).join('-')
  for (const theme of THEMES) {
    test(`window ${name} ${theme}`, async ({ page }) => {
      await openStage(page, { scenario: 'home', window: win, ...q }, theme)
      await expect(page).toHaveScreenshot(`window/${name}__${theme}.png`)
    })
  }
}

// A new learner (mock/scenarios/fresh-user.json: no saved lessons, empty progress, VS Code not connected yet).
for (const p of ['home', 'progress']) {
  for (const theme of THEMES) {
    test(`window library-${p} new learner ${theme}`, async ({ page }) => {
      await openStage(page, { scenario: 'fresh-user', window: 'library', page: p }, theme)
      await expect(page).toHaveScreenshot(`window/library-${p}-new__${theme}.png`)
    })
  }
}

// ---- behavior (the demo pass): checked once, at 1280 -------------------------------------------------------------

/** Commands the app sent to the inline mock (it logs each as `[mock] ← {json}`). */
function sent(page: Page): Array<{ type: string; payload: Record<string, unknown> }> {
  const out: Array<{ type: string; payload: Record<string, unknown> }> = []
  page.on('console', (m) => {
    const t = m.text()
    const at = t.indexOf('[mock] ← ')
    if (at < 0) return
    try {
      out.push(JSON.parse(t.slice(at + '[mock] ← '.length)))
    } catch {
      /* not a command */
    }
  })
  return out
}

test.describe('home for a demo', () => {
  test.beforeEach(({}, info) => test.skip(info.project.name !== '1280', 'behavior: one width is enough'))

  test('no greeting, no date, and no empty rail for a light learner', async ({ page }) => {
    await openStage(page, { scenario: 'home', window: 'library', page: 'home' }, 'light')
    const home = page.locator('[data-home]')
    await expect(home).toBeVisible()
    const text = await home.innerText()
    expect(text).not.toMatch(/Good (morning|afternoon|evening)|Welcome/)
    expect(text).not.toMatch(/(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), [A-Z][a-z]+ \d+/)
    const rail = page.locator('[data-home-rail]')
    if (await rail.count()) expect((await rail.innerText()).trim()).not.toBe('')
    await expect(page.locator('[data-home-ready] [data-lesson] [aria-hidden] svg')).toHaveCount(0)
  })

  test('a new learner gets one lesson to start, and Start lesson sends its goal', async ({ page }) => {
    const cmds = sent(page)
    await openStage(page, { scenario: 'fresh-user', window: 'library', page: 'home' }, 'light')
    await expect(page.locator('[data-home="v4-first"]')).toBeVisible()
    const start = page.locator('[data-home-start]')
    await expect(start).toContainText('A neural net from scratch')
    await expect(start.getByRole('button')).toHaveCount(1)
    await expect(page.locator('[data-idea]').first()).toHaveText('Build a neural network from scratch')
    await expect(page.getByText('Train an image classifier')).toHaveCount(0)
    await start.getByRole('button', { name: 'Start lesson' }).click()
    await expect.poll(() => cmds.filter((c) => c.type === 'learn')).toEqual([{ type: 'learn', payload: { query: 'build a neural network from scratch', mode: 'lesson' } }])
  })

  test('a short lesson on the first run starts on a click', async ({ page }) => {
    const cmds = sent(page)
    await openStage(page, { scenario: 'fresh-user', window: 'library', page: 'home' }, 'dark')
    await page.locator('[data-home-short] [data-lesson]').first().click()
    await expect.poll(() => cmds.filter((c) => c.type === 'learn').length).toBe(1)
  })

  test('the setup card says the fix once (button), never twice', async ({ page }) => {
    await openStage(page, { scenario: 'onboarding', window: 'library', page: 'home' }, 'light')
    const text = await page.locator('[data-home]').innerText()
    expect(text.split('Connect VS Code').length - 1).toBe(1)
  })

  test('the ask field shows a 2 px ring on keyboard focus (MIC-68)', async ({ page }) => {
    await openStage(page, { scenario: 'home', window: 'library', page: 'home' }, 'dark')
    await page.locator('[data-home-ask] input').focus()
    await page.clock.runFor(400)
    await expect.poll(() => page.locator('[data-home-ask]').evaluate((el) => getComputedStyle(el).boxShadow)).toContain(' 0px 0px 0px 2px')
  })

  test('progress continues the lesson in progress, never "Nothing passed yet"', async ({ page }) => {
    await openStage(page, { scenario: 'home', window: 'library', page: 'progress' }, 'light')
    await expect(page.locator('[data-progress-primary]')).toContainText('Continue Clean a CSV with pandas')
    await expect(page.getByText('Nothing passed yet')).toHaveCount(0)
  })

  test('progress for a new learner has no week of flat bars', async ({ page }) => {
    await openStage(page, { scenario: 'fresh-user', window: 'library', page: 'progress' }, 'light')
    await expect(page.locator('[data-progress-v4]')).toBeVisible()
    await expect(page.locator('[data-progress-main]').getByText('This week')).toHaveCount(0)
    await expect(page.locator('[data-progress-primary]')).toHaveCount(1)
  })
})
