/**
 * Feature: shell. The Settings page, v4 (Adrian's ui-next mock, screens settings, settings-apps and settings-data,
 * Nov 23-24): the page's own list on the left (Account; App; Learning; Privacy; About at the foot), and the panel on
 * the right with a 32 px title, an optional lede and two columns of groups, flat rows with hairlines between them
 * (features/settings v4/). The panel scrolls, the list stays in reach. The pill-born sheet is unchanged.
 *
 * `live` is true only while this page is on show: permissions poll, health asks, Save and Test run then and never
 * while the page sits hidden. The key flow (drafts, Save, Test) is the sheet's own hook; drafts live while the window
 * does and are never stored. `useShell.settings` (openPage('settings', section)) picks the panel when it changes.
 *
 * The mock's settings list replaces the app sidebar, and its top bar reads "Settings / General": both are the shell
 * frame's (the shell lane's), so here the list sits beside the app sidebar under the shell's own page header.
 */
import { useEffect, type ReactNode } from 'react'
import { fill } from '../../../core/theme'
import { useKeyFlow } from '../../settings/account'
import { Content } from '../../settings/Content'
import { setPagePanel, setQuery, useNav } from '../../settings/nav'
import { PageNav } from '../../settings/v4/PageNav'
import { useShell } from '../store'
import { PageColumn } from '../ui'

const SEG_CSS = '#settings-panel [role="radiogroup"] > button[role="radio"] { height: 26px !important; padding: 0 10px !important; font-size: 12.5px !important; }'

export function SettingsPage({ active }: { active: boolean }): ReactNode {
  const shellSection = useShell((s) => s.settings)
  const panel = useNav((s) => s.page)
  const flow = useKeyFlow(active)
  useEffect(() => {
    setPagePanel(shellSection)
  }, [shellSection])
  useEffect(() => {
    if (!active) setQuery('')
  }, [active])
  return (
    <PageColumn wide bottom={16} className="min-h-0 flex-1" data={{ 'data-shell-settings': panel }}>
      {/* The mock's segmented controls are 24 tall with 10 px sides (core's are 32 / 16, sized for the cards). */}
      <style>{SEG_CSS}</style>
      <div className="flex min-h-0 flex-1" style={{ gap: 32 }}>
        <aside className="flex w-[172px] shrink-0 flex-col pb-[8px]" aria-label="Settings">
          <PageNav panel={panel} onSelect={(p) => setPagePanel(p)} />
        </aside>
        <div
          id="settings-panel"
          role="tabpanel"
          aria-labelledby={`settings-tab-${panel}`}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto pb-[60px] pr-[4px] pt-[2px]"
          style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}
        >
          <Content panel={panel} onPick={(p) => setPagePanel(p)} flow={flow} live={active} big />
        </div>
      </div>
    </PageColumn>
  )
}
