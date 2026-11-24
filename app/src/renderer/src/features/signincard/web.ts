/**
 * Feature: signincard. The browser stage's switch (nothing here runs in Electron): `?scenario=signincard&nt=<variant>`
 * asks the inline mock for `dev.signincard.<variant>`, which plays a build and then the notice
 * (mock/scenarios/signincard.json):
 *
 *   signin | signin-error | anon | user | daily | global | builds | rate | full | token
 *
 * signin-error sends the notice inside an engine `error` frame (today's transport); token is a 401 that is NOT
 * signin_required (no UI). Sign in uses features/auth/web.ts's auth:google stand-in (1.6 s, then the fixture learner;
 * &auth=fail for a failure). Mock data only.
 */
import type { Outgoing } from '../../../../common/wire'
import { bridge, engineMode, isElectron } from '../../bridge'

function setupWeb(): void {
  const nt = new URLSearchParams(location.search).get('nt') ?? ''
  if (!/^[a-z-]{1,24}$/.test(nt)) return
  setTimeout(() => {
    if (engineMode() !== 'inline') return
    // A dev-only trigger for the inline mock (like dev.reset): it never reaches a real engine.
    bridge.send({ type: `dev.signincard.${nt}`, payload: {} } as unknown as Outgoing)
  }, 300)
}

if (!isElectron) setupWeb()
