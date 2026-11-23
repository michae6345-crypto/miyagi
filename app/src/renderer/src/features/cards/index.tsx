/**
 * Feature: cards. Coach cards that grow out of the pill, in the calm black-island look (mockup 02):
 *   offtrack  layout C (Adrian): ~620 wide, two columns (one below 520). Left: ring + "Not yet", the title,
 *             the guiding question (or the body), the citation. Right: the evidence panel (Evidence.tsx):
 *             yours | expected from the diff, the failing checks and the curve, all monochrome. Under both, at
 *             level 3, "Do it for me". Explain / Show me / Hint stay in the shortcut bar while it's up (A11): a
 *             card carries only its own action. Off track has no hue anywhere.
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
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, Code2, Download, ExternalLink, File, FileCode2, Footprints, FolderGit2, Hammer, History, Info, Lightbulb, ListChecks, MessageCircle, MessageSquareText, NotebookText, Play, Search, SkipForward, SquarePlay, SquareTerminal, Undo2, Wrench, FolderOpen, RotateCcw, type LucideIcon } from 'lucide-react'
import type { PreflightInfo } from '../../../../../../shared/contracts/events'
import type { Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useThinking, type Offtrack as OfftrackPayload } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { usePressed, type ActionKind } from '../../core/shortcuts'
import { CheckList, CloseButton, CodeText, OptionButton, PrimaryButton, Spinner, StatusDot, StatusGlyph } from '../../core/ui/atoms'
import { actionTone, color, copy, fill } from '../../core/theme'
import { isLinkRow, linkRowAct, refusedLink, useDrawer, useRefusedLinks } from '../drawer/store'
import { Curve, fmt, Key, plotPoints, type Line } from './Curve'
import { BODY_LINES, Clamp, HEADLINE_LINES } from './Clamp'
import { Evidence, useHasEvidence } from './Evidence'
import { shortEditor, useFitLevel } from './fit'
import { LinkText } from './LinkText'
import { isEditor, useFrontApp } from './front'
import { useDock } from '../../core/dock'
import { useRoutedAway } from './panel'
import { act, cardAct, installAll, itemDone, jumpTo, setupFolded, setupKey, SUCCESS_MS, useCards, useOverlayWidth, useSeries, type CardAction, type Install } from './store'
import { isEditorSheet, SHEET_W, VSCodeSheet } from './VSCodeSheet'
import { drawnOnCard, rowSettled, rowWaiting } from './setupHold'
import { needsLine, planSetup, PLAN_ACTIONS, settledLine, setupBody, setupCardWidth, type SetupBtn } from './setupPlan'
import { PANEL_W } from '../drawer/geometry'
import { useNotchInfo } from '../../core/notchInfo'
import { notchOf } from '../../core/notchGeometry'
import { beat, enter, fade, press, spring } from '../../core/ui/motion'

/** Layout C: about 620 wide; below NARROW (a small display) the two columns stack. */
const OFFTRACK_MAX = 620
const NARROW = 520
const SUCCESS_W = 460
const CARD_W = 420
const PAD = 20
const COL_GAP = 16

/** A setup row's name as the card shows it (an editor through copy.editorName: VS Code copy only). */
const rowName = (x: { kind: string; label: string }): string => (x.kind === 'editor' ? copy.editorName(x.label) : x.label)

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
  return (kind, icon, quiet) => ((thinking && pressed === kind && !UNANSWERED.has(kind)) || pending === kind ? (quiet ? SpinText : SpinInk) : icon)
}

/**
 * Actions the engine never answers (open_editor just brings the editor forward): their spin is the card's own short
 * settle (store SETTLE), never a later "thinking" about something else (desktop test 5: Open spun on and on).
 */
const UNANSWERED = new Set<string>(['open_editor'])

/**
 * A neutral (non-primary) card action: same shape as PrimaryButton, quiet fill. `compact` (a row that doesn't fit,
 * A22): a round icon-only button, the label as its tooltip and accessible name. A button without an icon keeps its label.
 */
function QuietButton({ label, icon: I, onClick, compact }: { label: string; icon?: LucideIcon; onClick: () => void; compact?: boolean }): ReactNode {
  const iconOnly = compact && !!I
  return (
    <motion.button
      type="button"
      data-compact={iconOnly ? '' : undefined}
      className={`flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full text-[13px] font-medium ${iconOnly ? 'w-[30px] justify-center' : 'px-[13px]'}`}
      style={{ backgroundColor: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: press.scale }}
      transition={{ ...fade.tint, scale: spring }}
      title={iconOnly ? label : undefined}
      aria-label={iconOnly ? label : undefined}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {I && <I size={13} strokeWidth={1.8} className="shrink-0" />}
      {!iconOnly && label}
    </motion.button>
  )
}

/**
 * A card title as the engine wrote it, ready for CodeText (backticks become mono, never shown literally; Michael's
 * desktop test 4: About `Every to-do app needs a pla…`). A title cut inside code loses its closing backtick: close it.
 */
const titleText = (t: string): string => ((t.match(/`/g)?.length ?? 0) % 2 ? `${t}\`` : t)

/** The engine's Socratic nudge, under the body (off-track and engine cards alike). */
function Question({ text }: { text: string }): ReactNode {
  return (
    <div data-question className="mt-[6px] text-[13px] leading-[18px]" style={{ color: color.label }}>
      {text}
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
    <motion.div key={id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={enter(beat)}>
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
 * A lesson surface carries the help options (the video drawer's help row, the "Just teach me" panel's Help row; the
 * bottom bar is gone). While a lesson is on, a card never repeats them (Michael's review A11: the same actions showed 2-3
 * times at once); a card carries only its own action (Do it for me, Run it, Install, Continue, Check…).
 */
const useBarHelp = (): boolean => useLesson((l) => !!l.lesson)

/**
 * Layout C (Adrian picked "side by side"). Left: ring + "Not yet", the title, the guiding question (or the body),
 * the citation as one faint line. Right: the evidence panel. Under both, full width: Explain, Show me, Hint (test 6:
 * always, even with the bar up), and at level 3 with apply_fix, the one white "Do it for me": the hint ladder's
 * top rung, which only this card offers. Below NARROW the panel drops under the left column.
 */
function Diagnosis({ o, checks }: { o: OfftrackPayload; checks: ReturnType<typeof useLesson.getState>['checks'] }): ReactNode {
  const busy = useBusyIcon()
  const keys = bridge.platform.keys
  // Michael, test 6: the Not yet card carries its own Hint / Show me again (the bar's alone read as "no actions"),
  // limited to what the engine offers when it lists any of them.
  const offered = OFFTRACK_OPTIONS.filter((x) => o.actions.includes(x.action))
  const options = offered.length > 0 ? offered : OFFTRACK_OPTIONS
  const width = useOfftrackWidth()
  const narrow = width < NARROW
  const inner = width - PAD * 2
  // Precise: only what's failing (with your value), not the checks that already pass.
  const failing = checks.filter((c) => c.status === 'fail')
  // No real code or value to compare (review A5): no evidence column, so the diagnosis takes the card's full width.
  const hasEvidence = useHasEvidence(o, failing)
  const leftW = narrow || !hasEvidence ? inner : Math.round((inner - COL_GAP) * 0.47)
  const rightW = narrow ? inner : inner - COL_GAP - leftW
  // "Do it for me" = apply_fix, offered at the top of the hint ladder (level 3; no level = an older engine, trust actions).
  const canFix = o.actions.includes('apply_fix') && (o.level ?? 3) === 3
  return (
    <div data-card="offtrack" data-layout={narrow ? 'stacked' : hasEvidence ? 'side-by-side' : 'single'} style={{ width, padding: `16px ${PAD}px 16px` }}>
      <div className="flex h-[22px] items-center gap-[8px] text-[13px] leading-none">
        <StatusDot status="offtrack" size={8} />
        {/* White, never the watching gray (A22): Not yet must not read as Watching. Still no hue. */}
        <span className="font-medium" style={{ color: color.text }}>
          Not yet
        </span>
        <span className="flex-1" />
        <CloseButton />
      </div>

      <div className={`mt-[10px] flex ${narrow ? 'flex-col gap-[14px]' : 'items-start'}`} style={narrow ? undefined : { gap: COL_GAP }}>
        <div className="min-w-0 flex-1" style={narrow ? undefined : { maxWidth: leftW }}>
          <div className="text-[18px] font-semibold leading-[23px] tracking-[-0.01em]"><CodeText text={titleText(o.title)} /></div>
          {/* The body folds to 3 lines with a "More" (Clamp), never cut off for good (A22). */}
          {/* Test 6: the body is never hidden behind the question, and both open in place (Clamp's "More"). */}
          {o.guidingQuestion && <Question text={o.guidingQuestion} />}
          {o.body && o.body !== o.guidingQuestion && (
            <Clamp text={o.body} lines={3} className="mt-[3px] text-[14px] leading-[20px]" style={{ color: color.label }} />
          )}

          {o.citation && (
            <div className="mt-[12px] flex min-w-0 items-start gap-[6px] text-[12px] leading-[16px]" style={{ color: color.faint }}>
              <BookOpen size={12} className="mt-[2px] shrink-0" />
              {/* Up to two lines, so a source like "§8.4 (breaking symmetry)" isn't cut mid-word. */}
              <LinkText label={o.citation.label} url={o.citation.url} wrap />
            </div>
          )}
        </div>

        {/* At level 2 the next rung brings the diff: keep its room so the card doesn't jump. Otherwise no empty room. */}
        <Evidence o={o} failing={failing} width={rightW} reserveDiff={o.level === 2} />
      </div>

      {/* Overlay round: the options and the one white "Do it for me" share one row, the primary on the right edge
          (it used to drop to a line of its own under the options). */}
      {(options.length > 0 || canFix) && (
        <div data-options className="mt-[16px] flex flex-wrap items-center gap-[8px]">
          {options.map((x) => (
            <OptionButton key={x.action} action={x.action} label={x.label} kbd={keys[x.action]} icon={busy(x.action)} onClick={() => act(x.action)} />
          ))}
          {canFix && (
            <div data-fix className="ml-auto flex">
              <PrimaryButton label={ACTION.apply_fix!.label} icon={busy('apply_fix', ACTION.apply_fix!.Icon)} onClick={() => act('apply_fix')} />
            </div>
          )}
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
  const { after, name } = useSeries(undefined, s?.since)
  // A "Just teach me" lesson has no video to pick up.
  const hasVideo = useLesson((l) => l.lesson?.mode !== 'lesson')
  if (!s) return null
  const showCurve = !!after && after.points.length > 1
  return (
    <div data-card="success" className="relative" style={{ padding: `16px ${PAD}px 14px` }}>
      <Header mark={<StatusDot status="passed" size={6} />} label={`Step ${s.index + 1} done`} tone={color.green} step={false} />
      {/* The step's real result (Michael, test 7): "Loss 0.82 to 0.0009" when this step's run has a curve; the header
          already says "Step N done", so without a result there's no title line. */}
      {showCurve && after ? (
        <Title>{`${capital(name)} ${fmt(after.points[0].value)} to ${fmt(after.points[after.points.length - 1].value)}`}</Title>
      ) : null}
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
        style={{ background: color.faint }} // gray: green only means passed (test 10 polish, item 8)
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
 * Header per card kind: a small icon tile on the card's header line (answers add a faint eyebrow, EYEBROW). The options that made the card keep
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

function KindTile({ k, size = 24 }: { k: Tile; size?: number }): ReactNode {
  return (
    <span
      className="grid shrink-0 place-items-center"
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), ...(k.tone ? { background: k.tone, color: color.onPastel } : { background: fill.tile, color: color.text }) }}
      aria-label={k.label}
      title={k.label}
    >
      <k.Icon size={size > 22 ? 13 : 12} strokeWidth={1.9} />
    </span>
  )
}

/**
 * Cards that answer the learner (Explain, Hint, an answer, Show me's where-to-work) say what answered in a faint
 * eyebrow beside their tile (Michael's review A23); status cards (step, run, setup…) carry the tile alone.
 */
const EYEBROW = new Set<Tile>([KIND.explain, KIND.hint, KIND.answer, KIND.where])

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
  show_me: { label: 'Show me' },
  // Smart setup (Nov 22): a licensed app (AutoCAD) is never installed. The engine labels them (setup.actionLabels:
  // "Get AutoCAD", "Try FreeCAD"); with no text the engine picks the first app row still waiting. On a setup card the
  // calm plan (setupPlan.ts) draws them and picks the one white primary: Get it, or I have it when the scan saw the app.
  have_it: { label: 'I have it', Icon: Check },
  get_it: { label: 'Get it', Icon: ExternalLink },
  alternative: { label: 'Free alternative', Icon: Download }
}

/** Card actions drawn as pastel OptionButtons with keycaps (like the off-track card), not as quiet buttons. */
const OPTION = ['show_me', 'hint'] as const
type OptionCardAction = (typeof OPTION)[number]
const isOption = (a: CardAction): a is OptionCardAction => (OPTION as readonly CardAction[]).includes(a)

/**
 * The engine names some buttons itself: setup.actionLabels ("Download tutorial files"), setup.editorLabel ("Open Visual Studio Code", through copy.editorName).
 * `short` (a row that doesn't fit on one line, A22): our own short label instead ("Download", "Open VS Code").
 */
function actionLabel(c: EngineCard, a: CardAction, short?: boolean): string {
  const custom = c.setup?.actionLabels?.[a]
  if (custom && !short) return custom
  // v2: VS Code copy only: an unsupported editor's name never reaches a button (copy.editorName).
  if (a === 'open_editor' && c.setup?.editorLabel) {
    const ed = copy.editorName(c.setup.editorLabel)
    return `Open ${short ? shortEditor(ed) : ed}`
  }
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
  // A setup card with something still to install: that item's Install is the one white primary (SetupItems lead),
  // and Open VS Code steps back to a quiet button. Michael's run (Sun 03:13): the white button was Open VS Code, the
  // NumPy row's Install a small grey one, and the engine only ever got skip_setup.
  // A licensed app's row (AutoCAD) leads nothing: its buttons are the card's own (I have it is the primary).
  if (c.setup?.items.some((x) => rowWaiting(x) && x.install.method !== 'none' && !drawnOnCard(c.actions, x))) return undefined
  // A lone action becomes the primary, except option actions and Try again, which stay pastel / neutral.
  // Skip on a setup card is never the primary (A17): the item's Install is. A lone Skip step stays quiet too (test 10
  // polish, item 3: a video lesson's Not yet card turned it into the white button).
  const lone = known.length === 1 && !isOption(known[0]) && known[0] !== 'retry' && known[0] !== 'skip_setup' && known[0] !== 'skip_step' ? known[0] : undefined
  // A setup card with everything ready: "Open <editor>" is never its primary (desktop test 5), it stays quiet.
  const ready = setupReady(c)
  return known.find((a) => ACTION[a]!.primary && !(ready && a === 'open_editor')) ?? (ready && lone === 'open_editor' ? undefined : lone)
}

/** A setup card that says everything is ready ("Ready to go"): every needed item is installed and ok, or settled. */
const setupReady = (c: EngineCard): boolean => c.kind === 'setup' && !!c.setup && c.setup.items.every((x) => !rowWaiting(x))

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
 * One setup row's button (contract SetupItem.install): "download" (a download page) and "open" (a web app) go to
 * main's setup list (drawer/store linkRowAct; never the engine's open_in_browser, app-harden), the rest install
 * (install {text: tool}).
 */
function itemAct(x: NonNullable<EngineCard['setup']>['items'][number]): void {
  // A link main refused (not on its setup list) is copied instead of opened.
  if (isLinkRow(x.install.method)) linkRowAct(x.tool, x.install.url)
  else cardAct('install', x.tool)
}

function itemLabel(x: NonNullable<EngineCard['setup']>['items'][number], run?: Install): string {
  if (isLinkRow(x.install.method) && refusedLink(useRefusedLinks.getState().byKey, x.tool, x.install.url) !== undefined) return 'Copy link'
  return x.install.method === 'download' ? 'Get it' : x.install.method === 'open' ? 'Open' : run?.error ? 'Retry' : 'Install'
}

/** A refused download link's row text: where it would have gone, never opened (app-harden). */
const refusedLine = (url: string): string => (url ? `Not on miyagi's list, so not opened: ${url}` : 'Not a web link, so not opened.')

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

/**
 * Setup card: one row per needed item (a mark, the tool, why or how it's going). The card's one white primary and its
 * quiet second buttons live in the action row (setupPlan.ts, CardActions): a row the plan owns carries no button of
 * its own. Other rows still missing keep a small grey button. Rows never move (A8: every row 34 px).
 */
function SetupItems({ card }: { card: EngineCard }): ReactNode {
  const installs = useCards((s) => s.installs)
  // Install all's run (store installAll): the rows still to go, in row order. It lives in the store, so a re-sent or
  // re-mounted card keeps it going.
  const queue = useCards((s) => s.queue)
  const refused = useRefusedLinks((s) => s.byKey)
  const setup = card.setup!
  const actions = card.actions
  // Rows come in a steady order (store steadySetup: by first appearance; an installed row stays as a check).
  const items = setup.items.filter((x) => x.needed)
  if (items.length === 0) return null
  const owns = planSetup(card, installs, !!queue).owns
  // A row the learner settled ("I have it", FreeCAD instead), a licensed row whose buttons are the card's own, and a
  // row the action row's primary or second button acts on carry no button here.
  const quiet = (x: (typeof items)[number]): boolean => rowSettled(x) || drawnOnCard(actions, x) || owns.includes(x.tool)
  return (
    <div className="mt-[12px] flex flex-col gap-[6px] text-[13px]">
      {items.map((x) => {
        const done = itemDone(x, installs) || rowSettled(x)
        const run = x.ok ? undefined : installs[x.tool]
        const waiting = !done && !run?.running && !!queue?.tools.includes(x.tool)
        // Until the first progress line, the reason stays (the slot already says "Installing...").
        const refusedUrl = refusedLink(refused, x.tool, x.install.url)
        const detail = settledLine(x) ?? (done ? (x.version ?? run?.version) : refusedUrl !== undefined ? refusedLine(refusedUrl) : run?.running ? (run.line ?? x.why) : (run?.error ?? x.why))
        return (
          // A8: every row is exactly 34 px (two 16 px detail lines fit), the mark sits in a fixed 13 px column, so
          // nothing moves while a row installs.
          <div key={x.tool} data-setup-row={x.tool} data-waiting={!done || undefined} className="flex h-[34px] items-center gap-[8px] overflow-hidden">
            <span className="flex w-[13px] shrink-0 justify-center" style={{ color: done ? color.text : color.faint }}>{done ? <Check size={13} /> : '·'}</span>
            <span className="shrink-0 truncate font-medium">{rowName(x)}</span>
            {/* The reason wraps to two lines instead of being cut off (A17). */}
            <span className="line-clamp-2 min-w-0 flex-1 text-[12px] leading-[16px]" style={{ color: run?.error ? color.text : color.faint }} title={detail}>
              {detail}
            </span>
            {!done && run?.running && (
              <span className="flex h-[30px] shrink-0 items-center gap-[6px] px-[4px] text-[12px] font-medium" style={{ color: color.faint }} aria-disabled>
                <Spinner size={12} c={color.faint} /> Installing…
              </span>
            )}
            {waiting && (
              <span className="flex h-[30px] shrink-0 items-center px-[4px] text-[12px] font-medium" style={{ color: color.faint }} aria-disabled>
                Waiting
              </span>
            )}
            {!done && !run?.running && !waiting && x.install.method !== 'none' && !quiet(x) && (
              <button
                className="flex shrink-0 cursor-pointer items-center gap-[5px] rounded-full px-[10px] py-[3px] text-[12px] font-medium"
                style={{ background: fill.button, color: color.text }}
                onMouseDown={(e) => e.preventDefault()}
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

/** A plan button (setupPlan.ts): install a row, Install all, open a page from main's list, or a card action. */
function planAct(b: SetupBtn): void {
  if (b.do === 'install') cardAct('install', b.tool)
  else if (b.do === 'install_all') installAll()
  else if (b.do === 'link') linkRowAct(b.tool, b.url)
  else cardAct(b.action, b.tool)
}

function planIcon(b: SetupBtn): LucideIcon {
  if (b.do === 'link') return ExternalLink
  if (b.do === 'card') return b.action === 'have_it' ? Check : b.action === 'get_it' ? ExternalLink : Download
  return Download
}

/** A link main refused (not on its setup list) is copied instead of opened: the button says so. */
function usePlanLabel(): (b: SetupBtn) => string {
  const refused = useRefusedLinks((s) => s.byKey)
  return (b) => (b.do === 'link' && refusedLink(refused, b.tool, b.url) !== undefined ? 'Copy link' : b.label)
}

/** How long a TwoTap stays armed after the first tap: long enough for a slow, deliberate second tap. */
const ARM_MS = 10_000

/**
 * Which TwoTap is armed (its armKey) and since when. Kept outside the component, so a re-sent or re-mounted card
 * keeps the armed button (Michael's desktop test 4: the second tap on "Tap again to start over" did nothing).
 */
const useArm = create<{ key?: string; at: number }>(() => ({ at: 0 }))

/**
 * A destructive card action as a quiet text link. The first tap only arms it: the link becomes a real button
 * ("Yes, start over") for ARM_MS, and pressing that acts. A stray click meant for the button next to it does nothing.
 */
function TwoTap({ armKey, label, armedLabel, onConfirm }: { armKey: string; label: string; armedLabel: string; onConfirm: () => void }): ReactNode {
  const armed = useArm((s) => s.key === armKey)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => {
      if (useArm.getState().key === armKey) useArm.setState({ key: undefined })
    }, Math.max(0, useArm.getState().at + ARM_MS - Date.now()))
    return () => clearTimeout(t)
  }, [armed, armKey])
  if (armed)
    return (
      <span data-two-tap="armed" className="mr-[12px] flex">
        <QuietButton
          label={armedLabel}
          icon={RotateCcw}
          onClick={() => {
            useArm.setState({ key: undefined })
            onConfirm()
          }}
        />
      </span>
    )
  return (
    <button
      type="button"
      data-two-tap="idle"
      className="mr-[12px] h-[30px] cursor-pointer px-[4px] text-[13px] transition-colors"
      style={{ color: color.faint }}
      // Like every other card button: no focus grab on press (the overlay never takes focus from the editor).
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => useArm.setState({ key: armKey, at: Date.now() })}
    >
      {label}
    </button>
  )
}

/** The launcher is open (main's signals to this window; the island hides meanwhile). */
let launcherShown = false
bridge.on('launcher:open', () => void (launcherShown = true))
bridge.on('launcher:closed', () => void (launcherShown = false))

/** Main takes no explicit open from a renderer, only launcher:toggle: toggle only while it's closed, so it never closes. */
function openLauncher(): void {
  if (!launcherShown) bridge.emit('launcher:toggle')
}

/** Longest "Yes, start over" waits for the engine to drop a loaded lesson before it lets the launcher be. */
const START_OVER_WAIT_MS = 4000

/**
 * "Yes, start over" (Michael's review A7): discard the save, then open the launcher (its input takes the caret on
 * open) so the next lesson can be typed right away. The launcher picks search or ask from the lesson it sees as it
 * opens, so a lesson still loaded here opens it only once lesson.ended has blanked it.
 */
function startOver(): void {
  cardAct('end_lesson')
  // cardAct drops a press while another button on the card waits for the engine: nothing was sent.
  if (useCards.getState().pending?.kind !== 'end_lesson') return
  if (!useLesson.getState().lesson) return openLauncher()
  const t = setTimeout(() => off(), START_OVER_WAIT_MS)
  const off = useLesson.subscribe((s) => {
    if (s.lesson) return
    off()
    clearTimeout(t)
    openLauncher()
  })
}

function CardActions({ card, actions }: { card: EngineCard; actions: CardAction[] }): ReactNode {
  const busy = useBusyIcon()
  // Hint / Show me (the judge's "Not yet" card) are the bar's while it's up (A11): the card keeps only its own buttons.
  const barHelp = useBarHelp()
  const installs = useCards((s) => s.installs)
  const queue = useCards((s) => s.queue)
  const planLabel = usePlanLabel()
  // The calm setup card (setupPlan.ts): the plan draws Install / Get it / I have it / the free alternative itself and
  // picks the one white primary; the card's other actions (Download, Open VS Code) stay quiet beside it.
  const setup = card.kind === 'setup'
  const plan = setup ? planSetup(card, installs, !!queue) : undefined
  const known = actions.filter((a) => ACTION[a] && !(barHelp && isOption(a)) && !(setup && PLAN_ACTIONS.has(a)))
  const primary = plan?.primary ? undefined : primaryOf(card, known)
  const keys = bridge.platform.keys
  const row = useRef<HTMLDivElement>(null)
  const planned = plan?.primary ? [planLabel(plan.primary)] : []
  // One row, always (A22): too wide, the labels go short (1), then the quiet buttons go icon-only (2). Never a wrap.
  const fit = useFitLevel(row, `${known.join()}|${known.map((a) => actionLabel(card, a)).join()}|${planned.join()}`, 2)
  if (known.length === 0 && planned.length === 0 && !plan?.secondary.length) return null
  const short = fit >= 1
  const kindOf = (b: SetupBtn): string => (b.do === 'card' ? b.action : b.do)
  // Option actions (Show me / Hint) first, then quiet actions, the one white primary on the right. A setup card's
  // second choices (Try FreeCAD, I have it) sit on their own line above, full labels, so the card can be narrow between
  // the drawer and the player and still say every choice in words.
  return (
    <>
    {plan && plan.secondary.length > 0 && (
      <div data-setup-options className="mt-[14px] flex flex-wrap items-center gap-[8px]">
        {plan.secondary.map((b) => (
          <QuietButton key={`plan-${kindOf(b)}-${b.label}`} label={planLabel(b)} icon={busy(kindOf(b), planIcon(b), true)} onClick={() => planAct(b)} />
        ))}
      </div>
    )}
    <div ref={row} data-actions data-fit={fit || undefined} className={`${plan?.secondary.length ? 'mt-[10px]' : 'mt-[16px]'} flex items-center gap-[8px]`}>
      {OPTION.filter((a) => known.includes(a)).map((a) => (
        <OptionButton key={a} action={a} label={ACTION[a]!.label} kbd={short ? undefined : keys[a]} icon={busy(a)} onClick={() => cardAct(a)} />
      ))}
      {known
        .filter((a) => a !== primary && !isOption(a) && a !== 'end_lesson')
        .map((a) => (
          a === 'skip_setup' ? (
            <QuietLink key={a} label={actionLabel(card, a, short)} onClick={() => cardAct(a)} />
          ) : (
            <QuietButton key={a} label={actionLabel(card, a, short)} icon={busy(a, ACTION[a]!.Icon, true)} compact={fit >= 2} onClick={() => cardAct(a)} />
          )
        ))}
      {/* "Start a new lesson" discards the save: it sits apart from Continue and needs a second tap (desktop test 3),
          then opens the launcher for the next one (A7). */}
      {known.includes('end_lesson') && primary !== 'end_lesson' && <TwoTap armKey={`${card.kind}:${card.title}`} label={actionLabel(card, 'end_lesson')} armedLabel={card.kind === 'resume' ? 'No, start a new lesson' : 'Start over'} onConfirm={startOver} />}
      <span className="flex-1" />
      {plan?.primary?.do === 'install_all' && queue ? (
        <span className="flex h-[30px] items-center gap-[6px] px-[9px] text-[12px] font-medium" style={{ color: color.faint }} aria-disabled>
          <Spinner size={12} c={color.faint} /> Installing all…
        </span>
      ) : (
        plan?.primary && <PrimaryButton label={planLabel(plan.primary)} icon={busy(kindOf(plan.primary), planIcon(plan.primary))} onClick={() => planAct(plan.primary!)} />
      )}
      {primary && <PrimaryButton label={actionLabel(card, primary, short)} icon={busy(primary, ACTION[primary]!.Icon)} onClick={() => cardAct(primary)} />}
    </div>
    </>
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
        <div className="line-clamp-2" style={{ color: color.label }} title={needs.map((x) => x.label).join(', ')}>
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
 * Where to go when the place isn't on screen ("Open app.py in VS Code"): up to two lines (the whole text on
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

// ---------------------------------------------------------------------------
// Chip: a step card the drawer already shows (Michael's review A4)
// ---------------------------------------------------------------------------

/** The chip's text is cut past this width (the full card is one tap away). */
const CHIP_TEXT_W = 240

/** A card across re-sends (the engine re-sends the same step card): a chip the learner opened stays open. */
const cardKey = (c: EngineCard): string => `${c.kind}:${c.stepId ?? ''}:${c.title}`

/** The chip the learner tapped open (its cardKey). */
const useOpened = create<{ key?: string }>(() => ({}))

/** The step the open drawer shows (its id, title and instructions), or undefined when the drawer isn't on a step. */
type Shown = { id: string; title: string; instructions: string }

/** Lowercase words only, so "Add the XOR data." matches "add the `XOR` data". */
const words = (s: string | undefined): string =>
  (s ?? '')
    .toLowerCase()
    .replace(/[`"'“”‘’.,:;!?…()[\]]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

/** The card only repeats what the drawer shows for that step: its text holds the step's title or its instructions. */
function repeatsDrawer(c: EngineCard, shown: Shown): boolean {
  const said = words(`${c.title ?? ''} ${c.body ?? ''}`)
  const title = words(shown.title)
  const how = words(shown.instructions)
  const body = words(c.body)
  return (title.length >= 8 && said.includes(title)) || (how.length >= 12 && (said.includes(how) || (body.length >= 12 && how.includes(body))))
}

/**
 * "Shrink a card to a chip when the drawer already shows the same content" (A4). Only a card that adds nothing to the
 * open drawer folds: a step or hint card the engine sent on its own (not one the learner asked for), for the step the
 * drawer shows, with no buttons (nothing to hide behind the tap), whose text just repeats that step's title or
 * instructions (e.g. the "Start here" nudge). The judge's "Not yet", "Wrong folder?", "Run it" and every card with a
 * button stay full: the drawer doesn't say what they say. Never once tapped open.
 */
function folds(c: EngineCard | undefined, cardFrom: string | undefined, shown: Shown | undefined, opened: string | undefined): boolean {
  if (!c || !shown || cardFrom || (c.kind !== 'step' && c.kind !== 'hint')) return false
  if (c.stepId && c.stepId !== shown.id) return false
  if ((c.actions ?? []).length > 0 || c.diff || c.output || c.where || c.videoJump) return false
  if (!repeatsDrawer(c, shown)) return false
  return cardKey(c) !== opened
}

/** The step the open drawer shows, or undefined (the drawer is closed, on a concept, or there's no step). */
function drawerShows(): Shown | undefined {
  const d = useDrawer.getState()
  const l = useLesson.getState()
  return d.open && !d.concept && l.lesson && l.stepId ? { id: l.stepId, title: l.stepTitle, instructions: l.instructions } : undefined
}

/**
 * The step the drawer showed when the card folded (its cardKey + that step). The card keeps folding against it when the
 * drawer or the lesson panel closes: hiding the side surfaces (Esc, the panel's hide key, a click) must not grow the
 * island into the full card (Michael, Nov 21: "the top island expands"). The learner's tap still opens it; a different
 * card, or the same one re-sent with something the drawer doesn't say (a button, a diff), is judged afresh.
 */
const useFolded = create<{ key?: string; shown?: Shown }>(() => ({}))
const stillFolded = (c: EngineCard | undefined, cardFrom: string | undefined, f: { key?: string; shown?: Shown }, opened: string | undefined): boolean =>
  !!c && !!f.key && cardKey(c) === f.key && folds(c, cardFrom, f.shown, opened)

/** Is the card a chip right now? (The island reads it through the card mode's width.) */
function isChip(): boolean {
  const s = useCards.getState()
  const opened = useOpened.getState().key
  return setupFolded(s) || folds(s.card, s.cardFrom, drawerShows(), opened) || stillFolded(s.card, s.cardFrom, useFolded.getState(), opened)
}

// Remember the card the moment it folds (before anything closes the drawer), so it keeps folding without it.
function noteFold(): void {
  const s = useCards.getState()
  const shown = drawerShows()
  if (!s.card || !shown || !folds(s.card, s.cardFrom, shown, useOpened.getState().key)) return
  const key = cardKey(s.card)
  const f = useFolded.getState()
  if (f.key !== key || f.shown?.id !== shown.id || f.shown.title !== shown.title || f.shown.instructions !== shown.instructions) useFolded.setState({ key, shown })
}
for (const st of [useCards, useDrawer, useLesson, useOpened] as { subscribe: (fn: () => void) => () => void }[]) st.subscribe(noteFold)

/** isChip() as a hook: re-renders on every input (the card, the drawer, the step, a tap). */
function useChip(): boolean {
  const card = useCards((x) => x.card)
  const cardFrom = useCards((x) => x.cardFrom)
  const drawerOnStep = useDrawer((d) => d.open && !d.concept)
  const id = useLesson((l) => (l.lesson ? l.stepId : undefined))
  const title = useLesson((l) => l.stepTitle)
  const instructions = useLesson((l) => l.instructions)
  const opened = useOpened((o) => o.key)
  const folded = useFolded()
  const setupChip = useCards(setupFolded)
  return setupChip || folds(card, cardFrom, drawerOnStep && id ? { id, title, instructions } : undefined, opened) || stillFolded(card, cardFrom, folded, opened)
}

/**
 * The card folded to a pill-sized row: its kind tile and a short title, ✕ still closes it. A tap on the row opens the
 * full card (the island springs back out to it).
 */
function Chip({ c, k }: { c: EngineCard; k: Tile }): ReactNode {
  const t = c.title?.trim()
  // A folded setup card says what it still needs ("Needs AutoCAD"), the one quiet line about setup outside its card.
  const needs = c.kind === 'setup' ? needsLine(c, rowName) : undefined
  const text = needs ?? (t && t.toLowerCase() !== k.label.toLowerCase() ? titleText(t) : c.body)
  return (
    <div data-card={c.kind} data-chip className="flex h-[34px] items-center gap-[8px] whitespace-nowrap pl-[5px] pr-[6px]">
      <button
        type="button"
        className="flex min-w-0 cursor-pointer items-center gap-[9px] opacity-90 transition-opacity duration-150 hover:opacity-100"
        style={{ color: color.text }}
        // Like every other card button: no focus grab on press.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => (c.kind === 'setup' ? useCards.setState({ setupFold: { key: setupKey(c), open: true } }) : useOpened.setState({ key: cardKey(c) }))}
        title={c.body}
      >
        <KindTile k={k} />
        {/* Desktop test 9, A5: wraps to two lines (both fit the 34 px row) instead of "Import libraries and load MNI…". */}
        <span className="line-clamp-2 whitespace-normal text-left text-[13px] font-medium leading-[15px]" style={{ maxWidth: CHIP_TEXT_W }} title={t || c.body}>
          <CodeText text={text} />
        </span>
      </button>
      <CloseButton />
    </div>
  )
}

function Card(): ReactNode {
  const c = useCards((x) => x.card)
  const from = useCards((x) => x.cardFrom)
  const chip = useChip()
  if (!c) return null
  const k = tileOf(c, from)
  if (chip)
    return (
      <Swap id="chip">
        <Chip c={c} k={k} />
      </Swap>
    )
  return (
    <Swap id="card">
      <FullCard c={c} k={k} />
    </Swap>
  )
}

function FullCard({ c, k }: { c: EngineCard; k: Tile }): ReactNode {
  const installs = useCards((s) => s.installs)
  if (isEditorSheet(c, installs)) return <VSCodeSheet card={c} />
  return <EngineCardBody c={c} k={k} />
}

function EngineCardBody({ c, k }: { c: EngineCard; k: Tile }): ReactNode {
  const front = useFrontApp((f) => f.app)
  // A ready setup card doesn't offer "Open <editor>" while that editor is the app in front (desktop test 5).
  const opened = setupReady(c) && isEditor(front, c.setup?.editorLabel)
  const actions = (c.actions ?? []).filter((a) => !(opened && a === 'open_editor'))
  // A title that only repeats the kind or the tile ("Hint") is dropped: the body becomes the headline.
  // Long bodies fold to a few lines with a "More" that opens them in place (never cut off for good).
  const t = c.title?.trim().toLowerCase()
  const redundant = !t || t === k.label.toLowerCase() || t === (KIND[c.kind] ?? KIND.answer).label.toLowerCase()
  // The setup card's body: what an older engine said that the card can't back up is dropped (setupBody), and it reads
  // in three lines at most: the rows and buttons say the rest.
  const body = c.kind === 'setup' ? setupBody(c) : c.body
  const bodyLines = c.kind === 'setup' ? 3 : BODY_LINES
  return (
    <div data-card={c.kind} style={{ padding: `16px ${PAD}px 16px` }}>
      {/* One left edge (A23): the tile (and its eyebrow) sit on the header line, like the off-track card's ring and
          "Not yet", so the title, the body and every row and button under them start at the card's padding. */}
      <div data-card-head className="flex h-[22px] items-center gap-[8px]">
        <KindTile k={k} size={22} />
        {EYEBROW.has(k) && (
          <span data-eyebrow className="truncate text-[12px] font-medium" style={{ color: color.faint }}>
            {k.label}
          </span>
        )}
        <span className="min-w-[8px] flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[10px] min-w-0">
        {redundant ? (
          <Clamp text={body} lines={HEADLINE_LINES} className="text-[16px] font-medium leading-[22px] tracking-[-0.01em]" />
        ) : (
          <>
            <div className="line-clamp-2 text-[17px] font-semibold leading-[22px] tracking-[-0.01em]" title={c.title}><CodeText text={titleText(c.title)} /></div>
            {body && <Clamp text={body} lines={bodyLines} className="mt-[3px] text-[14px] leading-[20px]" style={{ color: color.label }} />}
          </>
        )}
        {c.guidingQuestion && <Question text={c.guidingQuestion} />}
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
      {c.setup && <SetupItems card={{ ...c, actions }} />}
      {c.setup?.resources && <Resources resources={c.setup.resources} />}
      {/* The where line has its own Open button: don't repeat it below. */}
      <CardActions card={c} actions={c.where ? actions.filter((a) => a !== 'open_editor') : actions} />
      {c.waiting && <Waiting text={c.waiting} />}
    </div>
  )
}

/**
 * v2 Err-KernelInContext: what the engine is waiting for ("Watching for a kernel to start"), as the card's footer under
 * a hairline. The watching glyph is the dashed gray ring (decision 5: never a spinner); miyagi rechecks by itself, so
 * there's nothing to press.
 */
function Waiting({ text }: { text: string }): ReactNode {
  return (
    <div role="status" data-waiting className="mt-[16px] flex items-center gap-[8px] border-t pt-[12px]" style={{ borderColor: color.hairline }}>
      <StatusGlyph state="watching" size={14} />
      <span className="min-w-0 truncate text-[12px]" style={{ color: color.label }} title={text}>
        {text}
      </span>
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
        const o = useLesson((s) => s.offtrack)
        const has = !!o
        // v2 (A2): the docked lesson panel draws Not yet itself (Les-NotYet); the pill says "Not yet". A1 sees the live
        // off-track, so one carrying a fix ("Do it for me") stays on the island.
        const routed = useRoutedAway('offtrack', o)
        // Collapsed to the Mini pill, hovering it is how the learner reaches its click (open the panel): no peek there,
        // or in Not yet, when they most want the panel back, the off-track card would cover Mini under the cursor.
        const mini = useDock((d) => d.collapsed)
        // Hover peeks at the off-track card only when nothing else is open: with a card up, hovering it must not
        // swap it for the off-track card under the cursor (Michael couldn't click "Open" on a hint card).
        return has && !routed && (open || (hover && !covered && !mini))
      },
      Content: Offtrack
    },
    {
      id: 'success',
      priority: 60,
      width: SUCCESS_W,
      // Decision 7: with the panel shown, Les-Passed renders inside it, not on the island; collapsed to the Mini pill,
      // the step-passed island card is the progress feature's (A8, priority 55), so this one stays out of its way.
      useActive: () => {
        const routed = useRoutedAway('success')
        const mini = useDock((d) => d.collapsed)
        return useCards((c) => !!c.success) && !routed && !mini
      },
      Content: Success
    },
    {
      id: 'card',
      priority: 50,
      // A chip is pill-sized (no width: 34 tall, hugging its row); the VS Code sheet is 352 (Err-VSCodeSetup). Read
      // at render time like the off-track card's.
      get width() {
        const s = useCards.getState()
        if (isChip()) return undefined
        if (isEditorSheet(s.card, s.installs)) return SHEET_W
        if (s.card?.kind !== 'setup') return CARD_W
        const l = useLesson.getState().lesson
        const d = useDrawer.getState()
        const n = notchOf({ notch: useNotchInfo.getState().notch })
        return setupCardWidth(useOverlayWidth.getState().w, !!l && l.mode !== 'lesson', { open: d.open, at: d.at, w: PANEL_W }, CARD_W, n ? n.x + n.width / 2 : undefined)
      },
      useActive: () => {
        // The setup card's width follows the drawer, the lesson kind and the overlay (setupCardWidth).
        useOverlayWidth((s) => s.w)
        useDrawer((d) => `${d.open}:${d.at}`)
        useLesson((l) => l.lesson?.mode)
        useNotchInfo((n) => n.notch)
        useChip() // subscribes, so the island re-reads the width when the card folds or opens
        useCards((c) => isEditorSheet(c.card, c.installs)) // and when a setup card turns into the sheet or back
        const card = useCards((c) => c.card)
        // A card the docked panel draws itself (Les-Hint) skips the island while the panel shows (no double render), and
        // is spent there (store.ts consumeRouted), so collapsing to Mini doesn't replay it out of the pill.
        const routed = useRoutedAway(card?.kind, card)
        return !!card && !routed
      },
      Content: Card
    }
  ],
  // Renders nothing: it only reports the overlay's width (see WidthProbe).
  overlayLayers: [{ id: 'cards-width', z: 1, Component: WidthProbe }]
})

/** "loss" → "Loss" for a title line. */
function capital(t?: string): string {
  const w = t || 'Loss'
  return w.charAt(0).toUpperCase() + w.slice(1)
}
