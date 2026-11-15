/**
 * Feature: pill. The island's pill-sized states (34px tall, width hugs content), to mockup 01 + the
 * Miyagi brand (app/brand/BRAND.md): always black and white, the bonsai as a one-color glyph on the left
 * (monochrome everywhere in the app), the status on the right.
 *   idle      no lesson yet: "[bonsai] ask miyagi ⌥Space" (lowercase, Michael) (click opens the launcher); "Offline" with no engine
 *   building  between Build lesson and the first step: lesson.building message + spinner + progress line;
 *             once the lesson is set (lesson.ready, before the first step.started) it's static: "Lesson ready ●", no spinner, no line
 *   compact   during a lesson: "[bonsai] Step 4 · Define the residual  4/8 ●" (count = this step / steps, dot = status);
 *             "Next part is still building" after a pass while a long video's next part builds
 *   notice    one line for ~5 s over any of them (engine errors, a failed build, notify()), then back
 * While the engine is thinking, the bonsai becomes the small spinner (LeadMark). Offline mid-lesson: hollow dot.
 * Calm: nothing animates unless the state really changed (no timer ticks, no repeats of the same line).
 *
 * Measured from mockup 01 (1×): art 15 from the left edge, 11 before the text (= pad 13 + 16px mark box + gap 8) ·
 * 14 right · text → count 15 · count → dot 9 ·
 * 13px medium · "Step 4 ·" in the muted label color, title in the text color.
 * The step-pass moment (check → flash → crossfade) is driven by ./store.ts.
 */
import { AnimatePresence } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { notify, useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { color, copy } from '../../core/theme'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { BuildLine, LeadMark, MonoMark, StatusMark, StepCount, SwapText, type Mark } from './parts'
import { usePill } from './store'

/**
 * Offline, but the app is bringing its own engine up (main/localEngine.ts, built Mac app): say what's happening.
 * "Install the engine" copies Michael's one-liner; "Engine didn't start" opens the engine's log.
 */
function offlineLabel(state?: string): { text: string; busy: boolean } {
  if (state === 'installing') return { text: 'Setting up miyagi', busy: true }
  if (state === 'starting' || state === 'checking') return { text: 'Starting miyagi', busy: true }
  if (state === 'missing') return { text: 'Install the engine', busy: false }
  if (state === 'failed') return { text: "Engine didn't start", busy: false }
  return { text: 'Offline', busy: false }
}

function Idle(): ReactNode {
  const offline = usePill((s) => s.offline)
  const local = useLesson((s) => s.localEngine)
  const off = offlineLabel(local?.state)
  const click = (): void => {
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
      className={`group flex h-[34px] cursor-pointer items-center whitespace-nowrap pl-[13px] text-[13px] font-medium ${offline ? 'pr-[16px]' : 'pr-[7px]'}`}
      style={{ color: offline ? color.label : color.text }}
      onClick={click}
      title={offline ? local?.line : undefined}
      aria-label={offline ? `${off.text}: miyagi is not connected` : 'ask miyagi: open the launcher'}
    >
      <LeadMark />
      <SwapText id={offline ? `offline-${local?.state ?? ''}` : 'ask'} className="opacity-90 transition-opacity duration-150 group-hover:opacity-100">
        {offline ? off.text : copy.ask}
      </SwapText>
      {offline && off.busy && <span className="ml-[10px] inline-flex"><Spinner size={13} c={color.label} /></span>}
      {/* Concentric with the pill: 7px inset, fully round (radius 10 inside radius 17). Hidden offline: nothing to ask. */}
      {!offline && <Kbd className="ml-[10px] !h-[20px] !rounded-full !px-[8px]">{bridge.platform.keys.launcher}</Kbd>}
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

/** The building pill once lesson.ready has landed and the first step hasn't started: nothing is working any more. */
const READY = 'Lesson ready'

function Building(): ReactNode {
  const { message, progress, ready } = useLesson(
    useShallow((s) => ({ message: s.buildingMessage, progress: s.buildingProgress, ready: !!s.lesson }))
  )
  const kept = usePill((s) => s.buildMessage)
  // Calm: show only the stage. The text (and so the crossfade + width spring) changes on a real stage change,
  // never on the timer tick; the progress line carries the motion.
  const text = ready ? READY : buildingStage(message ?? kept) || 'Building your lesson'
  return (
    <div className="relative flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium" style={{ color: color.text }}>
      <MonoMark className="mr-[8px]" />
      <SwapText id={text}>{text}</SwapText>
      {/* Building: the spinner where the count will be. Set (Michael's audit A5): static, the gray dot only, no spinner, no line. */}
      <span className="ml-[15px] flex items-center">{ready ? <StatusMark mark="watching" /> : <Spinner size={16} />}</span>
      <AnimatePresence>{!ready && progress !== undefined && <BuildLine progress={progress} />}</AnimatePresence>
    </div>
  )
}

type Shown = { key: string; index: number; title: string; mark: Mark }

const NEXT_PART = 'Next part is still building'

/** What the pill shows: the engine's step, except during/after a pass, where the pill runs ahead. */
function useShown(): Shown & { total: number } {
  const l = useLesson(
    useShallow((s) => ({
      stepId: s.stepId,
      title: s.stepTitle,
      steps: s.steps,
      passed: s.passed,
      offtrack: !!s.offtrack,
      // A long video still building: after its last known step there is a next part coming, not the end.
      morePending: s.pendingNext || !s.complete
    }))
  )
  const { celebrating, advanced, offline } = usePill(
    useShallow((s) => ({ celebrating: s.celebrating, advanced: s.advanced, offline: s.offline }))
  )
  const total = Math.max(1, l.steps.length)
  const at = (id?: string): number => l.steps.findIndex((x) => x.id === id)
  const titleOf = (i: number, fallback = ''): string => l.steps[i]?.title ?? fallback

  // 1) The check is showing: hold the passed step on screen (even if step.started already moved on).
  if (celebrating) {
    const i = at(celebrating)
    return { key: celebrating, index: Math.max(0, i), title: titleOf(i, l.title), mark: 'check', total }
  }
  // 2) After a pass, before the engine's step.started: the next step, the next part still building, or the end.
  if (advanced && advanced.from === l.stepId) {
    // lesson.updated may have appended the next step since the pass: look it up now, not at pass time.
    const to = advanced.to ?? l.steps[at(advanced.from) + 1]?.id
    if (!to || at(to) < 0) {
      const i = at(advanced.from)
      if (l.morePending) return { key: 'pending', index: i + 1, title: NEXT_PART, mark: offline ? 'offline' : 'pending', total }
      return { key: 'complete', index: total, title: 'Lesson complete', mark: 'done', total }
    }
    const j = at(to)
    return { key: to, index: j, title: titleOf(j), mark: offline ? 'offline' : 'watching', total }
  }
  // 3) Normal: the engine's current step.
  const i = Math.max(0, at(l.stepId))
  const passed = !!l.stepId && l.passed.includes(l.stepId)
  return {
    key: l.stepId ?? '',
    index: i,
    title: l.title,
    mark: offline ? 'offline' : l.offtrack ? 'offtrack' : passed ? 'passed' : 'watching',
    total
  }
}

function Compact(): ReactNode {
  const s = useShown()
  return (
    <div className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium" style={{ color: color.text }} data-step={s.key}>
      <LeadMark />
      <SwapText id={s.key} className="flex">
        {s.mark === 'done' || s.mark === 'pending' ? (
          <span>{s.title}</span>
        ) : (
          <>
            <span style={{ color: color.label }}>Step {s.index + 1} ·&nbsp;</span>
            <span className="max-w-[240px] truncate">{s.title}</span>
          </>
        )}
      </SwapText>
      {s.mark === 'pending' ? (
        // Same shape as the building pill: a part is building, so the spinner sits where the count was.
        <span className="ml-[15px]">
          <Spinner size={16} />
        </span>
      ) : (
        <span className="ml-[15px] flex items-center gap-[9px]">
          <StepCount n={s.mark === 'done' ? s.total : Math.min(s.total, s.index + 1)} total={s.total} />
          <StatusMark mark={s.mark} />
        </span>
      )}
    </div>
  )
}

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
      <MonoMark className="mr-[8px]" />
      <SwapText id={n?.text ?? ''}>
        <span className="block max-w-[380px] truncate">{n?.text}</span>
      </SwapText>
    </div>
  )
}

export default defineFeature({
  id: 'pill',
  islandModes: [
    { id: 'idle', priority: 0, useActive: () => useLesson((s) => !s.lesson && !s.building), Content: Idle },
    { id: 'building', priority: 1, useActive: () => useLesson((s) => s.building && !s.stepId), Content: Building },
    { id: 'compact', priority: 2, useActive: () => useLesson((s) => !!s.stepId), Content: Compact },
    // Above the pill states, below hover (20) and cards (40+): a card the learner opened stays in front.
    { id: 'notice', priority: 5, useActive: () => usePill((s) => !!s.notice), Content: NoticeLine }
  ]
})
