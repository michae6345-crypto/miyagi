/**
 * Feature: shortcut bar, retired (Michael, Nov 21: no bottom bar in any lesson). It draws nothing: no overlay layer.
 * Every action it offered lives elsewhere (see agents/video-calm.md): ask miyagi (the launcher key and the notch
 * island), Back / Explain / Diagram / Show me / Hint (their keys, the steps drawer's help row in a video lesson, the
 * lesson panel's Help row in "Just teach me"), Check my work and Skip step (the player, the drawer's help row),
 * End lesson (the launcher's footer). front.ts stays: the front-app state the spotlight and the cards read.
 */
import { defineFeature } from '../../core/registry'
import './front'

export default defineFeature({ id: 'shortcut-bar' })
