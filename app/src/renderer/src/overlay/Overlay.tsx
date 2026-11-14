/** The full-screen, click-through overlay: dim + spotlight, the island, the shortcut bar. */
import { useEffect, useRef, type ReactNode } from 'react'
import type { SpotlightTarget as SpotlightEvent } from '../store'
import type { Rect } from '../../../main/platform'
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { useLesson } from '../store'
import { Island } from './Island'
import { ShortcutBar } from './ShortcutBar'
import { Spotlight } from './Spotlight'

export function Overlay({ layout, spotlightRect }: { layout: Layout; spotlightRect?: (sp: SpotlightEvent) => Rect | undefined }): ReactNode {
  const sp = useLesson((s) => s.spotlight)
  const rect = sp && spotlightRect ? spotlightRect(sp) : undefined
  const barBottom = layout.height - (layout.workArea.y + layout.workArea.height) + 24
  useVoice()
  return (
    <div className="absolute inset-0 overflow-hidden" style={{ width: layout.width, height: layout.height }}>
      <Spotlight rect={rect} screenW={layout.width} />
      <Island top={bridge.platform.pillTop} />
      <ShortcutBar bottom={barBottom} />
    </div>
  )
}

/**
 * Electron only: the window ignores the mouse (clicks fall through to VS Code) except while
 * the cursor is over something marked data-hit. Mouse moves are still forwarded, so we can tell.
 */
export function useClickThrough(): void {
  useEffect(() => {
    let on = false
    const set = (hit: boolean): void => {
      if (hit === on) return
      on = hit
      bridge.emit('overlay:interactive', hit)
    }
    const move = (e: MouseEvent): void => set(!!(e.target as Element | null)?.closest?.('[data-hit]'))
    const out = (): void => set(false)
    window.addEventListener('mousemove', move)
    document.addEventListener('mouseleave', out)
    return () => {
      window.removeEventListener('mousemove', move)
      document.removeEventListener('mouseleave', out)
    }
  }, [])
}

/** Play `speak` audio when voice is on. (ElevenLabs URLs come from the engine.) */
function useVoice(): void {
  const last = useLesson((s) => s.lastSpeak)
  const voiceOn = useLesson((s) => s.voiceOn)
  const audio = useRef<HTMLAudioElement>(undefined)
  useEffect(() => {
    if (!last || !voiceOn) return
    audio.current?.pause()
    const a = new Audio(last.url)
    audio.current = a
    a.onended = () => useLesson.setState({ lastSpeak: undefined })
    a.play().catch(() => useLesson.setState({ lastSpeak: undefined }))
  }, [last, voiceOn])
  useEffect(() => {
    if (!voiceOn) audio.current?.pause()
  }, [voiceOn])
}
