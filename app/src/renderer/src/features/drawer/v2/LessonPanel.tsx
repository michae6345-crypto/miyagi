/**
 * Feature: drawer (v2, BUILD-PLAN A1). The lesson panel docked at the right edge (Les-Working, Les-Checking,
 * Les-NotYet, Les-Hint, Les-Passed): 360 wide, 16 in from the edge, top 52 at 1440x900 (core/dock panelRect).
 *
 * Top to bottom: Header (tree, miyagi, collapse; lesson title, step dots, "Step N of M"), a hairline, the state's body,
 * the ONE primary (Check my work / Checking / Check again / Next step) over a fixed status slot, a hairline and "Need
 * help" (not on Les-Passed), then the keys line (Esc hide, ask miyagi, Back). The view comes from view.ts (passed >
 * checking > notyet > hint > working). The panel hugs its content; past the dock's height the middle scrolls.
 *
 * Motion (UI-POLISH-SPEC 5, persona QA "states snap"):
 *   in / out     a lesson's first step slides the panel in from the right edge; collapsing morphs it into the Mini pill
 *                and reopening grows it back out of the pill (useDrawer.via). Opacity only with reduced motion.
 *   height       the body's height springs to its content, so the card grows and shrinks instead of jumping.
 *   state        Not yet, Hint and Passed rise in (6 px, house spring, 180 ms fade; exit 120 ms). Working and
 *                Checking are one screen, so pressing Check moves nothing but the button and its caption.
 *   next step    "Next step" slides the passed screen out to the left and the new step in from the right (Back: the
 *                other way).
 *
 * The hint sits ABOVE the code, never instead of it (persona QA: the learner lost the lines they were typing at the
 * moment they were stuck). Enter presses the primary when focus isn't in a text field or on a button. While a
 * blocking island card is up (engine offline, the recovery card) the panel's primary steps down to the quiet style, so
 * the card's action is the only white button on screen.
 *
 * While shown it tells core/dock (setDock) where it is, so the island's cards step around it and the engine keeps VS
 * Code beside it (panel.state, when the engine lists it).
 */
import { AnimatePresence, motion, useIsPresent, useReducedMotion, type TargetAndTransition, type Variants } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../../preload/api'
import { panelRect, setDock } from '../../../core/dock'
import { islandBoxNow, useIslandBox } from '../../../core/Island'
import { useLesson } from '../../../core/lesson'
import { sendAction, triggerShortcut } from '../../../core/shortcuts'
import { color, type2 } from '../../../core/theme'
import { beat, fade, rise, sizeMove, spring, springOut } from '../../../core/ui/motion'
import { GlassCard } from '../../../core/ui/GlassCard'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { queueCheck, useLinkGate, useQueuedCheck, type Gate } from '../../errors/gate'
import { useSearch } from '../../launcher/store'
import { collapsePanel, useDrawer } from '../store'
import { closeHint, releasePass } from './panelStore'
import { Header } from './Header'
import { Help, useWaitingOn } from './Help'
import { KeysRow } from './KeysRow'
import { CodeBlock, MissingBlock, StepIntro } from './StepBody'
import { CheckingCaption, HintBox, NotYetBox, PassedBody } from './states'
import { Divider } from './ui'
import { PageSource } from './Source'
import { usePanelModel, type PanelModel } from './view'

export type PanelVia = 'edge' | 'pill'

/** Island modes that block the lesson until the learner acts on them: their button is the screen's one primary. */
const BLOCKING = (mode?: string): boolean => !!mode && (mode.startsWith('err-') || mode === 'onboarding-recovery')

export function LessonPanel({ layout }: { layout: Layout }): ReactNode {
  const m = usePanelModel()
  const rect = panelRect(layout)
  const box = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  // Only the winning mode, and only while a card is open: the panel never re-renders because the island moved.
  const blockingMode = useIslandBox((b) => (b.visible && !b.pill ? b.mode : undefined))
  // Where this panel came from, fixed at mount (the exit reads AnimatePresence's `custom`, see index.tsx).
  const [via] = useState<PanelVia>(() => useDrawer.getState().via ?? 'edge')
  // Paused (a blocking card owns Esc and the primary): the keys line dims and goes inert with the body, so the card's
  // own Esc keycap is the only live Esc hint on screen.
  const paused = useLinkGate().kind === 'paused'

  // Tell core/dock where the panel is (screen points, its real height), and that it's gone when it unmounts.
  // Motion (docs/MOTION.md): the height reported is the one the body is springing TO, not the one it is passing
  // through, so a hint or a check tells the dock once instead of on every frame (each report re-rendered the whole
  // panel and moved the island).
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const body = el.querySelector<HTMLElement>('[data-part="panel-body"]')
    const inner = body?.firstElementChild as HTMLElement | null | undefined
    const report = (): void => {
      // Collapsing: the panel is still on screen while it shrinks into the pill, but the dock is already free.
      if (!useDrawer.getState().open) return
      const settled = body && inner ? el.offsetHeight - body.offsetHeight + inner.offsetHeight : el.offsetHeight
      const h = Math.round(Math.min(rect.h, settled))
      setDock({ open: true, collapsed: false, rect: { x: rect.x + layout.origin.x, y: rect.y + layout.origin.y, w: rect.w, h } })
    }
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    if (inner) ro.observe(inner)
    return () => ro.disconnect()
  }, [rect.x, rect.y, rect.w, rect.h, layout.origin.x, layout.origin.y])
  useEffect(() => () => setDock({ open: false, rect: undefined }), [])

  // The pill's box, relative to the panel: where the panel grows from and shrinks back into. Read when the motion
  // starts (variant functions run then), so a collapse that begins while the island is still springing aims at
  // where the pill is now, and the panel doesn't re-render on every island move.
  const pill = (): { x: number; y: number; scale: number } => {
    const b = islandBoxNow()
    return {
      x: b.w ? b.x + b.w / 2 - (rect.x + rect.w / 2) : 0,
      y: b.w ? b.y - rect.y : -24,
      scale: b.w ? Math.max(0.2, Math.min(1, b.w / rect.w)) : 0.9
    }
  }
  // Off the right edge: the panel's width plus its inset, so it starts fully off screen.
  const edgeX = rect.w + Math.max(16, layout.width - (rect.x + rect.w))
  const away = (to: PanelVia): TargetAndTransition => (reduced ? { opacity: 0 } : to === 'pill' ? { opacity: 0, ...pill() } : { opacity: 0, x: edgeX, y: 0, scale: 1 })
  const variants: Variants = {
    hidden: (to: PanelVia = via) => away(to),
    // Out of the pill it grows with the quick fade (it starts small); off the edge, the big surface's slower one.
    shown: { opacity: 1, x: 0, y: 0, scale: 1, transition: { ...spring, opacity: via === 'pill' ? fade.in : fade.slow } },
    gone: (to: PanelVia = 'edge') => ({
      ...away(to),
      transition: { ...springOut, opacity: to === 'pill' ? fade.out : { ...fade.out, delay: beat } }
    })
  }

  return (
    <motion.div
      className="absolute"
      style={{ left: rect.x, top: rect.y, width: rect.w, transformOrigin: 'top center' }}
      custom={via}
      variants={variants}
      initial="hidden"
      animate="shown"
      exit="gone"
    >
      <GlassCard ref={box} hit surface="panel" width={rect.w} className="flex flex-col" style={{ maxHeight: rect.h }}>
        <aside aria-label="miyagi lesson" data-part="lesson-panel" data-view={m.view} data-via={via} className="flex min-h-0 flex-col">
          <Header lessonTitle={m.lessonTitle} total={m.step.total} index={m.step.index} passed={m.passed} skipped={m.skipped} onCollapse={collapsePanel} />
          <Divider />
          <div className="min-h-0 flex-initial overflow-y-auto overflow-x-hidden" style={{ scrollbarWidth: 'thin' }}>
            <AutoHeight>
              <Screens m={m} blocked={BLOCKING(blockingMode)} />
            </AutoHeight>
          </div>
          <motion.div
            className="shrink-0"
            inert={paused || undefined}
            aria-disabled={paused || undefined}
            initial={false}
            animate={{ opacity: paused ? 0.5 : 1 }}
            transition={fade.in}
          >
            <KeysRow onHide={collapsePanel} backDisabled={m.step.index <= 0} />
          </motion.div>
        </aside>
      </GlassCard>
    </motion.div>
  )
}

/** Its height springs to its content's (one spring for the whole body; with reduced motion it just follows). */
function AutoHeight({ children }: { children: ReactNode }): ReactNode {
  const inner = useRef<HTMLDivElement>(null)
  const [h, setH] = useState<number | 'auto'>('auto')
  const reduced = useReducedMotion()
  useLayoutEffect(() => {
    const el = inner.current
    if (!el) return
    const measure = (): void => setH(el.offsetHeight)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <motion.div data-part="panel-body" className="relative overflow-hidden" initial={false} animate={{ height: h }} transition={sizeMove(reduced)}>
      <div ref={inner}>{children}</div>
    </motion.div>
  )
}

type Swap = { kind: 'rise' } | { kind: 'slide'; dir: 1 | -1 }

/**
 * The body's screens: one per step, and on a step, "work" (Working / Checking / Not yet / Hint) or "passed". A new
 * step slides; work <-> passed rises. The old screen is popped out of the flow while it leaves, so the two overlap
 * in place and AutoHeight springs between their heights.
 */
function Screens({ m, blocked }: { m: PanelModel; blocked: boolean }): ReactNode {
  const reduced = useReducedMotion()
  const screen = `${m.step.id ?? 'none'}:${m.view === 'passed' ? 'passed' : 'work'}`
  const last = useRef({ screen, step: m.step.id, index: m.step.index, swap: { kind: 'rise' } as Swap })
  if (last.current.screen !== screen) {
    const stepChanged = last.current.step !== m.step.id
    const dir: 1 | -1 = m.step.index >= last.current.index ? 1 : -1
    last.current = { screen, step: m.step.id, index: m.step.index, swap: stepChanged ? { kind: 'slide', dir } : { kind: 'rise' } }
  }
  const swap = last.current.swap
  const variants: Variants = {
    enter: (s: Swap) => (reduced ? { opacity: 0 } : s.kind === 'slide' ? { opacity: 0, x: 28 * s.dir, y: 0 } : { opacity: 0, x: 0, y: 6 }),
    // A slide's new screen fades in a beat late, so the old one has mostly gone first.
    center: { opacity: 1, x: 0, y: 0, transition: { ...spring, opacity: swap.kind === 'slide' ? { ...fade.in, delay: beat } : fade.in } },
    leave: (s: Swap) =>
      reduced || s.kind === 'rise'
        ? { opacity: 0, transition: fade.out }
        : { opacity: 0, x: -28 * s.dir, transition: { ...springOut, opacity: fade.out } }
  }
  return (
    <AnimatePresence initial={false} mode="popLayout" custom={swap}>
      <motion.div key={screen} data-screen={screen} custom={swap} variants={variants} initial="enter" animate="center" exit="leave" style={{ width: '100%' }}>
        {m.view === 'passed' ? <Passed m={m} /> : <Work m={m} blocked={blocked} />}
      </motion.div>
    </AnimatePresence>
  )
}

const check = (): void => sendAction('check_step')

/** Les-Passed: the green check draws in, core copy.passed (today "Step done.", see Core request 9), Up next, and Next step. */
function Passed({ m }: { m: PanelModel }): ReactNode {
  useEnter(!m.last && m.canNext ? releasePass : undefined)
  return (
    <>
      <PassedBody summary={m.summary} upNext={m.upNext} total={m.step.total} />
      <div style={{ padding: 20 }}>
        {!m.last && <PrimaryButton size="lg" block label="Next step" disabled={!m.canNext} onClick={releasePass} />}
      </div>
    </>
  )
}

/**
 * Working, Checking, Not yet and Hint: one screen; only the boxes that differ come and go.
 *
 * The link gate (features/errors/gate.ts): while miyagi can't answer, the panel says so instead of looking live.
 * paused = a blocking card owns the screen: the body dims and goes inert, so the card's action is the one primary.
 */
function Work({ m, blocked }: { m: PanelModel; blocked: boolean }): ReactNode {
  const s = m.step
  const reduced = useReducedMotion()
  const r = rise(reduced)
  const waiting = useWaitingOn()
  const gate = useLinkGate()
  const paused = gate.kind === 'paused'
  const notYet = m.view === 'notyet' ? m.notYet : undefined
  const hint = m.view === 'hint' ? m.hint : undefined
  const checking = m.view === 'checking'
  const stepId = useLesson((x) => x.stepId)
  const queued = useQueuedCheck((q) => !!q.stepId && q.stepId === stepId)
  // Enter presses what the button would: Check when the link is up, queue it while the gate waits, nothing when paused.
  useEnter(checking || blocked || paused || queued ? undefined : gate.kind === 'wait' ? queueCheck : check)
  const caption = checking || gate.kind === 'ok' ? undefined : queued && gate.kind === 'wait' ? gate.queued ?? gate.caption : gate.caption
  return (
    <motion.div
      data-gate={gate.kind}
      inert={paused || undefined}
      aria-disabled={paused || undefined}
      initial={false}
      animate={{ opacity: paused ? 0.5 : 1 }}
      transition={fade.in}
    >
      <StepIntro title={s.title} instructions={s.instructions} />
      <AnimatePresence initial={false}>
        {notYet && (
          <motion.div key="notyet" initial={r.initial} animate={r.animate} exit={r.exit} transition={r.transition}>
            <NotYetBox lines={notYet.lines} />
          </motion.div>
        )}
        {hint && (
          <motion.div key="hint" initial={r.initial} animate={r.animate} exit={r.exit} transition={r.transition}>
            <HintBox lines={hint.lines} n={hint.n} of={hint.of} onClose={closeHint} onMore={() => triggerShortcut('hint')} moreBusy={waiting === 'hint'} />
          </motion.div>
        )}
      </AnimatePresence>
      {notYet?.missing ? (
        <MissingBlock key={`missing:${s.id}`} lines={notYet.missing} caption={notYet.fixCaption} />
      ) : (
        <CodeBlock key={`code:${s.id}`} code={s.code} where={s.where} kind={s.kind} then={s.then} waiting />
      )}
      <div className="flex flex-col gap-[8px]" style={{ padding: '20px 20px 16px' }}>
        <GatedCheck gate={gate} checking={checking} queued={queued} quiet={blocked} label={m.view === 'notyet' ? 'Check again' : 'Check my work'} />
        {/* A fixed slot under the primary: the Checking caption, or the gate's reason while miyagi can't answer, fades
            in here, so nothing below it moves. */}
        <div className="relative h-[16px]">
          <AnimatePresence initial={false}>
            {checking ? (
              <motion.div key="checking" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: fade.out }} transition={fade.in}>
                <CheckingCaption text={m.checkingCaption} />
              </motion.div>
            ) : (
              caption && (
                <motion.span
                  key={caption}
                  role="status"
                  data-gate-caption
                  className="absolute inset-0 block truncate text-center"
                  style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0, transition: fade.out }}
                  transition={fade.in}
                >
                  {caption}
                </motion.span>
              )
            )}
          </AnimatePresence>
        </div>
      </div>
      <Divider />
      <Help pressed={m.view === 'hint' ? 'hint' : undefined} watchStart={s.video?.start} waiting={waiting} gate={gate} />
      {/* Any link: a page lesson's source (the page, or this step's part of it) where a video lesson has Watch. */}
      <PageSource />
    </motion.div>
  )
}

/**
 * The step's one primary, driven by the link gate: live when ok (busy while checking); "Check when miyagi is back"
 * while waiting (pressed, it queues and turns into a quiet "Queued" with the spinner); disabled while a blocking card
 * is up. Every branch is the same button in the same slot, so a check (or the gate changing) keeps its DOM node and
 * keyboard focus. `quiet`: a blocking island card is up, so the panel's primary steps down to the quiet style.
 */
function GatedCheck({ gate, label, checking, queued, quiet }: { gate: Gate; label: string; checking: boolean; queued: boolean; quiet: boolean }): ReactNode {
  const Button = quiet ? QuietButton : PrimaryButton
  if (checking || gate.kind === 'ok') return <Button size="lg" block busy={checking} label={checking ? 'Checking' : label} onClick={checking ? () => undefined : check} />
  if (gate.kind === 'wait') return <Button size="lg" block busy={queued} disabled={queued} label={queued ? 'Queued' : gate.label ?? label} onClick={queueCheck} />
  return <Button size="lg" block disabled label={label} onClick={() => undefined} />
}

/** After a screen swap, Enter waits this long: a quick double Enter on Next step must not also press Check. */
const ENTER_SETTLE_MS = 300

/**
 * Enter presses the panel's primary (power users; persona QA). Not while typing in a field, not on a focused button
 * or link (Enter already presses that), not with a modifier, not while the launcher is open. Not on a screen that is
 * leaving (popLayout keeps the old one mounted while it fades), and not in the first moments of a new one.
 */
function useEnter(run: (() => void) | undefined): void {
  const present = useIsPresent()
  const ref = useRef(run)
  ref.current = present ? run : undefined
  useEffect(() => {
    const ready = Date.now() + ENTER_SETTLE_MS
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Enter' || e.repeat || e.isComposing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
      const t = e.target as HTMLElement | null
      if (t && (t.closest('input, textarea, select, button, a, [contenteditable=""], [contenteditable="true"]') || t.isContentEditable)) return
      if (useSearch.getState().open || !ref.current) return
      if (Date.now() < ready) return e.preventDefault()
      e.preventDefault()
      ref.current()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])
}
