/**
 * Feature: settings. What the grown sheet holds (Set-* mockups): the sidebar on the left (search, grouped panels), the
 * panel on the right (Content.tsx), scrolling inside its own pane when the clamped sheet is shorter than the panel.
 *
 * Mounted once per open (Settings.tsx keys it by the open generation), so the key flow's drafts and every
 * section's local state (a recording, a delete confirm) are dropped with the sheet. `live` is false while the sheet
 * collapses: no Save, no Test, no permission polling.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { fill } from '../../core/theme'
import { useKeyFlow } from './account'
import { Content } from './Content'
import type { AboutView } from './keys'
import { setQuery } from './nav'
import { isPanel } from './panels'
import { Sidebar } from './Sidebar'
import { setSection, useSettings } from './store'

export function Shell({ live, onClose }: { live: boolean; onClose: () => void }): ReactNode {
  const section = useSettings((s) => s.section)
  const flow = useKeyFlow(live)
  const [about, setAbout] = useState<AboutView>()

  useEffect(() => {
    setQuery('')
    let on = true
    bridge
      .invoke<AboutView>('settings:about')
      .then((a) => on && setAbout(a))
      .catch(() => {})
    return () => {
      on = false
    }
  }, [])

  return (
    <div className="flex h-full w-full">
      <Sidebar
        section={section}
        onSelect={(s, via) => {
          if (!isPanel(s)) return
          setQuery('')
          setSection(s, via)
        }}
        onClose={onClose}
        version={about?.version}
      />
      <main
        id="settings-panel"
        role="tabpanel"
        aria-labelledby={`settings-tab-${section}`}
        className="relative min-w-0 flex-1 overflow-y-auto"
        style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}
      >
        <div className="px-[40px] py-[32px]">
          <Content panel={section} onPick={(p) => setSection(p)} flow={flow} live={live} />
        </div>
      </main>
    </div>
  )
}
