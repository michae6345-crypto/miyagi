/**
 * Feature: settings. Brief: app/agents/settings.md
 *
 * Settings v2 (A4): a 912x576 sheet that grows out of the notch island and collapses back into it, with a sidebar:
 * General, Permissions, Privacy, Your own key (bring-your-own keys), Shortcuts.
 *   Electron      → its own focusable window (route `settings`), created by src/main/features/settings.ts,
 *                   which owns the keys (safeStorage) and sends config.keys.
 *   Browser stage → the same sheet as a stage window over the launcher; web.ts stands in for main.
 * Open it from anywhere with openSettings(section?) (./open.ts, or core/surfaces for features that don't import this).
 */
import { defineFeature } from '../../core/registry'
import { Settings } from './Settings'
import './store'
import './web'

export default defineFeature({
  id: 'settings',
  windows: [{ route: 'settings', Component: Settings, stage: 'fill', z: 20 }]
})
