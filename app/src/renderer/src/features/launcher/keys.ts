/**
 * Feature: launcher. The navigation keycaps (Enter, Tab, the arrows) and the Demo flag.
 *
 * Keycaps come from bridge.platform.keys only (app/CLAUDE.md). The platform has no names for Enter, Tab or the arrows
 * yet (Core request 13 in agents/launcher.md: add `enter`, `tab`, `arrows` to PlatformInfo.keys). Until it does, the
 * launcher reads those names off bridge.platform.keys first and falls back to this one table, keyed by the platform's
 * own `os`, so a Windows build shows "Enter" / "Tab" instead of the Mac glyphs. Nothing else in the launcher types a
 * key label by hand.
 */
import { bridge, isElectron } from '../../bridge'

export type NavKeyName = 'enter' | 'tab' | 'arrows'

const FALLBACK: Record<'mac' | 'win', Record<NavKeyName, string>> = {
  mac: { enter: '↵', tab: '⇥', arrows: '↑↓' },
  win: { enter: 'Enter', tab: 'Tab', arrows: '↑↓' }
}

/** The keycap label for a navigation key, from the platform when it has one. */
export function navKey(name: NavKeyName): string {
  const keys = bridge.platform.keys as Partial<Record<string, string>>
  return keys[name] || FALLBACK[bridge.platform.os === 'win' ? 'win' : 'mac'][name]
}

/** True when a flag is set in the stage URL (?demo, ?demo=1) or in this window's storage (miyagi.demo = 1). */
function flagged(): boolean {
  try {
    if (!isElectron && typeof location !== 'undefined') {
      const p = new URLSearchParams(location.search)
      if (p.has('demo') && p.get('demo') !== '0') return true
    }
  } catch {
    /* no location */
  }
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('miyagi.demo') === '1'
  } catch {
    return false
  }
}

/**
 * The "Demo" way (learn {mode:"demo"}: the engine's staged presenting lesson) is for presenting, not for learners
 * (persona QA: a first-timer can't tell what it does). It shows only:
 *   - in the desktop dev build (electron-vite dev: Michael's demo machine), or
 *   - with the flag: `?demo` on the browser stage, or localStorage `miyagi.demo = 1`.
 * A packaged app and the plain browser stage never offer it.
 */
export const demoEnabled: boolean = (import.meta.env.DEV && isElectron) || flagged()
