/** The full-screen, click-through overlay: dim + spotlight, the island, the shortcut bar. */
import { useEffect, useRef, type ReactNode } from 'react'
import type { Layout } from '../../../preload/api'
import { cmd } from '../../../common/wire'
import { bridge } from '../bridge'
import { useLesson, type Rect } from '../store'
import { Island } from './Island'
import { ShortcutBar } from './ShortcutBar'
import { Spotlight } from './Spotlight'

export function Overlay({ layout }: { layout: Layout }): ReactNode {
  const root = useRef<HTMLDivElement>(null)
  const sp = useLesson((s) => s.spotlight)
  // Engine rects are in screen points; this window starts at layout.origin.
  const rect: Rect | undefined = sp && { x: sp.rect.x - layout.origin.x, y: sp.rect.y - layout.origin.y, w: sp.rect.w, h: sp.rect.h }
  const barBottom = layout.height - (layout.workArea.y + layout.workArea.height) + 24
  useVoice()
  useReportBounds(root, layout)
  return (
    <div ref={root} className="absolute inset-0 overflow-hidden" style={{ width: layout.width, height: layout.height }}>
      <Spotlight rect={rect} screenW={layout.width} />
      <Island top={bridge.platform.pillTop} />
      <ShortcutBar bottom={barBottom} />
    </div>
  )
}

/**
 * Tell the engine where our own UI is (`overlay.bounds`, screen points) so its screen reader
 * ignores the pill, cards, caption and bar. Sampled every 300ms while anything is visible;
 * sent only when it changes. Elements opt in with data-hit (interactive) or data-ui (display only).
 */
function useReportBounds(root: React.RefObject<HTMLDivElement | null>, layout: Layout): void {
  useEffect(() => {
    let last = ''
    const tick = (): void => {
      const el = root.current
      if (!el) return
      const box = el.getBoundingClientRect()
      if (!box.width) return
      const k = layout.width / box.width // undo the browser stage's CSS scale (1 in Electron)
      const rects = Array.from(el.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .map((n) => n.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1)
        .map((r) => ({
          x: Math.round((r.left - box.left) * k + layout.origin.x),
          y: Math.round((r.top - box.top) * k + layout.origin.y),
          w: Math.round(r.width * k),
          h: Math.round(r.height * k)
        }))
      const key = JSON.stringify(rects)
      if (key === last) return
      last = key
      bridge.send(cmd('overlay.bounds', { rects }))
    }
    const id = setInterval(tick, 300)
    return () => clearInterval(id)
  }, [root, layout])
}

/**
 * Electron only: the window ignores the mouse (clicks fall through to the app below) except while
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
