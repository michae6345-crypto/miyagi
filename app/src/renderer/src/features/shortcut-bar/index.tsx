/** Feature: shortcut bar. Bottom bar during a lesson: Ask Miyagi + Back / Explain / Diagram / Show me / Hint / Voice. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
import { ABOVE_DOCK, useLift } from './lift'
import { BAR_HEIGHT, ShortcutBar } from './ShortcutBar'
import { SLIM_HEIGHT } from './slim'
import { useSlim } from './useSlim'


function BarLayer({ layout }: { layout: Layout }): ReactNode {
  // Lifted above the spotlight's hole when it reaches into the bar (./lift.ts).
  const dock = layout.height - (layout.workArea.y + layout.workArea.height)
  const bottom = dock + ABOVE_DOCK
  const slim = useSlim()
  const lift = useLift(layout, bottom, slim ? SLIM_HEIGHT : BAR_HEIGHT)
  return <ShortcutBar bottom={bottom} dock={dock} lift={lift} slim={slim} />
}

export default defineFeature({ id: 'shortcut-bar', overlayLayers: [{ id: 'shortcut-bar', z: 60, Component: BarLayer }] })
