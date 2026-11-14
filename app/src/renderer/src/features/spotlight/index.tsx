/** Feature: spotlight (screen-first). Dim + rounded cut-out with a hairline ring at the engine's rect + caption. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { dockRect } from '../player/dock'
import { hole, intersects, overlapShare, toLocal } from './place'
import { Spotlight } from './Spotlight'
import { spotlightMode, useSpotlight } from './store'

const mode = spotlightMode()

function SpotlightLayer({ layout }: { layout: Layout }): ReactNode {
  const t = useSpotlight((s) => s.target)
  const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
  const wa = layout.workArea
  // Engine rects are screen points from the primary display's top-left; this window starts at layout.origin.
  const local = t && toLocal(t.rect, layout.origin)
  const cut = local && hole(local)
  // Only draw on the display the target is on: dimming a display with no hole would hide the player.
  const here = cut && intersects(cut, screen) ? local : undefined
  // A target straddling two displays: the caption goes where most of it is.
  const showCaption = !!cut && overlapShare(cut, screen) >= 0.5
  // In Electron the lesson player is its own window (docked right 40%), so the overlay DOM can't see it:
  // keep the caption off it using the player's own dock math. (In the stage it's also in the DOM.)
  const lessonOn = useLesson((s) => !!s.lesson)
  const dock = lessonOn ? dockRect(wa) : undefined
  const avoid = dock ? [{ x: dock.x, y: dock.y, w: dock.width, h: dock.height }] : []
  return <Spotlight target={here && t} rect={here} bounds={{ x: wa.x, y: wa.y, w: wa.width, h: wa.height }} avoid={avoid} mode={mode} showCaption={showCaption} />
}

export default defineFeature({ id: 'spotlight', overlayLayers: [{ id: 'spotlight', z: 10, Component: SpotlightLayer }] })
