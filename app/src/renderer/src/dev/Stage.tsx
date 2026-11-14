/**
 * `npm run dev:web`: every screen over a fake Mac desktop (mockup 01 with the pill painted out),
 * at the mockups' exact 1600×1000 coordinates, scaled to fit the browser window.
 *
 * Keys: Ctrl+K / Ctrl+Shift+Space / Alt+Space → launcher · Alt+E/D/S/H/V, Alt+← → shortcuts · Esc → hide card
 * URL:  ?os=win (Windows labels) · ?scenario=happy|offtrack|full · ?engine=inline · ?clean (no dev HUD) · #/launcher (open on load)
 */
import { useEffect, useState, type ReactNode } from 'react'
import { RotateCcw } from 'lucide-react'
import { cmd, devReset } from '../../../common/wire'
import desktop from './desktop.png'
import { bridge, engineMode, STAGE } from '../bridge'
import { useLesson } from '../store'
import { Overlay } from '../overlay/Overlay'
import { Launcher } from '../launcher/Launcher'

const KEYMAP: Record<string, 'back' | 'explain' | 'diagram' | 'show_me' | 'hint' | 'voice_toggle'> = { ArrowLeft: 'back', KeyE: 'explain', KeyD: 'diagram', KeyS: 'show_me', KeyH: 'hint', KeyV: 'voice_toggle' }

export function Stage({ openLauncher = false }: { openLauncher?: boolean }): ReactNode {
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const fit = (): void => setScale(Math.min(innerWidth / STAGE.width, innerHeight / STAGE.height))
    fit()
    addEventListener('resize', fit)
    return () => removeEventListener('resize', fit)
  }, [])

  useEffect(() => {
    if (openLauncher) setTimeout(() => bridge.emit('launcher:toggle'), 300)
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
        bridge.send(cmd('action', { kind: KEYMAP[e.code] }))
        bridge.emit('shortcut', KEYMAP[e.code])
        return
      }
      if (e.key === 'Escape') useLesson.getState().closeCard()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="fixed inset-0 overflow-hidden bg-[#08080b]">
      <div
        className="absolute left-1/2 top-1/2 overflow-hidden"
        style={{ width: STAGE.width, height: STAGE.height, transform: `translate(-50%,-50%) scale(${scale})` }}
      >
        <img src={desktop} draggable={false} className="absolute inset-0 h-full w-full select-none" />
        <Overlay layout={STAGE} />
        <Launcher layout={STAGE} />
      </div>
      {!new URLSearchParams(location.search).has('clean') && <DevHud />}
    </div>
  )
}

function DevHud(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const mode = engineMode()
  const label = mode === 'inline' ? `inline mock · ${new URLSearchParams(location.search).get('scenario') ?? 'full'}` : mode === 'socket' ? 'ws://localhost:8787' : 'electron'
  return (
    <div className="fixed bottom-3 left-3 flex items-center gap-2 rounded-full border border-white/10 bg-black/70 py-1 pl-3 pr-1 text-[12px] text-white/70 backdrop-blur">
      <span className="h-[7px] w-[7px] rounded-full" style={{ background: connected ? '#30D158' : '#FFB020' }} />
      <span>{label}</span>
      <span className="text-white/35">· Ctrl+K launcher · Alt+D diagram · Esc</span>
      <button
        className="ml-1 flex cursor-pointer items-center gap-1 rounded-full bg-white/10 px-2 py-[3px] hover:bg-white/20"
        onClick={() => {
          useLesson.getState().reset()
          bridge.send(devReset)
        }}
      >
        <RotateCcw size={11} /> Reset
      </button>
    </div>
  )
}
