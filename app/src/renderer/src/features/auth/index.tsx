/**
 * Feature: auth (first-run login). Brief: app/agents/auth.md
 *
 * Flow: branded intro (the bonsai grows in) → "miyagi login" (New user / Returning user, Google / Apple / GitHub
 * boxes) → guided setup (onboarding) → home. Google is live through the main process (system browser, OAuth PKCE via
 * Supabase Auth, loopback redirect); Apple and GitHub are placeholders that send nothing.
 *
 *   window 'auth' (kind 'app')  the login window. main/features/onboarding.ts opens it on the first run; openLogin()
 *                               from core/surfaces opens it any time after (the Account page's Sign in).
 * The signed-in learner (store.ts useAuth().user) is read by the shell's Account page and sidebar chip.
 */
import { defineFeature } from '../../core/registry'
import { windowSize } from '../../core/theme'
import { AuthView } from './AuthView'
import { authOn } from './model'
import './web'

export default defineFeature({
  id: 'auth',
  enabled: authOn,
  windows: [{ route: 'auth', kind: 'app', size: windowSize.auth, Component: AuthView }]
})
