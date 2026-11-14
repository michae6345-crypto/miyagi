/** Feature: spotlight (screen-first). Dim + rounded glowing cut-out at the engine's rect + caption. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
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
  return <Spotlight target={here && t} rect={here} bounds={{ x: wa.x, y: wa.y, w: wa.width, h: wa.height }} mode={mode} showCaption={showCaption} />
}

export default defineFeature({ id: 'spotlight', overlayLayers: [{ id: 'spotlight', z: 10, Component: SpotlightLayer }] })
