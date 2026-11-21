/**
 * Main-process side of onboarding (A3; renderer: src/renderer/src/features/onboarding/).
 *
 *   - First-run order: branded intro → miyagi login → guided setup → home. While features/auth.ts says the login is
 *     needed, the login window (route `auth`, same size and spot) opens first and plays the intro; setup follows when
 *     the learner signs in or continues without an account (onLoginDone).
 *   - Flags: userData/onboarding.json {done, at, introSeen}. Not done → the Onboarding app window opens once the overlay
 *     has loaded, at the first-run size (FIRST_RUN): the branded intro the very first time ({view:'intro'}), guided
 *     setup after that ({view:'setup'}: a relaunch for Screen Recording lands back in the walk, not the intro).
 *     MIYAGI_SKIP_ONBOARDING=1 skips it (dev). The window's title stays "miyagi" whatever the page says.
 *   - Prompts happen ONLY here and ONLY on a click (BUILD-PLAN Section 6): onboarding:prompt(kind). Screen Recording:
 *     one tiny capture makes macOS ask; Accessibility: isTrustedAccessibilityClient(true). System Settings itself opens
 *     through core's permissions:open(kind) (fixed URLs in main/safeOpen.ts), never a URL from a renderer.
 *   - The VS Code companion (DISTRIBUTION-PLAN 2): VS Code's own CLI at its fixed path inside the app bundle, run with
 *     execFile (no shell) and a minimal environment, installs the bundled .vsix from Resources/vscode/ plus the Python
 *     and Jupyter extensions. No .vsix bundled (dev, until bundle-engine ships one) → {ok:false, reason:'no-vsix'} and
 *     the renderer falls back to the engine's own fix. Never another editor.
 *
 * Handles (bridge.invoke; ctx.handle checks the sender):
 *   onboarding:get                  → { done, introSeen }
 *   onboarding:done                 write the flag → true
 *   onboarding:intro-seen           the intro played (or was skipped) → true
 *   onboarding:prompt (kind)        the macOS prompt for 'screen' | 'accessibility' → boolean (asked)
 *   onboarding:relaunch             app.relaunch() + quit (macOS applies a Screen Recording grant after one)
 *   onboarding:install-companion    → { ok, reason? }; broadcasts feat:onboarding:companion {state}
 *
 * UNVERIFIED in Electron (cost freeze; no live run in this package): the TCC prompts, the relaunch, the CLI install.
 */
import { desktopCapturer, screen, systemPreferences, type BrowserWindow } from 'electron'
import { execFile } from 'node:child_process'
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { needsLogin, onLoginDone } from './auth'

/** The first launch's window (intro + guided setup). The renderer's stage uses the same numbers (features/onboarding/web.ts). */
const FIRST_RUN = { w: 944, h: 640 }
const INSTALL_TIMEOUT_MS = 180_000
const EXTENSIONS = ['ms-python.python', 'ms-toolsai.jupyter']
const VSIX_RE = /^miyagi[A-Za-z0-9._-]*\.vsix$/

type Flag = { done: boolean; at?: string; introSeen?: boolean }

/** VS Code's own CLI inside the app bundle: present even when `code` was never added to PATH. */
function codeCli(): string | undefined {
  if (process.platform !== 'darwin') return undefined
  const rel = 'Visual Studio Code.app/Contents/Resources/app/bin/code'
  return [join('/Applications', rel), join(homedir(), 'Applications', rel)].find((p) => existsSync(p))
}

/** The companion shipped inside miyagi.app (Resources/vscode/miyagi*.vsix), if this build has one. */
function bundledVsix(): string | undefined {
  try {
    const dir = join(process.resourcesPath ?? '', 'vscode')
    if (!process.resourcesPath || !existsSync(dir)) return undefined
    const name = readdirSync(dir).find((f) => VSIX_RE.test(f))
    return name ? join(dir, name) : undefined
  } catch {
    return undefined
  }
}

/** Only what VS Code's CLI needs: never our keys or the engine token. */
function cliEnv(): NodeJS.ProcessEnv {
  const keep = ['HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR']
  const env: NodeJS.ProcessEnv = { PATH: '/usr/bin:/bin:/usr/sbin:/sbin' }
  for (const k of keep) if (process.env[k]) env[k] = process.env[k]
  return env
}

function run(file: string, args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(file, args, { env: cliEnv(), timeout: INSTALL_TIMEOUT_MS, windowsHide: true, maxBuffer: 1024 * 1024 }, (err) => {
      // Never the output: it can carry paths. Only that it failed.
      if (err) console.warn('[onboarding] VS Code CLI step failed:', args[0], args[1]?.startsWith('/') ? '(bundled companion)' : args[1])
      resolve(!err)
    })
  })
}

export default defineMainFeature({
  id: 'onboarding',
  setup(ctx) {
    const file = join(ctx.app.getPath('userData'), 'onboarding.json')
    let flag: Flag = { done: false }
    if (existsSync(file)) {
      try {
        const raw = JSON.parse(readFileSync(file, 'utf8')) as Partial<Flag>
        flag = { done: raw.done === true, at: typeof raw.at === 'string' ? raw.at : undefined, introSeen: raw.introSeen === true }
      } catch {
        console.warn('[onboarding] onboarding.json could not be read; showing setup again')
      }
    }

    const save = (): void => {
      try {
        const tmp = `${file}.tmp`
        writeFileSync(tmp, JSON.stringify(flag), { mode: 0o600 })
        renameSync(tmp, file)
      } catch {
        console.warn('[onboarding] could not save onboarding.json')
      }
    }

    /** A first-run window (login or setup), centered on the display under the pointer, clamped to its work area. */
    const place = (win: BrowserWindow | undefined): BrowserWindow | undefined => {
      if (!win || win.isDestroyed()) return undefined
      // The product's name, lowercase, in the title bar and the Window menu (BRAND.md), whatever the page sets.
      win.setTitle('miyagi')
      win.on('page-title-updated', (e) => e.preventDefault())
      const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
      const w = Math.min(FIRST_RUN.w, area.width - 32)
      const h = Math.min(FIRST_RUN.h, area.height - 32)
      // Before it is shown (ready-to-show), so nothing animates or jumps.
      win.setBounds({ x: Math.round(area.x + (area.width - w) / 2), y: Math.round(area.y + (area.height - h) / 2), width: w, height: h })
      return win
    }

    /** The first run's setup window: intro (once) then guided setup. */
    const openFirstRun = (): BrowserWindow | undefined => place(ctx.openWindow('onboarding', { view: flag.introSeen ? 'setup' : 'intro' }))

    /**
     * First-run order (agents/auth.md): branded intro → miyagi login → guided setup → home. While the login is
     * needed (features/auth.ts: on, nobody signed in, no choice made yet), the login window opens first and plays the
     * intro itself; when the learner is done there (signed in, or "Continue without an account"), auth.ts asks for
     * setup, which opens without the intro (it already played).
     */
    let quitting = false
    ctx.app.on('before-quit', () => (quitting = true))
    let loginDone = false
    const introPlayed = (): void => {
      if (flag.introSeen) return
      flag = { ...flag, introSeen: true }
      save()
    }

    const startFirstRun = (): void => {
      if (!needsLogin()) {
        openFirstRun()
        return
      }
      const login = place(ctx.openWindow('auth', { view: flag.introSeen ? 'login' : 'intro' }))
      // Closed with the red button, no choice made: setup still opens (nobody is left with only the pill), and the
      // intro won't play again. The login itself shows again next launch, since nothing was chosen.
      login?.once('closed', () => {
        if (quitting || loginDone || flag.done) return
        introPlayed()
        openFirstRun()
      })
    }
    onLoginDone(() => {
      loginDone = true
      if (flag.done) return undefined // a later sign-in (Account page): no setup to open
      introPlayed()
      return openFirstRun()
    })

    if (!flag.done && process.env.MIYAGI_SKIP_ONBOARDING !== '1') ctx.overlay.webContents.once('did-finish-load', startFirstRun)

    ctx.handle('onboarding:get', () => ({ done: flag.done, introSeen: flag.introSeen === true }))
    ctx.handle('onboarding:done', () => {
      if (!flag.done) {
        flag = { ...flag, done: true, at: new Date().toISOString() }
        save()
      }
      return true
    })
    ctx.handle('onboarding:intro-seen', () => {
      if (!flag.introSeen) {
        flag = { ...flag, introSeen: true }
        save()
      }
      return true
    })

    // Only on the learner's click (the renderer calls this from a button handler, never from a poll).
    ctx.handle('onboarding:prompt', async (kind: unknown) => {
      if (process.platform !== 'darwin') return false
      if (kind === 'accessibility') {
        try {
          return systemPreferences.isTrustedAccessibilityClient(true)
        } catch {
          return false
        }
      }
      if (kind === 'screen') {
        if (systemPreferences.getMediaAccessStatus('screen') === 'granted') return true
        try {
          // The smallest capture there is: it exists to make macOS ask (and list miyagi in the pane).
          await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 1, height: 1 } })
        } catch {
          /* the prompt is the point; a refusal is fine */
        }
        return true
      }
      return false
    })

    ctx.handle('onboarding:relaunch', () => {
      // A dev copy (npm run dev) can't app.relaunch(): electron-vite owns the process. Hand the restart to the
      // ~/Applications/miyagi.app launcher, which stops this copy and starts a fresh one (Michael, Nov 20: Relaunch did nothing).
      const launcher = join(homedir(), 'Applications', 'miyagi.app')
      if (!ctx.app.isPackaged && existsSync(launcher)) {
        execFile('/usr/bin/open', ['-n', launcher], () => undefined)
        return true
      }
      ctx.app.relaunch()
      ctx.app.quit()
      return true
    })

    let installing: Promise<{ ok: boolean; reason?: string }> | undefined
    ctx.handle('onboarding:install-companion', () => {
      if (installing) return installing
      const cli = codeCli()
      const vsix = bundledVsix()
      if (!vsix) return { ok: false, reason: 'no-vsix' }
      if (!cli) return { ok: false, reason: 'no-vscode' }
      ctx.broadcast('onboarding:companion', { state: 'installing' })
      installing = (async () => {
        const ok = await run(cli, ['--install-extension', vsix, '--force'])
        // The lesson extensions: nice to have; the companion is what the row checks.
        for (const id of EXTENSIONS) await run(cli, ['--install-extension', id])
        ctx.broadcast('onboarding:companion', { state: ok ? 'done' : 'failed' })
        return ok ? { ok: true } : { ok: false, reason: 'failed' }
      })().finally(() => {
        installing = undefined
      })
      return installing
    })
  }
})
