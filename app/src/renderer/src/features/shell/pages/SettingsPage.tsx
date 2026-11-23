/**
 * Feature: shell. The Settings page: Notion-style settings inside the home window. A left list of panels in groups with
 * search on top, the panel on the right (features/settings Content.tsx, the same panels as the sheet that grows from the
 * pill, which is unchanged). The page scrolls its panel, not the list, so the list stays in reach.
 *
 * `live` is true only while this page is on show: permissions poll, health asks, Save and Test run then and never
 * while the page sits hidden. The key flow (drafts, Save, Test) is the sheet's own hook; drafts live while the window
 * does and are never stored. `useShell.settings` (openPage('settings', section)) picks the panel when it changes.
 */
import { useEffect, type ReactNode } from 'react'
import { fill, layout } from '../../../core/theme'
import { useKeyFlow } from '../../settings/account'
import { Content } from '../../settings/Content'
import { setPagePanel, setQuery, useNav } from '../../settings/nav'
import { Nav } from '../../settings/Sidebar'
import { SearchField } from '../../settings/Search'
import { useShell } from '../store'
import { PageColumn } from '../ui'

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
      <div className="flex min-h-0 flex-1" style={{ gap: layout.page.gutter }}>
        <aside className="flex w-[200px] shrink-0 flex-col gap-[12px]" aria-label="Settings">
          <SearchField />
          <div className="min-h-0 flex-1 overflow-y-auto pb-[16px]" style={{ scrollbarWidth: 'none' }}>
            <Nav section={panel} onSelect={(p) => setPagePanel(p)} focusOnMount={false} />
          </div>
        </aside>
        <div
          id="settings-panel"
          role="tabpanel"
          aria-labelledby={`settings-tab-${panel}`}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto pb-[48px] pr-[4px]"
          style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}
        >
          <Content panel={panel} onPick={(p) => setPagePanel(p)} flow={flow} live={active} />
        </div>
      </div>
    </PageColumn>
  )
}
