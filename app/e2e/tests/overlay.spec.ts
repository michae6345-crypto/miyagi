/** Every overlay scenario (the notch island, cards, drawer, player...) with the island in the real notch. */
import { expect, test } from '@playwright/test'
import { openStage, scenarios, THEMES } from './stage'

for (const sc of scenarios()) {
  for (const theme of THEMES) {
    test(`overlay ${sc} ${theme}`, async ({ page }) => {
      await openStage(page, { scenario: sc, notch: 'real' }, theme)
      await expect(page).toHaveScreenshot(`overlay/${sc}__${theme}.png`)
    })
  }
}
