/**
 * Feature: drawer. Brief: app/agents/drawer.md
 *
 * A slim tab on the right edge; click it and the lesson drawer slides in: every step (done / current /
 * locked, the current one with its checks), "More steps coming" while a long video builds part by part,
 * and the lesson's sources. One overlay layer at z 40 (under the island and the shortcut bar).
 *
 * Never covers the spotlight target: while a spotlight hole touches the open panel (or, closed, the tab),
 * it slides away; if the learner had it open, it slides back a beat after the target moves on.
 */
import { AnimatePresence } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { useLesson, type Rect } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { hole, intersects, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'
import { Panel, Tab } from './Drawer'
import { panelRect, tabRect } from './geometry'
import { useDrawer } from './store'

/** After the spotlight leaves, wait this long before sliding back (a spotlight tour hops between targets). */
const RETURN_MS = 700

function DrawerLayer({ layout }: { layout: Layout }): ReactNode {
  const on = useLesson((s) => !!s.lesson)
  const open = useDrawer((s) => s.open)
  const panelH = useDrawer((s) => s.panelH)
  const panel = panelRect(layout)
  const tab = tabRect(layout)
  // What the drawer covers: open (even while it has yielded) = the panel at its real height, out to the edge;
  // closed = just the tab.
  const area: Rect = open ? { x: panel.x, y: panel.y, w: tab.x + tab.w - panel.x, h: Math.min(panel.h, panelH ?? panel.h) } : tab
  const yielding = useYield(useSpotlightOn(area, layout))
  const showPanel = on && open && !yielding
  return (
    <>
      <Tab rect={tab} shown={on && !showPanel && !yielding} />
      <AnimatePresence>{showPanel && <Panel key="drawer" rect={panel} />}</AnimatePresence>
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

export default defineFeature({ id: 'drawer', overlayLayers: [{ id: 'drawer', z: 40, Component: DrawerLayer }] })
