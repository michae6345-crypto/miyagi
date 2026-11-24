/** Shared setup for the stage screenshots: pinned clock, offline, theme, settle, and the CSS that hides moving parts. */
import { readdirSync, readFileSync } from 'node:fs'
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

type Item = { wait?: number; goto?: string; type?: string }
type ScenarioFile = { on?: Record<string, string>; segments?: Record<string, Item[]> }

/**
 * How long the scenario's scripted start-up runs (ms): the time of the last event its `connect` segment plays,
 * following gotos. `full` starts idle (0). Shooting before it ends catches a different moment on a slower machine.
 */
export function startupMs(scenario: string): number {
  if (scenario === 'full') return 0
  let s: ScenarioFile
  try {
    s = JSON.parse(readFileSync(join(__dirname, '..', '..', 'mock', 'scenarios', `${scenario}.json`), 'utf8')) as ScenarioFile
  } catch {
    return 0
  }
  let last = 0
  const walk = (name: string | undefined, t: number, depth: number): number => {
    for (const it of (name && s.segments?.[name]) || []) {
      t += it.wait ?? 0
      if (it.goto && depth < 8) t = walk(it.goto, t, depth + 1)
      else if (it.type) last = Math.max(last, t)
    }
    return t
  }
  walk(s.on?.connect, 0, 0)
  return last
}

export async function openStage(page: Page, query: Record<string, string>, theme: Theme): Promise<void> {
  await page.clock.setFixedTime(NOW)
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
  // Offline: only the stage itself (YouTube embeds, fonts CDNs, the cloud are never reached).
  await page.route(/^https?:\/\/(?!localhost[:/]|127\.0\.0\.1[:/])/, (r) => r.abort())
  await page.goto('/?' + new URLSearchParams({ ...query, appearance: theme }).toString(), { waitUntil: 'load' })
  await page.evaluate(() => document.fonts.ready)
  await page.addStyleTag({ content: HIDE_CSS })
  // The scenario's scripted start-up (capped), then springs and enter transitions: reduced motion shortens them.
  const sc = query.scenario ?? 'full'
  await page.waitForTimeout(Math.min(startupMs(sc), 10_000) + 1200)
}
