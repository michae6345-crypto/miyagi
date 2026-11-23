/**
 * Feature: circle (brief: app/agents/app-circle-ask.md). Circle to ask, the Clicky way: hold the push-to-talk keys
 * (Fn+Control), circle anything on screen with the mouse, say a question or nothing, let go. miyagi explains what is
 * inside the circle in a small card beside it.
 *
 *   store.ts     follows push to talk, takes the overlay's mouse while the keys are held (and gives it back on every
 *                way out: release, Esc, blur, an 8 s cap), sends action ask {text, region, source "circle", askId}
 *   machine.ts   the pure state machine (idle, armed, sealed, asking, answered)
 *   geometry.ts  ink to box, box to screen points, the ink path, the card's place inside the screen edges
 *   Layer.tsx    the drawing surface, the ink, the "Looking" chip and the answer card
 *   web.ts       the browser stage's hand and engine (?circle=draw | answered)
 *
 * The one-time tip ("Hold [keys] and circle anything to ask.") is features/tips' `circle`.
 * Off with push to talk (PTT_ENABLED, common/flags.ts): the circle rides on its keys.
 *
 * An overlay layer at z 85: above the island (50) and the tips (70), so the ink and the card sit over everything the
 * overlay draws; below nothing. Passive (data-ui) except the answer card (data-hit).
 */
import { PTT_ENABLED } from '../../../../common/flags'
import { isElectron } from '../../bridge'
import { defineFeature } from '../../core/registry'
import { CircleLayer } from './Layer'
import './web'

/** The browser stage can show it with push to talk off (?circle=...); Electron follows PTT_ENABLED only. */
const stageOn = !isElectron && typeof location !== 'undefined' && new URLSearchParams(location.search).has('circle')

export default defineFeature({
  id: 'circle',
  enabled: PTT_ENABLED || stageOn,
  overlayLayers: [{ id: 'circle', z: 85, Component: CircleLayer }]
})
