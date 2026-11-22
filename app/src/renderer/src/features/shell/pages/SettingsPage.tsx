/**
 * Feature: shell. The Settings page: the settings sheet's five sections (features/settings sections/*) inline, so
 * nobody hunts for a separate window. General, Permissions, Privacy, Your key, Shortcuts, picked with a segmented
 * control. The sheet that grows from the pill (openSettings, the tray, the pill's gear) is unchanged.
 *
 * `live` is true only while this page is on show: permissions poll, health asks, Save and Test run then and never
 * while the page sits hidden. The key flow (drafts, Save, Test) is the sheet's own hook; drafts live while the window
 * does and are never stored.
 */
import { motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import type { SettingsSection } from '../../../core/surfaces'
import { Segmented } from '../../../core/ui/controls'
import { riseIn } from '../../../core/ui/motion'
import { useKeyFlow } from '../../settings/account'
import { Account } from '../../settings/sections/Account'
import { General } from '../../settings/sections/General'
import { Permissions } from '../../settings/sections/Permissions'
import { Privacy } from '../../settings/sections/Privacy'
import { Shortcuts } from '../../settings/sections/Shortcuts'
import { NAV } from '../../settings/Sidebar'
import { InlineSettings } from '../../settings/ui'
import { setSettingsSection, useShell } from '../store'

const OPTIONS = NAV.map((n) => ({ value: n.id, label: n.label }))

export function SettingsPage({ active }: { active: boolean }): ReactNode {
  const section = useShell((s) => s.settings)
  const flow = useKeyFlow(active)
  // The section the page opened on doesn't rise (the page's own entrance covers it); a later one does.
  const [first] = useState<SettingsSection>(section)
  const [moved, setMoved] = useState(false)
  useEffect(() => {
    if (section !== first) setMoved(true)
  }, [section, first])
  return (
    <InlineSettings.Provider value>
    <div data-shell-settings={section} className="flex flex-col gap-[24px]" style={{ padding: '8px 40px 40px', maxWidth: 820 }}>
      <div className="flex shrink-0">
        <Segmented<SettingsSection> label="Settings sections" options={OPTIONS} value={section} onChange={setSettingsSection} />
      </div>
      <motion.div key={section} initial={moved ? riseIn.initial : false} animate={riseIn.animate} transition={riseIn.transition} className="flex flex-col gap-[24px]">
        {section === 'general' && <General live={active} />}
        {section === 'permissions' && <Permissions live={active} />}
        {section === 'privacy' && <Privacy secure={flow.view?.secure} onDeleted={flow.replaceView} />}
        {section === 'account' && <Account flow={flow} live={active} />}
        {section === 'shortcuts' && <Shortcuts />}
      </motion.div>
    </div>
    </InlineSettings.Provider>
  )
}
