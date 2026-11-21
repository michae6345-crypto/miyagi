/**
 * Feature: settings. What the grown sheet holds (Set-* mockups): the sidebar on the left, the section on the right,
 * scrolling inside its own pane when the clamped sheet is shorter than the section.
 *
 * Mounted once per open (Settings.tsx keys it by the open generation), so the key flow's drafts and every
 * section's local state (a recording, a delete confirm) are dropped with the sheet. `live` is false while the sheet
 * collapses: no Save, no Test, no permission polling.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { fill } from '../../core/theme'
import { riseIn } from '../../core/ui/motion'
import { useKeyFlow } from './account'
import { isSection } from './env'
import type { AboutView } from './keys'
import { Account } from './sections/Account'
import { General } from './sections/General'
import { Permissions } from './sections/Permissions'
import { Privacy } from './sections/Privacy'
import { Shortcuts } from './sections/Shortcuts'
import { Sidebar } from './Sidebar'
import { setSection, useSettings } from './store'

export function Shell({ live, onClose }: { live: boolean; onClose: () => void }): ReactNode {
  const section = useSettings((s) => s.section)
  const flow = useKeyFlow(live)
  const [about, setAbout] = useState<AboutView>()

  useEffect(() => {
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
      <Sidebar section={section} onSelect={(s, via) => isSection(s) && setSection(s, via)} onClose={onClose} version={about?.version} />
      <main
        id="settings-panel"
        role="tabpanel"
        aria-labelledby={`settings-tab-${section}`}
        className="relative min-w-0 flex-1 overflow-y-auto"
        style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}
      >
        {/* Section switch: the old one fades out fast, the new one rises in on the core riseIn spring (opacity only
            with reduced motion, via MotionConfig). Not on open: the sheet's own entrance covers the first section. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={section} className="flex flex-col gap-[24px] px-[40px] py-[32px]" {...riseIn}>
            {section === 'general' && <General live={live} />}
            {section === 'permissions' && <Permissions live={live} />}
            {section === 'privacy' && <Privacy secure={flow.view?.secure} onDeleted={flow.replaceView} />}
            {section === 'account' && <Account flow={flow} live={live} />}
            {section === 'shortcuts' && <Shortcuts />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
