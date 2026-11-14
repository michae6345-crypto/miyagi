/**
 * Feature: settings. The one way to open it from anywhere (the overview's gear):
 *
 *   import { openSettings } from '../settings/open'
 *   <button onClick={openSettings}>…</button>
 *
 * The sheet grows out of the island wherever the island is right now (pill or card).
 */
import { bridge } from '../../bridge'

export function openSettings(): void {
  bridge.invoke('settings:open').catch(() => {})
}
