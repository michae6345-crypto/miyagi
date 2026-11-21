/**
 * Feature: drawer. Mockup 02, the concept panel: a concept chip in the current step collapses the drawer to a step
 * rail on the right edge and opens a ~560px panel beside it with
 *   - the concept's definition (lesson.primer body),
 *   - a picture made on demand (action {kind:"diagram", text:"<concept title>"}; diagrams/store keeps the answer
 *     for this panel instead of opening it on the island),
 *   - the example (primer code, with Copy),
 *   - "Check my understanding": there's no quiz field in the contract, so it asks miyagi for one short question
 *     (action ask); the answer card shows on the island as usual,
 *   - "Back to step N" (the one primary): the full drawer again.
 * Glass tokens like the drawer. The diagram sits on the island's black, the colors it's drawn for.
 */
import { motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { ArrowLeft, Check, CircleHelp, Minus } from 'lucide-react'
import type { GraphDiagramData } from '../../../../../../shared/contracts/events'
import { onMessage } from '../../core/bus'
import { useLesson, useProgress, useThinking, type Rect } from '../../core/lesson'
import { sendAction } from '../../core/shortcuts'
import { color, glass, radius, spring, springOut } from '../../core/theme'
import { GlassPrimary, GlassQuiet, GlassSpinner } from '../../core/ui/glass'
import { expectConceptDiagram, useDiagram } from '../diagrams/store'
import { Graph } from '../diagrams/Graph'
import { useStepStatuses } from './plan'
import { closeConcept, useDrawer } from './store'
import { CodeBlock } from './Teach'
import { fade } from '../../core/ui/motion'

/** A picture already asked for (by concept title) this lesson: don't ask the engine twice (StrictMode, reopening). */
const asked = new Set<string>()
onMessage('lesson.ready', () => asked.clear())
/** Give up waiting for a picture after this long. */
const DIAGRAM_WAIT_MS = 30000

const panelShell = (rect: Rect): React.CSSProperties => ({
  left: rect.x,
  top: rect.y,
  width: rect.w,
  maxHeight: rect.h,
  borderRadius: radius.card,
  background: glass.bg,
  borderColor: glass.hairline,
  boxShadow: `${glass.shadow}, inset 0 0 0 ${rect.w}px ${glass.bg}`,
  color: glass.text
})

export function ConceptPanel({ rect }: { rect: Rect }): ReactNode {
  const id = useDrawer((s) => s.concept)
  const item = useLesson((s) => s.lesson?.primer?.find((p) => p.id === id))
  const hasStep = useLesson((s) => !!s.stepId)
  const { index } = useProgress()
  const diagram = useDiagram((s) => (item ? s.concepts[item.title] : undefined))
  const thinking = useThinking()
  const [gaveUp, setGaveUp] = useState(false)

  // Ask for the picture once per concept per lesson.
  useEffect(() => {
    if (!item || diagram || asked.has(item.title)) return
    asked.add(item.title)
    expectConceptDiagram(item.title)
    sendAction('diagram', item.title)
  }, [item, diagram])
  useEffect(() => {
    setGaveUp(false)
    if (diagram) return
    const t = setTimeout(() => setGaveUp(true), DIAGRAM_WAIT_MS)
    return () => clearTimeout(t)
  }, [item?.title, diagram])

  if (!item) return null
  const away = rect.w + 24
  return (
    <motion.div
      data-hit
      data-part="drawer-concept"
      data-concept={item.id}
      className="absolute flex flex-col overflow-hidden border"
      style={panelShell(rect)}
      initial={{ x: 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: fade.in } }}
      transition={{ ...spring, opacity: fade.in }}
    >
      <div className="min-h-0 overflow-y-auto px-[20px] pb-[18px] pt-[16px]" style={{ scrollbarWidth: 'thin', scrollbarColor: `${glass.track} transparent` }}>
        <div className="text-[12px] font-semibold leading-[16px]" style={{ color: glass.label }}>
          Concept
        </div>
        <div className="mt-[2px] text-[19px] font-semibold leading-[24px] tracking-[-0.01em]">{item.title}</div>
        {item.body && (
          <p className="mt-[8px] text-[14px] leading-[20px]" style={{ color: glass.text }}>
            {item.body}
          </p>
        )}

        <div data-part="concept-diagram" className="mt-[14px] overflow-hidden" style={{ borderRadius: radius.chip, background: color.island }}>
          {diagram ? (
            diagram.kind === 'graph' ? (
              <Graph data={diagram.data as GraphDiagramData} />
            ) : (
              <div className="px-[14px] py-[12px] text-[13px]" style={{ color: color.label }}>
                {diagram.caption}
              </div>
            )
          ) : (
            <div className="flex h-[120px] items-center justify-center gap-[8px] text-[13px]" style={{ color: color.label }}>
              {gaveUp && !thinking ? (
                'No picture for this one.'
              ) : (
                <>
                  <GlassSpinner size={15} c={color.label} track={color.faint} />
                  Drawing it…
                </>
              )}
            </div>
          )}
        </div>

        {item.code && (
          <div className="mt-[4px]">
            <CodeBlock code={item.code} caption="Example" bleed={0} />
          </div>
        )}

        <div className="mt-[16px] flex flex-wrap items-center justify-between gap-[8px]">
          <GlassQuiet
            label="Check my understanding"
            icon={CircleHelp}
            onClick={() => sendAction('ask', `Ask me one short question to check I understand "${item.title}". Don't give the answer yet.`)}
          />
          <GlassPrimary label={hasStep ? `Back to step ${index + 1}` : 'Back to the steps'} icon={ArrowLeft} onClick={closeConcept} />
        </div>
      </div>
    </motion.div>
  )
}

/**
 * The drawer collapsed to its steps: numbered dots (done = the green tick, skipped = a dash, never green, current =
 * ringed), by the drawer's own rule (plan.ts stepStatuses: after Back the current step is current). Click = back.
 */
export function Rail({ rect }: { rect: Rect }): ReactNode {
  const steps = useLesson((s) => s.steps)
  const statuses = useStepStatuses()
  return (
    <motion.div
      data-hit
      data-part="drawer-rail"
      className="absolute flex flex-col items-center gap-[6px] overflow-y-auto border py-[10px]"
      style={panelShell(rect)}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: fade.in }}
      transition={fade.in}
    >
      {steps.map((s, i) => {
        const passed = statuses[i] === 'done'
        const current = statuses[i] === 'current'
        const skipped = statuses[i] === 'skipped'
        return (
          <button
            key={s.id}
            type="button"
            title={s.what || s.title}
            className="grid h-[28px] w-[28px] shrink-0 cursor-pointer place-items-center rounded-full border text-[12px] font-semibold"
            style={{
              borderColor: current ? glass.text : glass.rule,
              background: passed ? glass.pass : current ? glass.field : 'transparent',
              color: passed ? glass.buttonText : current ? glass.text : skipped ? glass.label : glass.faint
            }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={closeConcept}
          >
            {passed ? <Check size={13} strokeWidth={2.6} /> : skipped ? <Minus size={13} strokeWidth={2.2} /> : i + 1}
          </button>
        )
      })}
    </motion.div>
  )
}
