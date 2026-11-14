/**
 * Feature: settings. Open/close requests and a counter of config.status answers (Test waits on it).
 * Loaded in every window (the registry imports every feature); only the `settings` window renders the sheet.
 * No key ever lands here: typed values stay in the sheet's own state until Save sends them to main.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'

export type Size = { w: number; h: number }

type SettingsState = {
  /** Bumped on every open request; `from` = the island's shape to grow out of. */
  open: { seq: number; from?: Size }
  /** Bumped when something outside asks the sheet to collapse (Electron: the window lost focus). */
  close: number
  /** Bumped on every config.status from the engine. */
  statusSeq: number
}

export const useSettings = create<SettingsState>(() => ({ open: { seq: 0 }, close: 0, statusSeq: 0 }))

export function requestOpen(from?: Size): void {
  useSettings.setState((s) => ({ open: { seq: s.open.seq + 1, from } }))
}

export function requestClose(): void {
  useSettings.setState((s) => ({ close: s.close + 1 }))
}

onMessage('config.status', () => useSettings.setState((s) => ({ statusSeq: s.statusSeq + 1 })))

// Electron: main broadcasts these to every window (src/main/features/settings.ts).
bridge.onFeature('settings:open', (p) => requestOpen((p as { from?: Size } | undefined)?.from))
bridge.onFeature('settings:close', () => requestClose())

/** Resolves on the next config.status after `since`, or false after `ms`. */
export function nextStatus(since: number, ms = 3000): Promise<boolean> {
  return new Promise((resolve) => {
    if (useSettings.getState().statusSeq > since) return resolve(true)
    const timer = setTimeout(() => {
      off()
      resolve(false)
    }, ms)
    const off = useSettings.subscribe((s) => {
      if (s.statusSeq <= since) return
      clearTimeout(timer)
      off()
      resolve(true)
    })
  })
}
