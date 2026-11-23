/**
 * Feature: buddy. Brief: app/agents/buddy.md
 *
 * The living bonsai (LivingMark, Buddy, usePointerLean, useBuddy) and its pointing branch (Reach.tsx, pointing.ts,
 * marks.ts). The bonsai has no window or island mode of its own: the notch ears and other surfaces import it. The
 * branch is an overlay layer under the island (z 30: over the spotlight's dim, behind the notch it grows out of);
 * it draws nothing while features/annotate is mounted (Reach.tsx), so a mark is never circled twice.
 * Previews, only in the browser stage: ?buddy (every state of the mark) and ?buddy=point (try the pointing).
 */
import { defineFeature } from '../../core/registry'
import { CastStage } from './CastStage'
import { CompanionLayer } from './Companion'
import { PointStage, POINT_STAGE } from './PointStage'
import { ReachLayer } from './Reach'
import { BuddyStage } from './Stage'

const preview = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('buddy') : null

export default defineFeature({
  id: 'buddy',
  // The loops go under the island (z 30). The buddy itself goes over it (z 55): it lifts out of the notch.
  overlayLayers: [
    { id: 'buddy-reach', z: 30, Component: ReachLayer },
    { id: 'buddy', z: 55, Component: CompanionLayer }
  ],
  windows:
    preview === 'point'
      ? [{ route: 'buddy-point', Component: PointStage, stage: POINT_STAGE, z: 40 }]
      : preview === 'cast'
        ? [{ route: 'buddy-cast', Component: CastStage, stage: { x: 30, y: 44, w: 1540, h: 850 }, z: 40 }]
      : preview !== null
        ? [{ route: 'buddy', Component: BuddyStage, stage: { x: 40, y: 80, w: 980, h: 640 }, z: 40 }]
        : []
})

export { LivingMark, usePointerLean, type BuddyState, type LivingMarkProps } from './LivingMark'
// For a layer that draws its own stroke (features/annotate): where the living mark is, and the point pose.
export { useBonsaiPoint } from './Reach'
export { Character, type CharacterKind, type Mood } from './Character'
export { annotate, pointAt, usePointing } from './pointing'
export { say, sendHome, setActivity, summon, useTalk } from './talk'
export { Buddy, useBuddy } from './store'
