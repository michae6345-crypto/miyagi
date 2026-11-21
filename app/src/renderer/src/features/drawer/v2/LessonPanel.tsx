/**
 * Feature: drawer (v2, BUILD-PLAN A1). The lesson panel docked at the right edge (Les-Working, Les-Checking,
 * Les-NotYet, Les-Hint, Les-Passed): 360 wide, 16 in from the edge, top 52 at 1440x900 (core/dock panelRect).
 *
 * Top to bottom: Header (tree, miyagi, collapse; lesson title, step dots, "Step N of M"), a hairline, the state's body,
 * the ONE primary (Check my work / Checking / Check again / Next step), a hairline and "Need help" (not on Les-Passed),
 * then the keys line (Esc hide, ask miyagi, Back, Voice). The view comes from view.ts (passed > checking > notyet >
 * hint > working). The panel hugs its content; past the dock's height the middle scrolls, header and keys stay.
 *
 * Born from the island: it grows out of the pill's box and collapses back into it (transform and opacity, the one
 * spring; opacity only with reduced motion). While shown it tells core/dock (setDock) where it is, so the island's
 * cards step around it and the engine keeps VS Code beside it (panel.state, when the engine lists it).
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import type { Layout } from '../../../../../preload/api'
import { panelRect, setDock } from '../../../core/dock'
import { useIslandBox } from '../../../core/Island'
import { useLesson } from '../../../core/lesson'
import { sendAction } from '../../../core/shortcuts'
import { color, spring, springOut, type2 } from '../../../core/theme'
import { queueCheck, useLinkGate, useQueuedCheck, type Gate } from '../../errors/gate'
import { GlassCard } from '../../../core/ui/GlassCard'
import { PrimaryButton } from '../../../core/ui/buttons'
import { collapsePanel, useDrawer } from '../store'
import { closeHint, releasePass } from './panelStore'
import { Header } from './Header'
import { Help } from './Help'
import { KeysRow } from './KeysRow'
import { CodeBlock, MissingBlock, StepIntro } from './StepBody'
import { CheckingCaption, HintBox, NotYetBox, PassedBody } from './states'
import { Divider } from './ui'
import { usePanelModel, type PanelModel } from './view'

export function LessonPanel({ layout }: { layout: Layout }): ReactNode {
  const m = usePanelModel()
  const rect = panelRect(layout)
  const box = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const island = useIslandBox()

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

  // Grow out of the pill: start at the island's box (its center, its width), scale up into place.
  const fromX = island.w ? island.x + island.w / 2 - (rect.x + rect.w / 2) : 0
  const fromY = island.w ? island.y - rect.y : -24
  const fromScale = island.w ? Math.max(0.2, Math.min(1, island.w / rect.w)) : 0.9
  const hidden = reduced ? { opacity: 0 } : { opacity: 0, x: fromX, y: fromY, scale: fromScale }

  return (
    <motion.div
      className="absolute"
      style={{ left: rect.x, top: rect.y, width: rect.w, transformOrigin: 'top center' }}
      initial={hidden}
      animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
      exit={{ ...hidden, transition: { ...springOut, opacity: { duration: 0.16 } } }}
      transition={{ ...spring, opacity: { duration: 0.18 } }}
    >
      <GlassCard ref={box} hit surface="panel" width={rect.w} className="flex flex-col" style={{ maxHeight: rect.h }}>
        <aside aria-label="miyagi lesson" data-part="lesson-panel" data-view={m.view} className="flex min-h-0 flex-col">
          <Header lessonTitle={m.lessonTitle} total={m.step.total} index={m.step.index} passed={m.passed} skipped={m.skipped} onCollapse={collapsePanel} />
          <Divider />
          <div className="min-h-0 flex-initial overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
            <Body m={m} />
          </div>
          <KeysRow onHide={collapsePanel} backDisabled={m.step.index <= 0} />
        </aside>
      </GlassCard>
    </motion.div>
  )
}

const check = (): void => sendAction('check_step')

function Body({ m }: { m: PanelModel }): ReactNode {
  const s = m.step
  const gate = useLinkGate()
  if (m.view === 'passed') {
    return (
      <>
        <PassedBody summary={m.summary} upNext={m.upNext} total={s.total} />
        <div style={{ padding: 20 }}>
          {!m.last && <PrimaryButton size="lg" block label="Next step" disabled={!m.canNext} onClick={releasePass} />}
        </div>
      </>
    )
  }
  const notYet = m.view === 'notyet' ? m.notYet : undefined
  // The link gate (features/errors/gate.ts): while miyagi can't answer, the panel says so instead of looking live.
  // paused = a blocking card owns the screen: the body dims and goes inert, so the card's action is the one primary.
  const paused = gate.kind === 'paused'
  return (
    <motion.div
      data-gate={gate.kind}
      inert={paused || undefined}
      aria-disabled={paused || undefined}
      initial={false}
      animate={{ opacity: paused ? 0.5 : 1 }}
      transition={{ duration: 0.2 }}
    >
      <StepIntro title={s.title} instructions={s.instructions} />
      {notYet && <NotYetBox lines={notYet.lines} />}
      {m.view === 'hint' && m.hint && <HintBox lines={m.hint.lines} n={m.hint.n} of={m.hint.of} onClose={closeHint} />}
      {notYet?.missing ? (
        <MissingBlock lines={notYet.missing} caption={notYet.fixCaption} />
      ) : (
        m.view !== 'hint' && <CodeBlock code={s.code} where={s.where} kind={s.kind} then={m.view === 'working' ? s.then : undefined} />
      )}
      <div className="flex flex-col gap-[12px]" style={{ padding: 20 }}>
        {m.view === 'checking' ? (
          <>
            <PrimaryButton size="lg" block busy label="Checking" onClick={() => undefined} />
            <CheckingCaption text={m.checkingCaption} />
          </>
        ) : (
          <GatedCheck gate={gate} label={m.view === 'notyet' ? 'Check again' : 'Check my work'} />
        )}
      </div>
      <Divider />
      <Help pressed={m.view === 'hint' ? 'hint' : undefined} watchStart={s.video?.start} gate={gate} />
    </motion.div>
  )
}

/**
 * The step's one primary, driven by the link gate: live when ok; "Check when miyagi is back" while waiting (pressed, it
 * queues and turns into a quiet "Queued" with the spinner); disabled with the reason while a blocking card is up.
 * The caption fades in and out with the house spring, so the button comes back smoothly when the link recovers.
 */
function GatedCheck({ gate, label }: { gate: Gate; label: string }): ReactNode {
  const stepId = useLesson((x) => x.stepId)
  const queued = useQueuedCheck((q) => !!q.stepId && q.stepId === stepId)
  const reduced = useReducedMotion()
  const waiting = gate.kind === 'wait'
  const caption = gate.kind === 'ok' ? undefined : queued && waiting ? 'Queued. It runs when miyagi is back.' : gate.caption
  return (
    <>
      {gate.kind === 'ok' ? (
        <PrimaryButton size="lg" block label={label} onClick={check} />
      ) : waiting ? (
        <PrimaryButton size="lg" block busy={queued} disabled={queued} label={queued ? 'Queued' : gate.label ?? label} onClick={queueCheck} />
      ) : (
        <PrimaryButton size="lg" block disabled label={label} onClick={() => undefined} />
      )}
      <AnimatePresence initial={false}>
        {caption && (
          <motion.span
            key={caption}
            role="status"
            data-gate-caption
            className="block text-center"
            style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: 0.12 } }}
            transition={{ ...spring, opacity: { duration: 0.18 } }}
          >
            {caption}
          </motion.span>
        )}
      </AnimatePresence>
    </>
  )
}
