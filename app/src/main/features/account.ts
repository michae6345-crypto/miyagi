/**
 * Main-process feature: account (BUILD-PLAN A9, flag v2Cloud). The account window's main side, and nothing more.
 *
 * v2Cloud=false is the shipped state (Section 6): no payments, no OAuth, no `miyagi://` protocol handler, no quota that
 * blocks a lesson, no network. This file holds no token and stores nothing.
 *
 *   account:get        → null. No account backend exists in this push (DISTRIBUTION-PLAN: accounts attach to install
 *                        tokens later, through the proxy's GET /v1/me). The window then shows Sign in.
 *   account:open(link) → one of the fixed miyagi.study pages below, through safeOpenExternal (the allowlist). The
 *                        renderer names a link; it never passes a URL, and nothing is appended (no email, no token).
 *   account:sign-out   → true. Nothing is stored on this Mac to forget.
 *
 * Every handler answers false / null unless MIYAGI_V2_CLOUD=1 is set for this run, so a stray openAccount() in a
 * normal build can't reach the browser. The renderer's own switch is the build-time VITE_MIYAGI_V2_CLOUD (see Core
 * requests in agents/account.md for one shared flag).
 */
import { CONTACT_EMAIL, LEGAL_URL } from '../../common/consent'
import { defineMainFeature } from '../context'
import { safeOpenExternal } from '../safeOpen'

/** The site's home: the only miyagi.study page that answers today besides the terms and the policy. */
const HOME = 'https://miyagi.study/'

/**
 * The renderer's AccountLink names (features/account/model.ts). Keep the two lists in sync. /pricing, /teams and
 * /account answered 404 (checked Nov 21, R06): pricing, upgrade and restore open the home page until those pages exist,
 * and Talk to us (teams) writes to the contact address.
 */
const LINKS = {
  pricing: HOME,
  upgrade: HOME,
  teams: `mailto:${CONTACT_EMAIL}`,
  terms: LEGAL_URL.terms,
  privacy: LEGAL_URL.privacy,
  restore: HOME
} as const
type Link = keyof typeof LINKS

const isLink = (v: unknown): v is Link => typeof v === 'string' && Object.prototype.hasOwnProperty.call(LINKS, v)

export const v2CloudOn = (): boolean => process.env.MIYAGI_V2_CLOUD === '1'

export default defineMainFeature({
  id: 'account',
  setup(ctx) {
    const on = v2CloudOn()
    ctx.handle('account:get', () => null)
    ctx.handle('account:open', (link) => (on && isLink(link) ? safeOpenExternal(LINKS[link]) : false))
    ctx.handle('account:sign-out', () => on)
  }
})
