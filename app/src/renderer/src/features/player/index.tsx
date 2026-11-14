/**
 * Feature: player. Brief: app/agents/player.md
 *
 * The lesson's video with gating: plays the step's clip, holds at its end until the step's checks
 * pass, resumes 400ms after step.passed, follows the engine's seek/pause/play, reports video.state.
 *
 *   Electron      → its own window (route `player`), created and docked by src/main/features/player.ts
 *   Browser stage → an overlay layer at z 5 drawing the panel at the same dock rect. A stage *window*
 *                   paints above the whole overlay (it would hide the cards' right edge and their ✕,
 *                   and sit outside the spotlight dim), so the stage uses a layer until the Stage
 *                   honors window z (see Core requests in the brief). The layer renders nothing in Electron.
 */
import { defineFeature } from '../../core/registry'
import { PlayerWindow, StagePlayer } from './Player'
import './store'

export default defineFeature({
  id: 'player',
  windows: [{ route: 'player', Component: PlayerWindow }],
  overlayLayers: [{ id: 'player', z: 5, Component: StagePlayer }]
})
