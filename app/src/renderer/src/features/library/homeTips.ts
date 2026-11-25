/**
 * Feature: library. The tips Home's side column rotates through, one a day. Content lives here, not in the UI: a tip
 * is a sentence in three parts so the keycap in the middle always comes from bridge.platform.keys (Keycap), never typed.
 * Generic on purpose: nothing about a particular lesson.
 */
import type { KeyName } from '../../core/ui/Keycap'

export type Tip = { before: string; key?: KeyName; after?: string }

export const TIPS: readonly Tip[] = [
  { before: 'Press ', key: 'launcher', after: ' from any app to ask miyagi.' },
  { before: 'Stuck on a step? Press ', key: 'hint', after: ' for a nudge.' },
  { before: 'Press ', key: 'explain', after: ' to hear a step again, another way.' },
  { before: 'Press ', key: 'diagram', after: ' to see an idea drawn.' },
  { before: 'Paste a YouTube link and miyagi turns it into steps.' },
  { before: 'Finished lessons come back as short reviews, just before you forget.' }
]

/** The tip for a day (stable through the day, a new one tomorrow). */
export const tipFor = (now: number): Tip => TIPS[Math.floor(now / 86_400_000) % TIPS.length]
