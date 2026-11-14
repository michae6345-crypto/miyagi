/** Feature: spotlight (screen-first). Dim + rounded glowing cut-out at the engine's rect + caption. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
import { Spotlight } from './Spotlight'
import { useSpotlight } from './store'

function SpotlightLayer({ layout }: { layout: Layout }): ReactNode {
  const t = useSpotlight((s) => s.target)
  // Engine rects are in screen points; this window starts at layout.origin.
  const rect = t && { x: t.rect.x - layout.origin.x, y: t.rect.y - layout.origin.y, w: t.rect.w, h: t.rect.h }
  return <Spotlight rect={rect} screenW={layout.width} />
}

export default defineFeature({ id: 'spotlight', overlayLayers: [{ id: 'spotlight', z: 10, Component: SpotlightLayer }] })
