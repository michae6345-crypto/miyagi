/**
 * Feature: drawer. Where the live network panel is: docked in the drawer, or floating over the screen at one of the
 * four corners (Michael, Sun 2:57 AM: "make it so I can drag this around and move it, and it moves smoothly").
 * Remembered per lesson, so the next network push in the same lesson lands where the learner left it.
 */
import { create } from 'zustand'
import { useLesson } from '../../core/lesson'

export type Corner = 'tl' | 'tr' | 'bl' | 'br'
export type Spot = { floating: false } | { floating: true; corner: Corner }

/** The pointer and panel geometry at the moment a drag pulled the panel out of the drawer. */
export type Pickup = { pointerX: number; pointerY: number; x: number; y: number; w: number }

type NetFloat = {
  spot: Spot
  /** Set while a drag that started in the drawer is being handed to the floating card. */
  pickup?: Pickup
  /** The drawer's "Network · floating" row, in overlay coordinates: where a dock animates to. */
  dockAt?: { x: number; y: number }
}

const KEY = 'miyagi.netSpot'
function load(): Record<string, Spot> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, Spot>
  } catch {
    return {}
  }
}
const remembered: Record<string, Spot> = load()
const lessonKey = (): string => useLesson.getState().lesson?.id ?? ''

export const useNetFloat = create<NetFloat>(() => ({ spot: remembered[lessonKey()] ?? { floating: false } }))

function save(spot: Spot): void {
  const k = lessonKey()
  if (!k) return
  remembered[k] = spot
  try {
    localStorage.setItem(KEY, JSON.stringify(remembered))
  } catch {
    // Storage blocked: the spot still holds for this session.
  }
}

export function popOut(pickup: Pickup): void {
  useNetFloat.setState({ pickup })
}

export function settle(corner: Corner): void {
  const spot: Spot = { floating: true, corner }
  save(spot)
  useNetFloat.setState({ spot, pickup: undefined })
}

export function dock(): void {
  const spot: Spot = { floating: false }
  save(spot)
  useNetFloat.setState({ spot, pickup: undefined })
}

export function setDockAt(at: { x: number; y: number } | undefined): void {
  const cur = useNetFloat.getState().dockAt
  if (cur?.x === at?.x && cur?.y === at?.y) return
  useNetFloat.setState({ dockAt: at })
}

// A new lesson: its own remembered spot (docked by default).
let lastLesson = lessonKey()
useLesson.subscribe((s) => {
  const k = s.lesson?.id ?? ''
  if (k === lastLesson) return
  lastLesson = k
  useNetFloat.setState({ spot: remembered[k] ?? { floating: false }, pickup: undefined })
})
