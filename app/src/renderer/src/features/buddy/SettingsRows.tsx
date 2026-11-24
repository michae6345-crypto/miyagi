/**
 * Feature: buddy. Settings > General: the Buddy group, drawn into General the way features/ptt draws its own
 * (SettingsRows.tsx there). One row: the buddy and the colors to pick from. A pick saves at once (skin.ts) and the
 * buddy on the screen changes with it.
 */
import type { ReactNode } from 'react'
import { Group, Row } from '../settings/ui'
import { BuddyPreview, BuddySwatches } from './ColorPicker'
import { words } from './name'

export function BuddyColor(): ReactNode {
  return (
    <Group label={words.group}>
      <Row
        label={words.row}
        caption={words.rowCaption}
        right={
          <span data-settings-buddy className="flex shrink-0 items-center gap-[16px]">
            <BuddyPreview size={36} />
            <BuddySwatches size={22} gap={10} name={false} />
          </span>
        }
      />
    </Group>
  )
}
