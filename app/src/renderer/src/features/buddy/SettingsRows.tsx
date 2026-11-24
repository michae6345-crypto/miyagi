/**
 * Feature: buddy. Settings > General: the Buddy group, drawn into General the way features/ptt draws its own
 * (SettingsRows.tsx there). Its color: the buddy and the colors to pick from; a pick saves at once (skin.ts) and the
 * buddy on the screen changes with it. And how it has grown (GrowthCard.tsx): its level with the steps to the next one,
 * and the ladder of all eight levels with the rule under it.
 */
import type { ReactNode } from 'react'
import { Group, Row } from '../settings/ui'
import { color, type2 } from '../../core/theme'
import { BuddyPreview, BuddySwatches } from './ColorPicker'
import { BonBar, BonLadder, useLevelWords } from './GrowthCard'
import { words } from './name'

export function BuddyColor(): ReactNode {
  const level = useLevelWords()
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
      <Row label={level.title} caption={level.caption} right={<BonBar />} />
      <BonLadder />
    </Group>
  )
}
