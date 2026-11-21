/**
 * Main-process side of onboarding (A3; renderer: src/renderer/src/features/onboarding/).
 *
 *   - Done flag: userData/onboarding.json {done, at}. Not done → the Onboarding app window opens once the overlay has
 *     loaded, at the two-pane first-run size (Onb-Setup-Full, FIRST_RUN). MIYAGI_SKIP_ONBOARDING=1 skips it (dev).
 *   - Prompts happen ONLY here and ONLY on a click (BUILD-PLAN Section 6): onboarding:prompt(kind). Screen Recording:
 *     one tiny capture makes macOS ask; Accessibility: isTrustedAccessibilityClient(true). System Settings itself opens
 *     through core's permissions:open(kind) (fixed URLs in main/safeOpen.ts), never a URL from a renderer.
 *   - The VS Code companion (DISTRIBUTION-PLAN 2): VS Code's own CLI at its fixed path inside the app bundle, run with
 *     execFile (no shell) and a minimal environment, installs the bundled .vsix from Resources/vscode/ plus the Python
 *     and Jupyter extensions. No .vsix bundled (dev, until bundle-engine ships one) → {ok:false, reason:'no-vsix'} and
 *     the renderer falls back to the engine's own fix. Never another editor.
 *
 * Handles (bridge.invoke; ctx.handle checks the sender):
 *   onboarding:get                  → { done }
 *   onboarding:done                 write the flag → true
 *   onboarding:prompt (kind)        the macOS prompt for 'screen' | 'accessibility' → boolean (asked)
 *   onboarding:relaunch             app.relaunch() + quit (macOS applies a Screen Recording grant after one)
 *   onboarding:install-companion    → { ok, reason? }; broadcasts feat:onboarding:companion {state}
 *
 * UNVERIFIED in Electron (cost freeze; no live run in this package): the TCC prompts, the relaunch, the CLI install.
 */
import { desktopCapturer, screen, systemPreferences } from 'electron'
import { execFile } from 'node:child_process'
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

/** Onb-Setup-Full's dialog. The renderer's stage uses the same numbers (features/onboarding/web.ts). */
const FIRST_RUN = { w: 944, h: 640 }
const INSTALL_TIMEOUT_MS = 180_000
const EXTENSIONS = ['ms-python.python', 'ms-toolsai.jupyter']
const VSIX_RE = /^miyagi[A-Za-z0-9._-]*\.vsix$/

type Flag = { done: boolean; at?: string }

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
        flag = { done: raw.done === true, at: typeof raw.at === 'string' ? raw.at : undefined }
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

    /** The first run: the two-pane window, centered on the display under the pointer, clamped to its work area. */
    const openFirstRun = (): void => {
      const win = ctx.openWindow('onboarding', { view: 'welcome' })
      if (!win || win.isDestroyed()) return
      const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
      const w = Math.min(FIRST_RUN.w, area.width - 32)
      const h = Math.min(FIRST_RUN.h, area.height - 32)
      // Before it is shown (ready-to-show), so nothing animates or jumps.
      win.setBounds({ x: Math.round(area.x + (area.width - w) / 2), y: Math.round(area.y + (area.height - h) / 2), width: w, height: h })
    }

    if (!flag.done && process.env.MIYAGI_SKIP_ONBOARDING !== '1') ctx.overlay.webContents.once('did-finish-load', openFirstRun)

    ctx.handle('onboarding:get', () => ({ done: flag.done }))
    ctx.handle('onboarding:done', () => {
      if (!flag.done) {
        flag = { done: true, at: new Date().toISOString() }
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
