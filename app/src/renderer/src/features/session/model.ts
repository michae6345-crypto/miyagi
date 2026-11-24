/**
 * Feature: session (MIC-30, app side). The pure half (no bridge, no React, so test/session.test.ts runs it in Node).
 * Brief: app/agents/session.md
 *
 * Main (src/main/features/cloudSession.ts) answers session:get and broadcasts feat:session with a SessionView: the
 * account's plan and today's use (only while signed in), whether this install is linked, and the cloud's sign-in mode.
 * Never a token, an email or an account id.
 *
 *   cleanSession(raw)          a bounded copy of what came over IPC (unknown fields dropped, numbers finite), or null
 *   capsLine(caps, now, opts)  "$0.42 of $3.00 today · resets 4:00 PM", in the learner's own time zone
 *   planLabel(plan)            "Free plan" | "Pro plan"
 *   promptsOnBuild(view, me)   the sign-in card should show when a guest starts building ("build" / "all" modes)
 */

export type SigninMode = 'off' | 'build' | 'all'
export type Plan = 'free' | 'pro'
export type Caps = { dailyUsd: number | null; usedUsd: number; tokens: number | null; usedTokens: number; resetsAt?: string }
export type SessionView = { signedIn: boolean; linked: boolean; signinMode: SigninMode; plan?: Plan; caps?: Caps; fetchedAt?: string }

const MAX_USD = 1_000_000
const MAX_TOKENS = 1e12
const num = (v: unknown, max: number): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= max ? v : undefined)
const iso = (v: unknown): string | undefined => (typeof v === 'string' && v.length <= 40 && !Number.isNaN(Date.parse(v)) ? v : undefined)

/** A plain, bounded copy of a SessionView from IPC. Plan and caps are kept only for a signed-in learner. */
export function cleanSession(raw: unknown): SessionView | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const signedIn = r.signedIn === true
  const v: SessionView = { signedIn, linked: r.linked === true, signinMode: r.signinMode === 'build' ? 'build' : r.signinMode === 'all' ? 'all' : 'off' }
  const at = iso(r.fetchedAt)
  if (at) v.fetchedAt = at
  if (!signedIn) return v
  if (r.plan === 'free' || r.plan === 'pro') v.plan = r.plan
  const c = r.caps as Record<string, unknown> | undefined
  if (c && typeof c === 'object' && !Array.isArray(c)) {
    const usedUsd = num(c.usedUsd, MAX_USD)
    const usedTokens = num(c.usedTokens, MAX_TOKENS)
    if (usedUsd !== undefined && usedTokens !== undefined) {
      const cap = (x: unknown, max: number): number | null => {
        const n = num(x, max)
        return n !== undefined && n > 0 ? n : null
      }
      v.caps = { dailyUsd: cap(c.dailyUsd, MAX_USD), usedUsd, tokens: cap(c.tokens, MAX_TOKENS), usedTokens: Math.floor(usedTokens) }
      const resets = iso(c.resetsAt)
      if (resets) v.caps.resetsAt = resets
    }
  }
  return v
}

export const planLabel = (plan?: Plan): string => (plan === 'pro' ? 'Pro plan' : 'Free plan')

/** "$0.42". Cents always, so "$3.00" lines up with "$0.42". */
export const money = (usd: number): string => `$${(Math.round(usd * 100) / 100).toFixed(2)}`

export type TimeOpts = { timeZone?: string; locale?: string }

function dayNumber(d: Date, timeZone?: string): number {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(d)
  const get = (t: string): number => Number(parts.find((p) => p.type === t)?.value)
  return Math.round(Date.UTC(get('year'), get('month') - 1, get('day')) / 86_400_000)
}

/** "4:00 PM" today, "tomorrow 1:00 AM", else "Nov 26", in local time; null when missing, bad or past. */
export function resetLabel(at?: string, now: Date = new Date(), opts: TimeOpts = {}): string | null {
  if (!at) return null
  const t = new Date(at)
  if (Number.isNaN(t.getTime()) || t.getTime() <= now.getTime()) return null
  const { timeZone, locale } = opts
  const time = new Intl.DateTimeFormat(locale, { timeZone, hour: 'numeric', minute: '2-digit' }).format(t)
  const days = dayNumber(t, timeZone) - dayNumber(now, timeZone)
  if (days <= 0) return time
  if (days === 1) return `tomorrow ${time}`
  return new Intl.DateTimeFormat(locale, { timeZone, month: 'short', day: 'numeric' }).format(t)
}

/** Today's use in one calm line, or null when there is nothing to show. */
export function capsLine(caps: Caps | undefined, now: Date = new Date(), opts: TimeOpts = {}): string | null {
  if (!caps) return null
  const used = caps.dailyUsd ? `${money(Math.min(caps.usedUsd, caps.dailyUsd))} of ${money(caps.dailyUsd)} today` : `${money(caps.usedUsd)} used today`
  const when = caps.dailyUsd ? resetLabel(caps.resetsAt, now, opts) : null
  return when ? `${used} · resets ${when}` : used
}

/**
 * The sign-in card at the start of a new lesson build: the cloud needs an account to build ("build") or for
 * everything ("all"), and this learner is a guest (not signed in, and this install not linked: a linked install's
 * builds go through even signed out, since sign-out never unlinks). "off": only a cloud notice shows the card.
 */
export function promptsOnBuild(view: SessionView | null, signedIn: boolean): boolean {
  if (!view || signedIn || view.signedIn || view.linked) return false
  return view.signinMode === 'build' || view.signinMode === 'all'
}
