/**
 * Feature: cards. Coach cards that grow out of the pill, in the calm black-island look (mockup 02):
 *   offtrack  layout C (Adrian): ~620 wide, two columns (one below 520). Left: ring + "Not yet", the title,
 *             the guiding question (or the body), the citation. Right: the evidence panel (Evidence.tsx):
 *             yours | expected from the diff, the failing checks and the curve, all monochrome. Under both,
 *             the options in the shortcut bar's order (Explain, Show me, Hint) and, at level 3, "Do it for me"
 *             on its own row. Off track has no hue anywhere.
 *             After Do it for me, it collapses to "Waiting for the fix": the line the code should read
 *             (the engine may or may not write it), and the re-run's curve drawing live.
 *   success   green, "Good. Now the next one." after a recovered step: now-vs-before curve, auto-hides.
 *   card      explain / hint / answer from the engine, with an optional video jump.
 * Copy rule: readable in 2 seconds; a long engine-card body folds to 6 lines with "More" (Clamp.tsx). No red, no shaking.
 * Generality: every label comes from the data (metric name, check labels, step titles).
 * Brand (app/brand/BRAND.md): off track has no hue (a white ring), green ONLY = passed, everything else
 * neutral white / muted. Buttons white on dark. No blue, amber, gradients, glows, sparkles or emoji.
 */
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, Code2, Download, ExternalLink, File, FileCode2, Footprints, FolderGit2, Hammer, History, Info, Lightbulb, ListChecks, MessageCircle, MessageSquareText, NotebookText, Play, Search, SkipForward, SquarePlay, SquareTerminal, Undo2, Wrench, FolderOpen, RotateCcw, type LucideIcon } from 'lucide-react'
import type { PreflightInfo } from '../../../../../../shared/contracts/events'
import type { Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useThinking, type Offtrack as OfftrackPayload } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { usePressed, type ActionKind } from '../../core/shortcuts'
import { CheckList, CloseButton, OptionButton, PrimaryButton, Spinner, StatusDot } from '../../core/ui/atoms'
import { actionTone, color, copy, fill } from '../../core/theme'
import { Curve, fmt, Key, plotPoints, type Line } from './Curve'
import { BODY_LINES, Clamp, HEADLINE_LINES } from './Clamp'
import { Evidence } from './Evidence'
import { act, cardAct, jumpTo, SUCCESS_MS, useCards, useOverlayWidth, useSeries, type CardAction, type Install } from './store'

/** Layout C: about 620 wide; below NARROW (a small display) the two columns stack. */
const OFFTRACK_MAX = 620
const NARROW = 520
const SUCCESS_W = 460
const CARD_W = 420
const PAD = 20
const COL_GAP = 16

/** The off-track card's width for an overlay this wide (the island keeps 16 px from each edge). */
const offtrackWidth = (overlay: number): number => Math.max(300, Math.min(OFFTRACK_MAX, overlay - 32))
const useOfftrackWidth = (): number => offtrackWidth(useOverlayWidth((s) => s.w))

/** An invisible overlay layer that reports the overlay's width (the display in Electron, 1600 in the stage). */
function WidthProbe({ layout }: { layout: { width: number } }): ReactNode {
  useEffect(() => useOverlayWidth.setState({ w: layout.width }), [layout.width])
  return null
}

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
const SpinInk = ((p: { size?: number }) => <Spinner size={p.size ?? 13} c={color.onAccent} track={fill.onAccentKey} />) as unknown as LucideIcon
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
      {!expectedOnly && row(diff.line ? `yours · L${diff.line}` : 'yours', color.faint, diff.yours, true)}
    </div>
  )
}

/** The off-track card's options, in the shortcut bar's order (Explain, Show me, Hint); Do it for me comes after. */
const OFFTRACK_OPTIONS = [
  { action: 'explain', label: 'Explain' },
  { action: 'show_me', label: 'Show me' },
  { action: 'hint', label: 'Hint' }
] as const

/**
 * Layout C (Adrian picked "side by side"). Left: ring + "Not yet", the title, the guiding question (or the body),
 * the citation as one faint line. Right: the evidence panel. Under both, full width so three options with their
 * keycaps always fit on one row: Explain, Show me, Hint; at level 3 with apply_fix, the one white "Do it for me"
 * on its own row. Below NARROW the panel drops under the left column.
 */
function Diagnosis({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  const busy = useBusyIcon()
  const keys = bridge.platform.keys
  const width = useOfftrackWidth()
  const narrow = width < NARROW
  const inner = width - PAD * 2
  const leftW = narrow ? inner : Math.round((inner - COL_GAP) * 0.47)
  const rightW = narrow ? inner : inner - COL_GAP - leftW
  // Precise: only what's failing (with your value), not the checks that already pass.
  const failing = checks.filter((c) => c.status === 'fail')
  // "Do it for me" = apply_fix, offered at the top of the hint ladder (level 3; no level = an older engine, trust actions).
  const canFix = o.actions.includes('apply_fix') && (o.level ?? 3) === 3
  return (
    <div data-card="offtrack" data-layout={narrow ? 'stacked' : 'side-by-side'} style={{ width, padding: `16px ${PAD}px 16px` }}>
      <div className="flex h-[22px] items-center gap-[8px] text-[13px] leading-none">
        <StatusDot status="offtrack" size={8} />
        <span style={{ color: color.label }}>Not yet</span>
        <span className="flex-1" />
        <CloseButton />
      </div>

      <div className={`mt-[10px] flex ${narrow ? 'flex-col gap-[14px]' : 'items-start'}`} style={narrow ? undefined : { gap: COL_GAP }}>
        <div className="min-w-0 flex-1" style={narrow ? undefined : { maxWidth: leftW }}>
          <div className="text-[18px] font-semibold leading-[23px] tracking-[-0.01em]">{o.title}</div>
          {o.guidingQuestion ? <Question text={o.guidingQuestion} /> : <Body>{o.body}</Body>}

          {o.citation && (
            <div className="mt-[12px] flex min-w-0 items-center gap-[6px] text-[12px]" style={{ color: color.faint }}>
              <BookOpen size={12} className="shrink-0" />
              <LinkText label={o.citation.label} url={o.citation.url} />
            </div>
          )}
        </div>

        {/* No diff yet: the panel keeps its room, so the card doesn't jump when one arrives. */}
        <Evidence o={o} failing={failing} width={rightW} reserveDiff />
      </div>

      <div data-options className="mt-[14px] flex flex-wrap items-center gap-[8px]">
        {OFFTRACK_OPTIONS.map((x) => (
          <OptionButton key={x.action} action={x.action} label={x.label} kbd={keys[x.action]} icon={busy(x.action)} onClick={() => act(x.action)} />
        ))}
      </div>
      {canFix && (
        <div data-fix className="mt-[8px] flex">
          <PrimaryButton label={ACTION.apply_fix!.label} icon={busy('apply_fix', ACTION.apply_fix!.Icon)} onClick={() => act('apply_fix')} />
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
 * After Do it for me (apply_fix): the card collapses to this until the step passes. The engine writes the file only
 * when it knows the project folder, so this never claims the fix is applied: it shows the line the
 * code should read and leaves the change to the learner if it isn't there yet.
 */
function Fixing({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  const width = useOfftrackWidth()
  const where = o.diff?.line ? `Line ${o.diff.line}${o.diff.file ? ` of ${o.diff.file}` : ''} should read` : 'Your code should read'
  return (
    <div data-card="fixing" style={{ width, padding: `16px ${PAD}px 14px` }}>
      <Header mark={<Spinner size={12} />} label="Waiting for the fix" tone={color.text} />
      <div className="mt-[8px] text-[17px] font-semibold leading-[22px] tracking-[-0.01em]">{o.diff ? where : 'Make the fix, then rerun'}</div>
      {o.diff && <Diff diff={o.diff} expectedOnly />}
      <div className="mt-[8px] text-[13px] leading-[18px]" style={{ color: color.label }}>
        {o.diff ? 'Not in your file yet? Make the change, then rerun.' : 'Your checks rerun as soon as it changes.'}
      </div>
      <AfterCurve label={o.curve?.label} width={width} />
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
  // A "Just teach me" lesson has no video to pick up.
  const hasVideo = useLesson((l) => l.lesson?.mode !== 'lesson')
  if (!s) return null
  const showCurve = !!after && after.points.length > 1
  return (
    <div data-card="success" className="relative" style={{ padding: `16px ${PAD}px 14px` }}>
      <Header mark={<StatusDot status="passed" size={6} />} label={`Step ${s.index + 1} done`} tone={color.green} step={false} />
      <Title>{copy.passed}</Title>
      {s.summary && <Body>{s.summary}</Body>}
      {showCurve ? (
        <AfterCurve since={s.since} width={SUCCESS_W} passed />
      ) : (
        s.checks.length > 0 && (
          <div className="mt-[14px]">
            <CheckList checks={s.checks} />
          </div>
        )
      )}
      {hasVideo && (
        <Footer
          left={
            <>
              <Play size={11} fill="currentColor" className="shrink-0" /> The video picks up from here
            </>
          }
        />
      )}
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
 * their pastel (Explain sky, Hint pink, Show me lilac, same as their buttons); the rest are neutral tiles.
 * Typed against the contract so a new kind fails here, not at runtime. tileOf() picks the tile per card.
 */
const KIND: Record<EngineCard['kind'], { label: string; Icon: LucideIcon; tone?: string }> = {
  explain: { label: 'Explain', Icon: MessageSquareText, tone: actionTone.explain },
  hint: { label: 'Hint', Icon: Lightbulb, tone: actionTone.hint },
  answer: { label: 'Answer', Icon: MessageCircle },
  resume: { label: 'Continue?', Icon: History },
  setup: { label: 'Setup', Icon: Wrench },
  // Contract sync (integration/live): the cards agent gives it a real view.
  preflight: { label: 'Before you build', Icon: ListChecks },
  // integration/live 29d7e0d: the engine names these itself (A15).
  // step: step-control and step-judge cards ("Looks done?", "Not yet"): a status card, never an option.
  step: { label: 'Step', Icon: Footprints },
  // where: Show me's where-to-work card: lilac with the Show me glyph, like its button.
  where: { label: 'Show me', Icon: SquarePlay, tone: actionTone.show_me }
}

type Tile = (typeof KIND)[EngineCard['kind']]

/** A run step's card ("Run it for me") and its result (the program's output): a neutral terminal tile. */
const RUN: Tile = { label: 'Run', Icon: SquareTerminal }
/** Show me's answer (e.g. "Code not visible" + where): the "where" kind's tile. */
const SHOW_ME: Tile = KIND.where
/** Step controls and the step judge ("Looks done?", "Not yet", "Stuck on this step?"): the "step" kind's tile. */
const STEP: Tile = KIND.step
/** Wrong-folder card (use_this_folder). */
const FOLDER: Tile = { label: 'Folder', Icon: FolderOpen }
/** "Apply this fix?" (a diff to confirm): the Do it for me preview. */
const FIX: Tile = { label: 'Do it for me', Icon: Wrench }

const STEP_ACTIONS: CardAction[] = ['skip_step', 'check_step']
/** Cards that answer a question (the tile can follow the button that asked): not setup, resume or preflight. */
const ANSWERS: EngineCard['kind'][] = ['explain', 'hint', 'answer']

/**
 * The tile for a card: its kind's, unless what the card is about says otherwise. The engine now sends kind "step"
 * and "where" itself (integration/live 29d7e0d); for an older engine the guesses stay: output / run_command = Run;
 * source "judge" or step-control actions = Step; a diff = the fix preview; an answer that came right after Show me
 * (`from`, the pressed action) = Show me.
 */
function tileOf(c: EngineCard, from?: ActionKind): Tile {
  const actions = c.actions ?? []
  if (c.output || actions.includes('run_command') || from === 'run_command') return RUN
  if (c.kind === 'step' || c.kind === 'where') return KIND[c.kind]
  if (c.source === 'judge') return STEP
  if (actions.includes('use_this_folder')) return FOLDER
  if (actions.some((a) => STEP_ACTIONS.includes(a)) || (from && (STEP_ACTIONS as string[]).includes(from))) return STEP
  if (c.diff) return FIX
  if (from === 'show_me' && ANSWERS.includes(c.kind)) return SHOW_ME
  return KIND[c.kind] ?? KIND.answer
}

function KindTile({ k }: { k: Tile }): ReactNode {
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
  // Step controls ("Not yet" / "Looks done?" / "Stuck on this step?" cards).
  check_step: { label: 'Check again', Icon: Check },
  skip_step: { label: 'Skip step', Icon: SkipForward },
  // Wrong-folder card: the learner is editing the lesson file in another folder; adopt that folder (engine copies only missing files).
  use_this_folder: { label: 'Use this folder', Icon: FolderOpen },
  // Run steps: the engine runs the step's command in the lesson folder and shows the output.
  run_command: { label: 'Run it for me', Icon: Play, primary: true },
  confirm: { label: 'Yes', Icon: Check, primary: true },
  apply_fix: { label: 'Do it for me', Icon: Wrench, primary: true },
  open_editor: { label: 'Open VS Code', Icon: Code2, primary: true },
  resume: { label: 'Continue', Icon: Play, primary: true },
  // Preflight card: Build starts the lesson, Pick another reopens the results (`recommended` picks the primary).
  build: { label: 'Build lesson', Icon: Hammer, primary: true },
  pick_another: { label: 'Pick another', Icon: Search },
  download: { label: 'Download', Icon: Download },
  undo: { label: 'Undo', Icon: Undo2 },
  end_lesson: { label: 'Start a new lesson' },
  skip_setup: { label: 'Skip' },
  open_in_browser: { label: 'Open in browser', Icon: BookOpen },
  // "Couldn't reach Claude" answer card: the engine re-sends the learner's last ask / explain / hint.
  retry: { label: 'Try again', Icon: RotateCcw },
  // Judge "Not yet" card: the same Hint / Show me as the off-track card (drawn as OptionButtons in CardActions).
  hint: { label: 'Hint' },
  show_me: { label: 'Show me' }
}

/** Card actions drawn as pastel OptionButtons with keycaps (like the off-track card), not as quiet buttons. */
const OPTION = ['show_me', 'hint'] as const
type OptionCardAction = (typeof OPTION)[number]
const isOption = (a: CardAction): a is OptionCardAction => (OPTION as readonly CardAction[]).includes(a)

/** The engine names some buttons itself: setup.actionLabels ("Download tutorial files"), setup.editorLabel ("Open Cursor"). */
function actionLabel(c: EngineCard, a: CardAction): string {
  const custom = c.setup?.actionLabels?.[a]
  if (custom) return custom
  if (a === 'open_editor' && c.setup?.editorLabel) return `Open ${c.setup.editorLabel}`
  // "Type this for you?" (a fix preview): the confirm types the diff into the learner's file.
  if (a === 'confirm' && c.diff) return 'Type it'
  return ACTION[a]!.label
}

/**
 * The one white primary: the preflight card's `recommended`, else the first primary kind, else the only
 * button (a lone Download is primary; next to anything else it stays quiet).
 */
function primaryOf(c: EngineCard, known: CardAction[]): CardAction | undefined {
  if (c.kind === 'preflight' && c.recommended && known.includes(c.recommended)) return c.recommended
  // A lone action becomes the primary, except option actions and Try again, which stay pastel / neutral.
  // Skip on a setup card is never the primary (A17): the item's Install is.
  const lone = known.length === 1 && !isOption(known[0]) && known[0] !== 'retry' && known[0] !== 'skip_setup' ? known[0] : undefined
  return known.find((a) => ACTION[a]!.primary) ?? lone
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

/**
 * Setup card: one row per needed item, Install on the missing ones (action install {text: tool}).
 * lead (A17): the card has no other primary, so the first missing item's button is the card's one white primary.
 */
function SetupItems({ setup, lead }: { setup: NonNullable<EngineCard['setup']>; lead?: boolean }): ReactNode {
  const installs = useCards((s) => s.installs)
  const items = setup.items.filter((x) => x.needed)
  if (items.length === 0) return null
  const first = lead ? items.find((x) => !x.ok && !installs[x.tool]?.running && x.install.method !== 'none') : undefined
  return (
    <div className="mt-[12px] flex flex-col gap-[6px] text-[13px]">
      {items.map((x) => {
        const run = x.ok ? undefined : installs[x.tool]
        const detail = x.ok ? x.version : run?.running ? (run.line ?? 'Installing…') : (run?.error ?? x.why)
        return (
          <div key={x.tool} className="flex min-h-[28px] items-center gap-[8px]">
            <span style={{ color: x.ok ? color.text : color.faint }}>{x.ok ? <Check size={13} /> : '·'}</span>
            <span className="truncate">{x.label}</span>
            {/* The reason wraps to two lines instead of being cut off (A17). */}
            <span className="line-clamp-2 min-w-0 flex-1 text-[12px] leading-[16px]" style={{ color: run?.error ? color.text : color.faint }} title={detail}>
              {detail}
            </span>
            {!x.ok && run?.running && (
              <span className="flex items-center gap-[6px] px-[9px] py-[3px] text-[12px] font-medium" style={{ color: color.faint }} aria-disabled>
                <Spinner size={12} c={color.faint} /> Installing…
              </span>
            )}
            {x === first && (
              <PrimaryButton
                label={itemLabel(x, run)}
                icon={x.install.method === 'download' || x.install.method === 'open' ? ExternalLink : Download}
                onClick={() => itemAct(x)}
              />
            )}
            {x !== first && !x.ok && !run?.running && x.install.method !== 'none' && (
              <button
                className="flex cursor-pointer items-center gap-[5px] rounded-full px-[10px] py-[3px] text-[12px] font-medium"
                style={{ background: fill.button, color: color.text }}
                onClick={() => itemAct(x)}
              >
                {x.install.method === 'download' || x.install.method === 'open' ? <ExternalLink size={12} /> : <Download size={12} />}{' '}
                {itemLabel(x, run)}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

function itemLabel(x: NonNullable<EngineCard['setup']>['items'][number], run?: Install): string {
  return x.install.method === 'download' ? 'Get it' : x.install.method === 'open' ? 'Open' : run?.error ? 'Retry' : 'Install'
}

/** Skip on a setup card (A17): a quiet text link, never a button that competes with Install. */
function QuietLink({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <button
      type="button"
      className="h-[30px] shrink-0 cursor-pointer px-[4px] text-[13px]"
      style={{ color: color.faint }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

/** How long the second tap of a TwoTap button stays armed. */
const ARM_MS = 3000

/**
 * A destructive card action as a quiet text link: the first tap only arms it ("Tap again to start over"), the
 * second within ARM_MS acts. A stray click meant for the button next to it does nothing.
 */
function TwoTap({ label, onConfirm }: { label: string; onConfirm: () => void }): ReactNode {
  const [armed, setArmed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  return (
    <button
      type="button"
      data-two-tap={armed ? 'armed' : 'idle'}
      className="mr-[12px] h-[34px] px-[4px] text-[13px] transition-colors"
      style={{ color: armed ? color.label : color.faint }}
      onClick={() => {
        clearTimeout(timer.current)
        if (armed) {
          setArmed(false)
          onConfirm()
          return
        }
        setArmed(true)
        timer.current = setTimeout(() => setArmed(false), ARM_MS)
      }}
    >
      {armed ? 'Tap again to start over' : label}
    </button>
  )
}

function CardActions({ card, actions }: { card: EngineCard; actions: CardAction[] }): ReactNode {
  const busy = useBusyIcon()
  const known = actions.filter((a) => ACTION[a])
  if (known.length === 0) return null
  const primary = primaryOf(card, known)
  const keys = bridge.platform.keys
  // Option actions (Show me / Hint) first, then quiet actions, the one white primary on the right.
  return (
    <div className="mt-[16px] flex flex-wrap items-center gap-[8px]">
      {OPTION.filter((a) => known.includes(a)).map((a) => (
        <OptionButton key={a} action={a} label={ACTION[a]!.label} kbd={keys[a]} icon={busy(a)} onClick={() => cardAct(a)} />
      ))}
      {known
        .filter((a) => a !== primary && !isOption(a) && a !== 'end_lesson')
        .map((a) => (
          a === 'skip_setup' ? <QuietLink key={a} label={actionLabel(card, a)} onClick={() => cardAct(a)} /> : <QuietButton key={a} label={actionLabel(card, a)} icon={busy(a, ACTION[a]!.Icon, true)} onClick={() => cardAct(a)} />
        ))}
      {/* "Start a new lesson" discards the save: it sits apart from Continue and needs a second tap (desktop test 3). */}
      {known.includes('end_lesson') && primary !== 'end_lesson' && <TwoTap label={actionLabel(card, 'end_lesson')} onConfirm={() => cardAct('end_lesson')} />}
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
 * lesson needs, and the engine's warning (muted, an Info glyph) when the video doesn't fit the goal.
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
      {card.warning && <Note text={card.warning} />}
    </div>
  )
}

/** A quiet notice (preflight warning, "not on screen"): muted text with a small Info glyph, no hue. */
function Note({ text }: { text: string }): ReactNode {
  return (
    <div data-note className="flex items-start gap-[7px]" style={{ color: color.label }}>
      <Info size={13} strokeWidth={1.8} className="mt-[2.5px] shrink-0" />
      <span className="min-w-0">{text}</span>
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

/** Lines of a program's output the card shows: the last ones (the engine already sends the tail). */
const OUTPUT_LINES = 8
// eslint-disable-next-line no-control-regex
const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g
const thinScroll = { scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` } as const

/**
 * What the program printed ("Run it for me", card.output): a mono block of its last OUTPUT_LINES lines, kept as
 * printed (never wrapped; a long line scrolls sideways), with a faint count of the earlier lines it leaves out.
 */
function Output({ text }: { text: string }): ReactNode {
  const all = text.replace(ANSI, '').replace(/\s+$/, '').split(/\r?\n/)
  const shown = all.slice(-OUTPUT_LINES)
  const hidden = all.length - shown.length
  return (
    <div data-output className="mt-[12px] rounded-[12px] py-[8px] font-mono text-[12px] leading-[17px]" style={{ background: fill.field }}>
      {hidden > 0 && (
        <div className="px-[12px] pb-[2px] font-sans text-[11px]" style={{ color: color.faint }}>
          {hidden} earlier line{hidden === 1 ? '' : 's'}
        </div>
      )}
      <div className="overflow-x-auto px-[12px]" style={thinScroll}>
        <div className="w-max min-w-full whitespace-pre" style={{ color: color.text }}>
          {shown.join('\n') || ' '}
        </div>
      </div>
    </div>
  )
}

/**
 * Where to go when the place isn't on screen ("Open app.py in Cursor"): up to two lines (the whole text on
 * hover past that) and an Open button (action open_editor), so "code not visible" always says what to do.
 */
function Where({ text }: { text: string }): ReactNode {
  const busy = useBusyIcon()
  return (
    <div data-where className="mt-[12px] flex items-center gap-[10px] rounded-[12px] py-[6px] pl-[12px] pr-[6px]" style={{ background: fill.field }}>
      <Info size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
      <span
        className="min-w-0 flex-1 overflow-hidden text-[13px] leading-[18px]"
        style={{ color: color.label, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}
        title={text}
      >
        {text}
      </span>
      <QuietButton label="Open" icon={busy('open_editor', ExternalLink, true)} onClick={() => cardAct('open_editor')} />
    </div>
  )
}

function Card(): ReactNode {
  const c = useCards((x) => x.card)
  const from = useCards((x) => x.cardFrom)
  if (!c) return null
  const k = tileOf(c, from)
  const actions = c.actions ?? []
  // A title that only repeats the kind or the tile ("Hint") is dropped: the body becomes the headline.
  // Long bodies fold to a few lines with a "More" that opens them in place (never cut off for good).
  const t = c.title?.trim().toLowerCase()
  const redundant = !t || t === k.label.toLowerCase() || t === (KIND[c.kind] ?? KIND.answer).label.toLowerCase()
  return (
    <div data-card={c.kind} style={{ padding: `16px ${PAD}px 16px` }}>
      <div className="flex items-start gap-[10px]">
        <KindTile k={k} />
        <div className="min-w-0 flex-1 pt-[1px]">
          {redundant ? (
            <Clamp text={c.body} lines={HEADLINE_LINES} className="text-[16px] font-medium leading-[22px] tracking-[-0.01em]" />
          ) : (
            <>
              <div className="text-[17px] font-semibold leading-[22px] tracking-[-0.01em]">{c.title}</div>
              <Clamp text={c.body} lines={BODY_LINES} className="mt-[3px] text-[14px] leading-[20px]" style={{ color: color.label }} />
            </>
          )}
          {c.guidingQuestion && <Question text={c.guidingQuestion} />}
        </div>
        <CloseButton />
      </div>
      {c.kind === 'preflight' && <Preflight card={c} />}
      {c.where && <Where text={c.where} />}
      {c.output && <Output text={c.output} />}
      {c.videoJump && (
        <div className="mt-[14px] flex">
          <OptionButton action="watch" label={`Watch ${c.videoJump.label}`} onClick={() => jumpTo(c.videoJump!.t)} />
        </div>
      )}
      {c.diff && <UnifiedDiff diff={c.diff} />}
      {c.setup && <SetupItems setup={c.setup} lead={!primaryOf(c, actions.filter((a) => ACTION[a]))} />}
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
      // Read at render time: the overlay's width decides the card's (useActive subscribes, so the island re-renders).
      get width() {
        return offtrackWidth(useOverlayWidth.getState().w)
      },
      useActive: (hover) => {
        useOverlayWidth((s) => s.w)
        const open = useCards((c) => c.offtrackOpen)
        const covered = useCards((c) => !!c.card || !!c.success || c.offtrackClosed)
        const has = useLesson((s) => !!s.offtrack)
        // Hover peeks at the off-track card only when nothing else is open: with a card up, hovering it must not
        // swap it for the off-track card under the cursor (Michael couldn't click "Open" on a hint card).
        return has && (open || (hover && !covered))
      },
      Content: Offtrack
    },
    { id: 'success', priority: 60, width: SUCCESS_W, useActive: () => useCards((c) => !!c.success), Content: Success },
    { id: 'card', priority: 50, width: CARD_W, useActive: () => useCards((c) => !!c.card), Content: Card }
  ],
  // Renders nothing: it only reports the overlay's width (see WidthProbe).
  overlayLayers: [{ id: 'cards-width', z: 1, Component: WidthProbe }]
})
