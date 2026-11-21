/**
 * Feature: account (A9, flag v2Cloud). The account surfaces' data, as the main process (or the stage) hands it over.
 *
 * There is no account backend in this push (DISTRIBUTION-PLAN: accounts attach to install tokens later), so
 * `account:get` returns null in Electron and the stage serves a fixture. Nothing here is sent anywhere: no email,
 * code or token goes into a URL, localStorage or a log (BUILD-PLAN Section 6).
 */
import { isElectron } from '../../bridge'

/**
 * v2Cloud: the account surfaces exist at all. Off in a normal build: the feature isn't mounted (registry `enabled`).
 * On in the browser stage (mock data only), or in a build made with VITE_MIYAGI_V2_CLOUD=1.
 */
export const v2Cloud: boolean = !isElectron || import.meta.env.VITE_MIYAGI_V2_CLOUD === '1'

export type View = 'menu' | 'upgrade' | 'signin' | 'pricing'
export const VIEWS: readonly View[] = ['menu', 'upgrade', 'signin', 'pricing']
export const isView = (v: unknown): v is View => typeof v === 'string' && (VIEWS as readonly string[]).includes(v)

export type PlanId = 'free' | 'pro' | 'teams'

/** Live help this period (Explain, Hint, Show me, Diagram, Watch). Checks never count. */
export type HelpMeter = { used: number; limit: number; /** ISO date the count resets. */ resetsAt?: string }

/** Display prices, already formatted by the catalog ("$12"). Absent = not priced yet: the UI shows no number. */
export type Catalog = {
  pro?: { monthly?: string; yearly?: string; help?: number }
  teams?: { monthly?: string; yearly?: string }
  free?: { help?: number }
  /** "Yearly, save N%". */
  yearlySavePct?: number
  /** "Works with Anthropic keys". */
  providers?: string
}

export type Account = {
  signedIn: boolean
  name?: string
  email?: string
  plan: PlanId
  help?: HelpMeter
  catalog?: Catalog
}

/** Links main may open (main/features/account.ts maps each to a fixed https URL; keep the two lists in sync). */
export type AccountLink = 'pricing' | 'upgrade' | 'teams' | 'terms' | 'privacy' | 'restore'

const PLAN_LABEL: Record<PlanId, string> = { free: 'Free', pro: 'Pro', teams: 'Teams' }
export const planLabel = (p: PlanId): string => PLAN_LABEL[p] ?? 'Free'

/** A plain, bounded copy of what came over IPC: unknown fields dropped, strings capped, numbers finite. */
export function cleanAccount(raw: unknown): Account | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const str = (v: unknown, max = 120): string | undefined => (typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : undefined)
  const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined)
  const plan: PlanId = r.plan === 'pro' || r.plan === 'teams' ? r.plan : 'free'
  let help: HelpMeter | undefined
  const h = r.help as Record<string, unknown> | undefined
  if (h && typeof h === 'object') {
    const used = num(h.used)
    const limit = num(h.limit)
    if (used !== undefined && limit !== undefined && limit > 0) help = { used: Math.min(used, limit), limit, resetsAt: str(h.resetsAt, 32) }
  }
  let catalog: Catalog | undefined
  const c = r.catalog as Record<string, Record<string, unknown> | undefined> | undefined
  if (c && typeof c === 'object') {
    const price = (p?: Record<string, unknown>): { monthly?: string; yearly?: string } => ({ monthly: str(p?.monthly, 16), yearly: str(p?.yearly, 16) })
    catalog = {
      pro: c.pro ? { ...price(c.pro), help: num(c.pro.help) } : undefined,
      teams: c.teams ? price(c.teams) : undefined,
      free: c.free ? { help: num(c.free.help) } : undefined,
      yearlySavePct: num((c as Record<string, unknown>).yearlySavePct),
      providers: str((c as Record<string, unknown>).providers, 60)
    }
  }
  return { signedIn: r.signedIn === true, name: str(r.name, 80), email: str(r.email, 254), plan, help, catalog }
}

/** "December 1" for an ISO date, or undefined. UTC, so the day never shifts with the Mac's zone. */
export function resetDay(iso?: string): string | undefined {
  if (!iso) return undefined
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return undefined
  return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', timeZone: 'UTC' })
}

/** A plausible email, only to enable the sign-in button. Never stored, never logged. */
export const looksLikeEmail = (s: string): boolean => /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$/.test(s.trim())
