/**
 * Feature: onboarding. Guided setup: one step per screen (steps.ts), after the intro on the first launch.
 *
 *   header   the tree (it travels here from the intro: shared layoutId) and the wordmark; "1 of 4" and four bars
 *            (green = done, white = this step, the track = not reached; done and earlier bars jump back)
 *   body     the step's icon, a big title, one line of why, the live status (glyph + word + sentence) and, when the
 *            window is wide enough, a picture of what the learner will see (Illustration.tsx)
 *   footer   Back (chrome), an optional quiet second action (Skip for now, Open System Settings), the ONE primary
 *
 * Moving: a step that turns green while it is on screen shows Done for ~1 s (a thin bar fills under the status), then
 * the walk moves to the next step not done. Steps already done are skipped when the walk starts (a reopen). Back
 * always works; Continue on a done or unknown step moves on. The last step (the engine) has nothing to click: it
 * advances on its own once it is green. Enter presses the primary (unless focus is on another button).
 * Motion: steps slide 24 px on the house spring with a fade, their parts rise in with a 35 ms stagger; reduced motion
 * keeps only the fades (MotionConfig in main.tsx). Transform and opacity only.
 *
 * chrome 'flow' (the one-window first run, features/shell/flow): no header of its own (the flow's step strip and its
 * bonsai take that place). `resumeAt`: the step saved before a relaunch; when it is green by now (Screen Recording
 * after the relaunch) it shows Done for a moment, then the walk moves on, so the learner sees it worked.
 * Getting miyagi ready shows a soft progress line in its status while the engine starts or access is set up.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion, type Variants } from 'motion/react'
import { ChevronLeft } from 'lucide-react'
import { useCapability } from '../../core/lesson'
import { brand, color, elevation, fill, font, highlight, radius2, spring, status as tone, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { Dots } from './Dots'
import { Illustration } from './Illustration'
import { MARK_ID } from './Intro'
import { EASE_OUT, rise } from './parts'
import { wordColor } from './Row'
import type { Row } from './rows'
import { canSkip, firstOpen, guidedRows, nextOpen, STEP_COPY, statusLine, type StepId } from './steps'
import { runAction, setGuidedStep, skipStep, useOnboarding } from './store'
import { ease, fade, stagger as motionStagger } from '../../core/ui/motion'

/** How long a step that just turned green stays up before the walk moves on. */
export const ADVANCE_MS = 1100
/** How long the walk waits for the first permissions answer before it picks a step anyway. */
const SETTLE_MS = 900
/** The tallest the step plus its footer grows (Nov 22): a bit more than the first-run window has under its header. */
const STAGE_MAX_H = 640
/** In the flow, how long after enterDelay the loading shape may fade in (s): past the login's exit, and usually never
 * seen at all, since the first answer lands before it (the strip and the gliding bonsai carry that beat). */
const SKELETON_WAIT = 0.3

type Button = { label: string; onClick: () => void; busy?: boolean; disabled?: boolean }

// ---- header --------------------------------------------------------------------------------------------------------

// ---- one step ------------------------------------------------------------------------------------------------------

/** `custom`: the direction (1 forward, -1 back) and a start delay (the first step waits for the tree to land). */
type Slide = { d: number; delay: number }
const slide: Variants = {
  hidden: ({ d }: Slide) => ({ opacity: 0, x: d * 24 }),
  shown: ({ delay }: Slide) => ({
    opacity: 1,
    x: 0,
    transition: { x: { ...spring, delay }, opacity: { ...fade.in, delay }, staggerChildren: motionStagger.each, delayChildren: delay + 0.02 }
  }),
  exit: ({ d }: Slide) => ({ opacity: 0, x: d * -16, transition: fade.out })
}

/** Still on its way by itself (the engine starting, access being set up): no button to press, so the line moves. */
const settling = (row: Row): boolean => row.id === 'engine' && (row.state === 'watching' || row.state === 'checking') && !row.alt

/**
 * The soft progress line: one short neutral segment crossing the bottom of the status on a slow loop (transform only,
 * no hue, no gradient). Reduced motion: the segment stays and breathes instead (never frozen: frozen reads as a hang).
 */
function SoftProgress(): ReactNode {
  const reduce = useReducedMotion() ?? false
  return (
    <span aria-hidden data-onb-progress className="absolute bottom-0 left-0 right-0 block h-[2px] overflow-hidden" style={{ background: fill.trackSoft }}>
      <motion.span
        className="absolute bottom-0 left-0 top-0 block w-[28%]"
        style={{ background: fill.practicing, borderRadius: radius2.round }}
        initial={reduce ? { opacity: 0.35, x: '130%' } : { x: '-100%' }}
        animate={reduce ? { opacity: [0.35, 0.9, 0.35] } : { x: '360%' }}
        transition={reduce ? { duration: 2, ease: ease.inOut, repeat: Infinity } : { duration: 1.6, ease: ease.inOut, repeat: Infinity, repeatDelay: 0.2 }}
      />
    </span>
  )
}

function Status({ row, advancing }: { row: Row; advancing: boolean }): ReactNode {
  return (
    <div
      data-onb-status={row.state}
      aria-live="polite"
      className="relative mx-auto flex min-h-[44px] max-w-full items-center justify-center gap-[10px] overflow-hidden px-[4px] py-[10px]"
      // As wide as its words: the soft progress and the moving-on hairline run under the line, not across the window.
      style={{ width: 'fit-content' }}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={row.state} className="flex" initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, transition: fade.instant }} transition={spring}>
          <StatusGlyph state={row.state} size={20} />
        </motion.span>
      </AnimatePresence>
      <span className="shrink-0 whitespace-nowrap" style={{ fontSize: type2.sm, fontWeight: 600, color: wordColor(row.state) }}>
        {row.state === 'passed' ? 'Done' : row.word}
      </span>
      <span className="min-w-0 flex-1" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
        {statusLine(row)}
      </span>
      {settling(row) && <SoftProgress />}
      {/* Moving on: a hairline fills under the status while the done step waits its second (transform only). */}
      {advancing && (
        <motion.span
          aria-hidden
          className="absolute bottom-0 left-0 right-0 block h-[2px]"
          style={{ background: tone.passed, originX: 0 }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: ADVANCE_MS / 1000, ease: 'linear' }}
        />
      )}
    </div>
  )
}

/** How long a grant the learner asked for may stay missing before miyagi says what to try (the re-grant case). */
export const REGRANT_MS = 7000

/** Copy for a grant that macOS shows on but miyagi still lacks (an update changes the signature and macOS drops it). */
export function regrantLines(id: StepId): string[] {
  if (id === 'screen') return ['Already on? Switch miyagi off and on again.', 'Still stuck? Remove it with the minus, add it back, then relaunch.']
  return ['Already on? Switch miyagi off and on again.', 'Still stuck? Remove it with the minus, then add it back.']
}

/**
 * The picture's stage: the live picture floating on the window, nothing behind it (redraft, Adrian Nov 21: the tinted
 * floor per step read as decoration; the picture already has its own surface and shadow).
 */
function Stage({ row }: { row: Row }): ReactNode {
  return (
    <div data-onb-stage className="relative flex w-full items-center justify-center px-[24px] py-[8px]">
      <div className="w-full max-w-[320px] text-left">
        <Illustration row={row} />
      </div>
    </div>
  )
}

function StepScreen({ row, picture, advancing, stuck }: { row: Row; picture: boolean; advancing: boolean; stuck: boolean }): ReactNode {
  const c = STEP_COPY[row.id]
  return (
    <div className="mx-auto flex h-full w-full max-w-[520px] flex-col items-center justify-center px-[32px] text-center">
      {picture && (
        <motion.div variants={rise} className="w-full">
          <Stage row={row} />
        </motion.div>
      )}
      <motion.h1
        id="onb-title"
        variants={rise}
        className="m-0"
        style={{ marginTop: picture ? 28 : 0, fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}
      >
        {c.title}
      </motion.h1>
      <motion.p variants={rise} className="m-0 mt-[8px]" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label, maxWidth: 400 }}>
        {c.body}
      </motion.p>
      <motion.div variants={rise} className="mt-[22px] w-full text-left" style={{ maxWidth: 400 }}>
        <Status row={row} advancing={advancing} />
        {stuck && (
          <div data-onb-regrant={row.id} role="note" className="mt-[10px] flex flex-col gap-[2px] px-[4px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
            {regrantLines(row.id).map((l) => (
              <span key={l}>{l}</span>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  )
}

// ---- the walk ------------------------------------------------------------------------------------------------------

export function Guided({
  rows,
  height,
  enterDelay = 0,
  onFinish,
  chrome = 'window',
  resumeAt
}: {
  rows: Row[]
  width: number
  height: number
  enterDelay?: number
  onFinish: () => void
  chrome?: 'window' | 'flow'
  resumeAt?: StepId
}): ReactNode {
  const canAsk = useCapability('health.get')
  const steps = useMemo(() => guidedRows(rows, canAsk), [rows, canAsk])
  const skippedSteps = useOnboarding((s) => s.skippedSteps)
  const permsKnown = useOnboarding((s) => !!s.perms)
  /** Steps the learner moved past with Continue while miyagi couldn't tell (Not sure yet): done for the walk. */
  const [passedBy, setPassedBy] = useState<StepId[]>([])
  const done = useMemo(() => new Set<StepId>([...skippedSteps, ...passedBy]), [skippedSteps, passedBy])
  const [idx, setIdx] = useState<number | undefined>(undefined)
  const [dir, setDir] = useState(1)
  const [settled, setSettled] = useState(false)
  const [advancing, setAdvancing] = useState(false)
  /** The grant was asked for a while ago and macOS still does not report it: say what to try (re-grant case). */
  const [stuck, setStuck] = useState(false)
  const finish = useRef(onFinish)
  finish.current = onFinish

  // Pick the first step once the permissions are known (or after a short wait), so a done step never flashes.
  useEffect(() => {
    if (permsKnown) return setSettled(true)
    const t = setTimeout(() => setSettled(true), SETTLE_MS)
    return () => clearTimeout(t)
  }, [permsKnown])
  /** The step a relaunch came back to, while it is still the one on screen. */
  const resumed = useRef<number | undefined>(undefined)
  useEffect(() => {
    if (!settled || idx !== undefined) return
    // Back after a relaunch on a step that is green by now: show it done for a moment, then move on.
    const back = resumeAt ? steps.findIndex((s) => s.id === resumeAt) : -1
    if (back >= 0 && steps[back].state === 'passed') {
      resumed.current = back
      setIdx(back)
      return
    }
    const first = firstOpen(steps, done)
    if (first === undefined) finish.current()
    else setIdx(first)
  }, [settled, idx, steps, done, resumeAt])

  const go = useCallback((to: number | undefined, from?: number) => {
    setAdvancing(false)
    resumed.current = undefined
    if (to === undefined) return finish.current()
    setDir(from === undefined || to >= from ? 1 : -1)
    setIdx(to)
  }, [])

  const row = idx === undefined ? undefined : steps[idx]
  useEffect(() => setGuidedStep(row?.id), [row?.id])
  // The learner asked for a grant, and after REGRANT_MS macOS still does not report it. After an update macOS can drop
  // the grant while System Settings still shows miyagi on: tell them plainly to switch it off and on (or remove and add).
  const stuckId = row && (row.id === 'screen' || row.id === 'accessibility') && row.state === 'watching' ? row.id : undefined
  useEffect(() => {
    setStuck(false)
    if (!stuckId) return
    const t = setTimeout(() => setStuck(true), REGRANT_MS)
    return () => clearTimeout(t)
  }, [stuckId])
  useEffect(() => () => setGuidedStep(undefined), [])

  // Auto-advance: only a step that turns green while it is on screen (Back to a done step stays put), and the step a
  // relaunch came back to.
  const seen = useRef<{ id: StepId; state: string } | undefined>(undefined)
  useEffect(() => {
    if (!row || idx === undefined) return
    if (resumed.current === idx && row.state === 'passed') {
      seen.current = { id: row.id, state: row.state }
      setAdvancing(true)
      const t = setTimeout(() => go(nextOpen(steps, idx, done), idx), ADVANCE_MS)
      return () => clearTimeout(t)
    }
    const prev = seen.current
    seen.current = { id: row.id, state: row.state }
    if (!prev || prev.id !== row.id || prev.state === 'passed' || row.state !== 'passed') {
      if (row.state !== 'passed') setAdvancing(false)
      return
    }
    setAdvancing(true)
    const t = setTimeout(() => go(nextOpen(steps, idx, done), idx), ADVANCE_MS)
    return () => clearTimeout(t)
    // steps/done are read when the timer fires; re-running on their identity would restart the second.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id, row?.state, idx, go])

  const moveOn = useCallback(() => {
    if (idx === undefined || !row) return
    if (row.state !== 'passed' && !done.has(row.id)) setPassedBy((p) => [...p, row.id])
    const nextDone = new Set(done).add(row.id)
    go(nextOpen(steps, idx, nextDone), idx)
  }, [idx, row, done, steps, go])

  const back = useCallback(() => {
    if (idx !== undefined && idx > 0) go(idx - 1, idx)
  }, [idx, go])

  const primary: Button | undefined = useMemo(() => {
    if (!row) return undefined
    if (row.state === 'passed') return { label: 'Continue', onClick: moveOn }
    if (row.state === 'unknown') return { label: 'Continue', onClick: moveOn }
    const a = row.action
    if (a) {
      const label = a.id === 'relaunch' ? 'Relaunch miyagi' : row.state === 'checking' ? row.word : a.label
      return { label, onClick: () => void runAction(a.id, a.item), busy: row.state === 'checking', disabled: row.state === 'checking' }
    }
    // Nothing to click: the step finishes on its own (the engine starting, access being set up, VS Code checked).
    if (row.state === 'notyet') return { label: 'Waiting for the engine', onClick: () => undefined, disabled: true }
    return { label: row.word, onClick: () => undefined, busy: true, disabled: true }
  }, [row, moveOn])

  const secondary: Button | undefined = useMemo(() => {
    if (!row) return undefined
    // The engine didn't come up: Retry is the primary, "Copy details" sits beside it.
    const alt = row.alt
    if (alt) return { label: alt.label, onClick: () => void runAction(alt.id) }
    if (canSkip(row))
      return {
        label: 'Skip for now',
        onClick: () => {
          skipStep(row.id)
          if (idx !== undefined) go(nextOpen(steps, idx, new Set(done).add(row.id)), idx)
        }
      }
    // Screen Recording after the click: the primary is Relaunch; the pane can be opened again from here.
    if (row.id === 'screen' && row.action?.id === 'relaunch') return { label: 'Open System Settings', onClick: () => void runAction('allow-screen') }
    return undefined
  }, [row, idx, steps, done, go])

  // Enter presses the primary, unless the learner is on another control (Tab moves between them as usual).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Enter' || e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t && t.closest('button, input, textarea, select, a')) return
      if (!primary || primary.disabled) return
      e.preventDefault()
      primary.onClick()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [primary])

  // Only the first step waits for the intro's tree to land; later steps start at once.
  const first = useRef(true)
  useEffect(() => {
    if (row) first.current = false
  }, [row])
  const custom: Slide = { d: dir, delay: first.current ? enterDelay : 0 }
  const picture = height >= 520

  return (
    <div data-onb-view="setup" data-onb-step={row?.id} data-onb-chrome={chrome} role="dialog" aria-labelledby="onb-title" className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad flex shrink-0 items-center justify-between pr-[28px]">
        <div className="flex items-center gap-[10px]">
          <motion.div layoutId={MARK_ID} className="relative" style={{ width: 22, height: 22 }} transition={{ layout: spring }}>
            <MiyagiMark size={22} />
          </motion.div>
          <motion.span className="flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...fade.slow, delay: enterDelay }}>
            <MiyagiWordmark height={15} className="block h-[15px] w-auto" />
          </motion.span>
        </div>
        {row && idx !== undefined && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...fade.slow, delay: enterDelay }}>
            <Dots items={steps.map((s, i) => ({ id: s.id, label: STEP_COPY[s.id].short, state: i === idx ? "current" : s.state === "passed" || done.has(s.id) ? "done" : "next" }))} />
          </motion.div>
        )}
      </header>}

      {/* The step and its footer are one block, at most STAGE_MAX_H tall and centered in what is left of the window: at the
          first-run size (944x640) it fills the window as before; full screen, the actions stay under the step instead of
          sinking to the bottom edge 300 px away (Nov 22 layout pass). */}
      <div className="flex min-h-0 flex-1 flex-col justify-center">
      <div className="flex min-h-0 w-full flex-col" style={{ height: '100%', maxHeight: STAGE_MAX_H }}>
      <main className="relative min-h-0 flex-1 overflow-hidden">
        {row ? (
          <AnimatePresence custom={custom} initial={true} mode="popLayout">
            <motion.section
              key={row.id}
              custom={custom}
              variants={slide}
              initial="hidden"
              animate="shown"
              exit="exit"
              className="absolute inset-0"
              aria-label={`Step ${(idx ?? 0) + 1} of ${steps.length}: ${STEP_COPY[row.id].short}`}
            >
              <StepScreen row={row} picture={picture} advancing={advancing} stuck={stuck} />
            </motion.section>
          </AnimatePresence>
        ) : (
          // The first answer is on its way (under a second): the shape of a step, never a blank window. In the flow it
          // fades in only after the screen before it (the login) is gone, so two screens are never drawn over each other.
          <motion.div
            aria-hidden
            className="mx-auto flex h-full w-full max-w-[860px] flex-col justify-center gap-[16px] px-[56px]"
            initial={chrome === 'flow' ? { opacity: 0 } : false}
            animate={{ opacity: 0.6 }}
            transition={{ ...fade.slow, delay: chrome === 'flow' ? enterDelay + SKELETON_WAIT : 0 }}
          >
            <span className="block h-[56px] w-[56px]" style={{ borderRadius: radius2.group, background: fill.skeleton }} />
            <span className="mt-[8px] block h-[24px] w-[320px]" style={{ borderRadius: radius2.control, background: fill.skeleton }} />
            <span className="block h-[14px] w-[260px]" style={{ borderRadius: radius2.control, background: fill.skeleton }} />
          </motion.div>
        )}
      </main>

      {/* The footer shares a centered 720 column with the step: in a full-screen window the primary stays near the copy it
          answers instead of drifting to the far corner. */}
      <motion.footer
        // With no Back (the first step) the actions center under the step, like the copy above them.
        className={`mx-auto flex h-[84px] w-full max-w-[720px] shrink-0 items-center px-[40px] ${idx !== undefined && idx > 0 ? 'justify-between' : 'justify-center'}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: row ? 1 : 0 }}
        transition={{ ...fade.slow, delay: enterDelay }}
      >
        <div data-onb-back>{idx !== undefined && idx > 0 && <QuietButton size="lg" icon={ChevronLeft} label="Back" onClick={back} />}</div>
        <div className="flex items-center gap-[12px]">
          {secondary && (
            <span data-onb-secondary>
              <QuietButton size="lg" label={secondary.label} onClick={secondary.onClick} />
            </span>
          )}
          {primary && (
            <span data-onb-primary data-label={primary.label}>
              <PrimaryButton size="lg" label={primary.label} onClick={primary.onClick} busy={primary.busy} disabled={primary.disabled} />
            </span>
          )}
        </div>
      </motion.footer>
      </div>
      </div>
    </div>
  )
}

