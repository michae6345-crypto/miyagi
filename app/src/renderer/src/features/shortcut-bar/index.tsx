/** Feature: shortcut bar. Bottom bar during a lesson: Ask Miyagi + Back / Explain / Diagram / Show me / Hint / Voice. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
import { useLift } from './lift'
import { ShortcutBar } from './ShortcutBar'

/**
 * The bar's lower edge above the Dock / taskbar: clear of an editor's status bar (VS Code's is 22px) with a little air
 * (review A12: it covered the status bar). The folded handle sits lower, over the status bar's empty middle.
 */
const ABOVE_DOCK = 30

function BarLayer({ layout }: { layout: Layout }): ReactNode {
  // Lifted above the spotlight's hole when it reaches into the bar (./lift.ts).
  const dock = layout.height - (layout.workArea.y + layout.workArea.height)
  const bottom = dock + ABOVE_DOCK
  const lift = useLift(layout, bottom)
  return <ShortcutBar bottom={bottom} dock={dock} lift={lift} />
}

export default defineFeature({ id: 'shortcut-bar', overlayLayers: [{ id: 'shortcut-bar', z: 60, Component: BarLayer }] })
