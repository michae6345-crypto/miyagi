/**
 * Prog-Completion: the lesson-complete card grown out of the notch island, 408 wide.
 *
 *   header   the bonsai and wordmark, the dismiss keycap and ✕
 *   hero     a green check and "Lesson complete" only when every counted step passed; otherwise (a skip, a step
 *            that never reported passed, or no counts at all) it is "Lesson finished" under the plain ring (green
 *            only means passed)
 *   result   what the engine said the learner built (card title / body), and the number their own run printed
 *            (the newest metric series, else the trained network's loss). Left out when there's none.
 *   steps    "6 of 6 passed" / "5 of 6 passed, 1 skipped" from card.result, else counted from this lesson's
 *            step.passed events, and every step with its state
 *   skills   what this lesson grew: the track's mastered skills from skillMap, this lesson's first with a "new" tag
 *            (node.lesson, when the engine sends it) (a green check is a mastered skill, the
 *            one place green is earned here besides the hero), up to four, then "and N more"
 *   next up  skillMap.next[0]
 * Motion: no confetti. The hero check springs in, then each block settles in turn (40 ms apart) and the step rows tick
 * in one after another, so the card reads as a short replay of what was built. Opacity only with reduced motion.
 *   actions  Done (quiet) and the one primary, Start next lesson. Start next lesson needs a way to start: a cached
 *            lesson (next.id + library.start, zero model calls), or the goal outside the browser stage. Otherwise it
 *            is shown disabled. With no next lesson, Done is the primary.
 * Every number on the card comes from the engine's card, its metric lines or its network diagrams.
 */
import { BookOpen } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { engineMode } from '../../bridge'
import { useCapability, useLesson } from '../../core/lesson'
import { CloseButton, CodeText } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { color, fill, font, radius2, spring, surface, type2 } from '../../core/theme'
import { useOverlayWidth, useSeries } from '../cards/store'
import { lossStat, plain } from './net'
import { endLesson, startCached, startLesson, useComplete, type CompleteCard, type LessonResult } from './store'
import type { SkillNext } from './types'

export const COMPLETE_W = 408
const PAD = 24
/** Step rows shown before the list scrolls (26 px each). */
const ROWS = 8

/** The overlay keeps 16 px from each edge. */
export function panelWidth(overlay: number): number {
  return Math.max(320, Math.min(COMPLETE_W, overlay - 32))
}

const tab = { fontVariantNumeric: 'tabular-nums' } as const
/** Each block's entrance: up and in on the house spring, `i` blocks after the hero. */
const STEP_S = 0.04
function useEnter(): (i: number) => Record<string, unknown> {
  const reduce = useReducedMotion()
  return (i) => ({
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { ...spring, delay: reduce ? 0 : 0.08 + i * STEP_S, opacity: { duration: 0.2, delay: reduce ? 0 : 0.08 + i * STEP_S } }
  })
}
const caption = { fontSize: type2.xs, color: color.label } as const

/** The first up-next lesson (readSkillMap already checked its optional cached id and minutes). */
type Next = SkillNext
const readNext = (card: CompleteCard): Next | undefined => card.map?.next[0]

/** The lesson's steps as this window saw them: positions, titles and states (skipped is never passed). */
function useSteps(): Array<{ id: string; title: string; state: StatusState }> {
  const key = useLesson(
    useShallow((s) => ({
      ids: s.steps.map((x) => x.id).join('\u0001'),
      titles: s.steps.map((x) => x.title).join('\u0001'),
      passed: s.passed.join('\u0001'),
      skipped: s.skipped.join('\u0001')
    }))
  )
  return useMemo(() => {
    if (!key.ids) return []
    const ids = key.ids.split('\u0001')
    const titles = key.titles.split('\u0001')
    const passed = new Set(key.passed ? key.passed.split('\u0001') : [])
    const skipped = new Set(key.skipped ? key.skipped.split('\u0001') : [])
    return ids.map((id, i) => ({ id, title: titles[i] ?? '', state: skipped.has(id) ? 'skipped' : passed.has(id) ? 'passed' : 'next' }))
  }, [key])
}

/** The counts: the engine's result when it adds up, else this lesson's own events. Undefined when there are none. */
function useCounts(result?: LessonResult): LessonResult | undefined {
  const steps = useSteps()
  return useMemo(() => {
    if (result) return result
    if (!steps.length) return undefined
    return { passed: steps.filter((s) => s.state === 'passed').length, skipped: steps.filter((s) => s.state === 'skipped').length, total: steps.length }
  }, [result, steps])
}

function countLine(c: LessonResult): string {
  return `${c.passed} of ${c.total} passed${c.skipped ? `, ${c.skipped} skipped` : ''}`
}

/**
 * The number the learner's own run printed (the newest metric series, never the tutorial's run): first and last
 * point under the metric's own name. Else the trained network's loss frames. Undefined when neither exists.
 */
function useRunNumber(): { label: string; value: string } | undefined {
  const { name, series } = useSeries()
  const trained = useComplete((s) => s.trained)
  const net = useComplete((s) => s.net)
  return useMemo(() => {
    const pts = series?.run.points
    if (pts?.length && name) {
      const a = pts[0].value
      const b = pts[pts.length - 1].value
      return { label: `Your run's ${name}`, value: pts.length > 1 && a !== b ? `${plain(a)} → ${plain(b)}` : plain(b) }
    }
    const s = lossStat(trained?.frames ?? []) ?? (net ? lossStat(net.frames) : undefined)
    if (!s) return undefined
    return { label: s.epochs ? `Loss over ${s.epochs.toLocaleString('en-US')} epochs` : 'Loss', value: s.from !== undefined ? `${plain(s.from)} → ${plain(s.to)}` : plain(s.to) }
  }, [series, name, trained, net])
}

function Header(): ReactNode {
  return (
    <div className="flex items-center justify-between" style={{ height: 28 }}>
      <div className="flex items-center gap-[8px]">
        <MiyagiMark size={18} />
        <MiyagiWordmark height={15} className="h-[15px] w-auto" />
      </div>
      <div className="flex items-center gap-[8px]">
        <Keycap k="dismiss" size="sm" />
        <CloseButton />
      </div>
    </div>
  )
}

function Result({ card }: { card: CompleteCard }): ReactNode {
  const run = useRunNumber()
  const lead = card.title && card.title !== 'Lesson complete' ? card.title : ''
  if (!lead && !run && !card.body) return null
  return (
    <div data-complete-result className="flex flex-col gap-[4px]" style={{ padding: 16, borderRadius: radius2.chip, background: surface.row, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}` }}>
      {lead && <span style={caption}>{lead}</span>}
      {run && (
        <div className="flex items-baseline justify-between gap-[12px]" data-complete-loss>
          <span className="min-w-0 truncate font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
            {run.label}
          </span>
          <span className="shrink-0 font-semibold" style={{ fontFamily: font.mono, fontSize: 22, letterSpacing: '-0.01em', color: color.text, ...tab }}>
            {run.value}
          </span>
        </div>
      )}
      {card.body && (
        <span style={{ ...caption, lineHeight: '16px', textWrap: 'pretty' }}>
          <CodeText text={card.body} />
        </span>
      )}
    </div>
  )
}

function Steps({ counts, from = 0 }: { counts?: LessonResult; from?: number }): ReactNode {
  const steps = useSteps()
  const enter = useEnter()
  if (!steps.length && !counts) return null
  return (
    <div className="flex flex-col gap-[4px]" data-complete-steps>
      <div className="mb-[4px] flex items-baseline justify-between">
        <span className="font-semibold" style={caption}>
          Steps
        </span>
        {counts && (
          <span style={{ ...caption, ...tab }} data-complete-count>
            {countLine(counts)}
          </span>
        )}
      </div>
      {steps.length > 0 && (
        <ol className="m-0 flex list-none flex-col overflow-y-auto p-0" style={{ maxHeight: ROWS * 26 }}>
          {steps.map((s, i) => (
            <motion.li
              key={s.id}
              data-complete-step={s.state}
              className="flex shrink-0 items-center gap-[12px]"
              style={{ height: 26, fontSize: type2.sm, color: s.state === 'passed' ? color.text : color.label }}
              {...enter(from + Math.min(i, ROWS - 1))}
            >
              <StatusGlyph state={s.state} size={16} />
              <span className="min-w-0 truncate">{s.title}</span>
            </motion.li>
          ))}
        </ol>
      )}
    </div>
  )
}

/**
 * The track's mastered skills, up to four chips, then "and N more". The skills THIS lesson taught (node.lesson, not in
 * the contract yet: Core request in agents/progress.md) come first and carry a quiet "new" tag, so the card says which
 * skill leveled up. Without the flag the order is the track's own and nothing is tagged (never a guess).
 */
const SKILL_CHIPS = 4
function Skills({ card }: { card: CompleteCard }): ReactNode {
  const map = card.map
  if (!map) return null
  const all = map.nodes.filter((n) => n.state === 'mastered')
  if (!all.length) return null
  const mastered = [...all.filter((n) => n.lesson), ...all.filter((n) => !n.lesson)]
  const shown = mastered.slice(0, SKILL_CHIPS)
  const more = mastered.length - shown.length
  return (
    <div className="flex flex-col gap-[8px]" data-complete-skills>
      <div className="flex items-baseline justify-between gap-[12px]">
        <span className="min-w-0 truncate font-semibold" style={caption}>
          {map.track ? `Skills in ${map.track}` : 'Skills'}
        </span>
        <span className="shrink-0" style={{ ...caption, ...tab }}>
          {mastered.length} of {map.nodes.length} mastered
        </span>
      </div>
      <div className="flex flex-wrap gap-[6px]">
        {shown.map((n) => (
          <span
            key={n.id}
            title={n.detail}
            className="flex h-[26px] max-w-full items-center gap-[6px]"
            style={{ padding: '0 10px 0 6px', borderRadius: radius2.round, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.xs, color: color.text }}
          >
            <StatusGlyph state="passed" size={14} />
            <span className="truncate">{n.label}</span>
            {n.lesson && (
              <span className="shrink-0" style={{ fontSize: type2.micro, color: color.label }} data-complete-new>
                new
              </span>
            )}
          </span>
        ))}
        {more > 0 && (
          <span className="flex h-[26px] items-center" style={{ padding: '0 4px', fontSize: type2.xs, color: color.label }}>
            and {more} more
          </span>
        )}
      </div>
    </div>
  )
}

function NextUp({ next }: { next: Next }): ReactNode {
  return (
    <div className="flex flex-col gap-[8px]" data-complete-next>
      <span className="font-semibold" style={caption}>
        Next up
      </span>
      <div className="flex items-center gap-[12px]" style={{ padding: 12, borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
        <div className="grid shrink-0 place-items-center" style={{ width: 40, height: 40, borderRadius: radius2.row, background: fill.tile, color: fill.tileGlyph }}>
          <BookOpen size={18} strokeWidth={1.8} aria-hidden />
        </div>
        <div className="flex min-w-0 flex-col gap-[2px]">
          <span className="truncate font-semibold" style={{ fontSize: type2.md, color: color.text }} title={next.goal}>
            {next.title}
          </span>
          {next.estMinutes && <span style={caption}>About {next.estMinutes} min</span>}
        </div>
      </div>
    </div>
  )
}

function Actions({ next }: { next?: Next }): ReactNode {
  const ending = useComplete((s) => s.ending)
  const cached = useCapability('library.start')
  if (!next) return <PrimaryButton label="Done" size="lg" block busy={ending} onClick={endLesson} />
  // A cached lesson starts with zero model calls; a goal builds a new lesson, which the browser stage never does.
  const start = next.id && cached ? () => startCached(next.id!) : engineMode() !== 'inline' ? () => startLesson(next.goal) : undefined
  return (
    <div className="flex items-center gap-[8px]">
      <div style={{ width: 104 }} className="shrink-0">
        <QuietButton label="Done" size="lg" block busy={ending} onClick={endLesson} />
      </div>
      <div className="min-w-0 flex-1">
        <PrimaryButton label="Start next lesson" size="lg" block disabled={!start} title={start ? next.goal : 'miyagi can’t start this lesson from here yet'} onClick={() => start?.()} />
      </div>
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const lessonTitle = useLesson((s) => s.lesson?.title)
  const counts = useCounts(card?.result)
  const w = panelWidth(useOverlayWidth((s) => s.w))
  const enter = useEnter()
  // The blocks after the step rows wait for the last visible row, so the replay reads top to bottom.
  const rows = useSteps().length
  const after = 4 + Math.min(rows, ROWS)
  if (!card) return null
  // Green only when every counted step passed; no counts, a skip or a missed pass all get the plain ring.
  const clean = !!counts && counts.skipped === 0 && counts.passed >= counts.total
  const subtitle = card.result?.title || lessonTitle || card.map?.track || ''
  const minutes = card.result?.minutes
  const next = readNext(card)
  return (
    <section aria-label="Lesson complete" data-complete="panel" className="flex flex-col" style={{ width: w, padding: PAD, gap: 20 }}>
      <Header />
      <div className="flex flex-col gap-[8px]">
        <StatusGlyph state={clean ? 'passed' : 'skipped'} size={40} />
        <motion.h1 className="m-0 mt-[8px] font-semibold" style={{ fontSize: 24, lineHeight: '30px', letterSpacing: '-0.01em', color: color.text }} data-complete-head {...enter(0)}>
          {clean ? 'Lesson complete' : 'Lesson finished'}
        </motion.h1>
        {(subtitle || minutes) && (
          <motion.p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label, ...tab }} {...enter(1)}>
            {[subtitle, minutes ? `${minutes} min` : ''].filter(Boolean).join(' · ')}
          </motion.p>
        )}
      </div>
      <motion.div className="empty:hidden" {...enter(2)}>
        <Result card={card} />
      </motion.div>
      <motion.div className="empty:hidden" {...enter(3)}>
        <Steps counts={counts} from={4} />
      </motion.div>
      <motion.div className="empty:hidden" {...enter(after)}>
        <Skills card={card} />
      </motion.div>
      {next && (
        <motion.div {...enter(after + 1)}>
          <NextUp next={next} />
        </motion.div>
      )}
      <motion.div {...enter(after + 2)}>
        <Actions next={next} />
      </motion.div>
    </section>
  )
}
