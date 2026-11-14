/** Feature: launcher. Spotlight-style search window (⌥Space · Ctrl+Shift+Space on Windows). */
import { defineFeature } from '../../core/registry'
import { Launcher } from './Launcher'

export default defineFeature({
  id: 'launcher',
  windows: [{ route: 'launcher', Component: Launcher, stage: 'fill', z: 10 }]
})
