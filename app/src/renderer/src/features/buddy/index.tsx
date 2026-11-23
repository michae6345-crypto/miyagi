/**
 * Feature: buddy. Brief: app/agents/buddy.md
 *
 * The living bonsai (LivingMark, Buddy, usePointerLean, useBuddy) and its pointing branch (Reach.tsx, pointing.ts,
 * marks.ts). The bonsai has no window or island mode of its own: the notch ears and other surfaces import it. The
 * branch is an overlay layer under the island (z 30: over the spotlight's dim, behind the notch it grows out of).
 * Previews, only in the browser stage: ?buddy (every state of the mark) and ?buddy=point (try the pointing).
 */
import { defineFeature } from '../../core/registry'
import { PointStage, POINT_STAGE } from './PointStage'
import { ReachLayer } from './Reach'
import { BuddyStage } from './Stage'

const preview = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('buddy') : null

export default defineFeature({
  id: 'buddy',
  overlayLayers: [{ id: 'buddy-reach', z: 30, Component: ReachLayer }],
  windows:
    preview === 'point'
      ? [{ route: 'buddy-point', Component: PointStage, stage: POINT_STAGE, z: 40 }]
      : preview !== null
        ? [{ route: 'buddy', Component: BuddyStage, stage: { x: 40, y: 80, w: 980, h: 640 }, z: 40 }]
        : []
})

export { LivingMark, usePointerLean, type BuddyState, type LivingMarkProps } from './LivingMark'
export { annotate, clearMarks, usePointing } from './pointing'
export { Buddy, useBuddy } from './store'
