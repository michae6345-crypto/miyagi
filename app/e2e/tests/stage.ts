/** Shared setup for the stage screenshots: pinned clock, offline, theme, settle, and the CSS that hides moving parts. */
import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'

export const THEMES = ['dark', 'light'] as const
export type Theme = (typeof THEMES)[number]

/** A fixed instant, so "today", streaks and dates render the same on every run. */
const NOW = new Date('2026-11-24T15:00:00Z')

/** Hidden before the screenshot: the desktop wallpaper (large, not ours), blinking carets, video frames. */
export const HIDE_CSS = `
  img[src*="desktop.png"] { visibility: hidden !important; }
  video, iframe { visibility: hidden !important; }
  *, *::before, *::after { caret-color: transparent !important; }
`

/** Every mock scenario (app/mock/scenarios/*.json) plus `full`, sorted. */
export function scenarios(): string[] {
  const dir = join(__dirname, '..', '..', 'mock', 'scenarios')
  const names = readdirSync(dir).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5))
  return ['full', ...names.sort()]
}

export async function openStage(page: Page, query: Record<string, string>, theme: Theme): Promise<void> {
  await page.clock.setFixedTime(NOW)
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
  // Offline: only the stage itself (YouTube embeds, fonts CDNs, the cloud are never reached).
  await page.route(/^https?:\/\/(?!localhost[:/]|127\.0\.0\.1[:/])/, (r) => r.abort())
  await page.goto('/?' + new URLSearchParams({ ...query, appearance: theme }).toString(), { waitUntil: 'load' })
  await page.evaluate(() => document.fonts.ready)
  await page.addStyleTag({ content: HIDE_CSS })
  // Springs and enter transitions: reduced motion shortens them; this covers the rest.
  await page.waitForTimeout(1200)
}
