/**
 * Prog-Completion: the lesson-complete card grown out of the notch island, 408 wide.
 *
 *   header   the bonsai and wordmark, the dismiss keycap and ✕
 *   hero     a green check and "Lesson complete" only when every counted step passed; with a skip it is "Lesson
 *            finished" under the skipped ring (green only means passed)
 *   result   what the engine said the learner built (card title / body), and the number their own run printed
 *            (the newest metric series, else the trained network's loss). Left out when there's none.
 *   steps    "6 of 6 passed" / "5 of 6 passed, 1 skipped" from card.result, else counted from this lesson's
 *            step.passed events, and every step with its state
 *   next up  skillMap.next[0]
 *   actions  Done (quiet) and the one primary, Start next lesson. Start next lesson needs a way to start: a cached
 *            lesson (next.id + library.start, zero model calls), or the goal outside the browser stage. Otherwise it
 *            is shown disabled. With no next lesson, Done is the primary.
 * Every number on the card comes from the engine's card, its metric lines or its network diagrams.
 */
import { BookOpen } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { engineMode } from '../../bridge'
import { useCapability, useLesson } from '../../core/lesson'
import { CloseButton, CodeText } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { color, fill, font, radius2, surface, type2 } from '../../core/theme'
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
const caption = { fontSize: type2.xs, color: color.label } as const

/** A next lesson as the engine may send it: SkillNext, plus an optional cached-lesson id and minutes (Core request). */
type Next = SkillNext & { id?: string; estMinutes?: number }
const LIB_ID = /^[A-Za-z0-9_-]{1,64}$/

function readNext(card: CompleteCard): Next | undefined {
  const n = card.map?.next[0] as (SkillNext & Record<string, unknown>) | undefined
  if (!n) return undefined
  const id = typeof n.id === 'string' && LIB_ID.test(n.id) ? n.id : undefined
  const est = typeof n.estMinutes === 'number' && Number.isFinite(n.estMinutes) && n.estMinutes > 0 ? Math.round(n.estMinutes) : undefined
  return { title: n.title, goal: n.goal, ...(id ? { id } : {}), ...(est ? { estMinutes: est } : {}) }
}

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
        <MiyagiWordmark height={15} />
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

function Steps({ counts }: { counts?: LessonResult }): ReactNode {
  const steps = useSteps()
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
          {steps.map((s) => (
            <li key={s.id} data-complete-step={s.state} className="flex shrink-0 items-center gap-[12px]" style={{ height: 26, fontSize: type2.sm, color: s.state === 'passed' ? color.text : color.label }}>
              <StatusGlyph state={s.state} size={16} />
              <span className="min-w-0 truncate">{s.title}</span>
            </li>
          ))}
        </ol>
      )}
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
  if (!card) return null
  const clean = !counts || counts.skipped === 0
  const subtitle = card.result?.title || lessonTitle || card.map?.track || ''
  const minutes = card.result?.minutes
  const next = readNext(card)
  return (
    <section aria-label="Lesson complete" data-complete="panel" className="flex flex-col" style={{ width: w, padding: PAD, gap: 20 }}>
      <Header />
      <div className="flex flex-col gap-[8px]">
        <StatusGlyph state={clean ? 'passed' : 'skipped'} size={40} />
        <h1 className="m-0 mt-[8px] font-semibold" style={{ fontSize: 24, lineHeight: '30px', letterSpacing: '-0.01em', color: color.text }} data-complete-head>
          {clean ? 'Lesson complete' : 'Lesson finished'}
        </h1>
        {(subtitle || minutes) && (
          <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label, ...tab }}>
            {[subtitle, minutes ? `${minutes} min` : ''].filter(Boolean).join(' · ')}
          </p>
        )}
      </div>
      <Result card={card} />
      <Steps counts={counts} />
      {next && <NextUp next={next} />}
      <Actions next={next} />
    </section>
  )
}
