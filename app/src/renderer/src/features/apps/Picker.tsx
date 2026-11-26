/**
 * Feature: apps. "Add app": a small calm list beside the sidebar's Add app row. Tick an app to keep it in the sidebar,
 * untick to take it out (prefs.pinnedApps). The apps miyagi doesn't teach in yet sit under "Soon" as one greyed line
 * of names, no clicks (MIC-87: "Soon: one line of names"). "Reset to default" puts back the apps on this Mac.
 *
 * It hangs off the row (fixed, in a portal, so the sidebar's scroll box can't clip it), rises in on the house spring,
 * and closes on Esc, a click outside, a pick of "Open" or the window losing focus. Focus goes to the panel (the arrows
 * walk its rows, Tab too) and back to Add app on Esc.
 */
import { motion, useReducedMotion } from 'motion/react'
import { Check, ChevronRight } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { usePrefs } from '../../core/prefs'
import { color, focus, spring, v4, v4c, v4type } from '../../core/theme'
import { PLANS } from '../plans/catalog'
import { catalogApps } from './model'
import { closePicker, openApp, resetPins, togglePin, useApps, useAppStates } from './store'
import { AppIcon, stateWord } from './ui'

const W = 272
const GAP = 8
const EDGE = 12

export function AppPicker({ shown }: { shown: readonly string[] }): ReactNode {
  const at = useApps((s) => s.picker)
  if (!at || typeof document === 'undefined') return null
  return createPortal(<Panel at={at} shown={shown} />, document.body)
}

function Panel({ at, shown }: { at: { x: number; y: number; w: number }; shown: readonly string[] }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion() ?? false
  const pinned = usePrefs((s) => s.pinnedApps)
  const states = useAppStates(false)
  const apps = useMemo(() => catalogApps(PLANS), [])
  const supported = apps.filter((a) => !a.soon)
  const soon = apps.filter((a) => a.soon)
  const [top, setTop] = useState(at.y)

  // Keep the panel on screen: it starts level with the row and moves up as far as it must.
  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 0
    setTop(Math.max(EDGE, Math.min(at.y, innerHeight - h - EDGE)))
  }, [at.y])

  useEffect(() => {
    // The panel takes focus (no ring on a mouse open); the arrows then walk its rows.
    ref.current?.focus()
    const back = (): void => document.querySelector<HTMLButtonElement>('[data-shell-add-app]')?.focus()
    const onDown = (e: PointerEvent): void => {
      const t = e.target as Element | null
      if (ref.current?.contains(t) || t?.closest?.('[data-shell-add-app]')) return
      closePicker()
    }
    const onKey = (e: globalThis.KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      closePicker()
      back()
    }
    const onBlur = (): void => closePicker()
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('keydown', onKey)
    addEventListener('blur', onBlur)
    return () => {
      document.removeEventListener('pointerdown', onDown, true)
      document.removeEventListener('keydown', onKey)
      removeEventListener('blur', onBlur)
    }
  }, [])

  const walk = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const items = [...(ref.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') ?? [])]
    const i = items.indexOf(document.activeElement as HTMLButtonElement)
    const next = items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]
    if (next) {
      e.preventDefault()
      next.focus()
    }
  }

  const left = Math.min(at.x + at.w + GAP, innerWidth - W - EDGE)
  return (
    <motion.div
      ref={ref}
      role="dialog"
      aria-label="Apps in your sidebar"
      data-apps-picker
      data-no-drag
      tabIndex={-1}
      onKeyDown={walk}
      className="fixed z-[60] flex flex-col outline-none"
      style={{ left, top, width: W, padding: 6, borderRadius: v4.radius.card, background: v4c.card, boxShadow: v4c.e2, color: color.text }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, x: -6, scale: 0.98 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={spring}
    >
      <div style={{ ...v4type.navLabel, color: color.faint, padding: '6px 8px 6px' }}>Apps in your sidebar</div>
      {supported.map((a) => {
        const on = shown.includes(a.id)
        const word = stateWord(states[a.id])
        return (
          <div key={a.id} className="group flex items-center" style={{ gap: 2 }}>
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={on}
              data-app-pick={a.id}
              onClick={() => togglePin(shown, a.id)}
              className="mg-v4-side-row flex min-w-0 flex-1 cursor-pointer items-center text-left outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
              style={{ ...v4type.nav, height: 34, gap: 10, padding: '0 8px', borderRadius: v4.radius.row, outlineColor: focus.dark }}
            >
              <span aria-hidden className="grid shrink-0 place-items-center" style={{ width: 16, height: 16, borderRadius: 4, boxShadow: `inset 0 0 0 1.5px ${on ? color.text : v4c.ghost}`, background: on ? color.text : undefined }}>
                {on && <Check size={11} strokeWidth={3} style={{ color: v4c.card }} />}
              </span>
              <AppIcon id={a.id} size={16} style={{ color: color.faint, flexShrink: 0 }} />
              <span className="min-w-0 flex-1 truncate">{a.name}</span>
              {word && <span style={{ fontSize: 12, lineHeight: '16px', color: color.label, whiteSpace: 'nowrap' }}>{word}</span>}
            </button>
            <button
              type="button"
              aria-label={`Open ${a.name}`}
              title={`Open ${a.name}`}
              data-app-open={a.id}
              onClick={() => openApp(a.id)}
              className="mg-v4-side-row grid shrink-0 cursor-pointer place-items-center outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
              style={{ width: 28, height: 34, borderRadius: v4.radius.row, color: color.label, outlineColor: focus.dark }}
            >
              <ChevronRight aria-hidden size={14} strokeWidth={1.8} />
            </button>
          </div>
        )
      })}
      {soon.length > 0 && (
        <div data-apps-soon aria-disabled style={{ padding: '10px 8px 6px', borderTop: `1px solid ${v4c.hair}`, marginTop: 6 }}>
          <div style={{ ...v4type.navLabel, color: color.faint, marginBottom: 4 }}>Soon</div>
          <p className="m-0" style={{ fontSize: 12.5, lineHeight: '18px', color: color.faint }}>
            {soon.map((a) => a.name).join(', ')}
          </p>
        </div>
      )}
      {pinned !== null && (
        <button
          type="button"
          data-apps-reset
          onClick={resetPins}
          className="mg-v4-side-row cursor-pointer text-left outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
          style={{ fontSize: 12.5, lineHeight: '16px', height: 30, padding: '0 8px', marginTop: 2, borderRadius: v4.radius.row, color: color.label, outlineColor: focus.dark }}
        >
          Reset to default
        </button>
      )}
    </motion.div>
  )
}
