/**
 * Feature: pill. The settings gear beside the pill (Michael, Sun ~7:20 AM: "in the top right there should be a small
 * settings icon where you can just put your API key… Why did that disappear?"). Its only other button is the overview
 * hover card's footer gear, and that card doesn't open in a "Just teach me" lesson with the drawer open, over a
 * spotlight hole, or outside a lesson. So: a small round button of the same black, just right of the pill, whenever
 * the island is pill-sized (idle, building, a step, a notice, hovered without a card). A click grows the Settings sheet
 * out of the island (settings:open, main/features/settings.ts).
 *
 * It's an overlay layer, not part of the pill's content: the island measures its content for its width and clips it,
 * so a gear inside would widen the pill and move the step title. Instead it follows the island's live rect (its width
 * spring, its slide aside for VS Code's quick-pick, the launcher / settings hiding it) and hides while a card is open.
 * Beside a quick-pick (screen.avoid) or the video panel (the player's dock) it takes the pill's other side rather
 * than cover them.
 * Chrome, not an option: neutral glyph (muted, white on hover), no pastel, no glow.
 */
import { Settings } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { useAvoid } from '../../core/islandPlace'
import { useLesson } from '../../core/lesson'
import { getIslandModes } from '../../core/registry'
import { color, pill, shadows } from '../../core/theme'
import { dockRect } from '../player/dock'
import { intersects, toLocal } from '../spotlight/place'

/** The button's diameter, centred on the pill's 34px row. */
const SIZE = 28
/** Air between the pill's edge and the gear. */
const GAP = 6
/** Frames with no change before the follow loop stops (it restarts on the island's next change). */
const STILL_FRAMES = 6
/** Fallback check for a move that left no style mutation (an animation run off the main thread). */
const CHECK_MS = 300

/**
 * A card (a mode with a width) holds the island without the pointer on it. Same question Island.tsx asks (its `held`),
 * so the gear drops its data-hit in the very commit the card opens: the card's placement (islandPlace.ts) reads the
 * overlay's other UI in that commit, and must not step around a gear that is about to go.
 */
function useCardOpen(): boolean {
  const modes = getIslandModes()
  const held = modes.map((m) => m.useActive(false)) // stable list → stable hook order (as in Island.tsx)
  const at = held.indexOf(true)
  return at >= 0 && modes[at].width !== undefined
}

type Spot = { x: number; y: number; visible: boolean }

/** Where the gear goes, from the island's rect in the overlay (layout px), or hidden. */
function spotFor(root: HTMLElement, layout: Layout): Spot | undefined {
  // The island: the element holding the live mode layer (only a present layer carries data-island-layer).
  const island = root.querySelector<HTMLElement>('[data-island-layer]')?.parentElement
  const box = root.getBoundingClientRect()
  if (!island || !box.width) return undefined
  const k = root.offsetWidth / box.width // undo the browser stage's CSS scale (1 in Electron)
  const r = island.getBoundingClientRect()
  const x = (r.left - box.left) * k
  const y = (r.top - box.top) * k
  const w = r.width * k
  const h = r.height * k
  // Pill-sized and not handed over to the launcher / settings (they set the island's opacity to 0).
  const visible = w > 0 && h <= pill.height + 1 && Number(island.style.opacity || 1) > 0.5
  const top = Math.round(y + (h - SIZE) / 2)
  const right = Math.round(x + w + GAP)
  const left = Math.round(x - GAP - SIZE)
  const avoid = useAvoid.getState().rects.map((a) => toLocal(a, layout.origin))
  // The video panel (test 10 judge review: the gear sat on its header, the pill grows with the step title). In
  // Electron it's its own window, so the overlay DOM can't see it: use the player's own dock math, like the spotlight
  // caption does. A "Just teach me" lesson has no player.
  const lesson = useLesson.getState().lesson
  if (lesson && lesson.mode !== 'lesson') {
    const d = dockRect(layout.workArea)
    avoid.push({ x: d.x, y: d.y, w: d.width, h: d.height })
  }
  const blocked = (gx: number): boolean =>
    gx < 0 || gx + SIZE > root.offsetWidth || avoid.some((a) => intersects({ x: gx, y: top, w: SIZE, h: SIZE }, a))
  return { x: blocked(right) && !blocked(left) ? left : right, y: top, visible }
}

export function PillGear({ layout }: { layout: Layout }): ReactNode {
  const holder = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const cardOpen = useCardOpen()
  const shown = visible && !cardOpen

  useEffect(() => {
    const el = holder.current
    const root = el?.parentElement // the overlay root
    if (!el || !root) return
    let raf = 0
    let still = 0
    let last = ''
    /** Move the gear onto the island's current rect; returns what it saw, to tell when the island has settled. */
    const apply = (): string => {
      const s = spotFor(root, layout)
      const key = s ? `${s.x},${s.y},${s.visible}` : 'none'
      if (key === last) return key
      // Hidden: hold the last spot (no sliding down a growing card while it fades out).
      if (s?.visible) el.style.transform = `translate(${s.x}px, ${s.y}px)`
      setVisible(!!s?.visible)
      return key
    }
    const frame = (): void => {
      raf = 0
      const key = apply()
      still = key === last ? still + 1 : 0
      last = key
      if (still < STILL_FRAMES) raf = requestAnimationFrame(frame)
    }
    const kick = (): void => {
      still = 0
      if (!raf) raf = requestAnimationFrame(frame)
    }
    kick()
    // The island springs its width, slides aside, hides and swaps modes through style / DOM changes: follow them.
    const mo = new MutationObserver((records) => {
      if (records.some((r) => !el.contains(r.target))) kick()
    })
    mo.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['style', 'data-island-layer'] })
    const offAvoid = useAvoid.subscribe(kick)
    const check = setInterval(() => {
      if (!raf) {
        const s = spotFor(root, layout)
        if ((s ? `${s.x},${s.y},${s.visible}` : 'none') !== last) kick()
      }
    }, CHECK_MS)
    addEventListener('resize', kick)
    return () => {
      cancelAnimationFrame(raf)
      mo.disconnect()
      offAvoid()
      clearInterval(check)
      removeEventListener('resize', kick)
    }
  }, [layout])

  return (
    <div ref={holder} className="pointer-events-none absolute left-0 top-0" style={{ width: SIZE, height: SIZE }} data-pill-gear>
      <motion.button
        type="button"
        // Only while it's there: hidden, it's neither clickable nor UI the engine's reader or a card should step around.
        data-hit={shown || undefined}
        aria-label="Settings"
        aria-hidden={!shown || undefined}
        tabIndex={shown ? 0 : -1}
        title="Settings"
        className="grid h-full w-full cursor-pointer place-items-center rounded-full"
        style={{ background: color.island, boxShadow: shadows.pill, color: color.label, pointerEvents: shown ? 'auto' : 'none' }}
        initial={false}
        animate={{ opacity: shown ? 1 : 0, scale: shown ? 1 : 0.85 }}
        whileHover={{ color: color.text }}
        whileTap={{ scale: 0.92 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        onClick={() => {
          bridge.invoke('settings:open').catch(() => {})
        }}
      >
        <Settings size={15} strokeWidth={1.8} />
      </motion.button>
    </div>
  )
}
