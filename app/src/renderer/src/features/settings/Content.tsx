/**
 * Feature: settings. What a panel shows, shared by the sheet (Shell.tsx) and the home window's Settings page: the
 * panel's header (title, one line), its rows, smooth switching between panels, search results in its place while a
 * query is typed, and the flash that points at the row a search result opened.
 *
 * `live` is true only while the surface is on show (permissions poll, Save and Test run). The reduce-motion setting
 * reaches everything under it through MotionConfig.
 */
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { riseIn } from '../../core/ui/motion'
import type { useKeyFlow } from './account'
import { useLocal } from './local'
import { useNav } from './nav'
import { panelOf, type PanelId } from './panels'
import { PanelRows } from './rows'
import { SearchResults } from './Search'
import { Account } from './sections/Account'
import { General } from './sections/General'
import { Permissions } from './sections/Permissions'
import { Privacy } from './sections/Privacy'
import { Shortcuts } from './sections/Shortcuts'
import { InlineSettings, Note } from './ui'

type Flow = ReturnType<typeof useKeyFlow>

/** Reduce motion (Appearance): this surface's springs become fades, whatever macOS says. */
export function MotionScope({ children }: { children: ReactNode }): ReactNode {
  const reduce = useLocal((s) => s.motion === 'reduce')
  return <MotionConfig reducedMotion={reduce ? 'always' : 'user'}>{children}</MotionConfig>
}

function Header({ panel }: { panel: PanelId }): ReactNode {
  const p = panelOf(panel)
  return (
    <header className="flex flex-col gap-[4px]">
      <h2 className="m-0 font-semibold" style={{ fontSize: 22, letterSpacing: -0.2, color: color.text }}>
        {p.label}
      </h2>
      <p className="m-0" style={{ fontSize: type2.sm, color: color.label }}>
        {p.caption}
      </p>
    </header>
  )
}

function Body({ panel, flow, live }: { panel: PanelId; flow: Flow; live: boolean }): ReactNode {
  switch (panel) {
    case 'general':
      return <General live={live} />
    case 'permissions':
      return <Permissions live={live} />
    case 'privacy':
      return <Privacy secure={flow.view?.secure} onDeleted={flow.replaceView} />
    case 'account':
      return <Account flow={flow} live={live} />
    case 'shortcuts':
      return <Shortcuts />
    case 'lessons':
      return (
        <>
          <PanelRows panel="lessons" />
          <Note>These switches arrive with the next lesson update. Until then lessons use the defaults shown.</Note>
        </>
      )
    case 'editor':
      return (
        <>
          <PanelRows panel="editor" />
          <Note>miyagi checks your work in VS Code. More editors are not planned yet.</Note>
        </>
      )
    default:
      return <PanelRows panel={panel} />
  }
}

/** After a search result opens a panel: scroll its row into view and wash it once. */
function useFlash(): void {
  const flash = useNav((s) => s.flash)
  const reduce = useReducedMotion()
  useEffect(() => {
    if (!flash) return
    let raf = 0
    const t = setTimeout(() => {
      raf = requestAnimationFrame(() => {
        const el = document.querySelector<HTMLElement>(`[data-setting="${CSS.escape(flash.id)}"]`)
        if (!el) return
        el.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' })
        el.animate([{ background: fill.navActive, borderRadius: `${radius2.row}px` }, { background: 'transparent', borderRadius: `${radius2.row}px` }], { duration: reduce ? 1 : 1400, easing: 'ease-out' })
      })
    }, 120)
    return () => {
      clearTimeout(t)
      cancelAnimationFrame(raf)
    }
  }, [flash, reduce])
}

export function Content({ panel, onPick, flow, live }: { panel: PanelId; onPick: (p: PanelId) => void; flow: Flow; live: boolean }): ReactNode {
  const query = useNav((s) => s.query)
  useFlash()
  const searching = query.trim().length > 0
  return (
    <InlineSettings.Provider value>
      <MotionScope>
        <AnimatePresence mode="wait" initial={false}>
          {searching ? (
            <SearchResults key="search" query={query} onPick={onPick} />
          ) : (
            <motion.div key={panel} data-settings-panel={panel} className="flex flex-col gap-[24px]" {...riseIn}>
              <Header panel={panel} />
              <Body panel={panel} flow={flow} live={live} />
            </motion.div>
          )}
        </AnimatePresence>
      </MotionScope>
    </InlineSettings.Provider>
  )
}
