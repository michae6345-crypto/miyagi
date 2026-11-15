/**
 * Presenter keys for a Demo lesson (the launcher's "Demo" chip: learn {mode:"demo"}, the engine's stage.py).
 *
 * While a Demo lesson runs, three global keys drive it from anywhere (no window needs focus):
 *   ⌃⌥⌘→  next      pass the current step now (a run step gets its recorded good run first)
 *   ⌃⌥⌘←  back      the step before
 *   ⌃⌥⌘R  restart   step 1 again, with a clean nn.py
 * (Windows: Ctrl+Alt+Shift instead of ⌃⌥⌘.) They POST the engine's /stage/<cmd> (HTTP, same port as its socket).
 *
 * They exist only during a Demo lesson: on every lesson.ready main asks the engine (GET /stage) whether this one
 * is a Demo, binds the keys if so, and lets them go on lesson.ended or a lesson that isn't one. Nothing on screen
 * mentions them.
 *
 * UNVERIFIED in Electron (typechecked on Windows, where Smart App Control blocks electron.exe). Check on the Mac.
 */
import { globalShortcut } from 'electron'
import { defineMainFeature } from '../context'

const isMac = process.platform === 'darwin'
const MOD = isMac ? 'Control+Alt+Command' : 'Control+Alt+Shift'
const KEYS = { next: `${MOD}+Right`, back: `${MOD}+Left`, restart: `${MOD}+R` } as const
type Cmd = keyof typeof KEYS

/** The engine's HTTP origin: ENGINE_URL (ws://host:port) with http. The app's mock engine (DEMO=1) has none. */
function engineHttp(): string | undefined {
  if (process.env.DEMO === '1') return undefined
  try {
    const u = new URL(process.env.ENGINE_URL ?? 'ws://localhost:8787')
    u.protocol = u.protocol === 'wss:' ? 'https:' : 'http:'
    u.pathname = ''
    return u.origin
  } catch {
    return undefined
  }
}

export default defineMainFeature({
  id: 'presenter',
  setup(ctx) {
    const base = engineHttp()
    if (!base) return
    let bound = false

    const call = (cmd: Cmd): void => {
      void fetch(`${base}/stage/${cmd}`, { method: 'POST' }).catch(() => undefined)
    }
    const bind = (): void => {
      if (bound) return
      bound = true
      for (const cmd of Object.keys(KEYS) as Cmd[]) {
        if (!globalShortcut.register(KEYS[cmd], () => call(cmd))) console.warn(`[presenter] ${KEYS[cmd]} is taken`)
      }
    }
    const release = (): void => {
      if (!bound) return
      bound = false
      for (const key of Object.values(KEYS)) globalShortcut.unregister(key)
    }
    /** Is the lesson that just started a Demo lesson? */
    const check = async (): Promise<void> => {
      try {
        const r = await fetch(`${base}/stage`, { signal: AbortSignal.timeout(2000) })
        const s = (await r.json()) as { on?: boolean }
        if (s.on) bind()
        else release()
      } catch {
        release()
      }
    }

    ctx.engine.onEvent((e) => {
      if (e.type === 'lesson.ready') void check()
      else if (e.type === 'lesson.ended') release()
    })
  }
})
