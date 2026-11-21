/**
 * Main-process side of onboarding (A3; renderer: src/renderer/src/features/onboarding/).
 *
 *   - ONE WINDOW from start to finish (Michael, Nov 21: never a login window floating over home). On a first launch
 *     only the home window opens (route `library`); its first-run flow layer (renderer features/shell/flow) covers it:
 *     branded intro → Sign in (while features/auth.ts says the login is needed) → guided setup → You're ready → home
 *     slides in. No login window, no setup window, nothing behind them. The renderer asks onboarding:get whether the
 *     flow is on. The Dock click, the tray's Open miyagi and a second launch bring this same window forward
 *     (launch.ts); a relaunch for Screen Recording comes back to the step it left (flag.step).
 *   - Flags: userData/onboarding.json {done, at, introSeen, step, later}. done: setup finished (no flow). introSeen:
 *     the intro played once. step: the guided step on screen (onboarding:step). later: "Set up later" (no flow on
 *     launch; home's Finish setup runs setup over home again and clears it: onboarding:resume).
 *     MIYAGI_SKIP_ONBOARDING=1 skips all of it (dev).
 *   - The standalone setup window (route `onboarding`) and login window (route `auth`) stay as fallbacks only: the
 *     setup window opens when setup is asked for from outside the home window (the home window's Finish setup and
 *     Settings' Open setup run it over home instead); the Account page's Sign in opens the login.
 *   - Prompts happen ONLY here and ONLY on a click (BUILD-PLAN Section 6): onboarding:prompt(kind). Screen Recording:
 *     one tiny capture makes macOS ask; Accessibility: isTrustedAccessibilityClient(true). System Settings itself opens
 *     through core's permissions:open(kind) (fixed URLs in main/safeOpen.ts), never a URL from a renderer.
 *   - The VS Code companion (DISTRIBUTION-PLAN 2): VS Code's own CLI at its fixed path inside the app bundle, run with
 *     execFile (no shell) and a minimal environment, installs the bundled .vsix from Resources/vscode/ plus the Python
 *     and Jupyter extensions. No .vsix bundled (dev, until bundle-engine ships one) → {ok:false, reason:'no-vsix'} and
 *     the renderer falls back to the engine's own fix. Never another editor.
 *
 * Handles (bridge.invoke; ctx.handle checks the sender):
 *   onboarding:get                  → { done, introSeen, flow, login, step }   flow: the home window runs the first run
 *   onboarding:step (step)          the guided step on screen, saved for a relaunch → true
 *   onboarding:later                "Set up later": home on launch from now on, setup still not done → true
 *   onboarding:resume               setup again over home (home's Finish setup, Settings' Open setup): forget "later" → true
 *   onboarding:done                 write the flag → true
 *   onboarding:intro-seen           the intro played (or was skipped) → true
 *   onboarding:prompt (kind)        the macOS prompt for 'screen' | 'accessibility' → boolean (asked)
 *   onboarding:relaunch             app.relaunch() + quit (macOS applies a Screen Recording grant after one)
 *   onboarding:install-companion    → { ok, reason? }; broadcasts feat:onboarding:companion {state}
 *
 * UNVERIFIED in Electron (cost freeze; no live run in this package): the TCC prompts, the relaunch, the CLI install.
 */
import { desktopCapturer, systemPreferences, type BrowserWindow } from 'electron'
import { execFile } from 'node:child_process'
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { needsLogin, onLoginDone } from './auth'

/** The guided steps a relaunch may come back to (renderer onboarding/steps.ts STEP_ORDER). */
const STEPS = ['screen', 'accessibility', 'companion', 'engine'] as const
type Step = (typeof STEPS)[number]
const isStep = (s: unknown): s is Step => typeof s === 'string' && (STEPS as readonly string[]).includes(s)
const INSTALL_TIMEOUT_MS = 180_000
const EXTENSIONS = ['ms-python.python', 'ms-toolsai.jupyter']
const VSIX_RE = /^miyagi[A-Za-z0-9._-]*\.vsix$/

type Flag = { done: boolean; at?: string; introSeen?: boolean; step?: Step; later?: boolean }

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
        flag = { done: raw.done === true, at: typeof raw.at === 'string' ? raw.at : undefined, introSeen: raw.introSeen === true, step: isStep(raw.step) ? raw.step : undefined, later: raw.later === true }
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

    const skip = process.env.MIYAGI_SKIP_ONBOARDING === '1'
    /** The home window runs the first run (renderer features/shell/flow): setup not done and not put off. */
    const flowOn = (): boolean => !skip && !flag.done && !flag.later

    /** The product's name, lowercase, in the title bar and the Window menu (BRAND.md), whatever the page sets. */
    const pinned = new WeakSet<BrowserWindow>()
    const pinTitle = (win: BrowserWindow | undefined): BrowserWindow | undefined => {
      if (!win || win.isDestroyed()) return undefined
      win.setTitle('miyagi')
      if (!pinned.has(win)) {
        pinned.add(win)
        win.on('page-title-updated', (e) => e.preventDefault())
      }
      return win
    }

    /**
     * The first launch: only the home window. Its flow layer plays the intro, Sign in, guided setup and You're ready
     * in place, then home slides in (renderer features/shell/flow). A later launch with setup put off ("Set up later")
     * opens home too, without the flow.
     */
    const startFirstRun = (): void => {
      pinTitle(ctx.openWindow('library'))
    }

    /**
     * Done with the login (auth.ts auth:continue). In the one-window flow the login is a screen of the home window: the
     * flow moves on by itself, nothing opens. Only the standalone login window (a fallback: the Account page's Sign in)
     * hands over to a window: home, when setup isn't done yet (its flow carries on there), else nothing.
     */
    onLoginDone(() => {
      if (!ctx.appWindow('auth')) return undefined
      if (flag.done) return undefined
      return pinTitle(ctx.openWindow('library'))
    })

    if (!flag.done && !skip) ctx.overlay.webContents.once('did-finish-load', startFirstRun)

    ctx.handle('onboarding:get', () => ({ done: flag.done, introSeen: flag.introSeen === true, flow: flowOn(), login: flowOn() && needsLogin(), step: flag.step }))
    ctx.handle('onboarding:step', (step: unknown) => {
      if (isStep(step) && flag.step !== step && !flag.done) {
        flag = { ...flag, step }
        save()
      }
      return true
    })
    ctx.handle('onboarding:later', () => {
      if (!flag.later && !flag.done) {
        flag = { ...flag, later: true, introSeen: true }
        save()
      }
      return true
    })
    ctx.handle('onboarding:resume', () => {
      if (flag.later) {
        flag = { ...flag, later: false }
        save()
      }
      return true
    })
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
