/**
 * Feature: shell. The Settings page, v4 (Adrian's ui-next mock, screens settings, settings-apps and settings-data,
 * Nov 23-24): "Settings swaps the app sidebar for its own list". While this page is on show it hands the shell its
 * list (Account; App; Learning; Privacy; About at the foot) through `setSidebarList`, and the top bar reads
 * "Settings / General" through `setCrumbs`. The panel sits in the shell's v4 PageFrame (the 1040 column, so the two
 * columns are 492 each), which also hides the shell's own page title: the panel's 32 px title is the only one.
 *
 * `live` is true only while this page is on show: permissions poll, health asks, Save and Test run then and never
 * while the page sits hidden. The key flow (drafts, Save, Test) is the sheet's own hook; drafts live while the window
 * does and are never stored. `useShell.settings` (openPage('settings', section)) picks the panel when it changes.
 */
import { useEffect, type ReactNode } from 'react'
import { useKeyFlow } from '../../settings/account'
import { Content } from '../../settings/Content'
import { setPagePanel, setQuery, useNav } from '../../settings/nav'
import type { PanelId } from '../../settings/panels'
import { FOOT4, NAV4, navLabel, navRowOf } from '../../settings/v4/PageNav'
import { openPage, setPage, useShell } from '../store'
import { PageFrame, setCrumbs, setSidebarList, type SidebarList } from '../ui'

const pick = (id: string): void => {
  if (id === 'account-page') return void openPage('account')
  setPagePanel(id as PanelId)
}

export function SettingsPage({ active }: { active: boolean }): ReactNode {
  const shellSection = useShell((s) => s.settings)
  const panel = useNav((s) => s.page)
  const flow = useKeyFlow(active)
  const on = navRowOf(panel)
  useEffect(() => {
    setPagePanel(shellSection)
  }, [shellSection])
  useEffect(() => {
    if (!active) setQuery('')
  }, [active])
  // One sidebar on screen: the app's list gives way to Settings' own while this page shows.
  useEffect(() => {
    if (!active) return
    const list: SidebarList = {
      back: { label: 'Settings', onClick: () => setPage('home') },
      groups: NAV4.map((g) => ({ label: g.label, items: g.items.map((i) => ({ id: i.id, label: i.label, icon: i.icon })) })),
      foot: [{ id: FOOT4.id, label: FOOT4.label, icon: FOOT4.icon }],
      active: on,
      onPick: pick
    }
    setSidebarList(list)
    return () => setSidebarList(null)
  }, [active, on])
  useEffect(() => {
    if (!active) return
    setCrumbs('settings', [navLabel(on)])
    return () => setCrumbs('settings', null)
  }, [active, on])
  return (
    <PageFrame data={{ 'data-shell-settings': panel }}>
      <div id="settings-panel" role="region" aria-label={navLabel(on)} className="min-w-0">
        <Content panel={panel} onPick={(p) => setPagePanel(p)} flow={flow} live={active} big />
      </div>
    </PageFrame>
  )
}
