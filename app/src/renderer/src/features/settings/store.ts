/**
 * Feature: settings. Open/close requests, the section on show, and a counter of config.status answers (Test waits on it).
 * Loaded in every window (the registry imports every feature); only the `settings` window renders the sheet.
 * No key ever lands here: typed values stay in the sheet's own state until Save sends them to main.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { isPanel, type PanelId } from './panels'

/** `place: 'notch'` + `radii`: the island lives in the notch (the sheet starts flat on the display top with the notch's radii). */
export type Size = { w: number; h: number; place?: 'notch'; radii?: { top: number; bottom: number } }

type SettingsState = {
  /** Bumped on every open request; `from` = the island's shape to grow out of. */
  open: { seq: number; from?: Size }
  /** Bumped when something outside asks the sheet to collapse (Electron: the window lost focus). */
  close: number
  /** Bumped on every config.status from the engine. */
  statusSeq: number
  /** The sidebar section on show. An open request with a section switches to it; without one, the last stays. */
  section: PanelId
  /**
   * How the section was reached: 'keys' = ↑ / ↓ / Home / End in the sidebar (focus stays on the section list so the
   * arrows keep working); undefined = opened from outside (openSettings) or clicked, so the section may take focus.
   */
  via?: 'keys'
}

export const useSettings = create<SettingsState>(() => ({ open: { seq: 0 }, close: 0, statusSeq: 0, section: 'general' }))

export function requestOpen(from?: Size, section?: unknown): void {
  useSettings.setState((s) => ({ open: { seq: s.open.seq + 1, from }, section: isPanel(section) ? section : s.section, via: undefined }))
}

export function requestClose(): void {
  useSettings.setState((s) => ({ close: s.close + 1 }))
}

export function setSection(section: unknown, via?: 'keys'): void {
  if (isPanel(section)) useSettings.setState({ section, via })
}

onMessage('config.status', () => useSettings.setState((s) => ({ statusSeq: s.statusSeq + 1 })))

// Electron: main broadcasts these to every window (src/main/features/settings.ts).
bridge.onFeature('settings:open', (p) => {
  const o = (p ?? {}) as { from?: Size; section?: unknown }
  requestOpen(o.from, o.section)
})
// Already open: openSettings(section) only switches the section.
bridge.onFeature('settings:section', (p) => setSection((p as { section?: unknown } | undefined)?.section))
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
