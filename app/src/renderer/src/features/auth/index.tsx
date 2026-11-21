/**
 * Feature: auth (first-run login). Brief: app/agents/auth.md
 *
 * Flow: intro (the bonsai grows in) → "miyagi login" (New user / Returning user, Google / Apple / GitHub boxes) →
 * guided setup (onboarding) → home. Google is live through the main process (system browser, OAuth PKCE via
 * Supabase Auth, loopback redirect); Apple and GitHub are placeholders that send nothing.
 *
 * No window of its own yet: the account window mounts AuthView for view 'login' (an allowlisted route), until core
 * adds an 'auth' route (Core requests). This module only registers the stage stand-ins.
 */
import { defineFeature } from '../../core/registry'
import { authOn } from './model'
import './web'

export default defineFeature({ id: 'auth', enabled: authOn })
