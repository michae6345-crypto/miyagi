/**
 * Feature: buddy. Brief: app/agents/buddy.md
 *
 * The living bonsai (LivingMark, Buddy, usePointerLean, useBuddy). It has no window or island mode of its own: the
 * notch ears and other surfaces import it. The only window is a preview in the browser stage: ?buddy.
 */
import { defineFeature } from '../../core/registry'
import { BuddyStage } from './Stage'

const preview = typeof location !== 'undefined' && new URLSearchParams(location.search).has('buddy')

export default defineFeature({
  id: 'buddy',
  windows: preview ? [{ route: 'buddy', Component: BuddyStage, stage: { x: 40, y: 80, w: 980, h: 640 }, z: 40 }] : []
})

export { LivingMark, usePointerLean, type BuddyState, type LivingMarkProps } from './LivingMark'
export { Buddy, useBuddy } from './store'
