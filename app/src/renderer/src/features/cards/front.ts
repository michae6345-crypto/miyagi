/**
 * The app in front, as the engine last saw it (screen.seen.app, every few seconds), so a setup card doesn't offer
 * "Open Visual Studio Code" while VS Code is already open and in front (Michael's desktop test 5). Our own overlay
 * never counts: a click on a card must not bring the button back under the pointer.
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'

export const useFrontApp = create<{ app?: string }>(() => ({}))

const OWN = /^(miyagi|electron)$/i
onMessage('screen.seen', (p) => {
  const app = p.app?.trim()
  if (app && !OWN.test(app)) useFrontApp.setState({ app })
})
onUi('reset', () => useFrontApp.setState({ app: undefined }))

const norm = (s: string): string => s.toLowerCase().replace(/\s+/g, ' ').trim()

/**
 * Is `app` the editor named `label`? "Code" (VS Code's app name on the Mac) is "Visual Studio Code", "Cursor" is
 * "Cursor". No label: the engine's default editor, VS Code.
 */
export function isEditor(app: string | undefined, label: string | null | undefined): boolean {
  if (!app) return false
  const a = norm(app)
  const e = norm(label || 'Visual Studio Code')
  return a === e || e.endsWith(` ${a}`) || (e.includes('code') && /^(vs ?code|visual studio code)$/.test(a))
}
