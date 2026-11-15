/**
 * Feature: settings. Browser-stage stand-in for src/main/features/settings.ts (does nothing in Electron).
 *
 * Same channels, same rules: keys in this module's memory only (never localStorage, never logged), the
 * sheet gets {set, last4} back, config.keys always carries every name, re-sent on every (re)connect.
 * Stage extras: Ctrl+, / ⌘, opens the sheet; ?nosecure previews "no secure storage".
 */
import { cmd } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { onMessage } from '../../core/bus'
import { fullPayload, mergeKeys, needsKeys, viewOf, type Keys, type KeyStatus, type KeysView } from './keys'
import { openSettings } from './open'
import { requestOpen, type Size } from './store'

/**
 * The island's current size, read off the stage's DOM (main has ctx.islandSize(); the web bridge keeps
 * its copy private, see Core requests). offsetWidth/Height ignore the stage's scale transform.
 */
function islandSize(): Size | undefined {
  const top = `${bridge.platform.pillTop}px`
  for (const el of document.querySelectorAll<HTMLElement>('[data-hit]')) {
    const p = el.parentElement
    if (p && p.style.top === top && getComputedStyle(p).justifyContent === 'center' && el.offsetWidth > 0) return { w: el.offsetWidth, h: el.offsetHeight }
  }
  return undefined
}

function setupWeb(): void {
  const secure = !new URLSearchParams(location.search).has('nosecure')
  let keys: Keys = {}
  let lastStatus: KeyStatus | undefined
  let open = false
  let autoOpened = false

  const view = (): KeysView => ({ keys: viewOf(keys), secure, status: lastStatus })
  const sendKeys = (): void => bridge.send(cmd('config.keys', fullPayload(keys)))

  registerWebHandler('settings:open', () => {
    if (open) return
    open = true
    requestOpen(islandSize())
  })
  registerWebHandler('settings:get', () => view())
  registerWebHandler('settings:save', (patch) => {
    keys = mergeKeys(keys, patch)
    sendKeys()
    return view()
  })
  registerWebHandler('settings:test', () => sendKeys())
  registerWebHandler('settings:island', () => islandSize())
  registerWebHandler('settings:hidden', () => {
    open = false
  })

  // engine.onOpen's stand-in: every (re)connect.
  bridge.onStatus((connected) => connected && sendKeys())

  onMessage('config.status', (p) => {
    lastStatus = p
    // Never opens by itself (Adrian, Sat 5 PM): the learner opens Settings (gear, launcher, ⌘,).
  })

  addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === ',') {
      e.preventDefault()
      openSettings()
    }
  })
}

if (!isElectron) setupWeb()
