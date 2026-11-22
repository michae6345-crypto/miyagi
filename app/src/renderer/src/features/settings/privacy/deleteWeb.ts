/**
 * Feature: settings. Browser-stage stand-ins for main/features/accountDelete.ts (nothing here runs in Electron, and
 * nothing is sent anywhere: no miyagi-cloud, no Supabase).
 *   ?scenario=settings&settings=privacy&confirm=delete           the confirm
 *   &delete=pending | offline | partial                          the server's answer (default: deleted)
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
          resolve({ ok: true, account: variant === 'pending' ? 'pending' : 'deleted', local: variant !== 'partial' })
        }, 1200)
      )
  )
  registerWebHandler('account:restart', () => {
    console.log('[stage] account:restart (a built app relaunches here)')
    return false
  })
}
