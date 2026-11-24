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
import { CodePreview } from './Preview'
import { PanelRows } from './rows'
import { SearchResults } from './Search'
import { Account } from './sections/Account'
import { General } from './sections/General'
import { Permissions } from './sections/Permissions'
import { Privacy } from './sections/Privacy'
import { Shortcuts } from './sections/Shortcuts'
import { Flat, InlineSettings, Note } from './ui'
import { Apps4, Data4, General4 } from './v4/Panels'

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

/** The v4 page's header (Adrian's ui-next mock): a 32 px title and, where the panel has one, a lede. */
function BigHeader({ panel }: { panel: PanelId }): ReactNode {
  const p = panelOf(panel)
  const lede = panel === 'apps' || panel === 'data' ? p.caption : undefined
  return (
    <header className="flex flex-col">
      <h1 className="m-0" style={{ fontSize: 32, lineHeight: 1.2, fontWeight: 700, letterSpacing: '-0.022em', color: color.text }}>
        {p.label}
      </h1>
      {lede && (
        <p className="m-0" style={{ fontSize: 14.5, marginTop: 6, color: color.label }}>
          {lede}
        </p>
      )}
    </header>
  )
}

/** The v4 page: General takes Appearance, Lessons takes Editor, Your data takes Storage; the rest keep their panel in one 684 px column. */
function BigBody({ panel, flow, live }: { panel: PanelId; flow: Flow; live: boolean }): ReactNode {
  switch (panel) {
    case 'general':
    case 'appearance':
      return <General4 />
    case 'apps':
      return <Apps4 live={live} />
    case 'data':
    case 'storage':
      return <Data4 live={live} onDeleted={flow.replaceView} />
    case 'lessons':
      return (
        <div className="flex flex-col" style={{ maxWidth: 684 }}>
          <PanelRows panel="lessons" />
          <PanelRows panel="editor" />
        </div>
      )
    default:
      return (
        <div className="flex flex-col" style={{ maxWidth: 684 }}>
          <Body panel={panel} flow={flow} live={live} />
        </div>
      )
  }
}

function Body({ panel, flow, live }: { panel: PanelId; flow: Flow; live: boolean }): ReactNode {
  switch (panel) {
    case 'apps':
      return <Apps4 live={live} />
    case 'data':
      return <Data4 live={live} onDeleted={flow.replaceView} />
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
          <Note>Speed and volume apply from your next lesson.</Note>
        </>
      )
    case 'editor':
      return (
        <>
          <CodePreview />
          <PanelRows panel="editor" />
          <Note>miyagi checks your work in VS Code. More editors are not planned yet.</Note>
        </>
      )
    case 'appearance':
      return (
        <>
          <PanelRows panel="appearance" />
          <Note>Changes apply at once, in every miyagi window. The notch pill always stays black.</Note>
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

export function Content({ panel, onPick, flow, live, big }: { panel: PanelId; onPick: (p: PanelId) => void; flow: Flow; live: boolean; big?: boolean }): ReactNode {
  const query = useNav((s) => s.query)
  useFlash()
  const searching = query.trim().length > 0
  return (
    <InlineSettings.Provider value>
      <Flat.Provider value={!!big}>
        <MotionScope>
          <AnimatePresence mode="wait" initial={false}>
            {searching ? (
              <SearchResults key="search" query={query} onPick={onPick} />
            ) : big ? (
              <motion.div key={panel} data-settings-panel={panel} className="flex flex-col" {...riseIn}>
                <BigHeader panel={panel} />
                <BigBody panel={panel} flow={flow} live={live} />
              </motion.div>
            ) : (
              <motion.div key={panel} data-settings-panel={panel} className="flex flex-col gap-[24px]" {...riseIn}>
                <Header panel={panel} />
                <Body panel={panel} flow={flow} live={live} />
              </motion.div>
            )}
          </AnimatePresence>
        </MotionScope>
      </Flat.Provider>
    </InlineSettings.Provider>
  )
}
