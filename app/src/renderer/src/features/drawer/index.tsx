/**
 * Feature: drawer. Brief: app/agents/drawer.md
 *
 * A slim tab on the right edge; click it and the lesson drawer slides in: every step (done / current /
 * locked, the current one with its checks), "More steps coming" while a long video builds part by part,
 * and the lesson's sources. One overlay layer at z 40 (under the island and the shortcut bar).
 *
 * Never covers the spotlight target: while a spotlight hole touches the open panel (or, closed, the tab),
 * it slides away; if the learner had it open, it slides back a beat after the target moves on.
 * In a "Just teach me" lesson only a Show me answer makes it yield: the step's own "type here" spotlight stays up
 * for the whole step (A9), and hiding the drawer for it left the learner with no steps, code or checks, not even
 * the tab (Michael's test 5, Sun 2:10 AM).
 *
 * A run step (step.kind "run") tucks it to the "Steps" handle: the learner needs VS Code's Run button and the terminal,
 * both under the panel (Michael's test, Sun 2:56 AM). Pressing the handle shows it again for that step; the next step
 * puts it back as it was.
 */
import { AnimatePresence } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { useLesson, type Rect } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { hole, intersects, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'
import { ConceptPanel, Rail } from './Concept'
import { Panel, Tab } from './Drawer'
import { FloatNetLayer } from './FloatNet'
import { conceptRects, panelRect, tabRect } from './geometry'
import { Selectable, SelectionExplain } from './SelectionExplain'
import { useStepDetail } from './plan'
import { peekDrawer, useDrawer } from './store'

/** After the spotlight leaves, wait this long before sliding back (a spotlight tour hops between targets). */
const RETURN_MS = 700

function DrawerLayer({ layout }: { layout: Layout }): ReactNode {
  const on = useLesson((s) => !!s.lesson)
  const open = useDrawer((s) => s.open)
  const panelH = useDrawer((s) => s.panelH)
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  // Mockup 02: a concept open = the drawer collapsed to a step rail + the concept panel beside it.
  const concept = useDrawer((s) => s.concept)
  const panel = panelRect(layout, lessonMode)
  const conceptAt = conceptRects(layout, lessonMode)
  const tab = tabRect(layout, lessonMode)
  // What the drawer covers: open (even while it has yielded) = the panel at its real height (or the concept
  // panel + rail), out to the edge; closed = just the tab.
  const left = concept ? conceptAt.panel.x : panel.x
  const area: Rect = open ? { x: left, y: panel.y, w: tab.x + tab.w - left, h: concept ? panel.h : Math.min(panel.h, panelH ?? panel.h) } : tab
  const showMe = useSpotlight((s) => s.showMe)
  const yielding = useYield(useSpotlightOn(area, layout) && (!lessonMode || showMe))
  const runStep = useStepDetail((s) => (s.detail?.kind === 'run' ? s.detail.stepId : undefined))
  const peekStep = useDrawer((s) => s.peekStep)
  const tucked = lessonMode && open && !!runStep && peekStep !== runStep
  const showPanel = on && open && !yielding && !tucked
  return (
    <>
      <Tab rect={tab} shown={on && !showPanel && (!yielding || tucked)} labeled={lessonMode} onOpen={tucked && runStep ? () => peekDrawer(runStep) : undefined} />
      <Selectable>
        <AnimatePresence>
          {showPanel && !concept && <Panel key="drawer" rect={panel} />}
          {showPanel && concept && <Rail key="rail" rect={conceptAt.rail} />}
          {showPanel && concept && <ConceptPanel key="concept" rect={conceptAt.panel} />}
        </AnimatePresence>
      </Selectable>
      <SelectionExplain />
    </>
  )
}

/** Does the spotlight's hole (engine rect + the spotlight's own padding) touch `area`? */
function useSpotlightOn(area: Rect, layout: Layout): boolean {
  const rect = useSpotlight((s) => s.target?.rect)
  return !!rect && intersects(hole(toLocal(rect, layout.origin)), area)
}

/** Yield at once; come back RETURN_MS after the reason is gone. */
function useYield(reason: boolean): boolean {
  const [held, setHeld] = useState(reason)
  useEffect(() => {
    if (reason) return setHeld(true)
    const id = setTimeout(() => setHeld(false), RETURN_MS)
    return () => clearTimeout(id)
  }, [reason])
  return reason || held
}

export default defineFeature({ id: 'drawer', overlayLayers: [
    { id: 'drawer', z: 40, Component: DrawerLayer },
    // The live network, dragged out of the drawer: over the drawer, under the island (z 50).
    { id: 'drawer-net-float', z: 45, Component: FloatNetLayer }
  ]
})
