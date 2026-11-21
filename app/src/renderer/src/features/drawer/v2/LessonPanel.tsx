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
import { AnimatePresence, motion, useReducedMotion, type Variants } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../../preload/api'
import { panelRect, setDock } from '../../../core/dock'
import { useIslandBox } from '../../../core/Island'
import { sendAction, triggerShortcut } from '../../../core/shortcuts'
import { spring, springOut } from '../../../core/theme'
import { GlassCard } from '../../../core/ui/GlassCard'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { useSearch } from '../../launcher/store'
import { collapsePanel, useDrawer } from '../store'
import { closeHint, releasePass } from './panelStore'
import { Header } from './Header'
import { Help, useWaitingOn } from './Help'
import { KeysRow } from './KeysRow'
import { FADE_IN, FADE_OUT, rise } from './motion'
import { CodeBlock, MissingBlock, StepIntro } from './StepBody'
import { CheckingCaption, HintBox, NotYetBox, PassedBody } from './states'
import { Divider } from './ui'
import { usePanelModel, type PanelModel } from './view'

export type PanelVia = 'edge' | 'pill'

/** Island modes that block the lesson until the learner acts on them: their button is the screen's one primary. */
const BLOCKING = (mode?: string): boolean => !!mode && (mode.startsWith('err-') || mode === 'onboarding-recovery')

export function LessonPanel({ layout }: { layout: Layout }): ReactNode {
  const m = usePanelModel()
  const rect = panelRect(layout)
  const box = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const island = useIslandBox()
  // Where this panel came from, fixed at mount (the exit reads AnimatePresence's `custom`, see index.tsx).
  const [via] = useState<PanelVia>(() => useDrawer.getState().via ?? 'edge')

  // Tell core/dock where the panel is (screen points, its real height), and that it's gone when it unmounts.
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const report = (): void => {
      // Collapsing: the panel is still on screen while it shrinks into the pill, but the dock is already free.
      if (!useDrawer.getState().open) return
      setDock({ open: true, collapsed: false, rect: { x: rect.x + layout.origin.x, y: rect.y + layout.origin.y, w: rect.w, h: el.offsetHeight } })
    }
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [rect.x, rect.y, rect.w, layout.origin.x, layout.origin.y])
  useEffect(() => () => setDock({ open: false, rect: undefined }), [])

  // The pill's box, relative to the panel: where the panel grows from and shrinks back into.
  const pill = {
    x: island.w ? island.x + island.w / 2 - (rect.x + rect.w / 2) : 0,
    y: island.w ? island.y - rect.y : -24,
    scale: island.w ? Math.max(0.2, Math.min(1, island.w / rect.w)) : 0.9
  }
  // Off the right edge: the panel's width plus its inset, so it starts fully off screen.
  const edgeX = rect.w + Math.max(16, layout.width - (rect.x + rect.w))
  const variants: Variants = {
    hidden: (to: PanelVia = via) =>
      reduced
        ? { opacity: 0 }
        : to === 'pill'
          ? { opacity: 0, x: pill.x, y: pill.y, scale: pill.scale }
          : { opacity: 0, x: edgeX, y: 0, scale: 1 },
    shown: { opacity: 1, x: 0, y: 0, scale: 1, transition: { ...spring, opacity: { duration: via === 'pill' ? 0.18 : 0.24 } } },
    gone: (to: PanelVia = 'edge') => ({
      ...(reduced ? { opacity: 0 } : to === 'pill' ? { opacity: 0, x: pill.x, y: pill.y, scale: pill.scale } : { opacity: 0, x: edgeX, y: 0, scale: 1 }),
      transition: { ...springOut, opacity: { duration: to === 'pill' ? 0.16 : 0.2, delay: to === 'pill' ? 0 : 0.06 } }
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
              <Screens m={m} blocked={BLOCKING(island.visible && !island.pill ? island.mode : undefined)} />
            </AutoHeight>
          </div>
          <KeysRow onHide={collapsePanel} backDisabled={m.step.index <= 0} />
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
    <motion.div data-part="panel-body" className="relative overflow-hidden" initial={false} animate={{ height: h }} transition={reduced ? { duration: 0 } : spring}>
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
    center: { opacity: 1, x: 0, y: 0, transition: { ...spring, opacity: { duration: FADE_IN, delay: swap.kind === 'slide' ? 0.05 : 0 } } },
    leave: (s: Swap) =>
      reduced || s.kind === 'rise'
        ? { opacity: 0, transition: { duration: FADE_OUT } }
        : { opacity: 0, x: -28 * s.dir, transition: { ...spring, opacity: { duration: FADE_OUT } } }
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

/** Les-Passed: the green check draws in, "Good. Now the next one.", Up next, and Next step. */
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

/** Working, Checking, Not yet and Hint: one screen; only the boxes that differ come and go. */
function Work({ m, blocked }: { m: PanelModel; blocked: boolean }): ReactNode {
  const s = m.step
  const reduced = useReducedMotion()
  const r = rise(reduced)
  const waiting = useWaitingOn()
  const notYet = m.view === 'notyet' ? m.notYet : undefined
  const hint = m.view === 'hint' ? m.hint : undefined
  const checking = m.view === 'checking'
  useEnter(!checking && !blocked ? check : undefined)
  const Button = blocked ? QuietButton : PrimaryButton
  return (
    <>
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
        {checking ? (
          <Button size="lg" block busy label="Checking" onClick={() => undefined} />
        ) : (
          <Button size="lg" block label={m.view === 'notyet' ? 'Check again' : 'Check my work'} onClick={check} />
        )}
        {/* A fixed slot under the primary: the Checking caption fades in here, so nothing below it moves. */}
        <div className="relative h-[16px]">
          <AnimatePresence>
            {checking && (
              <motion.div key="caption" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: FADE_IN }}>
                <CheckingCaption text={m.checkingCaption} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      <Divider />
      <Help pressed={m.view === 'hint' ? 'hint' : undefined} watchStart={s.video?.start} waiting={waiting} />
    </>
  )
}

/**
 * Enter presses the panel's primary (power users; persona QA). Not while typing in a field, not on a focused button
 * or link (Enter already presses that), not with a modifier, not while the launcher is open.
 */
function useEnter(run: (() => void) | undefined): void {
  const ref = useRef(run)
  ref.current = run
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Enter' || e.repeat || e.isComposing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
      const t = e.target as HTMLElement | null
      if (t && (t.closest('input, textarea, select, button, a, [contenteditable=""], [contenteditable="true"]') || t.isContentEditable)) return
      if (useSearch.getState().open || !ref.current) return
      e.preventDefault()
      ref.current()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])
}
