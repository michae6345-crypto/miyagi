/** Every app window page (library pages, settings sections, onboarding, sign-in, account, progress) on the home data. */
import { expect, test } from '@playwright/test'
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
