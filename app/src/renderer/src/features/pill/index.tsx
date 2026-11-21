/**
 * Feature: pill. The island's pill-sized states (34px tall, width hugs content), to mockup 01 + the
 * Miyagi brand (app/brand/BRAND.md): always black, the bonsai in color on the left (green pads, as everywhere in
 * the app), the status on the right.
 *   idle      no lesson yet: "[bonsai] ask miyagi ⌥Space ●" (lowercase, Michael) (click opens the launcher);
 *             with no engine, once a connect attempt has failed: "[bonsai] Can't reach miyagi · [Retry]" (click tries now,
 *             review A16), or what the app's own engine is doing (setting up, starting, missing, failed);
 *             while the engine offers a saved lesson back: "[bonsai] Continue · <lesson>  2/7 ●" (click resumes it, review A7)
 *   building  between Build lesson and the first step: "Planning your lesson…" + spinner from the moment the build is
 *             sent until the engine's first lesson.building (review A20: it was blank), then its message + spinner + progress line
 *             (the stage's words always in full, at most STAGE_MAX characters, never cut mid-word: desktop test 3, item 9);
 *             once the lesson is set (lesson.ready, before the first step.started) it's static: "Lesson ready ●", no spinner, no line
 *   compact   during a lesson (v2 Les-Working): "[bonsai] Normalize the pixels  2 of 6 ●" (count = this step of the
 *             lesson's steps, dot = status; the step's title from lesson.steps, the same title the drawer has: review A20);
 *             v2 phase lines (A2): "[spinner] Checking your work 2 of 6", "[ring] Not yet 2 of 6", "[✓] Step 2 passed 2 of 6";
 *             "Next part is still building" after a pass while a long video's next part builds
 *   mini      v2 Les-Mini (priority 9): the lesson panel collapsed to the pill, 380 wide, with step bars; click opens it
 *   saved     after End (lesson.ended "stopped"): "[bonsai] Lesson saved · [Undo]" for ~8 s, then idle (review A3)
 *   notice    one line for ~5 s over any of them (engine errors, a failed build, notify()), then back
 * While the engine is thinking, the bonsai becomes the small spinner (LeadMark). Offline mid-lesson: hollow dot.
 * Calm: nothing animates unless the state really changed (no timer ticks, no repeats of the same line).
 *
 * Measured from mockup 01 (1×): art 15 from the left edge, 11 before the text (= pad 13 + 16px mark box + gap 8) ·
 * 14 right · text → count 15 · count → dot 9 ·
 * 13px medium · "Step 4 ·" in the muted label color, title in the text color.
 * The step-pass moment (check → flash → crossfade) is driven by ./store.ts.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useRef, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { useDock } from '../../core/dock'
import { notify, useCurrentStep, useLesson, useStepPhase } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { color, copy, dock, fill } from '../../core/theme'
import { Kbd, Spinner, StepDots } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { PillGear } from './Gear'
import { openPanel } from './panel'
import { BuildLine, FitSwap, LeadMark, PhaseLead, StatusMark, StepCount, SwapText, type Mark, type Phase } from './parts'
import { LESSON_SAVED, resumeSaved, retryEngine, undoEnd, UNREACHABLE, usePill, type SavedOffer } from './store'

/**
 * Offline, but the app is bringing its own engine up (main/localEngine.ts, built Mac app): say what's happening.
 * "Install the engine" copies Michael's one-liner; "Engine didn't start" opens the engine's log.
 */
function offlineLabel(state?: string): { text: string; busy: boolean } | undefined {
  if (state === 'installing') return { text: 'Setting up miyagi', busy: true }
  if (state === 'starting' || state === 'checking') return { text: 'Starting miyagi', busy: true }
  if (state === 'missing') return { text: 'Install the engine', busy: false }
  if (state === 'failed') return { text: "Engine didn't start", busy: false }
  return undefined // nothing more to say than "Can't reach miyagi · Retry" (Unreachable)
}

/**
 * No engine answers and a connect attempt has failed (Michael's review A16): "Can't reach miyagi · Retry". The whole
 * pill is the Retry (a 34px target); the chip is drawn like the saved line's Undo (neutral chrome, concentric with the
 * pill's right end). Pressed, the bonsai spins until that attempt ends; main also keeps retrying by itself.
 */
function Unreachable(): ReactNode {
  const retrying = usePill((s) => s.retrying)
  const [hot, setHot] = useState(false)
  return (
    <button
      type="button"
      className="flex h-[34px] cursor-pointer items-center whitespace-nowrap pl-[13px] pr-[6px] text-[13px] font-medium"
      style={{ color: color.label }}
      onClick={retryEngine}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      aria-label={`${UNREACHABLE}. Retry`}
      aria-busy={retrying || undefined}
      data-offline
    >
      <LeadMark busy={retrying} />
      <span>{UNREACHABLE}</span>
      <span>&nbsp;·&nbsp;</span>
      <motion.span
        className="ml-[4px] inline-flex h-[22px] items-center rounded-full px-[10px] text-[12px] font-medium"
        style={{ color: color.text }}
        initial={false}
        animate={{ backgroundColor: hot ? fill.chipHover : fill.button }}
        whileTap={{ scale: 0.96 }}
        transition={{ duration: 0.12 }}
      >
        Retry
      </motion.span>
    </button>
  )
}

/**
 * Cut a label at a word boundary with "…" past `max` characters, never mid-word (desktop test 3, item 9). One very long
 * word stays whole (a CSS max width is the last resort).
 */
function clipWords(text: string, max: number): string {
  if (text.length <= max) return text
  const at = text.lastIndexOf(' ', max)
  return at > 0 ? `${text.slice(0, at).replace(/[\s,:·–—-]+$/, '')}…` : text
}

/** Longest lesson title the Continue pill shows (about 180px at 13px), so the pill stays near the notice line's width. */
const OFFER_MAX = 28

/** The idle pill's words for a saved lesson the engine offers back (review A7). */
function continueLabel(o: SavedOffer): { id: string; title?: string; count?: { n: number; total: number }; full?: string; aria: string } {
  const title = o.title ? clipWords(o.title, OFFER_MAX) : undefined
  const count = o.n !== undefined && o.total !== undefined ? { n: o.n, total: o.total } : undefined
  return {
    id: `continue-${o.title ?? ''}-${o.n ?? ''}-${o.total ?? ''}`,
    title,
    count,
    full: o.title && title !== o.title ? `Continue ${o.title}` : undefined,
    aria: `Continue ${o.title ?? 'the lesson'}${count ? `, step ${count.n} of ${count.total}` : ''}`
  }
}

function Idle(): ReactNode {
  const offline = usePill((s) => s.offline)
  const resuming = usePill((s) => s.resuming)
  const offer = usePill((s) => s.offer)
  const local = useLesson((s) => s.localEngine)
  const off = offlineLabel(local?.state)
  // The engine offers a saved lesson back and its card is closed (review A7): the pill is the way back into it.
  const cont = !offline && offer ? continueLabel(offer) : undefined
  if (offline && !off) return <Unreachable />
  const click = (): void => {
    if (cont) return resumeSaved()
    if (offline && local?.state === 'missing') {
      void bridge.invoke('engine-local:copy').then(() => notify('Install command copied. Paste it in Terminal.')).catch(() => undefined)
      return
    }
    if (offline && local?.state === 'failed') {
      void bridge.invoke('engine-local:logs').catch(() => undefined)
      return
    }
    bridge.emit('launcher:toggle')
  }
  return (
    <button
      className="group flex h-[34px] cursor-pointer items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium"
      style={{ color: offline ? color.label : color.text }}
      onClick={click}
      title={offline ? local?.line : cont?.full}
      aria-label={offline && off ? `${off.text}: miyagi is not connected` : cont ? cont.aria : 'ask miyagi: open the launcher'}
      data-offer={cont ? cont.id : undefined}
    >
      <LeadMark busy={resuming} />
      <SwapText
        id={offline ? `offline-${local?.state ?? ''}` : cont ? cont.id : 'ask'}
        className="flex opacity-90 transition-opacity duration-150 group-hover:opacity-100"
      >
        {offline && off ? (
          off.text
        ) : cont ? (
          cont.title ? (
            // Like compact's "Step 4 · <title>": the lead-in muted, the lesson in the text color.
            <>
              <span style={{ color: color.label }}>Continue ·&nbsp;</span>
              <span className="max-w-[220px] truncate">{cont.title}</span>
            </>
          ) : (
            'Continue the lesson'
          )
        ) : (
          copy.ask
        )}
      </SwapText>
      {offline && off?.busy && <span className="ml-[10px] inline-flex"><Spinner size={13} c={color.label} /></span>}
      {/* Fully round (radius 10 inside the pill's 17). Hidden offline: nothing to ask. Hidden on Continue: a click resumes. */}
      {!offline && !cont && <Kbd className="ml-[10px] !h-[20px] !rounded-full !px-[8px]">{bridge.platform.keys.launcher}</Kbd>}
      {/* The status dot on the right, like every pill state (BRAND.md): gray watching, hollow gray offline (audit A21).
          Spaced like compact: 15 after text, 9 after the key chip, spinner or step count. */}
      {cont ? (
        <span className="ml-[15px] flex items-center gap-[9px]">
          {cont.count && <StepCount n={cont.count.n} total={cont.count.total} />}
          <StatusMark mark="watching" />
        </span>
      ) : (
        <span className={`flex items-center ${offline && !off?.busy ? 'ml-[15px]' : 'ml-[9px]'}`}>
          <StatusMark mark={offline ? 'offline' : 'watching'} />
        </span>
      )}
    </button>
  )
}

/**
 * The stage part of a lesson.building message: drops a trailing timer ("· 0:15", "(0:15)", "· 15s")
 * and the "Gemini is " lead-in, so "Gemini is watching the video · 0:15" → "Watching the video".
 */
function buildingStage(message?: string): string {
  if (!message) return ''
  const s = message
    .replace(/\s*(?:[·•|–—-]\s*)?\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*$/, '')
    .replace(/\s*(?:[·•|–—-]\s*)?\(?\d+(?:\.\d+)?\s*s\)?\s*$/, '')
    .replace(/^\s*gemini\s+is\s+/i, '')
    .replace(/[\s·•|–—-]+$/, '')
    .trim()
  return s ? s[0].toUpperCase() + s.slice(1) : ''
}

/** Longest stage label the building pill shows (about 220px at 13px), so it stays close to the 300px landing width. */
const STAGE_MAX = 34

/**
 * The pill's words for a build stage (desktop test 3, item 9): the stage's first clause ("First steps ready; the rest
 * builds while you work" → "First steps ready"), and past STAGE_MAX characters it ends at a word boundary with "…",
 * never mid-word. The pill keeps the full stage as its title and accessible label.
 */
function stageLabel(stage: string): string {
  const clause = stage.split(/\s*;\s*|\.\s+|\s[–—]\s/)[0].trim() || stage
  return clipWords(clause, STAGE_MAX)
}

/** The building pill once lesson.ready has landed and the first step hasn't started: nothing is working any more. */
const READY = 'Lesson ready'
/** From the moment a build is sent until the engine's first lesson.building (Michael's review A20). */
export const PLANNING = 'Planning your lesson…'

function Building(): ReactNode {
  const { message, progress, lesson, building } = useLesson(
    useShallow((s) => ({ message: s.buildingMessage, progress: s.buildingProgress, lesson: !!s.lesson, building: s.building }))
  )
  const kept = usePill((s) => s.buildMessage)
  const planned = usePill((s) => s.planning)
  const shown = useRef<string>(undefined)
  // Planning: the pill's own flag (the launcher just landed on it with a build), or, freshly drawn with no build running
  // yet, the launcher's collapse onto the pill (it draws this content before the engine has said anything).
  const planning = planned || (!building && !shown.current)
  const ready = lesson && building && !planning
  // Calm: show only the stage. The text (and so the crossfade) changes on a real stage change, never on the timer
  // tick; the progress line carries the motion. Leaving (a failed or dropped build) it keeps its last words.
  const stage =
    !building && !planning && shown.current ? shown.current : planning ? PLANNING : ready ? READY : buildingStage(message ?? kept) || PLANNING
  shown.current = stage
  const text = stageLabel(stage)
  return (
    <div
      role="status"
      aria-label={stage}
      title={text !== stage ? stage : undefined}
      className="relative flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium"
      style={{ color: color.text }}
      data-planning={planning || undefined}
    >
      <MiyagiMark size={16} className="mr-[8px]" />
      {/* Never cut mid-word (item 9): the slot is always as wide as the stage's words; the island springs around it. */}
      <FitSwap id={text}>{text}</FitSwap>
      {/* Building: the spinner where the count will be. Set (Michael's audit A5): static, the gray dot only, no spinner, no line. */}
      <span className="ml-[15px] flex items-center">{ready ? <StatusMark mark="watching" /> : <Spinner size={16} />}</span>
      <AnimatePresence>{!ready && !planning && progress !== undefined && <BuildLine progress={progress} />}</AnimatePresence>
    </div>
  )
}

/**
 * What a lesson pill line shows. `phase` set = a v2 phase line (Les-Checking / Les-NotYet / Les-Passed): its glyph leads
 * instead of the bonsai and there's no status dot; otherwise the step's title with the dot on the right (Les-Working).
 */
type Shown = { key: string; index: number; title: string; mark: Mark; phase?: Phase }

const NEXT_PART = 'Next part is still building'
/** Les-Checking's line while a check the learner asked for is in flight. */
export const CHECKING = 'Checking your work'
/** Les-NotYet: no hue, the white ring and these words. */
export const NOT_YET = 'Not yet'
/** Les-Passed: "Step 2 passed" (the green check leads). */
export const passedLine = (n: number): string => `Step ${n} passed`

/** What the pill shows: the engine's step, except during/after a pass, where the pill runs ahead. */
function useShown(): Shown & { total: number } {
  const l = useLesson(
    useShallow((s) => ({
      stepId: s.stepId,
      title: s.stepTitle,
      steps: s.steps,
      // v2: the outline's count when the engine sends it, so "2 of 6" never jumps while later steps are still written.
      outline: s.lesson?.outline?.count ?? 0,
      complete: s.complete,
      // A long video still building: after its last known step there is a next part coming, not the end.
      morePending: s.pendingNext || !s.complete
    }))
  )
  const phase = useStepPhase()
  const { celebrating, advanced, offline } = usePill(
    useShallow((s) => ({ celebrating: s.celebrating, advanced: s.advanced, offline: s.offline }))
  )
  const total = Math.max(1, l.steps.length, l.outline)
  const at = (id?: string): number => l.steps.findIndex((x) => x.id === id)
  const titleOf = (i: number, fallback = ''): string => l.steps[i]?.title ?? fallback

  // 1) The check is drawing: hold the passed step on screen (even if step.started already moved on).
  if (celebrating) {
    const i = Math.max(0, at(celebrating))
    return { key: `${celebrating}:passed`, index: i, title: passedLine(i + 1), mark: 'watching', phase: 'passed', total }
  }
  // 2) After a pass, before the engine's step.started: the next step, the next part still building, or the end.
  //    (Only without the lesson panel: with it, the pill holds the passed line, case 3.)
  if (advanced && advanced.from === l.stepId) {
    // lesson.updated may have appended the next step since the pass: look it up now, not at pass time.
    const to = advanced.to ?? l.steps[at(advanced.from) + 1]?.id
    if (!to || at(to) < 0) {
      const i = at(advanced.from)
      if (l.morePending) return { key: 'pending', index: i + 1, title: NEXT_PART, mark: offline ? 'offline' : 'pending', total }
      return { key: 'complete', index: total - 1, title: 'Lesson complete', mark: 'done', total }
    }
    const j = at(to)
    return { key: to, index: j, title: titleOf(j), mark: offline ? 'offline' : 'watching', total }
  }
  // 3) Normal: the engine's current step, titled from lesson.steps like the drawer and cases 1-2 (review A20: the pill
  // named steps differently from the drawer); step.started's title only for a step the list doesn't have.
  const found = at(l.stepId)
  const i = Math.max(0, found)
  const id = l.stepId ?? ''
  const mark: Mark = offline ? 'offline' : 'watching'
  if (phase === 'passed') {
    const lastKnown = found === l.steps.length - 1
    if (lastKnown && l.morePending) return { key: 'pending', index: i + 1, title: NEXT_PART, mark: offline ? 'offline' : 'pending', total }
    if (lastKnown && i === total - 1 && l.complete) return { key: 'complete', index: total - 1, title: 'Lesson complete', mark: 'done', total }
    return { key: `${id}:passed`, index: i, title: passedLine(i + 1), mark, phase: 'passed', total }
  }
  if (phase === 'checking') return { key: `${id}:checking`, index: i, title: CHECKING, mark, phase: 'checking', total }
  if (phase === 'notyet') return { key: `${id}:notyet`, index: i, title: NOT_YET, mark, phase: 'notyet', total }
  return { key: id, index: i, title: found >= 0 ? titleOf(i, l.title) : l.title, mark, total }
}

/** The right end of a lesson line: "2 of 6" and the status dot (no dot on a phase line), or the spinner of a part still building. */
function LineEnd({ s, gap = 15 }: { s: Shown & { total: number }; gap?: number }): ReactNode {
  if (s.mark === 'pending')
    // Same shape as the building pill: a part is building, so the spinner sits where the count was.
    return (
      <span className="flex shrink-0 items-center" style={{ marginLeft: gap }}>
        <Spinner size={16} />
      </span>
    )
  return (
    <span className="flex shrink-0 items-center gap-[9px]" style={{ marginLeft: gap }}>
      <StepCount n={Math.min(s.total, s.index + 1)} total={s.total} />
      {!s.phase && <StatusMark mark={s.mark} />}
    </span>
  )
}

/**
 * The step pill (Les-Working and the pill lines of Les-Checking / NotYet / Passed): "[bonsai] Normalize the pixels
 * 2 of 6 ●", "[spinner] Checking your work 2 of 6", "[ring] Not yet 2 of 6", "[✓] Step 2 passed 2 of 6". No "Step N ·"
 * lead-in: the count on the right says which step (Michael, test 10).
 */
function Compact(): ReactNode {
  const s = useShown()
  const label = s.phase ? `${s.title}, step ${Math.min(s.total, s.index + 1)} of ${s.total}` : `miyagi is watching step ${Math.min(s.total, s.index + 1)} of ${s.total}`
  return (
    <div
      role="status"
      aria-label={label}
      className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium"
      style={{ color: color.text }}
      data-step={s.key}
      data-line={s.phase ?? 'working'}
    >
      {s.phase ? <PhaseLead phase={s.phase} /> : <LeadMark />}
      <SwapText id={s.key} className="flex">
        {s.mark === 'done' || s.mark === 'pending' ? <span>{s.title}</span> : <span className="max-w-[360px] truncate">{s.title}</span>}
      </SwapText>
      <LineEnd s={s} />
    </div>
  )
}

/**
 * Les-Mini: the lesson panel collapsed to the pill (core/dock `collapsed`, A1 sets it). dock.miniW wide (380), 34 tall
 * until wave 2: the bonsai (or the phase glyph), the step's title, one bar per step (StepDots 'bars': passed green, this
 * step white, the rest faint; past 10 steps one proportional track), "2 of 6" and the status dot. The whole pill is
 * the button that opens the panel again.
 */
function Mini(): ReactNode {
  const s = useShown()
  const cur = useCurrentStep()
  const n = Math.min(s.total, s.index + 1)
  const label = s.phase ? `${s.title}, step ${n} of ${s.total}. Click to open.` : `miyagi is watching step ${n} of ${s.total}, ${s.title}. Click to open.`
  return (
    <button
      type="button"
      data-mini
      data-line={s.phase ?? 'working'}
      data-step={s.key}
      className="flex h-[34px] cursor-pointer items-center whitespace-nowrap pl-[13px] pr-[14px] text-left text-[13px] font-medium"
      style={{ width: dock.miniW, color: color.text }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={openPanel}
      aria-label={label}
      title={s.title}
    >
      {s.phase ? <PhaseLead phase={s.phase} /> : <LeadMark />}
      <span className="relative min-w-0 flex-1 overflow-hidden">
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span
            key={s.key}
            className="block truncate leading-[18px]"
            initial={{ opacity: 0, y: 7 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.24, ease: 'easeOut', delay: 0.11 } }}
            exit={{ opacity: 0, y: -7, transition: { duration: 0.1, ease: 'easeIn' } }}
          >
            {s.title}
          </motion.span>
        </AnimatePresence>
      </span>
      <span className="ml-[8px] flex shrink-0 items-center" aria-hidden>
        <StepDots variant="bars" total={s.total} current={s.index} passed={cur.passed} skipped={cur.skipped} cap={MINI_BARS_CAP} width={MINI_TRACK_W} />
      </span>
      <LineEnd s={s} gap={8} />
    </button>
  )
}

/** Les-Mini: one bar per step up to 10, then one proportional track this wide. */
const MINI_BARS_CAP = 10
const MINI_TRACK_W = 96

/** The notice line: the bonsai and one line of text. White for errors too: nothing red, no extra icon. */
function NoticeLine(): ReactNode {
  const notice = usePill((s) => s.notice)
  // While the mode fades out the notice is already gone: keep the last line so the width doesn't collapse.
  const last = useRef(notice)
  if (notice) last.current = notice
  const n = last.current
  return (
    <div
      role={n?.tone === 'error' ? 'alert' : 'status'}
      className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[16px] text-[13px] font-medium"
      style={{ color: color.text }}
      data-notice={n?.tone}
    >
      <MiyagiMark size={16} className="mr-[8px]" />
      <SwapText id={n?.text ?? ''}>
        <span className="block max-w-[380px] truncate">{n?.text}</span>
      </SwapText>
    </div>
  )
}

/**
 * After End kept the save (review A3): where it went, and a way back for UNDO_MS. Undo is a small neutral chip (chrome,
 * not an option: no pastel; not the surface's primary: no white fill), concentric with the pill's right end.
 */
function SavedLine(): ReactNode {
  return (
    <div role="status" className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[6px] text-[13px] font-medium" style={{ color: color.text }} data-saved>
      <MiyagiMark size={16} className="mr-[8px]" />
      <span>{LESSON_SAVED}</span>
      <span style={{ color: color.label }}>&nbsp;·&nbsp;</span>
      <motion.button
        type="button"
        data-hit
        className="ml-[4px] h-[22px] cursor-pointer rounded-full px-[10px] text-[12px] font-medium"
        style={{ backgroundColor: fill.button, color: color.text }}
        whileHover={{ backgroundColor: fill.chipHover }}
        whileTap={{ scale: 0.96 }}
        transition={{ duration: 0.12 }}
        onClick={undoEnd}
        aria-label="Undo: continue the lesson"
      >
        Undo
      </motion.button>
    </div>
  )
}

export default defineFeature({
  id: 'pill',
  islandModes: [
    // No step and nothing building. Also a lesson that's set but stopped building before its first step (a failed or
    // dropped build after lesson.ready): no mode covered that, and the island drew nothing (review A20: "blank").
    { id: 'idle', priority: 0, useActive: () => useLesson((s) => !s.stepId && !s.building), Content: Idle },
    { id: 'compact', priority: 2, useActive: () => useLesson((s) => !!s.stepId), Content: Compact },
    // Over compact while a new build is being planned (a lesson started from the launcher during another one); otherwise
    // building (no step yet) and compact (a step) never overlap.
    {
      id: 'building',
      priority: 3,
      useActive: () => {
        const planning = usePill((s) => s.planning)
        const building = useLesson((s) => s.building && !s.stepId)
        return planning || building
      },
      Content: Building
    },
    // Over the idle pill only (a new lesson building or on screen wins), and never offline: Undo would go nowhere.
    {
      id: 'saved',
      priority: 4,
      useActive: () => {
        const undo = usePill((s) => s.undo && !s.offline)
        const idle = useLesson((s) => !s.lesson && !s.building)
        return undo && idle
      },
      Content: SavedLine
    },
    // Above the pill states, below hover (20) and cards (40+): a card the learner opened stays in front.
    { id: 'notice', priority: 5, useActive: () => usePill((s) => !!s.notice), Content: NoticeLine },
    // v2 Les-Mini (README priority table: 9): the lesson panel collapsed to the pill. It steps aside for the pill's own
    // notice line (5) while that shows, and for A7's lines while the engine is offline or busy (6) or the lesson is
    // paused or blocked (7), so 'Reconnecting', 'Lesson paused' or a kernel blocker is never hidden for the whole
    // collapsed lesson. Mini comes back as soon as they clear.
    {
      id: 'mini',
      priority: 9,
      useActive: () => {
        const collapsed = useDock((d) => d.collapsed)
        const step = useLesson((s) => !!s.stepId)
        const engineLine = useLesson((s) => !s.connected || !!s.busy || !!s.paused || Object.keys(s.blockers).length > 0)
        const notice = usePill((s) => !!s.notice)
        return collapsed && step && !notice && !engineLine
      },
      Content: Mini
    }
  ],
  // The settings gear just right of the pill (./Gear.tsx): over the island (z 50) and under the shortcut bar (60).
  overlayLayers: [{ id: 'pill-gear', z: 55, Component: PillGear }]
})
