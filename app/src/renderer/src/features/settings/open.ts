/**
 * Feature: settings. The one way to open it from anywhere (the overview's gear):
 *
 *   import { openSettings } from '../settings/open'
 *   <button onClick={() => openSettings()}>…</button>      or openSettings('permissions')
 *
 * Features that don't import settings use core/surfaces `openSettings(section?)`: the same `settings:open` call.
 * The sheet grows out of the island wherever the island is right now (pill or card). Already open: it switches section.
 */
import { bridge } from '../../bridge'
import { isSection, type SettingsSection } from './env'

/** `section` is checked: an onClick passing its event straight through still opens the sheet, on the last section. */
export function openSettings(section?: SettingsSection | unknown): void {
  bridge.invoke('settings:open', isSection(section) ? { section } : undefined).catch(() => {})
}
