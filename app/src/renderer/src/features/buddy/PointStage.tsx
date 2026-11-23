/**
 * Feature: buddy. Try the pointing branch, only in the browser stage with ?buddy=point (index.tsx). Not an app window.
 * A small strip of presets over the stage's fake desktop, and a click anywhere on the desktop points there. Each one
 * calls the same annotate() the engine's event does, with the rects in stage (screen) points.
 *   One     one named mark on a line of code
 *   Two     two marks: the second forks off the first one's branch
 *   Answer  the mark a circle-to-ask answer names (why "answer"), unnamed
 *   Far     a mark in the far corner, the longest reach
 *   Clear   the engine's { clear: true }
 * A mark that faded stays gone for its step even when re-sent (pointing.ts), so every press here sends its marks
 * under fresh ids: each press is a new mark, and a preset can be played again and again.
 * The little tree in the strip is <Buddy />: it leans the way the branch went.
 */
import { useEffect, useRef, type ReactNode } from 'react'
import { STAGE } from '../../bridge'
import { contains, grow } from '../../core/geometry'
import { color, fill, radius, text } from '../../core/theme'
import { REACH, type AnnotatePayload, type Mark } from './marks'
import { annotate, usePointing } from './pointing'
import { Buddy } from './store'

/** Where the strip sits in the stage: bottom left, above the Dock. */
export const POINT_STAGE = { x: 20, y: Math.round(STAGE.height * 0.855), w: 468, h: 40 }

/** Share-of-the-stage rects, so the presets land in the same places at any ?size. */
const at = (x: number, y: number, w: number, h: number): Pick<Mark, 'x' | 'y' | 'w' | 'h'> => ({ x: Math.round(x * STAGE.width), y: Math.round(y * STAGE.height), w: Math.round(w * STAGE.width), h: Math.round(h * STAGE.height) })

/** `n`: this press's number, so its marks are new ones. */
const PRESETS: { name: string; payload: (n: number) => AnnotatePayload }[] = [
  { name: 'One', payload: (n) => ({ marks: [{ id: `line-${n}`, ...at(0.0625, 0.563, 0.2375, 0.018), why: 'point', label: 'The optimizer' }] }) },
  {
    name: 'Two',
    payload: (n) => ({
      marks: [
        { id: `line-${n}`, ...at(0.0625, 0.563, 0.2375, 0.018), why: 'point', label: 'Set here' },
        { id: `flag-${n}`, ...at(0.321, 0.474, 0.0975, 0.034), why: 'point', label: 'Used here' }
      ],
      holdMs: 7000
    })
  },
  { name: 'Answer', payload: (n) => ({ marks: [{ id: `answer-${n}`, ...at(0.044, 0.714, 0.2625, 0.085), why: 'answer', askId: `ask-${n}` }] }) },
  { name: 'Far', payload: (n) => ({ marks: [{ id: `far-${n}`, ...at(0.9, 0.86, 0.06, 0.03), why: 'point', label: 'Down here' }] }) },
  { name: 'Clear', payload: () => ({ clear: true }) }
]

export function PointStage(): ReactNode {
  const strip = useRef<HTMLDivElement>(null)
  const count = usePointing((s) => s.marks.length)
  const presses = useRef(0)

  // A press anywhere on the desktop: point there. A press inside a mark is the learner's click (the layer fades it).
  useEffect(() => {
    const down = (e: MouseEvent): void => {
      const el = strip.current
      if (!el || (e.target as Element | null)?.closest?.('[data-buddy-controls]')) return
      const box = el.getBoundingClientRect()
      if (!box.width) return
      const k = POINT_STAGE.w / box.width
      const p = { x: POINT_STAGE.x + (e.clientX - box.left) * k, y: POINT_STAGE.y + (e.clientY - box.top) * k }
      if (p.x < 0 || p.y < 0 || p.x > STAGE.width || p.y > STAGE.height) return
      if (usePointing.getState().marks.some((m) => contains(grow(m.rect, REACH.pad), p))) return
      annotate({ marks: [{ id: `press-${++presses.current}`, x: p.x - 70, y: p.y - 13, w: 140, h: 26, why: 'point', label: 'Here' }], holdMs: 8000 })
    }
    window.addEventListener('mousedown', down)
    return () => window.removeEventListener('mousedown', down)
  }, [])

  return (
    <div
      ref={strip}
      data-hit
      data-buddy-controls
      data-theme="dark"
      className="absolute inset-0 flex items-center gap-[6px] px-[10px]"
      style={{ background: color.island, borderRadius: radius.chip, color: color.text, fontSize: text.xs }}
    >
      <Buddy size={20} />
      {PRESETS.map((p) => (
        <button
          key={p.name}
          data-preset={p.name}
          className="cursor-pointer px-[10px] py-[3px] font-medium"
          style={{ background: fill.chip, border: `1px solid ${fill.chipBorder}`, borderRadius: radius.chip, color: fill.chipText }}
          onClick={() => annotate(p.payload(++presses.current))}
        >
          {p.name}
        </button>
      ))}
      <span className="ml-auto whitespace-nowrap pr-[2px]" style={{ color: color.faint }} data-count={count}>
        or click anywhere
      </span>
    </div>
  )
}
