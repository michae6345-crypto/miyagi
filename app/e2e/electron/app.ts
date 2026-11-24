/**
 * Launch helpers for the Electron E2E. Each launch gets its own --user-data-dir, the mock engine (DEMO=1) and no
 * telemetry, network to the cloud is pointed at a dead local port, and every window's console errors are collected.
 */
import { _electron, type ElectronApplication, type Page } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export const APP_DIR = join(__dirname, '..', '..')
export const HELPER = join(APP_DIR, 'build', 'helpers', 'miyagi-listen')
const electronBin = createRequire(join(APP_DIR, 'package.json'))('electron') as unknown as string

/** Console errors we do not own: third-party frames (the YouTube player) and Chromium's own autofill noise. */
const IGNORED = [/youtube\.com|ytimg\.com|googlevideo/i, /Autofill\.enable/i, /Electron Security Warning/i]

export type Launched = { app: ElectronApplication; errors: string[]; userData: string }

export async function launch(env: Record<string, string> = {}, userData = mkdtempSync(join(tmpdir(), 'miyagi-e2e-'))): Promise<Launched> {
  const errors: string[] = []
  const app = await _electron.launch({
    executablePath: electronBin,
    args: [APP_DIR, `--user-data-dir=${userData}`],
    cwd: APP_DIR,
    env: {
      ...process.env,
      DEMO: '1',
      SCENARIO: 'full',
      MIYAGI_TELEMETRY: 'off',
      MIYAGI_CLOUD_URL: 'http://127.0.0.1:9', // nothing listens: the cloud is never reached
      MIYAGI_REGULAR_APP: '1',
      ...env
    }
  })
  const watch = (page: Page): void => {
    page.on('console', (m) => {
      if (m.type() !== 'error') return
      const text = `${page.url().split('#')[1] ?? '/'}: ${m.text()}`
      if (!IGNORED.some((re) => re.test(text))) errors.push(text.slice(0, 400))
    })
    page.on('pageerror', (e) => errors.push(`${page.url().split('#')[1] ?? '/'}: pageerror ${String(e).slice(0, 400)}`))
  }
  for (const w of app.windows()) watch(w)
  app.on('window', watch)
  return { app, errors, userData }
}

/** The window whose URL hash starts with `#/<route>` (core overlay: route ''), waiting for it to appear. */
export async function windowFor(app: ElectronApplication, route: string, timeout = 20_000): Promise<Page> {
  const match = (p: Page): boolean => {
    const hash = p.url().split('#')[1] ?? ''
    return route === '' ? hash === '' || hash === '/' || hash.startsWith('/overlay') : hash.startsWith(`/${route}`)
  }
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const found = app.windows().find(match)
    if (found) {
      await found.waitForLoadState('domcontentloaded')
      return found
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`no window for route "${route}"; open: ${app.windows().map((w) => w.url().split('#')[1] ?? '/').join(', ')}`)
}

/** The layout main sends this window (window.tut, preload): includes notch {place, hasNotch}. */
export function layoutOf(page: Page): Promise<{ notch: { place: string; hasNotch: boolean; width: number } }> {
  return page.evaluate(
    () =>
      new Promise((resolve) => {
        const tut = (window as unknown as { tut: { on(s: string, cb: (p: unknown) => void): () => void; ready(): void } }).tut
        const off = tut.on('layout', (l) => {
          off()
          resolve(l as never)
        })
        tut.ready()
      })
  )
}

/** Open an app window through main's allowlist, from any of our windows (the same call the UI makes). */
export function openWindow(from: Page, route: string, args?: Record<string, string>): Promise<unknown> {
  return from.evaluate(
    ([r, a]) => (window as unknown as { tut: { invoke(c: string, ...x: unknown[]): Promise<unknown> } }).tut.invoke('window:open', r, a),
    [route, args] as const
  )
}
