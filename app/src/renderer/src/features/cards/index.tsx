/**
 * Feature: cards. Coach cards that grow out of the pill, in the calm black-island look (mockup 02):
 *   offtrack  amber: what's wrong in one line, yours-vs-tutorial curve of the live `metric`,
 *             expected vs yours (`offtrack.diff`), the checks, Show me / Explain / Apply fix.
 *             After Apply fix it collapses to "Waiting for the fix": the line the code should read
 *             (the engine may or may not write it), and the re-run's curve drawing live.
 *   success   green, "Good. Now the next one." after a recovered step: now-vs-before curve, auto-hides.
 *   card      explain / hint / answer from the engine, with an optional video jump.
 * Copy rule: readable in 2 seconds; body text is clamped to 2–3 lines. No red, no shaking.
 * Generality: every label comes from the data (metric name, check labels, step titles).
 * Brand (app/brand/BRAND.md): amber ONLY = off track, green ONLY = passed, everything else neutral
 * white / muted. Buttons white on dark. No blue, gradients, glows, sparkles or emoji.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, Code2, Download, History, Info, Lightbulb, MessageSquareText, Play, Undo2, Wrench, type LucideIcon } from 'lucide-react'
import type { Payload } from '../../../../common/wire'
import { useLesson, useProgress, type Offtrack as OfftrackPayload } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CardButton, CheckList, CloseButton, Spinner, StatusDot } from '../../core/ui/atoms'
import { color, copy } from '../../core/theme'
import { Curve, fmt, Key, plotArray, plotPoints, type Line } from './Curve'
import { act, cardAct, jumpTo, SUCCESS_MS, useCards, useSeries, type CardAction } from './store'

const OFFTRACK_W = 460
const CARD_W = 420
const PAD = 20

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

/** "Step 6 of 7 · ● Off track ……… reason ✕": the same header line as the expanded pill. */
function Header({ mark, label, tone, right, step = true }: { mark: ReactNode; label: string; tone: string; right?: ReactNode; step?: boolean }): ReactNode {
  const { index, total } = useProgress()
  return (
    <div className="flex h-[22px] items-center gap-[7px] text-[13px] leading-none">
      {step && <span style={{ color: color.label }}>Step {index + 1} of {total}</span>}
      {mark}
      <span className="font-medium" style={{ color: tone }}>
        {label}
      </span>
      <span className="min-w-[8px] flex-1" />
      {right && (
        <span className="truncate text-[12px]" style={{ color: color.faint }}>
          {right}
        </span>
      )}
      <CloseButton />
    </div>
  )
}

function Title({ children }: { children: ReactNode }): ReactNode {
  return <div className="mt-[8px] text-[20px] font-semibold leading-[25px] tracking-[-0.015em]">{children}</div>
}

function Body({ children, lines = 2 }: { children: ReactNode; lines?: number }): ReactNode {
  return (
    <div className="mt-[3px] overflow-hidden text-[14px] leading-[20px]" style={{ color: color.label, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: lines }}>
      {children}
    </div>
  )
}

/** Small uppercase caption above a curve, with its legend on the right. */
function CurveCaption({ label, children }: { label?: string; children: ReactNode }): ReactNode {
  return (
    <div className="mb-[4px] flex items-center gap-[12px] text-[11px]" style={{ color: color.faint }}>
      {label && <span className="truncate font-semibold uppercase tracking-[0.06em]">{label}</span>}
      <span className="flex-1" />
      {children}
    </div>
  )
}

/** Hairline footer: a quiet left note and right note. */
function Footer({ left, right }: { left?: ReactNode; right?: ReactNode }): ReactNode {
  if (!left && !right) return null
  return (
    <div className="mt-[14px] flex items-center gap-[10px] border-t pt-[11px] text-[12px]" style={{ borderColor: color.hairline, color: color.faint }}>
      <span className="flex min-w-0 flex-1 items-center gap-[6px] truncate">{left}</span>
      {right && <span className="shrink-0">{right}</span>}
    </div>
  )
}

/**
 * Swap views inside one island mode: the new view fades in rising 4px while the container springs
 * to its height. No exit animation on purpose: the swap never waits on a frame (a hidden window
 * draws none), so state and DOM always agree.
 */
function Swap({ id, children }: { id: string; children: ReactNode }): ReactNode {
  return (
    <motion.div key={id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, delay: 0.06, ease: 'easeOut' }}>
      {children}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Off-track
// ---------------------------------------------------------------------------

/**
 * Yours vs tutorial. Live `metric` events when there are any (the tutorial line = runId "tutorial");
 * otherwise both lines come from the off-track payload's optional `curve`. The two sources are never
 * mixed on one chart, since they may not share units.
 */
function OfftrackCurve({ o }: { o: OfftrackPayload }): ReactNode {
  const { name, before: run, tutorial } = useSeries(o.curve?.label)
  const live = run && run.points.length > 1 ? run : undefined
  const yours = live ? plotPoints(live.points) : o.curve ? plotArray(o.curve.yours) : []
  if (yours.length < 2) return null
  const ref = live ? (tutorial && tutorial.length > 1 ? plotPoints(tutorial) : []) : o.curve ? plotArray(o.curve.tutorial) : []
  const lines: Line[] = [
    { key: 'yours', pts: yours, stroke: color.amber },
    { key: 'tutorial', pts: ref, stroke: color.label, reference: true }
  ]
  const lastValue = live?.points[live.points.length - 1].value
  return (
    <div className="mt-[14px]" data-curve={live ? 'live' : 'fallback'}>
      <CurveCaption label={live ? name : o.curve?.label}>
        <Key tone={color.amber}>yours</Key>
        {ref.length > 1 && <Key tone={color.label}>tutorial</Key>}
      </CurveCaption>
      <Curve lines={lines} width={OFFTRACK_W - PAD * 2} height={64} end={{ label: lastValue !== undefined ? fmt(lastValue) : undefined, at: live?.at }} />
    </div>
  )
}

/** Expected vs yours, one mono line each (`expectedOnly`: just the expected line). */
function Diff({ diff, expectedOnly }: { diff: NonNullable<OfftrackPayload['diff']>; expectedOnly?: boolean }): ReactNode {
  const row = (label: string, tone: string, text: string, top?: boolean): ReactNode => (
    <div className={`flex items-baseline gap-[12px] px-[12px] py-[7px] ${top ? 'border-t' : ''}`} style={top ? { borderColor: color.hairline } : undefined}>
      <span className="w-[78px] shrink-0 whitespace-nowrap font-sans text-[10.5px] font-semibold uppercase tracking-[0.06em]" style={{ color: tone }}>
        {label}
      </span>
      <span className="truncate text-white/90">{text}</span>
    </div>
  )
  return (
    <div className="mt-[12px] overflow-hidden rounded-[12px] font-mono text-[12.5px] leading-[18px]" style={{ background: 'rgba(255,255,255,.06)' }}>
      {row('Expected', color.label, diff.expected)}
      {!expectedOnly && row(diff.line ? `Yours · L${diff.line}` : 'Yours', color.amber, diff.yours, true)}
    </div>
  )
}

function Diagnosis({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  return (
    <div data-card="offtrack" style={{ padding: `16px ${PAD}px 14px` }}>
      <Header mark={<StatusDot status="offtrack" size={6} />} label="Off track" tone={color.amber} right={o.reason} />
      <Title>{o.title}</Title>
      <Body>{o.body}</Body>

      <OfftrackCurve o={o} />
      {o.diff && <Diff diff={o.diff} />}

      {checks.length > 0 && (
        <div className="mt-[14px]">
          <CheckList checks={checks} />
        </div>
      )}

      <div className="mt-[16px] flex gap-[8px]">
        {o.actions.includes('show_me') && (
          <CardButton onClick={() => act('show_me')}>
            <Play size={13} fill="currentColor" /> Show me
          </CardButton>
        )}
        {o.actions.includes('explain') && (
          <CardButton onClick={() => act('explain')}>
            <Info size={14} /> Explain
          </CardButton>
        )}
        {o.actions.includes('hint') && (
          <CardButton onClick={() => act('hint')}>
            <Lightbulb size={14} /> Hint
          </CardButton>
        )}
        {o.actions.includes('apply_fix') && (
          <CardButton primary onClick={() => act('apply_fix')}>
            <Wrench size={14} /> Apply fix
          </CardButton>
        )}
      </div>

      <Footer
        left={
          o.citation && (
            <>
              <BookOpen size={12} className="shrink-0" /> <span className="truncate">{o.citation.label}</span>
            </>
          )
        }
        right="Video waits until all pass"
      />
    </div>
  )
}

/**
 * Now vs before the fix (muted, dashed). Until the new run starts, only "before".
 * "now" is white while waiting and green only once the step has passed (green ONLY means passed).
 */
function AfterCurve({ label, since, width, passed }: { label?: string; since?: number; width: number; passed?: boolean }): ReactNode {
  const { name, after, before } = useSeries(label, since)
  const now = passed ? color.green : color.text
  const lines: Line[] = []
  if (after && after.points.length > 0) lines.push({ key: 'now', pts: plotPoints(after.points), stroke: now })
  if (before && before.points.length > 1) lines.push({ key: 'before', pts: plotPoints(before.points), stroke: color.label, reference: true, dashed: true })
  if (lines.length === 0) return null
  const lastValue = after?.points[after.points.length - 1]?.value
  return (
    <div className="mt-[14px]" data-curve={after ? 'after' : 'before'}>
      <CurveCaption label={name}>
        {after && <Key tone={now}>now</Key>}
        {before && <Key tone={color.label} dashed={!!after}>before fix</Key>}
      </CurveCaption>
      <Curve
        lines={after ? lines : [{ ...lines[0], reference: false }]}
        width={width - PAD * 2}
        height={64}
        end={{ label: lastValue !== undefined ? fmt(lastValue) : undefined, at: after?.at }}
      />
    </div>
  )
}

/**
 * After Apply fix: the card collapses to this until the step passes. The engine writes the file only
 * when it knows the project folder, so this never claims the fix is applied: it shows the line the
 * code should read and leaves the change to the learner if it isn't there yet.
 */
function Fixing({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  const where = o.diff?.line ? `Line ${o.diff.line}${o.diff.file ? ` of ${o.diff.file}` : ''} should read` : 'Your code should read'
  return (
    <div data-card="fixing" style={{ padding: `16px ${PAD}px 14px` }}>
      <Header mark={<Spinner size={12} />} label="Waiting for the fix" tone={color.text} />
      <div className="mt-[8px] text-[17px] font-semibold leading-[22px] tracking-[-0.01em]">{o.diff ? where : 'Make the fix, then rerun'}</div>
      {o.diff && <Diff diff={o.diff} expectedOnly />}
      <div className="mt-[8px] text-[13px] leading-[18px]" style={{ color: color.label }}>
        {o.diff ? 'Not in your file yet? Make the change, then rerun.' : 'Your checks rerun as soon as it changes.'}
      </div>
      <AfterCurve label={o.curve?.label} width={OFFTRACK_W} />
      {checks.length > 0 && (
        <div className="mt-[14px]">
          <CheckList checks={checks} />
        </div>
      )}
      <Footer right="Video resumes when all pass" />
    </div>
  )
}

function Offtrack(): ReactNode {
  const s = useLesson(useShallow((x) => ({ o: x.offtrack, checks: x.checks })))
  const fixing = useCards((c) => c.fixing)
  if (!s.o) return null
  return <Swap id={fixing ? 'fixing' : 'diagnosis'}>{fixing ? <Fixing o={s.o} checks={s.checks} /> : <Diagnosis o={s.o} checks={s.checks} />}</Swap>
}

// ---------------------------------------------------------------------------
// Back on track
// ---------------------------------------------------------------------------

function Success(): ReactNode {
  const s = useCards((x) => x.success)
  const { after } = useSeries(undefined, s?.since)
  if (!s) return null
  const showCurve = !!after && after.points.length > 1
  return (
    <div data-card="success" className="relative" style={{ padding: `16px ${PAD}px 14px` }}>
      <Header mark={<StatusDot status="passed" size={6} />} label={`Step ${s.index + 1} done`} tone={color.green} step={false} />
      <Title>{copy.passed}</Title>
      {s.summary && <Body>{s.summary}</Body>}
      {showCurve ? (
        <AfterCurve since={s.since} width={OFFTRACK_W} passed />
      ) : (
        s.checks.length > 0 && (
          <div className="mt-[14px]">
            <CheckList checks={s.checks} />
          </div>
        )
      )}
      <Footer
        left={
          <>
            <Play size={11} fill="currentColor" className="shrink-0" /> The video picks up from here
          </>
        }
      />
      {/* Auto-hide countdown: a hairline that drains (transform only). */}
      <motion.div
        key={s.at}
        className="absolute inset-x-0 bottom-0 h-[2px] origin-left"
        style={{ background: color.green, opacity: 0.45 }}
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: SUCCESS_MS / 1000, ease: 'linear' }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Explain / Hint / Answer
// ---------------------------------------------------------------------------

type EngineCard = Payload<'card'>

/** Header per card kind. Typed against the contract so a new kind fails here, not at runtime. */
const KIND: Record<EngineCard['kind'], { label: string; Icon: LucideIcon; tone: string }> = {
  explain: { label: 'Explain', Icon: Info, tone: color.label },
  hint: { label: 'Hint', Icon: Lightbulb, tone: color.label },
  answer: { label: 'Answer', Icon: MessageSquareText, tone: color.label },
  resume: { label: 'Continue?', Icon: History, tone: color.label },
  setup: { label: 'Setup', Icon: Wrench, tone: color.label },
  // Contract sync (integration/live): the cards agent gives it a real view.
  preflight: { label: 'Before you build', Icon: Wrench, tone: color.label }
}

/** Button per card action. At most one white primary per card: the first primary kind present. */
const ACTION: Partial<Record<CardAction, { label: string; Icon?: LucideIcon; primary?: boolean }>> = {
  confirm: { label: 'Yes', Icon: Check, primary: true },
  apply_fix: { label: 'Do it for me', Icon: Wrench, primary: true },
  open_editor: { label: 'Open VS Code', Icon: Code2, primary: true },
  resume: { label: 'Continue', Icon: Play, primary: true },
  undo: { label: 'Undo', Icon: Undo2 },
  end_lesson: { label: 'Start a new lesson' },
  skip_setup: { label: 'Skip' }
}

/** A unified diff as monospace lines: + white, - muted and struck, context faint. Headers dropped. */
function UnifiedDiff({ diff }: { diff: string }): ReactNode {
  const lines = diff.split(/\r?\n/).filter((l) => l && !l.startsWith('+++') && !l.startsWith('---') && !l.startsWith('@@') && !l.startsWith('diff '))
  const shown = lines.slice(0, 14)
  return (
    <div data-diff className="mt-[12px] overflow-hidden rounded-[12px] py-[6px] font-mono text-[12px] leading-[18px]" style={{ background: 'rgba(255,255,255,.06)' }}>
      {shown.map((l, i) => {
        const add = l.startsWith('+')
        const del = l.startsWith('-')
        return (
          <div key={i} className={`truncate whitespace-pre px-[12px] ${del ? 'line-through' : ''}`} style={{ color: add ? color.text : del ? color.label : color.faint }}>
            {l}
          </div>
        )
      })}
      {lines.length > shown.length && (
        <div className="px-[12px]" style={{ color: color.faint }}>
          +{lines.length - shown.length} more lines
        </div>
      )}
    </div>
  )
}

/** Setup card: one row per needed item, Install on the missing ones (action install {text: tool}). */
function SetupItems({ setup }: { setup: NonNullable<EngineCard['setup']> }): ReactNode {
  const items = setup.items.filter((x) => x.needed)
  if (items.length === 0) return null
  return (
    <div className="mt-[12px] flex flex-col gap-[6px] text-[13px]">
      {items.map((x) => (
        <div key={x.tool} className="flex h-[28px] items-center gap-[8px]">
          <span style={{ color: x.ok ? color.text : color.faint }}>{x.ok ? <Check size={13} /> : '·'}</span>
          <span className="truncate">{x.label}</span>
          <span className="min-w-0 flex-1 truncate text-[12px]" style={{ color: color.faint }}>
            {x.ok ? x.version : x.why}
          </span>
          {!x.ok && (
            <button className="flex cursor-pointer items-center gap-[5px] rounded-[9px] px-[9px] py-[3px] text-[12px] font-medium" style={{ background: 'rgba(255,255,255,.09)' }} onClick={() => cardAct('install', x.tool)}>
              <Download size={12} /> Install
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

function CardActions({ actions }: { actions: CardAction[] }): ReactNode {
  const known = actions.filter((a) => ACTION[a])
  if (known.length === 0) return null
  const primary = known.find((a) => ACTION[a]!.primary)
  return (
    <div className="mt-[16px] flex gap-[8px]">
      {known.map((a) => {
        const { label, Icon } = ACTION[a]!
        return (
          <CardButton key={a} primary={a === primary} onClick={() => cardAct(a)}>
            {Icon && <Icon size={14} />} {label}
          </CardButton>
        )
      })}
    </div>
  )
}

function Card(): ReactNode {
  const c = useCards((x) => x.card)
  const hasStep = useLesson((s) => !!s.stepId)
  if (!c) return null
  const k = KIND[c.kind] ?? KIND.answer
  const actions = c.actions ?? []
  // A title that only repeats the header ("Hint") is dropped: the body becomes the headline.
  const redundant = !c.title || c.title.trim().toLowerCase() === k.label.toLowerCase()
  return (
    <div data-card={c.kind} style={{ padding: `16px ${PAD}px 16px` }}>
      <Header mark={<k.Icon size={14} style={{ color: k.tone }} />} label={k.label} tone={k.tone} step={false} right={hasStep ? <StepNote /> : undefined} />
      {redundant ? (
        <div className="mt-[8px] text-[16px] font-medium leading-[22px] tracking-[-0.01em]">{c.body}</div>
      ) : (
        <>
          <div className="mt-[8px] text-[18px] font-semibold leading-[23px] tracking-[-0.01em]">{c.title}</div>
          <Body lines={3}>{c.body}</Body>
        </>
      )}
      {c.videoJump && (
        <motion.button
          className="mt-[14px] flex h-[34px] cursor-pointer items-center gap-[8px] rounded-[12px] pl-[6px] pr-[12px] text-[13px] font-medium"
          style={{ background: 'rgba(255,255,255,.09)' }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.94 }}
          transition={{ duration: 0.09 }}
          onClick={() => jumpTo(c.videoJump!.t)}
        >
          <span className="grid h-[22px] w-[22px] place-items-center rounded-full" style={{ background: color.accent, color: color.onAccent }}>
            <Play size={10} fill="currentColor" className="ml-[1px]" />
          </span>
          Watch {c.videoJump.label}
        </motion.button>
      )}
      {c.guidingQuestion && (
        <div className="mt-[10px] text-[13px] italic leading-[18px]" style={{ color: color.label }}>
          {c.guidingQuestion}
        </div>
      )}
      {c.diff && <UnifiedDiff diff={c.diff} />}
      {c.setup && <SetupItems setup={c.setup} />}
      <CardActions actions={actions} />
    </div>
  )
}

function StepNote(): ReactNode {
  const { index, total } = useProgress()
  return (
    <>
      Step {index + 1} of {total}
    </>
  )
}

export default defineFeature({
  id: 'cards',
  islandModes: [
    {
      id: 'offtrack',
      priority: 70,
      width: OFFTRACK_W,
      useActive: (hover) => {
        const open = useCards((c) => c.offtrackOpen)
        const has = useLesson((s) => !!s.offtrack)
        return has && (open || hover)
      },
      Content: Offtrack
    },
    { id: 'success', priority: 60, width: OFFTRACK_W, useActive: () => useCards((c) => !!c.success), Content: Success },
    { id: 'card', priority: 50, width: CARD_W, useActive: () => useCards((c) => !!c.card), Content: Card }
  ]
})
