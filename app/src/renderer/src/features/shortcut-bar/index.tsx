/** Feature: shortcut bar. Bottom bar during a lesson: Ask anything + Back / Explain / Diagram / Show me / Hint / Voice. */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { defineFeature } from '../../core/registry'
import { ShortcutBar } from './ShortcutBar'

function BarLayer({ layout }: { layout: Layout }): ReactNode {
  // 24px above the dock / taskbar.
  return <ShortcutBar bottom={layout.height - (layout.workArea.y + layout.workArea.height) + 24} />
}

export default defineFeature({ id: 'shortcut-bar', overlayLayers: [{ id: 'shortcut-bar', z: 60, Component: BarLayer }] })
