/**
 * Feature: session (MIC-30, app side). Brief: app/agents/session.md
 *
 * No UI of its own: the store (store.ts) holds what main's POST /v1/session answered, for Settings › Your own key (the
 * plan and today's use) and the sign-in card (signin_mode, at the start of a build). Main side:
 * src/main/features/cloudSession.ts. Stage side: ./web.ts.
 */
import { defineFeature } from '../../core/registry'
import './web'
import './store'

export default defineFeature({ id: 'session' })
