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
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../../preload/api'
import { panelRect, setDock } from '../../../core/dock'
import { useIslandBox } from '../../../core/Island'
import { sendAction } from '../../../core/shortcuts'
import { spring, springOut } from '../../../core/theme'
import { GlassCard } from '../../../core/ui/GlassCard'
import { PrimaryButton } from '../../../core/ui/buttons'
import { riseIn } from '../../../core/ui/motion'
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
  // Polish (UI-POLISH-SPEC 5): the rise is keyed on the view, with Working and Checking sharing a key, so pressing
  // Check never replays it. `rise` is the key whose new block (Not yet, Hint, Passed) rises when it mounts. Not yet,
  // Checking, Not yet changes key twice, so the fresh finding (remounted after the check) rises like any other state.
  // Null on the first render: the panel's own grow is the entrance there.
  const key: View = m.view === 'checking' ? 'working' : m.view
  const [settled, setSettled] = useState<View>(key)
  const [rise, setRise] = useState<View | null>(null)
  if (key !== settled) {
    setSettled(key)
    setRise(key)
  }

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
            <Body m={m} rise={rise === m.view} />
          </div>
          <KeysRow onHide={collapsePanel} backDisabled={m.step.index <= 0} />
        </aside>
      </GlassCard>
    </motion.div>
  )
}

type View = PanelModel['view']

const check = (): void => sendAction('check_step')

/**
 * Polish: only the block that is new rises 6 px into place (no exit: the old state is gone at once). The step text,
 * the code box, the Check button and Help keep their DOM nodes, so keyboard focus stays put across a check and the
 * unchanged content never blinks. Every rising block sits above other content, so its 6 px never overflows the scroller.
 */
function Rise({ on, children }: { on: boolean; children: ReactNode }): ReactNode {
  return (
    <motion.div initial={on ? riseIn.initial : false} animate={riseIn.animate} transition={riseIn.transition}>
      {children}
    </motion.div>
  )
}

function Body({ m, rise }: { m: PanelModel; rise: boolean }): ReactNode {
  const s = m.step
  if (m.view === 'passed') {
    return (
      <>
        <Rise on={rise}>
          <PassedBody summary={m.summary} upNext={m.upNext} total={s.total} />
        </Rise>
        <div style={{ padding: 20 }}>
          {!m.last && <PrimaryButton size="lg" block label="Next step" disabled={!m.canNext} onClick={releasePass} />}
        </div>
      </>
    )
  }
  const notYet = m.view === 'notyet' ? m.notYet : undefined
  return (
    <>
      <StepIntro title={s.title} instructions={s.instructions} />
      {notYet && (
        <Rise on={rise}>
          <NotYetBox lines={notYet.lines} />
        </Rise>
      )}
      {m.view === 'hint' && m.hint && (
        <Rise on={rise}>
          <HintBox lines={m.hint.lines} n={m.hint.n} of={m.hint.of} onClose={closeHint} />
        </Rise>
      )}
      {notYet?.missing ? (
        <Rise on={rise}>
          <MissingBlock lines={notYet.missing} caption={notYet.fixCaption} />
        </Rise>
      ) : (
        m.view !== 'hint' && <CodeBlock code={s.code} where={s.where} kind={s.kind} then={m.view === 'working' ? s.then : undefined} />
      )}
      <div className="flex flex-col gap-[12px]" style={{ padding: 20 }}>
        {/* Polish: one button in the slot (busy while checking), so it keeps its DOM node and keyboard focus. */}
        <PrimaryButton
          size="lg"
          block
          busy={m.view === 'checking'}
          label={m.view === 'checking' ? 'Checking' : m.view === 'notyet' ? 'Check again' : 'Check my work'}
          onClick={check}
        />
        {m.view === 'checking' && <CheckingCaption text={m.checkingCaption} />}
      </div>
      <Divider />
      <Help pressed={m.view === 'hint' ? 'hint' : undefined} watchStart={s.video?.start} />
    </>
  )
}
