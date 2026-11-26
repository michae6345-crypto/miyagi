/**
 * Feature: settings. Browser-stage stand-ins for main/features/accountDelete.ts (nothing here runs in Electron, and
 * nothing is sent anywhere: no miyagi-cloud, no Supabase).
 *   ?scenario=settings&settings=privacy&confirm=delete           the confirm
 *   &delete=pending | email | offline | refused | partial        the server's answer (default: deleted; email = 404)
 * account:delete answers after 1.2 s; account:restart only logs.
 */
import { isElectron, registerWebHandler } from '../../../bridge'

if (!isElectron) {
  const variant = new URLSearchParams(location.search).get('delete')
  registerWebHandler(
    'account:delete',
    () =>
      new Promise((resolve) =>
        setTimeout(() => {
          if (variant === 'offline') return resolve({ ok: false, reason: 'unreachable' })
          if (variant === 'refused') return resolve({ ok: false, reason: 'account' })
          resolve({ ok: true, account: variant === 'pending' || variant === 'email' ? variant : 'deleted', local: variant !== 'partial' })
        }, 1200)
      )
  )
  registerWebHandler('account:restart', () => {
    console.log('[stage] account:restart (a built app relaunches here)')
    return false
  })
}
