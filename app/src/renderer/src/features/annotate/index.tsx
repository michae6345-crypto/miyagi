/**
 * Feature: annotate (buddy draws; brief: app/agents/app-buddy-draw.md). When the coach points at something (engine
 * `annotate`, or today's spotlight box), a thin mint stroke grows out of the island and loops loosely around it, holds,
 * and fades when the learner goes there, the step changes, or after a few seconds.
 *
 * An overlay layer at z 48: under the island (z 50), over the spotlight (10) and the lesson panel (40). Click-through.
 */
// Load order (features load A to Z, and this one is first): core/Island pulls in core/islandPlace, which imports the
// cards store, and cards -> drawer -> diagrams -> cards is a cycle that only works when the drawer store loads first
// (entered from cards, diagrams reads useCards before it exists and the whole renderer fails). So load it first here.
// Core request in agents/app-buddy-draw.md: break that cycle in core.
import '../drawer/store'
import { defineFeature } from '../../core/registry'
import { BuddyLayer } from './BuddyLayer'
import './store'

// The character draws (Adrian, Nov 23): when features/buddy's character is in the build, BuddyLayer draws nothing.
// `yieldsToBuddy` says so to features/buddy (its marks.ts standsDown), which otherwise stands down for this layer,
// and then nothing would draw at all.
export default Object.assign(defineFeature({ id: 'annotate', overlayLayers: [{ id: 'annotate', z: 48, Component: BuddyLayer }] }), { yieldsToBuddy: true })
