/** Feature: shortcut bar. Bottom bar during a lesson: Ask Miyagi + Back / Explain / Diagram / Show me / Hint / Voice. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
import { ABOVE_DOCK, useLift } from './lift'
import { ShortcutBar } from './ShortcutBar'


function BarLayer({ layout }: { layout: Layout }): ReactNode {
  // Lifted above the spotlight's hole when it reaches into the bar (./lift.ts).
  const dock = layout.height - (layout.workArea.y + layout.workArea.height)
  const bottom = dock + ABOVE_DOCK
  const lift = useLift(layout, bottom)
  return <ShortcutBar bottom={bottom} dock={dock} lift={lift} />
}

export default defineFeature({ id: 'shortcut-bar', overlayLayers: [{ id: 'shortcut-bar', z: 60, Component: BarLayer }] })
