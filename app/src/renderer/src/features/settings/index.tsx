/**
 * Feature: settings. Brief: app/agents/settings.md
 *
 * Bring-your-own keys: the Keys sheet grows out of the notch island and collapses back into it.
 *   Electron      → its own focusable window (route `settings`), created by src/main/features/settings.ts,
 *                   which owns the keys (safeStorage) and sends config.keys.
 *   Browser stage → the same sheet as a stage window over the launcher; web.ts stands in for main.
 * Open it from anywhere with openSettings() (./open.ts). First run opens it when a required key is missing.
 */
import { defineFeature } from '../../core/registry'
import { Settings } from './Settings'
import './store'
import './web'

export default defineFeature({
  id: 'settings',
  windows: [{ route: 'settings', Component: Settings, stage: 'fill', z: 20 }]
})
