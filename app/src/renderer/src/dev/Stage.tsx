/**
 * `npm run dev:web`: the overlay + every feature window over a fake Mac desktop (mockup 01 with the
 * pill painted out), at the mockups' exact 1600×1000 coordinates, scaled to fit the browser.
 *
 * Keys: Ctrl+K / Ctrl+Shift+Space / Alt+Space → launcher · Alt+E/D/S/H/V, Alt+← → shortcuts · Esc → dismiss
 * URL:  ?scenario=<name> (any mock/scenarios/*.json; default full) · ?engine=socket (use ws://localhost:8787,
 *       or ?engine=ws://host:port) · ?os=win · ?clean (hide the dev HUD) · #/launcher (open on load)
 *       v2: ?size=1440x900 (the stage's size; the v2 mockups are 1440×900) · ?window=<route> (open an app window:
 *       onboarding, library, progress, account; &id= / &view= / &section= become its args) · ?perm=accessibility-off
 *       (permissions:get, see bridge.ts) · ?engine-local=external
 *
 * Backdrop (audit A24): the mockup desktop has a Dock, so the overlay's work area ends above it (the bar sits 24px
 * over the Dock, as on a Mac). A text lesson ("Just teach me", lesson.mode "lesson") is no video tutorial: the editor
 * is full screen, so the stage drops the mockup's tutorial for a plain neutral backdrop with no Dock.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { RotateCcw } from 'lucide-react'
import { devReset } from '../../../common/wire'
import desktop from './desktop.png'
import { bridge, engineMode, STAGE } from '../bridge'
import { emitUi } from '../core/bus'
import { useLesson } from '../core/lesson'
import { brand, color, fill, radius2, surface, windowSize } from '../core/theme'
import type { Layout } from '../../../preload/api'
import { getAppWindows, getFeatureWindows } from '../core/registry'
import { triggerShortcut, type ActionShortcut } from '../core/shortcuts'
import { Overlay } from '../core/Overlay'

const KEYMAP: Record<string, ActionShortcut> = { ArrowLeft: 'back', KeyE: 'explain', KeyD: 'diagram', KeyS: 'show_me', KeyH: 'hint', KeyV: 'voice_toggle' }

/** Top of the Dock in desktop.png (its tiles start at 921), less a few px of margin, like a Mac's workArea. Scaled with ?size. */
const DOCK_TOP = Math.round((916 / 1000) * STAGE.height)
/** The overlay over the mockup desktop: its work area stops above the Dock. */
const DESKTOP: Layout = { ...STAGE, workArea: { ...STAGE.workArea, height: DOCK_TOP - STAGE.workArea.y } }

export function Stage({ openLauncher = false }: { openLauncher?: boolean }): ReactNode {
  const [scale, setScale] = useState(1)
  // A text lesson isn't the mockup's video tutorial: neutral backdrop, full-screen editor (no Dock).
  const neutral = useLesson((s) => s.lesson?.mode === 'lesson')

  useEffect(() => {
    const fit = (): void => setScale(Math.min(innerWidth / STAGE.width, innerHeight / STAGE.height))
    fit()
    addEventListener('resize', fit)
    return () => removeEventListener('resize', fit)
  }, [])

  // #/launcher: open it once. StrictMode runs this effect twice in dev, so the first timer must be cleared, or the
  // two toggles open and close it again (agents/launcher.md, Core request 9).
  useEffect(() => {
    if (!openLauncher) return
    const t = setTimeout(() => bridge.emit('launcher:toggle'), 300)
    return () => clearTimeout(t)
  }, [openLauncher])

  // Browser stand-ins for the global shortcuts main registers in Electron.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const launcher = ((e.ctrlKey || e.metaKey) && e.code === 'KeyK') || (e.altKey && e.code === 'Space') || (e.ctrlKey && e.shiftKey && e.code === 'Space')
      if (launcher) {
        e.preventDefault()
        return bridge.emit('launcher:toggle')
      }
      if (e.altKey && KEYMAP[e.code] && useLesson.getState().lesson) {
        e.preventDefault()
        return triggerShortcut(KEYMAP[e.code])
      }
      if (e.key === 'Escape') emitUi('dismiss')
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  const windows = getFeatureWindows().filter((w) => w.stage && w.kind !== 'app').sort((a, b) => (a.z ?? 0) - (b.z ?? 0))

  return (
    <div className="fixed inset-0 overflow-hidden bg-[#08080b]">
      <div className="absolute left-1/2 top-1/2 overflow-hidden" style={{ width: STAGE.width, height: STAGE.height, transform: `translate(-50%,-50%) scale(${scale})` }}>
        {neutral ? (
          <div className="absolute inset-0" style={{ background: brand.ink }} data-backdrop="neutral" />
        ) : (
          <img src={desktop} draggable={false} className="absolute inset-0 h-full w-full select-none" data-backdrop="desktop" />
        )}
        <Overlay layout={neutral ? STAGE : DESKTOP} />
        <AppWindows />
        {windows.map(({ route, Component, stage }) =>
          stage === 'fill' ? (
            <Component key={route} layout={STAGE} />
          ) : (
            <div key={route} className="absolute overflow-hidden" style={{ left: stage!.x, top: stage!.y, width: stage!.w, height: stage!.h }}>
              <Component layout={{ origin: { x: stage!.x, y: stage!.y }, width: stage!.w, height: stage!.h, workArea: { x: 0, y: 0, width: stage!.w, height: stage!.h } }} />
            </div>
          )
        )}
      </div>
      {!new URLSearchParams(location.search).has('clean') && <DevHud />}
    </div>
  )
}

/**
 * v2 (W0-4): app windows (FeatureWindow kind 'app': Onboarding, Library, Progress, Account) over the stage, centered at
 * their size, as macOS would show a new window. ?window=<route> opens one on load; core/surfaces.ts opens and closes
 * them (bridge.ts stands in for main/appWindows.ts). The traffic lights are neutral dots here (OS chrome, not ours).
 */
function AppWindows(): ReactNode {
  const [open, setOpen] = useState<string[]>([])
  useEffect(() => {
    bridge
      .invoke<string[]>('window:stage-list')
      .then((l) => setOpen(Array.isArray(l) ? l : []))
      .catch(() => undefined)
    return bridge.onFeature('window:stage', (p) => {
      const { route, open: on } = (p ?? {}) as { route?: string; open?: boolean }
      if (!route) return
      setOpen((list) => (on ? [...list.filter((r) => r !== route), route] : list.filter((r) => r !== route)))
    })
  }, [])
  const all = getAppWindows()
  return (
    <>
      {open.map((route, i) => {
        const win = all.find((w) => w.route === route)
        if (!win) return null
        const sized = (windowSize as Record<string, { w: number; h: number } | undefined>)[route]
        const w = Math.min(win.size?.w ?? sized?.w ?? 960, STAGE.width - 32)
        const h = Math.min(win.size?.h ?? sized?.h ?? 640, STAGE.height - 64)
        const x = Math.round((STAGE.width - w) / 2) + i * 24
        const y = Math.round(STAGE.workArea.y + (STAGE.height - STAGE.workArea.y - h) / 2) + i * 24
        const { Component } = win
        return (
          <div
            key={route}
            data-kind="app"
            data-app-window={route}
            className="absolute overflow-hidden"
            style={{ left: x, top: y, width: w, height: h, zIndex: 100 + i, background: color.window, borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${fill.hairline}, ${surface.shadow}` }}
          >
            <div className="pointer-events-none absolute left-[14px] top-[14px] z-10 flex gap-[8px]" aria-hidden>
              {[0, 1, 2].map((d) => (
                <span key={d} className="block h-[12px] w-[12px] rounded-full" style={{ background: fill.toggleOff }} />
              ))}
            </div>
            <Component layout={{ origin: { x, y }, width: w, height: h, workArea: { x: 0, y: 0, width: w, height: h } }} />
          </div>
        )
      })}
    </>
  )
}

function DevHud(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const seen = useLesson((s) => s.seen)
  const mode = engineMode()
  const keys = bridge.platform.keys
  const label = mode === 'inline' ? `inline mock · ${new URLSearchParams(location.search).get('scenario') ?? 'full'}` : mode === 'socket' ? 'engine socket' : 'electron'
  return (
    <div className="fixed bottom-3 left-3 flex max-w-[calc(100vw-24px)] items-center gap-2 rounded-full border border-white/10 bg-black/70 py-1 pl-3 pr-1 text-[12px] text-white/70 backdrop-blur">
      {/* Gray, like the pill's watching dot (green only means passed): filled when connected, a ring when not. */}
      <span className="h-[7px] w-[7px] shrink-0 rounded-full border" style={{ borderColor: brand.watching, background: connected ? brand.watching : fill.clear }} />
      <span className="shrink-0">{label}</span>
      <span className="truncate text-white/35">{seen ? `· sees ${seen.app}: ${seen.summary}` : `· ${keys.launcher} launcher · ${keys.diagram} diagram · Esc`}</span>
      <button
        className="ml-1 flex shrink-0 cursor-pointer items-center gap-1 rounded-full bg-white/10 px-2 py-[3px] hover:bg-white/20"
        onClick={() => {
          emitUi('reset')
          bridge.send(devReset)
        }}
      >
        <RotateCcw size={11} /> Reset
      </button>
    </div>
  )
}
