/**
 * Feature: launcher. A cached lesson's picture in the launcher's rows (v4: the Library's rows draw the same art,
 * plans/Thumb), from the tool it runs in and its title. Neutral line art, never a hue (brand). Mirrors the Library's
 * fallback for a lesson outside any plan. Pure (type imports only), so it is tested offline.
 */
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import type { Art } from '../plans/Thumb'

export function artOfItem(item: Pick<LibraryItem, 'tools' | 'title'>): Art {
  const t = item.tools?.[0]
  if (t === 'terminal') return 'terminal'
  if (t === 'excel') return 'table'
  if (t !== 'jupyter') return 'code'
  if (/plot|chart/i.test(item.title)) return 'plot'
  if (/csv|pandas|table|sales/i.test(item.title)) return 'table'
  if (/neural|network|layer/i.test(item.title)) return 'network'
  return 'code'
}
