/**
 * Feature: shell / flow. The order of the first run's screens after the intro, pure (no bridge, no window), so
 * test/consent.test.ts checks it with node --test: the login while it is needed, then consent while it is needed
 * (R05, R06), then guided setup. Consent always comes before setup, so no macOS prompt can come first.
 */
export type AfterPhase = 'login' | 'consent' | 'setup'

/** The phase after `at` ('intro': the intro just ended; 'login': the login just ended or isn't needed). */
export function phaseAfter(at: 'intro' | 'login', s: { login: boolean; consent: boolean }): AfterPhase {
  if (at === 'intro' && s.login) return 'login'
  return s.consent ? 'consent' : 'setup'
}
