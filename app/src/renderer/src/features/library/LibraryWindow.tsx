/**
 * Feature: library. The Library app window (route `library`): the list, or a lesson's preview when opened with
 * openLibrary(id) or a card click. Loads on open, whenever the window comes forward, and when the engine connects.
 */
import { useEffect, type ReactNode } from 'react'
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
    if (!args) return
    if (typeof args.id === 'string') openDetail(args.id)
    else closeDetail()
  }, [args])

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
