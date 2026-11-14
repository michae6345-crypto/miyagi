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
import {
  BookOpen,
  Check,
  Code2,
  Download,
  ExternalLink,
  File,
  FileCode2,
  FolderGit2,
  Hammer,
  History,
  Lightbulb,
  ListChecks,
  MapPin,
  MessageCircle,
  MessageSquareText,
  NotebookText,
  Play,
  Search,
  Undo2,
  Wrench,
  type LucideIcon
} from 'lucide-react'
import type { PreflightInfo } from '../../../../../../shared/contracts/events'
import type { Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useThinking, type Offtrack as OfftrackPayload } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { usePressed } from '../../core/shortcuts'
import { CheckList, CloseButton, OptionButton, PrimaryButton, Spinner, StatusDot } from '../../core/ui/atoms'
import { actionTone, color, copy, fill, kindTone } from '../../core/theme'
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

/** A spinner shaped like a lucide icon, so it can stand in for a button's icon (ink on white/pastel, text on quiet). */
const spinIcon = (c: string): LucideIcon => ((p: { size?: number }) => <Spinner size={p.size ?? 13} c={c} />) as unknown as LucideIcon
const SpinInk = spinIcon(color.onAccent)
const SpinText = spinIcon(color.text)

/**
 * Never look dead: while the engine thinks about the action this button sent (core rule:
 * `useThinking() && usePressed().kind === kind`), or while a card waits on its pressed button, the icon spins.
 * `quiet` = the button has a quiet fill (light spinner) instead of white / pastel (ink spinner).
 */
function useBusyIcon(): (kind: string, icon?: LucideIcon, quiet?: boolean) => LucideIcon | undefined {
  const thinking = useThinking()
  const pressed = usePressed((p) => p.kind)
  const pending = useCards((c) => c.pending?.kind)
  return (kind, icon, quiet) => ((thinking && pressed === kind) || pending === kind ? (quiet ? SpinText : SpinInk) : icon)
}

/** A neutral (non-primary) card action: same shape as PrimaryButton, quiet fill. */
function QuietButton({ label, icon: I, onClick }: { label: string; icon?: LucideIcon; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      className="flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full px-[13px] text-[13px] font-medium"
      style={{ backgroundColor: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {I && <I size={13} strokeWidth={1.8} className="shrink-0" />}
      {label}
    </motion.button>
  )
}

/** The engine's Socratic nudge, under the body (off-track and engine cards alike). */
function Question({ text }: { text: string }): ReactNode {
  return (
    <div data-question className="mt-[6px] text-[13px] leading-[18px]" style={{ color: color.label }}>
      {text}
    </div>
  )
}

/** A label that opens its URL outside the overlay (window.open; Electron's main hands https to the browser). */
function LinkText({ label, url }: { label: string; url?: string }): ReactNode {
  if (!url) return <span className="truncate">{label}</span>
  return (
    <a
      href={url}
      data-link
      className="cursor-pointer truncate underline-offset-2 hover:underline"
      style={{ color: 'inherit' }}
      onClick={(e) => {
        e.preventDefault()
        window.open(url, '_blank', 'noopener,noreferrer')
      }}
    >
      {label}
    </a>
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
  // No legend row: amber is yours (off track), the muted line is the tutorial. Name the metric on hover only.
  return (
    <div className="mt-[12px]" data-curve={live ? 'live' : 'fallback'} title={live ? name : o.curve?.label}>
      <Curve lines={lines} width={OFFTRACK_W - PAD * 2} height={44} end={{ label: lastValue !== undefined ? fmt(lastValue) : undefined, at: live?.at }} />
    </div>
  )
}

/** Expected vs yours, one mono line each (`expectedOnly`: just the expected line). */
function Diff({ diff, expectedOnly }: { diff: NonNullable<OfftrackPayload['diff']>; expectedOnly?: boolean }): ReactNode {
  const row = (label: string, tone: string, text: string, top?: boolean): ReactNode => (
    <div className={`flex items-baseline gap-[12px] px-[12px] py-[7px] ${top ? 'border-t' : ''}`} style={top ? { borderColor: color.hairline } : undefined}>
      <span className="w-[72px] shrink-0 whitespace-nowrap font-sans text-[12px] font-medium" style={{ color: tone }}>
        {label}
      </span>
      <span className="truncate" style={{ color: color.text }}>
        {text}
      </span>
    </div>
  )
  return (
    <div className="mt-[12px] overflow-hidden rounded-[12px] font-mono text-[12.5px] leading-[18px]" style={{ background: fill.field }}>
      {row('expected', color.label, diff.expected)}
      {!expectedOnly && row(diff.line ? `yours · L${diff.line}` : 'yours', color.amber, diff.yours, true)}
    </div>
  )
}

function Diagnosis({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  const busy = useBusyIcon()
  const keys = bridge.platform.keys
  // Precise: only what's failing (with your value), not the checks that already pass.
  const failing = checks.filter((c) => c.status === 'fail')
  return (
    <div data-card="offtrack" style={{ padding: `16px ${PAD}px 16px` }}>
      <Header mark={<StatusDot status="offtrack" size={6} />} label="Off track" tone={color.amber} step={false} />
      <Title>{o.title}</Title>
      <Body>{o.body}</Body>
      {o.guidingQuestion && <Question text={o.guidingQuestion} />}

      <OfftrackCurve o={o} />
      {o.diff && <Diff diff={o.diff} />}

      {failing.length > 0 && (
        <div className="mt-[12px]">
          <CheckList checks={failing} />
        </div>
      )}

      {/* Options in their pastels (same color as everywhere else), the one primary on the right. */}
      <div className="mt-[16px] flex flex-wrap items-center gap-[8px]">
        {o.actions.includes('show_me') && <OptionButton action="show_me" label="Show me" kbd={keys.show_me} icon={busy('show_me')} onClick={() => act('show_me')} />}
        {o.actions.includes('explain') && <OptionButton action="explain" label="Explain" kbd={keys.explain} icon={busy('explain')} onClick={() => act('explain')} />}
        {o.actions.includes('hint') && <OptionButton action="hint" label="Hint" kbd={keys.hint} icon={busy('hint')} onClick={() => act('hint')} />}
        <span className="flex-1" />
        {o.actions.includes('apply_fix') && <PrimaryButton label="Apply fix" icon={busy('apply_fix', Wrench)} onClick={() => act('apply_fix')} />}
      </div>

      {/* The source behind the fix, as a paper (pink kind tone, like the launcher's tiles). No other footer copy. */}
      {o.citation && (
        <div className="mt-[12px] flex items-center gap-[7px] text-[12px]" style={{ color: color.faint }}>
          <BookOpen size={12} className="shrink-0" style={{ color: kindTone.paper }} />
          <LinkText label={o.citation.label} url={o.citation.url} />
        </div>
      )}
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
      {checks.some((c) => c.status !== 'pass') && (
        <div className="mt-[12px]">
          <CheckList checks={checks.filter((c) => c.status !== 'pass')} />
        </div>
      )}
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

/**
 * Header per card kind: a small icon tile instead of a text eyebrow. The options that made the card keep
 * their pastel (Explain sky, Hint pink, same as their buttons); the rest are neutral tiles.
 * Typed against the contract so a new kind fails here, not at runtime.
 */
const KIND: Record<EngineCard['kind'], { label: string; Icon: LucideIcon; tone?: string }> = {
  explain: { label: 'Explain', Icon: MessageSquareText, tone: actionTone.explain },
  hint: { label: 'Hint', Icon: Lightbulb, tone: actionTone.hint },
  answer: { label: 'Answer', Icon: MessageCircle },
  resume: { label: 'Continue?', Icon: History },
  setup: { label: 'Setup', Icon: Wrench },
  // Contract sync (integration/live): the cards agent gives it a real view.
  preflight: { label: 'Before you build', Icon: ListChecks }
}

function KindTile({ k }: { k: (typeof KIND)[EngineCard['kind']] }): ReactNode {
  return (
    <span
      className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-[7px]"
      style={k.tone ? { background: k.tone, color: color.onAccent } : { background: fill.tile, color: color.text }}
      aria-label={k.label}
      title={k.label}
    >
      <k.Icon size={13} strokeWidth={1.9} />
    </span>
  )
}

/** Button per card action. At most one white primary per card: the first primary kind present. */
const ACTION: Partial<Record<CardAction, { label: string; Icon?: LucideIcon; primary?: boolean }>> = {
  confirm: { label: 'Yes', Icon: Check, primary: true },
  apply_fix: { label: 'Do it for me', Icon: Wrench, primary: true },
  open_editor: { label: 'Open VS Code', Icon: Code2, primary: true },
  resume: { label: 'Continue', Icon: Play, primary: true },
  build: { label: 'Build', Icon: Hammer, primary: true },
  pick_another: { label: 'Pick another', Icon: Search },
  download: { label: 'Download', Icon: Download },
  undo: { label: 'Undo', Icon: Undo2 },
  end_lesson: { label: 'Start a new lesson' },
  skip_setup: { label: 'Skip' }
}

/** The engine names some buttons itself: setup.actionLabels ("Download tutorial files"), setup.editorLabel ("Open Cursor"). */
function actionLabel(c: EngineCard, a: CardAction): string {
  const custom = c.setup?.actionLabels?.[a]
  if (custom) return custom
  if (a === 'open_editor' && c.setup?.editorLabel) return `Open ${c.setup.editorLabel}`
  return ACTION[a]!.label
}

/**
 * The one white primary: the preflight card's `recommended`, else the first primary kind, else the only
 * button (a lone Download is primary; next to anything else it stays quiet).
 */
function primaryOf(c: EngineCard, known: CardAction[]): CardAction | undefined {
  if (c.kind === 'preflight' && c.recommended && known.includes(c.recommended)) return c.recommended
  return known.find((a) => ACTION[a]!.primary) ?? (known.length === 1 ? known[0] : undefined)
}

/** A unified diff as monospace lines: + white, - muted and struck, context faint. Headers dropped. */
function UnifiedDiff({ diff }: { diff: string }): ReactNode {
  const lines = diff.split(/\r?\n/).filter((l) => l && !l.startsWith('+++') && !l.startsWith('---') && !l.startsWith('@@') && !l.startsWith('diff '))
  const shown = lines.slice(0, 14)
  return (
    <div data-diff className="mt-[12px] overflow-hidden rounded-[12px] py-[6px] font-mono text-[12px] leading-[18px]" style={{ background: fill.field }}>
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

/**
 * One setup row's button (contract SetupItem.install): method "download" opens its URL here (nothing to
 * send), "open" (a web app) asks the engine to open it (open_in_browser), the rest install (install {text: tool}).
 */
function itemAct(x: NonNullable<EngineCard['setup']>['items'][number]): void {
  if (x.install.method === 'download' && x.install.url) window.open(x.install.url, '_blank', 'noopener,noreferrer')
  else if (x.install.method === 'open') cardAct('open_in_browser', x.tool)
  else cardAct('install', x.tool)
}

/** Setup card: one row per needed item, Install on the missing ones (action install {text: tool}). */
function SetupItems({ setup }: { setup: NonNullable<EngineCard['setup']> }): ReactNode {
  const installs = useCards((s) => s.installs)
  const items = setup.items.filter((x) => x.needed)
  if (items.length === 0) return null
  return (
    <div className="mt-[12px] flex flex-col gap-[6px] text-[13px]">
      {items.map((x) => {
        const run = x.ok ? undefined : installs[x.tool]
        const detail = x.ok ? x.version : run?.running ? (run.line ?? 'Installing…') : (run?.error ?? x.why)
        return (
          <div key={x.tool} className="flex h-[28px] items-center gap-[8px]">
            <span style={{ color: x.ok ? color.text : color.faint }}>{x.ok ? <Check size={13} /> : '·'}</span>
            <span className="truncate">{x.label}</span>
            <span className="min-w-0 flex-1 truncate text-[12px]" style={{ color: run?.error ? color.text : color.faint }} title={detail}>
              {detail}
            </span>
            {!x.ok && run?.running && (
              <span className="flex items-center gap-[6px] px-[9px] py-[3px] text-[12px] font-medium" style={{ color: color.faint }} aria-disabled>
                <Spinner size={12} c={color.faint} /> Installing…
              </span>
            )}
            {!x.ok && !run?.running && x.install.method !== 'none' && (
              <button
                className="flex cursor-pointer items-center gap-[5px] rounded-full px-[10px] py-[3px] text-[12px] font-medium"
                style={{ background: fill.button, color: color.text }}
                onClick={() => itemAct(x)}
              >
                {x.install.method === 'download' || x.install.method === 'open' ? <ExternalLink size={12} /> : <Download size={12} />}{' '}
                {x.install.method === 'download' ? 'Get it' : x.install.method === 'open' ? 'Open' : run?.error ? 'Retry' : 'Install'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

function CardActions({ card, actions }: { card: EngineCard; actions: CardAction[] }): ReactNode {
  const busy = useBusyIcon()
  const known = actions.filter((a) => ACTION[a])
  if (known.length === 0) return null
  const primary = primaryOf(card, known)
  // Quiet actions on the left, the one white primary on the right.
  return (
    <div className="mt-[16px] flex flex-wrap items-center gap-[8px]">
      {known
        .filter((a) => a !== primary)
        .map((a) => (
          <QuietButton key={a} label={actionLabel(card, a)} icon={busy(a, ACTION[a]!.Icon, true)} onClick={() => cardAct(a)} />
        ))}
      <span className="flex-1" />
      {primary && <PrimaryButton label={actionLabel(card, primary)} icon={busy(primary, ACTION[primary]!.Icon)} onClick={() => cardAct(primary)} />}
    </div>
  )
}

const STYLE: Record<NonNullable<PreflightInfo['style']>, string> = { coding: 'Coding', 'no-code': 'No code', conceptual: 'Conceptual' }

/** 1120 s -> "19 min", 6960 s -> "1 h 56 min". */
function minutes(s: number): string {
  const m = Math.round(s / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ''}`
}

/**
 * Preflight (before anything is built): one meta line (style · length · chapters · captions), what the
 * lesson needs, and the engine's warning in amber when the video doesn't fit the goal.
 * Captions come from the finder's result for the same video (preflight doesn't carry them).
 */
function Preflight({ card }: { card: EngineCard }): ReactNode {
  const results = useCards((s) => s.results)
  const p = card.preflight
  const r = (p?.videoId && results[p.videoId]) || (p?.url && results[p.url]) || undefined
  const style = p?.style ?? r?.style
  const length = p?.durationS ?? r?.durationS
  const chapters = p?.chapters ?? r?.chapters
  const meta = [
    style && STYLE[style],
    length !== undefined && minutes(length),
    chapters !== undefined && (chapters === 0 ? 'No chapters' : `${chapters} chapter${chapters === 1 ? '' : 's'}`),
    r?.captions !== undefined && (r.captions ? 'Captions' : 'No captions')
  ].filter((x): x is string => !!x)
  const needs = (card.items ?? []).filter((x) => x.needed)
  const missing = needs.filter((x) => !x.ok).length
  return (
    <div data-preflight className="mt-[12px] flex flex-col gap-[6px] text-[13px] leading-[18px]">
      {meta.length > 0 && <div style={{ color: color.label }}>{meta.join(' · ')}</div>}
      {needs.length > 0 && (
        <div className="truncate" style={{ color: color.label }} title={needs.map((x) => x.label).join(', ')}>
          <span style={{ color: color.faint }}>Needs </span>
          {needs.map((x) => x.label).join(', ')}
          {missing > 0 && <span style={{ color: color.faint }}> · {missing} to install</span>}
        </div>
      )}
      {card.warning && <div style={{ color: color.amber }}>{card.warning}</div>}
    </div>
  )
}

type Resource = NonNullable<NonNullable<EngineCard['setup']>['resources']>[number]
const RESOURCE_ICON: Record<Resource['kind'], LucideIcon> = { repo: FolderGit2, notebook: NotebookText, gist: FileCode2, file: File }

/** The files the video links (what the Download button fetches): name + kind, one row each. */
function Resources({ resources }: { resources: Resource[] }): ReactNode {
  if (resources.length === 0) return null
  return (
    <div data-resources className="mt-[10px] flex flex-col gap-[2px] text-[13px]">
      {resources.map((x) => {
        const I = RESOURCE_ICON[x.kind] ?? File
        return (
          <div key={x.url} className="flex h-[26px] items-center gap-[8px]" title={x.url}>
            <I size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
            <span className="min-w-0 truncate">{x.name}</span>
            <span className="shrink-0 text-[12px]" style={{ color: color.faint }}>
              {x.kind}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/**
 * Where to go when the place isn't on screen ("Open app.py in Cursor"): one line and an Open button
 * (action open_editor), so "code not visible" always says what to do.
 */
function Where({ text }: { text: string }): ReactNode {
  const busy = useBusyIcon()
  return (
    <div data-where className="mt-[12px] flex items-center gap-[10px] rounded-[12px] py-[6px] pl-[12px] pr-[6px]" style={{ background: fill.field }}>
      <MapPin size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
      <span className="min-w-0 flex-1 truncate text-[13px]">{text}</span>
      <QuietButton label="Open" icon={busy('open_editor', ExternalLink, true)} onClick={() => cardAct('open_editor')} />
    </div>
  )
}

function Card(): ReactNode {
  const c = useCards((x) => x.card)
  if (!c) return null
  const k = KIND[c.kind] ?? KIND.answer
  const actions = c.actions ?? []
  // A title that only repeats the header ("Hint") is dropped: the body becomes the headline.
  const redundant = !c.title || c.title.trim().toLowerCase() === k.label.toLowerCase()
  // A title that only repeats the kind ("Hint") is dropped: the body becomes the headline (clamped to 2 lines).
  return (
    <div data-card={c.kind} style={{ padding: `16px ${PAD}px 16px` }}>
      <div className="flex items-start gap-[10px]">
        <KindTile k={k} />
        <div className="min-w-0 flex-1 pt-[1px]">
          {redundant ? (
            <div
              className="overflow-hidden text-[16px] font-medium leading-[22px] tracking-[-0.01em]"
              style={{ display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}
            >
              {c.body}
            </div>
          ) : (
            <>
              <div className="text-[17px] font-semibold leading-[22px] tracking-[-0.01em]">{c.title}</div>
              <Body lines={3}>{c.body}</Body>
            </>
          )}
          {c.guidingQuestion && <Question text={c.guidingQuestion} />}
        </div>
        <CloseButton />
      </div>
      {c.kind === 'preflight' && <Preflight card={c} />}
      {c.where && <Where text={c.where} />}
      {c.videoJump && (
        <div className="mt-[14px] flex">
          <OptionButton action="watch" label={`Watch ${c.videoJump.label}`} onClick={() => jumpTo(c.videoJump!.t)} />
        </div>
      )}
      {c.diff && <UnifiedDiff diff={c.diff} />}
      {c.setup && <SetupItems setup={c.setup} />}
      {c.setup?.resources && <Resources resources={c.setup.resources} />}
      {/* The where line has its own Open button: don't repeat it below. */}
      <CardActions card={c} actions={c.where ? actions.filter((a) => a !== 'open_editor') : actions} />
    </div>
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
