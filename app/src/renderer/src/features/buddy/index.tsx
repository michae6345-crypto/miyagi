/**
 * Feature: buddy. Brief: app/agents/buddy.md
 *
 * Two things live here:
 *   - The living bonsai (LivingMark, Buddy, usePointerLean, useBuddy): the logo in the notch, alive. No window or
 *     island mode of its own; the notch ears and other surfaces import it.
 *   - The buddy: a character of its own (Character.tsx), not the logo. It comes out of the island, flies to what the
 *     coach points at, circles it, says what it is, listens, thinks and answers (Companion.tsx, talk.ts, wire.ts,
 *     trip.ts), and draws its loops (Reach.tsx, pointing.ts, marks.ts).
 * Both overlay layers draw nothing while features/annotate is mounted (Reach.tsx), so a mark is never circled twice.
 * Previews, only in the browser stage: ?buddy (every state of the living mark), ?buddy=point (try the buddy),
 * ?buddy=cast (the character sheet), ?buddy=colors (the color sheet) and ?buddy=pick (the setup step where the
 * learner picks its color). ?skin=<name> puts the buddy in one color.
 */
import { defineFeature } from '../../core/registry'
import { CastStage } from './CastStage'
import { ColorStage } from './ColorStage'
import { CompanionLayer } from './Companion'
import { PickStage, PICK_STAGE } from './PickStage'
import { PointStage, POINT_STAGE } from './PointStage'
import { ReachLayer } from './Reach'
import { BuddyStage } from './Stage'
import './wire' // the back and forth, wired to the engine and push to talk

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
      : preview === 'pick'
        ? [{ route: 'buddy-pick', Component: PickStage, stage: PICK_STAGE, z: 40 }]
      : preview === 'colors'
        ? [{ route: 'buddy-colors', Component: ColorStage, stage: { x: 30, y: 44, w: 1540, h: 850 }, z: 40 }]
      : preview !== null
        ? [{ route: 'buddy', Component: BuddyStage, stage: { x: 40, y: 80, w: 980, h: 640 }, z: 40 }]
        : []
})

export { LivingMark, usePointerLean, type BuddyState, type LivingMarkProps } from './LivingMark'
// For a layer that draws its own stroke (features/annotate): where the living mark is, and the point pose.
export { useBonsaiPoint } from './Reach'
export { Character, type CharacterKind, type Mood } from './Character'
// For setup and Settings: the picker, and the learner's color.
export { BuddyColorPicker } from './ColorPicker'
export { pickSkin, useSkin, useSkinName } from './skin'
export { annotate, pointAt, usePointing } from './pointing'
export { say, sendHome, setActivity, summon, useTalk } from './talk'
export { Buddy, useBuddy } from './store'
