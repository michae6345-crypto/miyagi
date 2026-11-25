/**
 * Main-process feature: the account session with miyagi-cloud (MIC-30, app side). Brief: app/agents/session.md
 *
 * POST <cloud>/v1/session after each Google sign-in and on every launch while signed in, falling back to POST /v1/link
 * on an older cloud (404). The protocol, the retries and the cache (userData/session.json) live in
 * cloudSession/client.ts. This file wires it:
 *
 *   when     a sign-in (auth.ts onSignedIn, forced); launch, LAUNCH_DELAY_MS after start (forced, never on the UI's
 *            path); the install token appearing or changing (first mint, self-heal; skipped when the last answer is
 *            fresh); session:get with an answer older than STALE_MS (Settings opening). Only while signed in.
 *   401      cloud.ts healInstall() (the self-heal), then one retry
 *   403      auth.ts refreshedAccessToken(), then one retry
 *   sign-out the account's plan and use leave the cache (auth.ts onSignedOut); the sign-in mode and the link stay
 *
 * Renderer (no token, no email, no account id ever crosses; viewOf bounds every field):
 *   session:get        → SessionView
 *   feat:session       SessionView, whenever the cache changes
 */
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { accessToken, isSignedIn, loginEnabled, onSignedIn, onSignedOut, refreshedAccessToken } from './auth'
import { healInstall, installToken, onInstallToken } from './cloud'
import { createLinker } from './cloudLink'
import { cleanCaps, createSessionClient, signinModeOf, type Caps, type Plan, type SessionRecord, type SigninMode } from './cloudSession/client'

/** The launch call waits this long, so it never competes with the first windows. */
const LAUNCH_DELAY_MS = 4_000
/** session:get refreshes in the background when the cached answer is older than this. */
export const STALE_MS = 5 * 60_000

/** What a renderer may see. plan and caps only while signed in. */
export type SessionView = { signedIn: boolean; linked: boolean; signinMode: SigninMode; plan?: Plan; caps?: Caps; fetchedAt?: string }

/** The renderer's copy of the cache: only these fields, bounded; the account's own numbers only while signed in. */
export function viewOf(rec: SessionRecord | undefined, signedIn: boolean): SessionView {
  const v: SessionView = { signedIn, linked: rec?.linked === true, signinMode: signinModeOf(rec?.signinMode) }
  if (!rec) return v
  if (typeof rec.fetchedAt === 'string' && rec.fetchedAt.length <= 40) v.fetchedAt = rec.fetchedAt
  if (signedIn) {
    v.plan = rec.plan === 'pro' ? 'pro' : 'free'
    const caps = cleanCaps(rec.caps)
    if (caps) v.caps = caps
  }
  return v
}

export default defineMainFeature({
  id: 'cloudSession',
  setup(ctx) {
    const userData = ctx.app.getPath('userData')
    const linker = createLinker({ fetch: (input, init) => fetch(input, init), accessToken, install: installToken, file: join(userData, 'cloud-link.json') })
    const publish = (): void => ctx.broadcast('session', viewOf(client.current(), isSignedIn()))
    const client = createSessionClient({
      fetch: (input, init) => fetch(input, init),
      accessToken,
      refreshAccessToken: refreshedAccessToken,
      install: installToken,
      heal: () => healInstall(),
      legacyLink: () => linker.link({ force: true }),
      file: join(userData, 'session.json'),
      onChange: publish
    })
    const check = (force = false): void => {
      if (loginEnabled() && isSignedIn()) void client.sync({ force })
    }

    onSignedIn(() => void client.sync({ force: true }))
    onSignedOut(() => {
      client.signedOut()
      publish()
    })
    const off = onInstallToken(() => check())
    ctx.app.on('before-quit', () => {
      off()
      client.dispose()
    })
    void ctx.app.whenReady().then(() => setTimeout(() => check(true), LAUNCH_DELAY_MS).unref?.())

    ctx.handle('session:get', () => {
      const rec = client.current()
      const age = rec ? Date.now() - Date.parse(rec.fetchedAt) : Infinity
      if (!(age < STALE_MS)) check(true)
      return viewOf(rec, isSignedIn())
    })
  }
})
