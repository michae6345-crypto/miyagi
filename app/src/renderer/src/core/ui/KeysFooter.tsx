/**
 * Core (v2, W0-3): the quiet keys line at the bottom of a panel or window (Les-*: "Esc hide · ⌥Space ask miyagi
 * anything"). Keycaps come from the platform only; a key this platform lacks drops its item.
 *
 *   <KeysFooter items={[{ k: 'dismiss', label: 'hide' }, { k: 'launcher', label: copy.launcherPlaceholder }]} />
 */
import type { ReactNode } from 'react'
import { Keycap, keyLabel, type KeyName } from './Keycap'
import { color, fill, paper, type2 } from '../theme'

export type KeysFooterItem = { k: KeyName; label: string; onClick?: () => void }

export function KeysFooter({ items, surface = 'dark', divider = true }: { items: ReadonlyArray<KeysFooterItem>; surface?: 'dark' | 'paper'; divider?: boolean }): ReactNode {
  const shown = items.filter((i) => keyLabel(i.k))
  if (!shown.length) return null
  const onPaper = surface === 'paper'
  return (
    <div
      data-keys-footer
      className="flex items-center gap-[14px] px-[16px]"
      style={{ height: 36, borderTop: divider ? `1px solid ${onPaper ? paper.hairline : fill.hairline}` : undefined, fontSize: type2.xs, color: onPaper ? paper.faint : color.label }}
    >
      {shown.map((i) => {
        const body = (
          <>
            <Keycap k={i.k} on={onPaper ? 'paper' : 'dark'} size="sm" />
            <span className="truncate">{i.label}</span>
          </>
        )
        return i.onClick ? (
          <button key={i.k} type="button" className="flex min-w-0 cursor-pointer items-center gap-[6px]" onClick={i.onClick}>
            {body}
          </button>
        ) : (
          <span key={i.k} className="flex min-w-0 items-center gap-[6px]">
            {body}
          </span>
        )
      })}
    </div>
  )
}
