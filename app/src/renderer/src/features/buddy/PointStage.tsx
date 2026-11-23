/**
 * Feature: buddy. Try the buddy, only in the browser stage with ?buddy=point (index.tsx). Not an app window.
 * A strip of controls over the stage's fake desktop. Everything it does goes through what the app really uses: marks
 * are `annotate` events sent through the bus (as the engine sends them), and the talking drives talk.ts (as push to
 * talk and the engine's status do).
 *   One / Far      the coach points at one thing
 *   Tour           three things, one at a time, with Next
 *   Clear          the engine's { clear: true }
 *   Hold to talk   hold it: the buddy comes to the pointer and listens; let go: it thinks, then answers
 *   the ask box    type a question about the fake screen and press Enter: the same, typed
 *   a click anywhere on the desktop points there
 * The answers are canned (ANSWERS): this is a stand-in for the engine, so the back and forth can be seen. A mark
 * that faded stays gone for its step even when re-sent (pointing.ts), so every press sends its marks under fresh ids.
 */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { STAGE } from '../../bridge'
import { dispatch } from '../../core/bus'
import { contains, grow } from '../../core/geometry'
import { color, fill, radius, text } from '../../core/theme'
import { REACH, type AnnotatePayload, type Mark } from './marks'
import { usePointing } from './pointing'
import { say, sendHome, setActivity, setResponder, summon } from './talk'

/** Send it the way the engine does, through the bus, so whichever layer draws `annotate` gets it. The cast goes with the contract. */
const annotate = (payload: AnnotatePayload): void => dispatch({ type: 'annotate', payload } as never)

/** Where the strip sits in the stage: bottom left, above the Dock. */
export const POINT_STAGE = { x: 20, y: Math.round(STAGE.height * 0.855), w: 760, h: 40 }

/** Share-of-the-stage rects, so everything lands in the same places at any ?size. */
const at = (x: number, y: number, w: number, h: number): Pick<Mark, 'x' | 'y' | 'w' | 'h'> => ({ x: Math.round(x * STAGE.width), y: Math.round(y * STAGE.height), w: Math.round(w * STAGE.width), h: Math.round(h * STAGE.height) })

const SPOT = {
  imports: at(0.064, 0.136, 0.1, 0.034),
  model: at(0.064, 0.224, 0.31, 0.125),
  optimizer: at(0.0625, 0.563, 0.2375, 0.018),
  rate: at(0.2615, 0.563, 0.0385, 0.018),
  loss: at(0.044, 0.714, 0.2625, 0.085),
  equation: at(0.54, 0.268, 0.118, 0.04),
  corner: at(0.9, 0.86, 0.06, 0.03)
}

/** `n`: this press's number, so its marks are new ones. */
const PRESETS: { name: string; payload: (n: number) => AnnotatePayload }[] = [
  { name: 'One', payload: (n) => ({ marks: [{ id: `line-${n}`, ...SPOT.optimizer, why: 'point', label: 'The optimizer' }], holdMs: 9000 }) },
  {
    name: 'Tour',
    payload: (n) => ({
      marks: [
        { id: `t1-${n}`, ...SPOT.imports, why: 'point', label: 'Start with the imports' },
        { id: `t2-${n}`, ...SPOT.model, why: 'point', label: 'Then build the model' },
        { id: `t3-${n}`, ...SPOT.optimizer, why: 'point', label: 'Then set the optimizer' }
      ],
      holdMs: 30000
    })
  },
  { name: 'Far', payload: (n) => ({ marks: [{ id: `far-${n}`, ...SPOT.corner, why: 'point', label: 'Down here' }], holdMs: 9000 }) },
  { name: 'Clear', payload: () => ({ clear: true }) }
]

/** The stand-in engine's answers: the first whose words are in the question. `where`: what it points at. */
const ANSWERS: { words: string[]; where?: keyof typeof SPOT; label?: string; says: string; more: string }[] = [
  { words: ['learning rate', ' lr', 'rate'], where: 'rate', label: 'Learning rate', says: 'The learning rate is set right here.', more: 'Smaller is steadier but slower. Try 1e-4 if the loss jumps around.' },
  { words: ['loss', 'training', 'epoch'], where: 'loss', label: 'The loss', says: 'The loss falls each epoch. Read down this column.', more: 'It should keep falling. If it stops early, the model is stuck.' },
  { words: ['equation', 'video', 'convection'], where: 'equation', label: 'The equation', says: 'This is the equation the video is solving.', more: 'The network learns u so that this stays true everywhere.' },
  { words: ['model', 'layer', 'network', 'mlp'], where: 'model', label: 'The model', says: 'The model is built here, layer by layer.', more: 'Each layer is a Linear and a Tanh. The last one has no Tanh.' },
  { words: ['optimizer', 'adam'], where: 'optimizer', label: 'The optimizer', says: 'Adam takes the steps. It is set on this line.', more: 'It reads the gradients and moves every weight a little.' }
]
const UNSURE = 'Ask me where something is. Try the learning rate.'
/** What the Hold to talk button "hears", a word at a time. */
const SPOKEN = 'where do I set the learning rate'

const chip: CSSProperties = { background: fill.chip, border: `1px solid ${fill.chipBorder}`, borderRadius: radius.chip, color: fill.chipText, cursor: 'pointer', padding: '3px 10px', fontWeight: 500, whiteSpace: 'nowrap' }

export function PointStage(): ReactNode {
  const strip = useRef<HTMLDivElement>(null)
  const count = usePointing((s) => s.marks.length)
  const presses = useRef(0)
  const [question, setQuestion] = useState('')
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const later = (ms: number, fn: () => void): void => {
    timers.current.push(setTimeout(fn, ms))
  }

  /** The stand-in engine answers a question: it thinks a moment, then points and says. */
  const answer = (q: string): void => {
    const found = ANSWERS.find((a) => a.words.some((w) => ` ${q.toLowerCase()} `.includes(w)))
    setActivity('thinking')
    later(950, () => {
      setActivity('idle')
      if (!found?.where) return say(found?.says ?? UNSURE)
      const id = `ans-${++presses.current}`
      annotate({ marks: [{ id, ...SPOT[found.where], why: 'answer', label: found.label }], holdMs: 12000 })
      say(found.says, `id:${id}`)
    })
  }

  // The stand-in for Explain: it thinks, then says a little more about the mark it is at.
  useEffect(() => {
    setResponder((kind, key) => {
      if (kind !== 'explain') return false
      const label = usePointing.getState().marks.find((m) => m.key === key)?.label
      const more = ANSWERS.find((a) => a.label === label)?.more ?? 'This is the part this step is about. Change it and run the cell.'
      setActivity('thinking')
      later(900, () => {
        setActivity('idle')
        say(more, key)
      })
      return true
    })
    const pending = timers.current
    return () => {
      setResponder(undefined)
      pending.forEach(clearTimeout)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A press anywhere on the desktop: point there. A press inside a mark is the learner's click (the layer fades it).
  useEffect(() => {
    const down = (e: MouseEvent): void => {
      const el = strip.current
      if (!el || (e.target as Element | null)?.closest?.('[data-buddy-controls], [data-part="bubble"]')) return
      const box = el.getBoundingClientRect()
      if (!box.width) return
      const k = POINT_STAGE.w / box.width
      const p = { x: POINT_STAGE.x + (e.clientX - box.left) * k, y: POINT_STAGE.y + (e.clientY - box.top) * k }
      if (p.x < 0 || p.y < 0 || p.x > STAGE.width || p.y > STAGE.height) return
      if (usePointing.getState().marks.some((m) => contains(grow(m.rect, REACH.pad), p))) return
      annotate({ marks: [{ id: `press-${++presses.current}`, x: p.x - 70, y: p.y - 13, w: 140, h: 26, why: 'point', label: 'Here' }], holdMs: 9000 })
    }
    window.addEventListener('mousedown', down)
    return () => window.removeEventListener('mousedown', down)
  }, [])

  // Hold to talk: while it is held the buddy listens and "hears" a question a word at a time; let go and it answers.
  const hearing = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const talkDown = (): void => {
    const all = SPOKEN.split(' ')
    let n = 0
    summon()
    setActivity('listening', '')
    clearInterval(hearing.current)
    hearing.current = setInterval(() => {
      n = Math.min(all.length, n + 1)
      setActivity('listening', all.slice(0, n).join(' '))
    }, 230)
  }
  const talkUp = (): void => {
    if (!hearing.current) return
    clearInterval(hearing.current)
    hearing.current = undefined
    answer(SPOKEN)
  }

  return (
    <div
      ref={strip}
      data-hit
      data-buddy-controls
      data-theme="dark"
      className="absolute inset-0 flex items-center gap-[6px] px-[10px]"
      style={{ background: color.island, borderRadius: radius.chip, color: color.text, fontSize: text.xs }}
    >
      {PRESETS.map((p) => (
        <button key={p.name} data-preset={p.name} style={chip} onClick={() => annotate(p.payload(++presses.current))}>
          {p.name}
        </button>
      ))}
      <button data-preset="Home" style={chip} onClick={sendHome}>
        Home
      </button>
      <span style={{ width: 1, alignSelf: 'stretch', margin: '8px 4px', background: fill.rule }} />
      <button data-preset="Talk" style={chip} onMouseDown={talkDown} onMouseUp={talkUp} onMouseLeave={talkUp}>
        Hold to talk
      </button>
      <form
        className="flex min-w-0 flex-1"
        onSubmit={(e) => {
          e.preventDefault()
          const q = question.trim()
          if (!q) return
          setQuestion('')
          summon()
          answer(q)
        }}
      >
        <input
          data-part="buddy-ask"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="ask about this screen"
          className="min-w-0 flex-1 outline-none"
          style={{ background: fill.field, border: `1px solid ${fill.fieldBorder}`, borderRadius: radius.chip, color: color.text, padding: '4px 11px', fontSize: text.xs }}
          data-count={count}
        />
      </form>
    </div>
  )
}
