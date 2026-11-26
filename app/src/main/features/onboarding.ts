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
 *     launch; home's Finish setup runs setup over home again and clears it: onboarding:resume; leaving that before
 *     it is done puts it back). With later, a start at login or MIYAGI_QUIET_LAUNCH=1 opens nothing (launch.ts).
 *     MIYAGI_SKIP_ONBOARDING=1 skips all of it (dev).
 *   - The standalone setup window (route `onboarding`) and login window (route `auth`) stay as fallbacks only: every
 *     ask for setup runs it over home in the home window (renderer core/surfaces.ts openOnboarding: from another
 *     window it opens the home window with {setup}); the setup window opens only when the home window can't. The
 *     Account page's Sign in opens the login.
 *   - Prompts happen ONLY here and ONLY on a click (BUILD-PLAN Section 6): onboarding:prompt(kind). Screen Recording:
 *     one tiny capture makes macOS ask; Accessibility: isTrustedAccessibilityClient(true). System Settings itself opens
 *     through core's permissions:open(kind) (fixed URLs in main/safeOpen.ts), never a URL from a renderer.
 *   - Consent first (launch register R05, R06): no prompt and no capture before the learner continued past the consent
 *     screen ("By continuing you agree to the terms and privacy policy") for this build's CONSENT_VERSION
 *     (common/consent.ts). onboarding:prompt refuses until then, and the launch gate's 'consent' part stays closed, so
 *     no overlay, launcher or lesson exists either. onboarding:agree stamps prefs.consent {version, at} with main's own
 *     clock (main/prefs.ts patchPrefs; a renderer's prefs:set can't write it). A build with a newer CONSENT_VERSION
 *     finds the old record, closes the gate and asks again.
 *   - The VS Code companion (DISTRIBUTION-PLAN 2): VS Code's own CLI (mac: fixed path in the app bundle; Windows: see vscodeCli.ts), run with
 *     execFile (no shell) and a minimal environment, installs the bundled .vsix from Resources/vscode/ plus the Python
 *     and Jupyter extensions. No .vsix bundled (dev, until bundle-engine ships one) → {ok:false, reason:'no-vsix'} and
 *     the renderer falls back to the engine's own fix. Never another editor.
 *
 * Handles (bridge.invoke; ctx.handle checks the sender):
 *   onboarding:get                  → { done, introSeen, flow, login, consent, step, gate }   flow: the home window
 *                                     runs the first run; login: the login is needed (always, flow or not); consent:
 *                                     the learner agreed to this build's policy version; gate: the launch gate's view
 *                                     (common/gate.ts GateView)
 *   onboarding:agree                the consent screen's Continue: prefs.consent = {version: CONSENT_VERSION, at: now}
 *                                   (kept if already current) → true
 *   onboarding:step (step)          the guided step on screen, saved for a relaunch → true
 *   onboarding:later                "Set up later": home on launch from now on, setup still not done → true
 *   onboarding:resume               setup again over home (home's Finish setup, Settings' Open setup): forget "later" → true
 *   onboarding:done                 write the flag → true
 *   onboarding:intro-seen           the intro played (or was skipped) → true
 *   onboarding:prompt (kind)        the macOS prompt for 'screen' | 'accessibility' → boolean (asked); false, with
 *                                   nothing asked or captured, until consent is current
 *   onboarding:tour (what)          the first-lesson walkthrough in the overlay (rules: onboarding/tour.ts). 'start'
 *                                   opens it (broadcast feat:onboarding:tour {open, seq}; held until the launch gate
 *                                   opens, then run); 'end' closes it; 'seen' remembers it (onboarding.json tourSeen,
 *                                   clears tourDue); 'auto' (the first-run flow handed over to home) starts it once,
 *                                   AUTO_TOUR_DELAY_MS later, when a first run made it due (tourDue) and it is unseen.
 *                                   onboarding:get carries tour {open, seq, due} so the overlay catches a start it missed.
 *   onboarding:relaunch            app.relaunch() + quit (macOS applies a Screen Recording grant after one)
 *   onboarding:install-companion    → { ok, reason? }; broadcasts feat:onboarding:companion {state}
 *
 * Broadcast: feat:onboarding:gate  GateView (cleanGate) on every change of the launch gate (main/gate.ts).
 *
 * Launch gate (main/gate.ts, part 'setup'): open once setup is done or put off ("Set up later"), closed again by
 * onboarding:resume until it is done or put off again. Part 'consent': open once prefs.consent is this build's version.
 * A launch with the gate closed opens the home window (its flow starts at the login, then consent, then setup),
 * whatever onboarding.json says.
 *
 * UNVERIFIED in Electron (cost freeze; no live run in this package): the TCC prompts, the relaunch, the CLI install.
 */
import { desktopCapturer, systemPreferences, type App, type BrowserWindow } from 'electron'
import { execFile } from 'node:child_process'
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { CONSENT_VERSION, consentCurrent, makeConsent } from '../../common/consent'
import { cleanGate } from '../../common/gate'
import { defineMainFeature } from '../context'
import { gateIsOpen, gateView, onGate, setGatePart } from '../gate'
import { getPrefs, onPrefsChange, patchPrefs } from '../prefs'
import { needsLogin, onLoginDone } from './auth'
import { AUTO_TOUR_DELAY_MS, onGateOpened, shouldAutoTour, startDecision, tourDueAtLaunch } from './onboarding/tour'
import { cliEnvFor, cliInvocation, findCodeCli, stepLabel, type CodeCli } from './vscodeCli'

/** The guided steps a relaunch may come back to (renderer onboarding/steps.ts STEP_ORDER). */
const STEPS = ['screen', 'accessibility', 'companion', 'engine'] as const
type Step = (typeof STEPS)[number]
const isStep = (s: unknown): s is Step => typeof s === 'string' && (STEPS as readonly string[]).includes(s)
const INSTALL_TIMEOUT_MS = 180_000
const EXTENSIONS = ['ms-python.python', 'ms-toolsai.jupyter']
const VSIX_RE = /^miyagi[A-Za-z0-9._-]*\.vsix$/

type Flag = { done: boolean; at?: string; introSeen?: boolean; step?: Step; later?: boolean; tourSeen?: boolean; tourDue?: boolean }

/** Started by macOS at login (launch.ts reads it the same way). */
function startedAtLogin(app: App): boolean {
  try {
    return process.platform === 'darwin' && app.getLoginItemSettings().wasOpenedAtLogin === true
  } catch {
    return false
  }
}

/** VS Code's own CLI (mac: inside the app bundle; Windows: Code.exe + cli.js or code.cmd): see vscodeCli.ts. */
function codeCli(): CodeCli | undefined {
  return findCodeCli({
    platform: process.platform,
    env: process.env,
    home: homedir(),
    exists: existsSync,
    readdir: (p) => readdirSync(p)
  })
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

function run(cli: CodeCli, args: string[]): Promise<boolean> {
  const inv = cliInvocation(cli, args)
  return new Promise((resolve) => {
    execFile(
      inv.file,
      inv.args,
      { env: cliEnvFor(process.platform, process.env, cli.extraEnv), timeout: INSTALL_TIMEOUT_MS, windowsHide: true, windowsVerbatimArguments: inv.verbatim, maxBuffer: 1024 * 1024 },
      (err) => {
        // Never the output or the .vsix path: they carry the user's folders. Only that it failed.
        if (err) console.warn('[onboarding] VS Code CLI step failed:', args[0], stepLabel(args[1]))
        resolve(!err)
      }
    )
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
        flag = { done: raw.done === true, at: typeof raw.at === 'string' ? raw.at : undefined, introSeen: raw.introSeen === true, step: isStep(raw.step) ? raw.step : undefined, later: raw.later === true, tourSeen: raw.tourSeen === true, tourDue: raw.tourDue === true }
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
    /** The launch gate's setup part: done, put off, or skipped. Called after every change of the flag. */
    const reportSetup = (): void => setGatePart('setup', skip || flag.done || flag.later === true)
    /** The learner agreed to this build's terms and privacy policy version (prefs.consent, written only by main). */
    const consented = (): boolean => skip || consentCurrent(getPrefs().consent)
    /** The launch gate's consent part. Called at launch and after every prefs change (onboarding:agree writes it). */
    const reportConsent = (): void => setGatePart('consent', consented())
    reportConsent()
    onPrefsChange(reportConsent)
    reportSetup()
    // Every window hears the gate (the home window's flow, the overlay's renderer store).
    onGate((_open, view) => ctx.broadcast('onboarding:gate', cleanGate(view)))

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
     * A launch with the gate closed: only the home window. Its flow layer plays the intro (once), Sign in, guided setup
     * and You're ready in place, then home slides in (renderer features/shell/flow). launch.ts may have opened the same
     * window already: then it is only titled, never opened again with args.
     */
    const startFirstRun = (): void => {
      if (gateIsOpen()) return
      const open = ctx.appWindow('library')
      pinTitle(open && !open.isDestroyed() ? open : ctx.openWindow('library'))
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

    // Setup done or put off keeps launch.ts's quiet cold launches: nothing opens when miyagi starts at login or with
    // MIYAGI_QUIET_LAUNCH=1 (recordings). A real first run (setup never done or put off) always opens.
    const quiet = (flag.done || flag.later === true) && (startedAtLogin(ctx.app) || process.env.MIYAGI_QUIET_LAUNCH === '1')
    // Whenever the gate is closed at launch (login or setup ahead), not only on a first run: launch = start from new.
    if (!skip && !quiet) ctx.overlay.webContents.once('did-finish-load', startFirstRun)

    // ---- the first-lesson walkthrough (renderer features/tips TourLayer.tsx, drawn in the overlay) --------------------
    // Main owns whether it is open: every start goes through here, so a start from the home window (Settings, You're
    // ready) reaches the overlay, and the overlay asks onboarding:get (tour.open) when its gate opens, so a start it
    // missed (still loading, hidden behind the gate) is never lost. Rules: onboarding/tour.ts.
    // A first run makes the tour due (kept in onboarding.json until it is seen or declined): an upgrade never pops one.
    if (tourDueAtLaunch(flag) && !flag.tourDue) {
      flag = { ...flag, tourDue: true }
      save()
    }
    let tourOpen = false
    /** An explicit start asked for while the gate was closed: it runs when the gate opens. */
    let tourHeld = false
    /** Started (by hand or by itself) or auto-asked in this run: the auto tour runs at most once per launch. */
    let tourTried = false
    let tourSeq = 0
    let autoTimer: ReturnType<typeof setTimeout> | undefined
    const startTourNow = (): void => {
      tourHeld = false
      tourTried = true
      tourOpen = true
      tourSeq += 1
      // The overlay is a click-through panel over the home window: make sure it is up and on top before it draws.
      try {
        if (!ctx.overlay.isDestroyed()) {
          ctx.overlay.showInactive()
          ctx.raise(ctx.overlay)
          ctx.overlay.moveTop()
        }
      } catch {
        /* a test context or an older main: the broadcast still opens it */
      }
      ctx.broadcast('onboarding:tour', { open: true, seq: tourSeq })
    }
    let gateWasOpen = gateIsOpen()
    onGate((open) => {
      const opened = open && !gateWasOpen
      gateWasOpen = open
      if (!open) {
        // A sign-out: the overlay hides, so does the tour; an auto start not yet run is dropped.
        if (autoTimer) clearTimeout(autoTimer)
        autoTimer = undefined
        if (tourOpen) {
          tourOpen = false
          ctx.broadcast('onboarding:tour', { open: false, seq: tourSeq })
        }
        return
      }
      if (opened && onGateOpened({ held: tourHeld }) === 'start') startTourNow()
    })
    ctx.handle('onboarding:tour', (what: unknown) => {
      if (what === 'seen') {
        // Done, skipped, or declined on You're ready: never owed again.
        if (!flag.tourSeen || flag.tourDue) {
          flag = { ...flag, tourSeen: true, tourDue: false }
          save()
        }
        return true
      }
      if (what === 'start') {
        if (autoTimer) clearTimeout(autoTimer)
        autoTimer = undefined
        if (startDecision({ gateOpen: gateIsOpen() }) === 'now') startTourNow()
        else tourHeld = true
        return true
      }
      if (what === 'end') {
        tourHeld = false
        if (autoTimer) clearTimeout(autoTimer)
        autoTimer = undefined
        tourOpen = false
        ctx.broadcast('onboarding:tour', { open: false, seq: tourSeq })
        return true
      }
      if (what === 'auto') {
        // The home window's first-run flow handed over to home (renderer shell/flow): the tour's turn, once.
        const go = shouldAutoTour({ due: flag.tourDue === true, seen: flag.tourSeen === true, gateOpen: gateIsOpen(), tried: tourTried || !!autoTimer, skip, quiet })
        if (!go) return false
        tourTried = true
        autoTimer = setTimeout(() => {
          autoTimer = undefined
          if (gateIsOpen() && !flag.tourSeen && !tourOpen) startTourNow()
        }, AUTO_TOUR_DELAY_MS)
        return true
      }
      return false
    })
    ctx.handle('onboarding:get', () => ({
      done: flag.done,
      introSeen: flag.introSeen === true,
      tourSeen: flag.tourSeen === true,
      tour: { open: tourOpen, seq: tourSeq, due: flag.tourDue === true && flag.tourSeen !== true },
      flow: flowOn(),
      login: needsLogin(),
      consent: consented(),
      consentVersion: CONSENT_VERSION,
      step: flag.step,
      gate: gateView()
    }))
    // The consent screen's Continue ("By continuing you agree to the terms and privacy policy"). Main stamps the record
    // itself: this build's version and main's clock, never a version or time from a window.
    ctx.handle('onboarding:agree', () => {
      if (!consentCurrent(getPrefs().consent)) patchPrefs({ consent: makeConsent() })
      reportConsent()
      return true
    })
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
      reportSetup()
      return true
    })
    ctx.handle('onboarding:resume', () => {
      if (flag.later) {
        flag = { ...flag, later: false }
        save()
      }
      reportSetup()
      return true
    })
    ctx.handle('onboarding:done', () => {
      if (!flag.done) {
        flag = { ...flag, done: true, at: new Date().toISOString() }
        save()
      }
      reportSetup()
      return true
    })
    ctx.handle('onboarding:intro-seen', () => {
      if (!flag.introSeen) {
        flag = { ...flag, introSeen: true }
        save()
      }
      return true
    })

    // Only on the learner's click (the renderer calls this from a button handler, never from a poll), and only once
    // the learner has agreed (R05): before that nothing is asked and nothing is captured, not even the 1x1 thumbnail.
    ctx.handle('onboarding:prompt', async (kind: unknown) => {
      if (!consented()) {
        console.warn('[onboarding] a permission prompt was asked for before consent; refused')
        return false
      }
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
      // A dev copy (npm run dev) can't app.relaunch(): electron-vite owns the process. It never starts another miyagi
      // either (it used to `open -n ~/Applications/miyagi.app`, a second copy that fought this one): restart by hand.
      if (!ctx.app.isPackaged) {
        console.log('[onboarding] relaunch asked in a dev copy: restart npm run dev')
        return false
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
