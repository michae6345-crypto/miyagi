/**
 * Feature: settings. General (Set-General): Appearance, Launch at login, Voice; Works with (VS Code, Jupyter); Set up
 * miyagi. Each control applies at once through core prefs (setPrefs → main saves userData/prefs.json and tells every
 * window). Appearance switches the glass panels (theme.glass); the notch island, the cards and this sheet stay black
 * (decision 9: the caption reads copy.appearanceCaption).
 *
 * Neutral chrome only (Adrian): no pastel, no green. The selected segment and an "on" switch are white, never a hue.
 * Works with reads the engine's health rows when it has them; nothing is shown that the engine didn't say.
 */
import { CodeXml, Compass, NotebookText, Wrench } from 'lucide-react'
import { useContext, useEffect, useState, type ReactNode } from 'react'
import { VOICE_ENABLED } from '../../../../../common/flags'
import type { IslandPlace } from '../../../../../common/notch'
import { useLesson } from '../../../core/lesson'
import { setPrefs, usePrefs } from '../../../core/prefs'
import { bridge } from '../../../bridge'
import { useNotchInfo } from '../../../core/notchInfo'
import { openOnboarding } from '../../../core/surfaces'
import { startTour } from '../../tips/tourStore'
import { requestClose } from '../store'
import { BuddyColor } from '../../buddy/SettingsRows'
import { QuietButton, Segmented, StatusGlyph, Toggle } from '../../../core/ui/atoms'
import { color, copy, type2 } from '../../../core/theme'
import type { HealthItem } from '../../../../../../../shared/contracts/events'
import { PushToTalk } from '../../ptt/SettingsRows'
import { useHealth } from '../permissions'
import { PanelRows, Select } from '../rows'
import { Flat, Group, OnWord, PageHeader, Row } from '../ui'
import { AmbientSettings } from '../../ambient/Settings'

const PLACES: { value: IslandPlace; label: string }[] = [
  { value: 'notch', label: 'In the notch' },
  { value: 'below', label: 'Below the menu bar' }
]

/** Where the island lives. macOS only. */
export function IslandRow({ label = 'Island' }: { label?: string } = {}): ReactNode {
  const flat = useContext(Flat)
  const place = usePrefs((s) => s.island?.place ?? 'notch')
  const effective = useNotchInfo((s) => s.notch?.place)
  const mac = bridge.platform.os === 'mac'
  // A short "Saved." after a choice (the row saves as you click; this just says so).
  const [saved, setSaved] = useState(false)
  useEffect(() => {
    if (!saved) return
    const t = setTimeout(() => setSaved(false), 2500)
    return () => clearTimeout(t)
  }, [saved])
  // Ask main to read the notch afresh (the cached answer can be old), when this opens and when the window is focused again.
  useEffect(() => {
    if (!mac) return
    const look = (): void => void bridge.invoke('notch:recheck').catch(() => undefined)
    look()
    window.addEventListener('focus', look)
    return () => window.removeEventListener('focus', look)
  }, [mac])
  if (!mac) return null
  // What main actually did with the choice (layout.notch.place), so a click never looks like it did nothing.
  const actual = effective ?? place
  const where = actual === 'notch' ? 'miyagi is in the notch now.' : 'miyagi is below the menu bar now.'
  const caption = place !== actual ? 'Moving miyagi…' : where
  const pick = (p: IslandPlace): void => setPrefs({ island: { place: p } })
  return (
    <Row
      label={label}
      caption={saved && place === actual ? `Saved. ${where}` : caption}
      right={
        // The v4 page's narrow columns take a menu (Adrian's mock); the sheet keeps the two segments.
        flat ? (
          <Select label={label} options={PLACES} value={place} onChange={(v) => pick(v as IslandPlace)} />
        ) : (
          <Segmented label={label} options={PLACES} value={place} onChange={pick} />
        )
      }
    />
  )
}

export function General({ live }: { live: boolean }): ReactNode {
  const voiceOnStart = usePrefs((s) => s.voiceOnStart)
  const launchAtLogin = usePrefs((s) => s.launchAtLogin)
  const health = useHealth(live)
  const inLesson = useLesson((s) => s.connected && !!s.lesson && !!s.stepId)

  return (
    <>
      <PageHeader title="General" caption="Changes save as you make them." />

      <PanelRows panel="general" />

      <Group label="Where miyagi lives">
        <IslandRow />
        <Row
          tight
          label="Launch at login"
          caption="miyagi waits in the pill until you need it."
          right={<Toggle label="Launch at login" on={launchAtLogin} onChange={(v) => setPrefs({ launchAtLogin: v })} />}
        />
        {/* Voice is off for now (common/flags): the row comes back with the flag. */}
        {VOICE_ENABLED && (
          <Row
            tight
            label="Voice"
            caption="Read lessons out loud when one starts."
            right={<Toggle label="Voice" on={voiceOnStart} onChange={(v) => setPrefs({ voiceOnStart: v })} />}
          />
        )}
      </Group>

      <PushToTalk />

      <BuddyColor />

      <AmbientSettings />

      <WorksWith health={health} inLesson={inLesson} />

      <Group label="Setup">
        <Row
          icon={Wrench}
          label={`Set up ${copy.name}`}
          caption={bridge.platform.os === 'mac' ? 'Check permissions and VS Code again.' : 'Check VS Code again.'}
          right={<QuietButton label="Open setup" onClick={() => void openOnboarding()} />}
        />
        <Row icon={Compass} label="Show me around" caption="A short tour of the pill and the launcher." right={<QuietButton label="Start" onClick={showMeAround} />} />
      </Group>
    </>
  )
}

function WorksWith({ health, inLesson }: { health: Record<string, HealthItem | undefined>; inLesson: boolean }): ReactNode {
  const vscode = health.vscode
  const jupyter = health.jupyter
  return (
    <Group label="Works with" title="Works with" caption="Cards stay clear of your Explorer, tabs and toolbar." inset={64}>
      <Row
        icon={CodeXml}
        label="VS Code"
        caption={vscode?.detail ? `Version ${vscode.detail}` : 'Where you write the code.'}
        right={inLesson ? <Watching /> : <HealthWord item={vscode} />}
      />
      <Row icon={NotebookText} label="Jupyter notebooks" caption="Checked by running your cells." right={<HealthWord item={jupyter} />} />
    </Group>
  )
}

/** Gray dashed ring + "Watching" (decision 5: never a spinner). */
function Watching(): ReactNode {
  return (
    <span className="flex shrink-0 items-center gap-[8px] whitespace-nowrap" style={{ fontSize: type2.xs, color: color.label }}>
      <StatusGlyph state="watching" size={12} />
      Watching
    </span>
  )
}

/** What the engine said about this tool, in a word. Nothing when it said nothing. */
function HealthWord({ item }: { item?: HealthItem }): ReactNode {
  if (!item) return null
  if (item.state === 'ok') return <OnWord>Ready</OnWord>
  if (item.state === 'checking') return <StatusGlyph state="checking" size={14} />
  const word = item.state === 'unknown' ? 'Not sure yet' : 'Not found'
  return (
    <span className="flex shrink-0 items-center gap-[8px] whitespace-nowrap" style={{ fontSize: type2.xs, color: item.state === 'unknown' ? color.label : color.text }}>
      <StatusGlyph state={item.state === 'unknown' ? 'unknown' : 'notyet'} size={12} />
      {word}
    </span>
  )
}

/**
 * Show me around: the tour draws in the overlay, and the Settings sheet's own window sits above the overlay (both
 * float at the same level, the sheet raised last), so a tour started from the sheet drew behind it and the button
 * looked dead. The sheet steps aside first (in the home window's Settings page this is a no-op), then main opens it.
 */
function showMeAround(): void {
  requestClose()
  startTour()
}
