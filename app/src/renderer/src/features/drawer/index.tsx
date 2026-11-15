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
 * puts it back as it was. The live network floats out meanwhile (runTuck.ts, FloatNet.tsx).
 *
 * Left or right (Michael, Nov 15 5:45 AM): dragging the header sideways moves it to the other edge, and it stays there.
 * When the spotlight's target sits under it (its center inside the panel: the Run ▷ box, a button, never a whole-line
 * "type here" box, whose center is in the code), it slides to the other edge instead of hiding or tucking, and slides
 * back RETURN_MS after the target moves on. Only when both edges would cover the target does the old yield / tuck apply.
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
import { useRunTuck } from './runTuck'
import { peekDrawer, setDrawerAt, useDrawer, type Side } from './store'

/** After the spotlight leaves, wait this long before sliding back (a spotlight tour hops between targets). */
const RETURN_MS = 700

function DrawerLayer({ layout }: { layout: Layout }): ReactNode {
  const on = useLesson((s) => !!s.lesson)
  const open = useDrawer((s) => s.open)
  const panelH = useDrawer((s) => s.panelH)
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  // Mockup 02: a concept open = the drawer collapsed to a step rail + the concept panel beside it.
  const concept = useDrawer((s) => s.concept)
  const chosen = useDrawer((s) => s.side)
  const other: Side = chosen === 'left' ? 'right' : 'left'
  // The spotlight target's center: under the chosen edge's panel and clear of the other edge's? Slide over.
  const target = useSpotlight((s) => s.target?.rect)
  const center = target ? centerOf(toLocal(target, layout.origin)) : undefined
  const under = (side: Side): boolean => !!center && inside(center, panelArea(layout, lessonMode, side, open, !!concept, panelH))
  const flip = useHold(open && under(chosen) && !under(other))
  const side: Side = flip ? other : chosen
  useEffect(() => setDrawerAt(side), [side])
  const panel = panelRect(layout, lessonMode, side)
  const conceptAt = conceptRects(layout, lessonMode, side)
  const tab = tabRect(layout, lessonMode, side)
  // What the drawer covers: open (even while it has yielded) = the panel at its real height (or the concept
  // panel + rail), out to the edge; closed = just the tab.
  const left = concept ? conceptAt.panel.x : panel.x
  const area: Rect = open ? { x: left, y: panel.y, w: tab.x + tab.w - left, h: concept ? panel.h : Math.min(panel.h, panelH ?? panel.h) } : tab
  const showMe = useSpotlight((s) => s.showMe)
  const yielding = useYield(useSpotlightOn(area, layout) && (!lessonMode || showMe))
  const runStep = useRunTuck()
  // A run step whose target the drawer already slid off (or never covered) stays out: no need to tuck it away.
  const tucked = !!runStep && !(center && !under(side))
  const showPanel = on && open && !yielding && !tucked
  return (
    <>
      <Tab rect={tab} shown={on && !showPanel && (!yielding || tucked)} labeled={lessonMode} onOpen={tucked && runStep ? () => peekDrawer(runStep) : undefined} />
      <Selectable>
        <AnimatePresence>
          {/* Keyed by side: moving edges slides it out one side and in at the other (transform only). */}
          {showPanel && !concept && <Panel key={`drawer-${side}`} rect={panel} side={side} />}
          {showPanel && concept && <Rail key="rail" rect={conceptAt.rail} />}
          {showPanel && concept && <ConceptPanel key="concept" rect={conceptAt.panel} />}
        </AnimatePresence>
      </Selectable>
      <SelectionExplain />
    </>
  )
}

const centerOf = (r: Rect): { x: number; y: number } => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })
const inside = (p: { x: number; y: number }, r: Rect): boolean => p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h

/** What the open drawer covers on `side` (the panel at its real height, or the concept panel + rail). */
function panelArea(layout: Layout, lessonMode: boolean, side: Side, open: boolean, concept: boolean, panelH?: number): Rect {
  const p = panelRect(layout, lessonMode, side)
  if (!open) return tabRect(layout, lessonMode, side)
  if (!concept) return { ...p, h: Math.min(p.h, panelH ?? p.h) }
  const c = conceptRects(layout, lessonMode, side)
  const x = Math.min(c.rail.x, c.panel.x)
  return { x, y: p.y, w: Math.max(c.rail.x + c.rail.w, c.panel.x + c.panel.w) - x, h: p.h }
}

/** On at once; off RETURN_MS after the reason is gone (so a spotlight hopping between targets doesn't bounce it). */
function useHold(reason: boolean): boolean {
  return useYield(reason)
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
