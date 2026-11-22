/**
 * Main-process feature: Delete account (Settings › Privacy; renderer settings/privacy/erase.ts). No window.
 *
 *   account:delete ({lessons: boolean}) → DeleteAccountResult
 *     1. the server first (accountDelete/server.ts): POST /v1/account/delete with the install token and the Supabase
 *        access token. Unreachable or refused: {ok: false, reason: 'unreachable'} and NOTHING is deleted here.
 *     2. then everything miyagi keeps on this Mac (accountDelete/wipe.ts eraseTargets): the files and folders in
 *        userData, the logs, the engine's caches and state, ~/miyagi/lessons only when `lessons` is true. The install
 *        token leaves memory and the engine too (cloud.ts forgetInstall). Electron's storage goes through the session
 *        API: cookies, localStorage, IndexedDB, service workers and the HTTP cache (the YouTube player's iframe runs in
 *        the default session). The built-in lessons the app ships are put back into the engine's cache.
 *     → {ok: true, account: 'deleted' | 'none' | 'pending', local: true when nothing was left behind}
 *     The renderer then calls settings:delete (the keys in settings.ts's memory and on the engine) and auth:sign-out
 *     (the session in auth.ts's memory), and account:restart.
 *   account:restart → a built app relaunches from new (every feature's memory goes too: the first-run screen, the
 *     age step, the intro). `npm run dev` can't relaunch itself (electron-vite owns the process): false, and the
 *     renderer stays on the signed-out login, which the sign-out already brought back.
 *
 * Tokens never reach a renderer; logs carry no path and no token.
 */
import { app, session } from 'electron'
import { cpSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { ageForgotten } from './agegate'
import { accessToken, refreshedAccessToken } from './auth'
import { forgetInstall, installToken } from './cloud'
import { deleteOnServer, type AccountOutcome } from './accountDelete/server'
import { allowedRoots, eraseTargets, wipe, type Where } from './accountDelete/wipe'

export type DeleteAccountResult = { ok: true; account: AccountOutcome; local: boolean } | { ok: false; reason: 'unreachable' | 'busy' }

function where(lessons: boolean): Where {
  let crashDumps: string | undefined
  try {
    crashDumps = app.getPath('crashDumps')
  } catch {
    crashDumps = undefined
  }
  const env = process.env
  return {
    userData: app.getPath('userData'),
    logs: app.getPath('logs'),
    crashDumps,
    home: homedir(),
    packaged: app.isPackaged,
    env: { MIYAGI_HOME: env.MIYAGI_HOME, MIYAGI_STATE_DIR: env.MIYAGI_STATE_DIR, COACH_TTS_DIR: env.COACH_TTS_DIR, MIYAGI_LESSONS_DIR: env.MIYAGI_LESSONS_DIR, MIYAGI_LESSONS: env.MIYAGI_LESSONS },
    lessons
  }
}

/** The engine bundle's own cache (built-in lessons), as localEngine.ts bundleDir() finds it. */
function bundledCache(): string {
  const dev = !app.isPackaged ? process.env.MIYAGI_BUNDLE_DIR?.trim() : ''
  return join(dev || join(process.resourcesPath, 'engine'), 'src', 'demo', 'cache')
}

async function clearBrowserStorage(): Promise<boolean> {
  try {
    const s = session.defaultSession
    await s.clearStorageData()
    await s.clearCache()
    await s.clearAuthCache()
    return true
  } catch {
    console.warn('[account-delete] could not clear the browser storage')
    return false
  }
}

export default defineMainFeature({
  id: 'accountDelete',
  setup(ctx) {
    let running: Promise<DeleteAccountResult> | undefined

    const run = async (lessons: boolean): Promise<DeleteAccountResult> => {
      const server = await deleteOnServer({ fetch: (i, init) => fetch(i, init), install: installToken, accessToken, refreshedAccessToken })
      if (!server.ok) return { ok: false, reason: 'unreachable' }

      forgetInstall()
      const w = where(lessons)
      const files = wipe(eraseTargets(w), allowedRoots(w))
      const storage = await clearBrowserStorage()
      // Put back the lessons the app ships (the wipe took the engine's whole lesson cache), only into an engine source
      // tree that is there (the managed engine's ~/miyagi/engine/src).
      const engineSrc = join(w.env.MIYAGI_HOME?.trim() || join(w.home, 'miyagi', 'engine'), 'src')
      const shipped = bundledCache()
      if (existsSync(engineSrc) && existsSync(shipped)) {
        try {
          cpSync(shipped, join(engineSrc, 'demo', 'cache'), { recursive: true, force: false, errorOnExist: false })
        } catch {
          console.warn('[account-delete] could not put the built-in lessons back')
        }
      }
      ageForgotten()
      if (!files.ok) console.warn(`[account-delete] left behind: ${files.failed.join(', ')}`)
      if (files.skipped.length) console.warn(`[account-delete] skipped (outside miyagi's folders): ${files.skipped.join(', ')}`)
      return { ok: true, account: server.account, local: files.ok && storage }
    }

    ctx.handle('account:delete', (p) => {
      if (running) return { ok: false, reason: 'busy' } satisfies DeleteAccountResult
      const lessons = (p as { lessons?: unknown } | undefined)?.lessons === true
      running = run(lessons)
        .catch((): DeleteAccountResult => ({ ok: false, reason: 'unreachable' }))
        .finally(() => {
          running = undefined
        })
      return running
    })

    ctx.handle('account:restart', () => {
      if (!ctx.app.isPackaged) {
        console.log('[account-delete] restart asked in a dev copy: restart npm run dev')
        return false
      }
      ctx.app.relaunch()
      ctx.app.quit()
      return true
    })
  }
})
