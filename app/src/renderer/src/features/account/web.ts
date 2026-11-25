/**
 * Feature: account. Browser-stage stand-ins for main/features/account.ts (does nothing in Electron).
 *
 * The fixture is mock data for the stage only: the prices and counts are placeholders, not a decision.
 *   ?account=menu|upgrade|signin|pricing   opens the account window on that view
 *   ?plan=pro                              the account is on Pro (no Upgrade button, Pro is the current plan)
 *   ?signedout                             account:get answers null (the window starts on Sign in)
 * Upgrade shows the meter full (the moment the sheet exists for).
 */
import { isElectron, registerWebHandler } from '../../bridge'
import { openAccount } from '../../core/surfaces'
import { isView, type Account } from './model'

function fixture(params: URLSearchParams): Account | null {
  if (params.has('signedout')) return null
  const full = params.get('account') === 'upgrade'
  return {
    signedIn: true,
    name: 'Sam Rivera',
    email: 'sam@example.edu',
    plan: params.get('plan') === 'pro' ? 'pro' : 'free',
    help: { used: full ? 20 : 14, limit: 20, resetsAt: '2026-12-01' },
    catalog: {
      free: { help: 20 },
      pro: { monthly: '$12', yearly: '$10', help: 300 },
      teams: { monthly: '$8', yearly: '$7' },
      yearlySavePct: 17,
      providers: 'Anthropic'
    }
  }
}

function setupWeb(): void {
  const params = new URLSearchParams(location.search)
  let account = fixture(params)
  registerWebHandler('account:get', () => account)
  registerWebHandler('account:open', (link) => {
    console.info(`[tut] stage: would open the account link "${typeof link === 'string' ? link.slice(0, 16) : '?'}"`)
    return typeof link === 'string'
  })
  registerWebHandler('account:sign-out', () => {
    account = null
    return true
  })
  const view = params.get('account')
  if (isView(view)) setTimeout(() => void openAccount(view), 0)
}

if (!isElectron) setupWeb()
