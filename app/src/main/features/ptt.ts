/**
 * Feature: ptt (main). Push to talk: hold Fn+Control (or Control+Option), speak, release; miyagi gets the words as an ask.
 * The speech-to-text runs in a Swift helper, miyagi-listen, spawned here with piped stdio (not detached, so macOS
 * attributes the microphone and Input Monitoring to miyagi.app). Design and protocol: miyagi-v2/PUSH-TO-TALK.md;
 * the parser and the session rules are pure and tested (pttProtocol.ts, common/pttState.ts).
 *
 *   bridge.invoke('ptt:get')            -> PttState (now)
 *   bridge.invoke('ptt:config', prefs)  the learner's ptt pref changed (Settings): send config to the helper
 *   bridge.invoke('ptt:allow', which)   'mic' | 'input' | 'both': ask the helper to raise the macOS prompt (an explicit
 *                                       click only, never on a bare key press)
 *   bridge.invoke('ptt:open-settings', 'mic' | 'input')   the Privacy pane (fixed URL, safeOpen.ts)
 *   bridge.invoke('ptt:cancel')         end the session in flight
 *   bridge.invoke('ptt:prefill', text) / 'ptt:prefill-take'   the launcher's prefilled text (no lesson running)
 *   bridge.invoke('ptt:capture', region) -> CaptureResult   circle to ask: the circled region as a JPEG file (pttProtocol.ts);
 *                                       overlay only, at most 2 waiting (else 'busy')
 *   bridge.invoke('ptt:capture-release', id) -> boolean   the overlay won't send that capture: the helper deletes it now
 *   bridge.onFeature('ptt:state', cb)   every change of the one PttState
 *   bridge.onFeature('ptt:final', cb)   {id, text}: the words to ask (the overlay routes them, features/ptt/store.ts)
 *   bridge.onFeature('ptt:down', cb)    {id}: the keys went down (before the 250 ms debounce). The engine is told ask.warm
 *                                       later, on every 'listening' of the helper (the hold passed the minimum)
 *   bridge.onFeature('ptt:partial', cb) {id, text}: each new partial of the hold in flight (held, and during the release tail)
 *   bridge.onFeature('ptt:prefill', cb) text: the launcher is already open, fill it
 *
 * macOS only. If the helper binary is missing (a dev checkout that never built it) the feature stays quiet: no state,
 * no respawns. The helper is respawned with backoff when it dies, and told `quit` (then stdin closes) when the app quits.
 * UNVERIFIED in Electron (typechecked and unit-tested only: no app runs during this lane).
 *
 * ptt:capture saves no time yet: nothing calls it (no renderer sends it, no engine reads take_capture), and the 0.3 to
 * 0.5 s saving is an estimate, not a measurement. The renderer must never wait for a capture at release: if it has not
 * settled by then, send the ask without it (the engine grabs its own frame), or the 2 s timeout here adds up to 2 s.
 */
import { app, ipcMain, type IpcMainInvokeEvent } from 'electron'
import { execFile, spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { PTT_ENABLED } from '../../common/flags'
import { DEFAULT_PREFS, sanitizePrefs, type PttPrefs } from '../../common/prefs'
import { active, PTT_REST, reducePtt, type PttInput, type PttState } from '../../common/pttState'
import { cmd } from '../../common/wire'
import { defineMainFeature } from '../context'
import {
  backoffMs,
  CANCEL_COMMAND,
  CAPTURE_TIMEOUT_MS,
  captureAdmit,
  captureCommand,
  captureLogLine,
  captureReleaseCommand,
  captureRequest,
  type CaptureResult,
  configCommand,
  contextCommand,
  contextTerms,
  GIVE_UP_AFTER,
  HARD_CAP_MS,
  HEALTHY_MS,
  isCaptureId,
  libraryNames,
  lineBuffer,
  parseCaptureLine,
  parseCaptureWarmLine,
  parseLine,
  permissionsCommand,
  QUIT_COMMAND,
  tccResetArgs
} from '../pttProtocol'
import { openPttSettings } from '../safeOpen'

/** Where the helper is: shipped in the app's resources, in dev under app/build/helpers (the other lane builds it there). */
export function helperPath(): string {
  return app.isPackaged ? join(process.resourcesPath, 'helpers', 'miyagi-listen') : join(app.getAppPath(), 'build', 'helpers', 'miyagi-listen')
}

/**
 * A small log of what the helper did (never what was said): ~/Library/Logs/miyagi/ptt.log, cut back to its newest half
 * past 200 KB. A packaged miyagi has no console, so this is the only way to see why a hold did nothing.
 */
const LOG_MAX = 200_000
export function pttLog(line: string): void {
  try {
    const dir = app.getPath('logs')
    const file = join(dir, 'ptt.log')
    mkdirSync(dir, { recursive: true })
    if (existsSync(file) && statSync(file).size > LOG_MAX) writeFileSync(file, readFileSync(file, 'utf8').slice(-LOG_MAX / 2))
    appendFileSync(file, `${new Date().toISOString()} ${line}\n`)
  } catch {
    /* logging never breaks push to talk */
  }
}

/** `tccutil reset` for miyagi's own rows (packaged builds only: a dev run belongs to Electron, not miyagi). */
function resetGrant(kind: 'input' | 'mic'): Promise<void> {
  if (!app.isPackaged) return Promise.resolve()
  return Promise.all(
    tccResetArgs(kind).map(
      (args) =>
        new Promise<void>((done) => {
          execFile('/usr/bin/tccutil', args, { timeout: 5000 }, (err) => {
            pttLog(`tccutil ${args.join(' ')} ${err ? 'failed: ' + err.message : 'ok'}`)
            done()
          })
        })
    )
  ).then(() => undefined)
}

/** An error stays up this long, then the island goes back to rest. */
const ERROR_MS = 4000
/** The second prompt (input) follows the first (mic) after its answer, or this long. */
const PROMPT_GAP_MS = 10_000
const PREFILL_TTL_MS = 15_000

export default defineMainFeature({
  id: 'ptt',
  setup(ctx) {
    if (!PTT_ENABLED || ctx.platform.os !== 'mac' || process.platform !== 'darwin') return
    // A second copy of the app (`open -n`) is about to exit (features/launch.ts, windows.ts): it must not start a helper
    // of its own. The lock is already held by the first copy, so asking again is a no-op there.
    if (!app.requestSingleInstanceLock()) return
    const bin = helperPath()
    if (!existsSync(bin)) {
      console.log('[ptt] no miyagi-listen helper at', bin, '(push to talk stays off)')
      pttLog(`no helper at ${bin}: push to talk stays off`)
      return
    }

    let state: PttState = PTT_REST
    let prefs: PttPrefs = DEFAULT_PREFS.ptt
    try {
      prefs = sanitizePrefs(JSON.parse(readFileSync(join(app.getPath('userData'), 'prefs.json'), 'utf8'))).ptt ?? prefs
    } catch {
      /* first run: defaults */
    }

    let child: ChildProcessWithoutNullStreams | undefined
    let quitting = false
    let failures = 0
    let startedAt = 0
    let respawn: ReturnType<typeof setTimeout> | undefined
    let capTimer: ReturnType<typeof setTimeout> | undefined
    let errTimer: ReturnType<typeof setTimeout> | undefined
    let pendingInput: ReturnType<typeof setTimeout> | undefined
    let lastTerms = ''
    let prefill: { text: string; at: number } | undefined
    /** The hold that was released last, and when: for the 'final N ms after release' log line. */
    let up: { id: string; at: number } | undefined
    /**
     * The hold passed the minimum and the mic opened (the helper's 'listening'): let the engine get ready for the ask
     * (contract ask.warm, v2: only if it said so). On every such hold: it is one local WebSocket line, and the keep-alive
     * link it reopens (engine to cloud to Anthropic) closes a few seconds after its last use, so a warm-up from minutes
     * ago does nothing for this ask. The engine throttles only the paid prompt-cache write. Not on the raw key-down: a
     * tap ('short') or Fn+Control+arrow (window tiling, 'keypress') never asks. Capture and TLS still get a head start.
     */
    const warm = (id: string): void => {
      if (!ctx.engine.connected || !ctx.engine.can('ask.warm')) return
      ctx.engine.send(cmd('ask.warm', { pttId: id }))
    }

    const send = (line: string): void => {
      if (!child || child.killed || !child.stdin.writable) return
      try {
        child.stdin.write(line)
      } catch {
        /* the helper is going away: its exit handler takes over */
      }
    }

    const apply = (e: PttInput): void => {
      const r = reducePtt(state, e)
      const before = state
      state = r.state
      // The hard cap: a session that never ends (a lost key-up, a hung helper) is ended here, whatever the helper says.
      if (active(state) && !active(before)) {
        clearTimeout(capTimer)
        capTimer = setTimeout(() => {
          if (!active(state)) return
          send(CANCEL_COMMAND)
          apply({ type: 'reset' })
        }, HARD_CAP_MS)
      } else if (!active(state)) clearTimeout(capTimer)
      clearTimeout(errTimer)
      if (state.phase === 'error') errTimer = setTimeout(() => apply({ type: 'clear-error' }), ERROR_MS)
      if (state !== before) ctx.broadcast('ptt:state', state)
      if (r.final) ctx.broadcast('ptt:final', r.final)
    }

    const sendConfig = (): void => send(configCommand({ enabled: prefs.enabled, chord: prefs.chord }))

    // ---- the helper process ----
    const start = (): void => {
      if (quitting || child) return
      const buf = lineBuffer()
      let p: ChildProcessWithoutNullStreams
      try {
        p = spawn(bin, [], { stdio: ['pipe', 'pipe', 'pipe'], detached: false })
      } catch (err) {
        console.warn('[ptt] could not start the helper', err)
        return again()
      }
      child = p
      startedAt = Date.now()
      pttLog(`spawned helper pid=${p.pid ?? '?'} (${bin})`)
      let configured = false
      p.stdout.setEncoding('utf8')
      p.stdout.on('data', (chunk: string) => {
        for (const l of buf.push(chunk)) {
          const ev = parseLine(l)
          if (!ev) {
            const c = parseCaptureLine(l)
            // A late answer (main already said 'timeout'): nobody will use the file, so it goes now.
            if (c && !settleCapture(c) && c.ok) send(captureReleaseCommand(c.id))
            const warm = c ? undefined : parseCaptureWarmLine(l)
            if (warm) pttLog(`capture warm-up ${warm.ok ? 'ok' : 'failed'} ${warm.ms} ms`)
            continue
          }
          if (ev.type === 'ready') pttLog(`ready stt=${ev.stt} locale=${ev.locale} chord=${ev.chord}`)
          else if (ev.type === 'perm') pttLog(`perm mic=${ev.mic} input=${ev.input} assets=${ev.assets ?? '?'}`)
          else if (ev.type === 'error') pttLog(`error ${ev.code}: ${ev.message}`)
          else if (ev.type === 'cancelled') pttLog(`cancelled ${ev.reason}`)
          else if (ev.type === 'ptt') pttLog(`ptt ${ev.state}`)
          else if (ev.type === 'listening' || ev.type === 'final') pttLog(ev.type)
          if (ev.type === 'ready') {
            // Once per helper process: a config line makes the helper re-check its speech engine, and a second ready
            // answering a second config would be a loop.
            if (!configured) {
              configured = true
              sendConfig()
            }
            lastTerms = ''
            pushContext()
          }
          if (ev.type === 'perm' && pendingInput) {
            clearTimeout(pendingInput)
            pendingInput = undefined
            if (ev.input !== 'granted') void ask('input')
          }
          apply(ev)
          if (ev.type === 'ptt' && ev.state === 'down' && state.id === ev.id) ctx.broadcast('ptt:down', { id: ev.id })
          if (ev.type === 'listening' && state.id === ev.id) warm(ev.id)
          if (ev.type === 'ptt' && ev.state === 'up') up = { id: ev.id, at: Date.now() }
          if (ev.type === 'partial' && state.id === ev.id) ctx.broadcast('ptt:partial', { id: ev.id, text: ev.text })
          // Timed per hold: a final of an older hold that ends after a newer release must not log the new one's time.
          if ((ev.type === 'final' || ev.type === 'cancelled') && up?.id === ev.id) {
            if (ev.type === 'final') pttLog(`final ${Date.now() - up.at} ms after release`)
            up = undefined
          }
        }
      })
      p.stderr.on('data', () => undefined) // drained, never logged: it could hold what was said
      p.stdin.on('error', () => undefined)
      p.on('error', (err) => {
        console.warn('[ptt] helper error', err.message)
        pttLog(`helper error: ${err.message}`)
        // A spawn failure (no pid) never emits exit: take the same way out as a death.
        if (p.pid === undefined && child === p) {
          child = undefined
          apply({ type: 'exit' })
          again()
        }
      })
      p.on('exit', (code, signal) => {
        pttLog(`helper exited code=${code ?? '-'} signal=${signal ?? '-'} after ${Date.now() - startedAt} ms`)
        if (child !== p) return
        child = undefined
        buf.reset()
        for (const id of [...captures.keys()]) settleCapture({ ok: false, id, error: 'unavailable', message: 'The helper stopped.' })
        apply({ type: 'exit' })
        if (Date.now() - startedAt > HEALTHY_MS) failures = 0
        again()
      })
      sendConfig()
    }
    const again = (): void => {
      if (quitting || respawn) return
      if (failures >= GIVE_UP_AFTER) return console.warn('[ptt] the helper keeps dying; push to talk stays off for this run')
      const wait = backoffMs(failures++)
      respawn = setTimeout(() => {
        respawn = undefined
        start()
      }, wait)
    }

    // ---- what to teach the recognizer: the lesson and step in front of the learner ----
    let lessonTitle = ''
    let stepTitle = ''
    let concepts: string[] = []
    let libraries: string[] = []
    const pushContext = (): void => {
      const terms = contextTerms({ lessonTitle, stepTitle, concepts, libraries })
      const key = terms.join('\u0001')
      if (key === lastTerms) return
      lastTerms = key
      send(contextCommand(terms))
    }
    ctx.engine.onEvent((e) => {
      if (e.type === 'lesson.ready') {
        lessonTitle = e.payload.lesson.title
        stepTitle = ''
        concepts = [...(e.payload.lesson.primer ?? []).map((p) => p.title), ...(e.payload.lesson.prerequisites ?? []).map((p) => p.title)]
        libraries = (e.payload.lesson.primer ?? []).flatMap((p) => libraryNames(p.code ?? ''))
      } else if (e.type === 'step.started') {
        stepTitle = e.payload.title
        concepts = [...concepts.slice(0, 20), ...(e.payload.concepts ?? [])]
        libraries = [...libraries, ...libraryNames(e.payload.code ?? ''), ...libraryNames(e.payload.instructions ?? '')]
      } else if (e.type === 'lesson.ended') {
        lessonTitle = stepTitle = ''
        concepts = libraries = []
      } else return
      pushContext()
    })

    // ---- the renderer's side ----
    ctx.handle('ptt:get', () => state)
    ctx.handle('ptt:config', (raw) => {
      const next = sanitizePrefs({ ptt: raw }).ptt
      if (!next) return false
      prefs = next
      sendConfig()
      return true
    })
    /** Ask for one permission. A grant that reads denied is usually this build's stale row (ad-hoc signing) or an old
     *  "No": clear miyagi's row first so macOS asks for real instead of silently answering no. */
    const ask = async (which: 'mic' | 'input'): Promise<void> => {
      const denied = which === 'input' ? state.perms.input === 'denied' : state.perms.mic === 'denied'
      if (denied) await resetGrant(which)
      pttLog(`asking for ${which}${denied ? ' (after reset)' : ''}`)
      send(permissionsCommand(which))
    }
    ctx.handle('ptt:allow', async (which) => {
      if (which === 'mic' || which === 'input') return void (await ask(which))
      if (which !== 'both') return
      // mic first; input after the answer (the next perm event) so two system prompts never stack.
      await ask('mic')
      clearTimeout(pendingInput)
      pendingInput = setTimeout(() => {
        pendingInput = undefined
        void ask('input')
      }, PROMPT_GAP_MS)
    })
    ctx.handle('ptt:open-settings', (kind) => openPttSettings(kind))
    ctx.handle('ptt:cancel', () => {
      if (!active(state)) return false
      send(CANCEL_COMMAND)
      apply({ type: 'reset' })
      return true
    })
    // ---- circle to ask: one region of the screen, captured by the helper while the keys are held ----
    // Never logs pixels or paths: only the size and the time.
    let captureSeq = 0
    const captures = new Map<string, { done: (r: CaptureResult) => void; timer: ReturnType<typeof setTimeout>; at: number }>()
    /** Ids answered ok, so the overlay can release one it no longer needs (a newer stroke, the hold cancelled). */
    const issued: string[] = []
    /** Hand the answer to its waiting invoke. false = nobody is waiting any more (it timed out). */
    function settleCapture(r: CaptureResult): boolean {
      const p = captures.get(r.id)
      if (!p) return false
      captures.delete(r.id)
      clearTimeout(p.timer)
      pttLog(captureLogLine(r, Date.now() - p.at)) // the helper's ms and the round trip: the 150 to 400 ms budget, measured
      if (r.ok) {
        issued.push(r.id)
        if (issued.length > 16) issued.shift()
      }
      p.done(r)
      return true
    }
    /** Only the overlay's own page asks (the circle lives there): no other window can make the helper read the screen. */
    const fromOverlay = (e: IpcMainInvokeEvent): boolean =>
      !ctx.overlay.isDestroyed() && e.sender === ctx.overlay.webContents && !!e.senderFrame && e.senderFrame === e.sender.mainFrame
    // Not ctx.handle: that one hides the sender, and this needs to know it is the overlay (Core request).
    ipcMain.handle('feat:ptt:capture', (e, raw): Promise<CaptureResult> => {
      if (!fromOverlay(e)) throw new Error('untrusted sender')
      const id = `cap-${++captureSeq}`
      const req = captureRequest(raw)
      if (!req) return Promise.resolve({ ok: false, id, error: 'bad_request', message: 'Not a screen region.' })
      const no = captureAdmit(captures.size, !!child && child.stdin.writable)
      if (no === 'unavailable') return Promise.resolve({ ok: false, id, error: no, message: 'The helper is not running.' })
      if (no === 'busy') return Promise.resolve({ ok: false, id, error: no, message: 'A capture is already on its way.' })
      return new Promise((done) => {
        const timer = setTimeout(() => {
          settleCapture({ ok: false, id, error: 'timeout', message: 'The capture took too long.' })
          send(captureReleaseCommand(id)) // a late file is deleted on arrival, never left in the temp folder
        }, CAPTURE_TIMEOUT_MS)
        captures.set(id, { done, timer, at: Date.now() })
        send(captureCommand(id, req))
      })
    })
    /** The overlay is done with a capture it will not send (a newer stroke, a cancelled hold): delete it now. */
    ipcMain.handle('feat:ptt:capture-release', (e, id): boolean => {
      if (!fromOverlay(e)) throw new Error('untrusted sender')
      if (!isCaptureId(id) || !issued.includes(id)) return false
      issued.splice(issued.indexOf(id), 1)
      send(captureReleaseCommand(id))
      return true
    })
    ctx.handle('ptt:prefill', (text) => {
      if (typeof text !== 'string' || !text.trim() || text.length > 2000) return false
      prefill = { text: text.trim(), at: Date.now() }
      ctx.broadcast('ptt:prefill', prefill.text)
      return true
    })
    ctx.handle('ptt:prefill-take', () => {
      const p = prefill
      prefill = undefined
      return p && Date.now() - p.at < PREFILL_TTL_MS ? p.text : null
    })

    app.on('before-quit', () => {
      quitting = true
      clearTimeout(respawn)
      clearTimeout(capTimer)
      clearTimeout(errTimer)
      send(QUIT_COMMAND)
      try {
        child?.stdin.end()
      } catch {
        /* already closed */
      }
    })
    // No orphan: if the app is going down by any route, the helper (mic, key tap) goes with it. It also exits by itself
    // when its stdin closes, which covers the app being killed outright.
    app.on('will-quit', () => {
      try {
        child?.kill('SIGTERM')
      } catch {
        /* already gone */
      }
    })
    start()
  }
})
