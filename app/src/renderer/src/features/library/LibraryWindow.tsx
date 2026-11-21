/**
 * Feature: library. The Library app window (route `library`): the list, or a lesson's preview when opened with
 * openLibrary(id) or a card click. Loads on open, whenever the window comes forward, and when the engine connects.
 */
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { useWindowArgs } from '../../core/surfaces'
import { color, font } from '../../core/theme'
import { Detail } from './Detail'
import { Library } from './Library'
import { closeDetail, openDetail, refresh, useLibrary } from './store'

export function LibraryWindow(): ReactNode {
  const args = useWindowArgs('library')
  const openId = useLibrary((s) => s.openId)
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)

  // Each open carries its own args: {id} = that lesson's preview, none = the list.
  useEffect(() => {
    if (args && typeof args.id === 'string') openDetail(args.id)
  }, [args])
  // useWindowArgs can't tell "opened without args" from "not loaded yet", so a re-open with no id is read here:
  // openLibrary() on a window showing a preview goes back to the list. (Electron sends the args to this window
  // only; the stage's one bus tags them with the route.)
  useEffect(
    () =>
      bridge.onFeature('window:args', (p) => {
        const tagged = !!p && typeof p === 'object' && 'route' in p
        if (tagged && (p as { route?: unknown }).route !== 'library') return
        const a = (tagged ? (p as { args?: unknown }).args : p) as { id?: unknown } | null | undefined
        if (!a || typeof a.id !== 'string') closeDetail()
      }),
    []
  )

  useEffect(() => {
    void refresh()
  }, [connected, hello])

  useEffect(() => {
    const onFocus = (): void => void refresh()
    addEventListener('focus', onFocus)
    return () => removeEventListener('focus', onFocus)
  }, [])

  return (
    <div data-window="library" className="h-full w-full select-none overflow-hidden" style={{ fontFamily: font.ui, background: color.window }}>
      {openId ? <Detail id={openId} /> : <Library />}
    </div>
  )
}
