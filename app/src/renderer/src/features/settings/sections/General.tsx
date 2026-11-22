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
import { useEffect, type ReactNode } from 'react'
import { VOICE_ENABLED } from '../../../../../common/flags'
import type { IslandPlace } from '../../../../../common/notch'
import { useLesson } from '../../../core/lesson'
import { setPrefs, usePrefs, type Appearance } from '../../../core/prefs'
import { bridge } from '../../../bridge'
import { useNotchInfo } from '../../../core/notchInfo'
import { openOnboarding } from '../../../core/surfaces'
import { startTour } from '../../tips/tourStore'
import { QuietButton, Segmented, StatusGlyph, Toggle } from '../../../core/ui/atoms'
import { color, copy, type2 } from '../../../core/theme'
import type { HealthItem } from '../../../../../../../shared/contracts/events'
import { PushToTalk } from '../../ptt/SettingsRows'
import { useHealth } from '../permissions'
import { Group, OnWord, PageHeader, Row } from '../ui'

const APPEARANCES: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'Match system' },
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' }
]

const PLACES: { value: IslandPlace; label: string }[] = [
  { value: 'notch', label: 'In the notch' },
  { value: 'below', label: 'Below the menu bar' }
]

/** Where the island lives. macOS only; while Boring Notch is running it has the notch, so the pill sits below the bar. */
function IslandRow(): ReactNode {
  const place = usePrefs((s) => s.island?.place ?? 'notch')
  const boring = useNotchInfo((s) => !!s.notch?.boringNotch)
  const mac = bridge.platform.os === 'mac'
  // Ask main to look for Boring Notch now (the cached answer can be seconds old), when this opens, when the window is
  // focused again, and every 2 s while it is believed to run, so the caption and the island follow its quitting.
  useEffect(() => {
    if (!mac) return
    const look = (): void => void bridge.invoke('notch:recheck').catch(() => undefined)
    look()
    window.addEventListener('focus', look)
    const t = boring ? setInterval(look, 2000) : undefined
    return () => {
      window.removeEventListener('focus', look)
      if (t) clearInterval(t)
    }
  }, [mac, boring])
  if (!mac) return null
  return (
    <Row
      label="Island"
      caption={
        boring
          ? place === 'notch'
            ? 'Boring Notch is using the notch, so miyagi sits below the menu bar. It moves into the notch when you quit it.'
            : 'Boring Notch is using the notch. Quit it to put miyagi there.'
          : 'Where miyagi sits at the top of the screen.'
      }
      right={<Segmented label="Island" options={PLACES} value={place} onChange={(p) => setPrefs({ island: { place: p } })} />}
    />
  )
}

export function General({ live }: { live: boolean }): ReactNode {
  const appearance = usePrefs((s) => s.appearance)
  const voiceOnStart = usePrefs((s) => s.voiceOnStart)
  const launchAtLogin = usePrefs((s) => s.launchAtLogin)
  const health = useHealth(live)
  const inLesson = useLesson((s) => s.connected && !!s.lesson && !!s.stepId)

  return (
    <>
      <PageHeader title="General" caption="Changes save as you make them." />

      <Group label="Look and startup">
        <Row
          label="Appearance"
          caption={copy.appearanceCaption}
          right={<Segmented label="Appearance" options={APPEARANCES} value={appearance} onChange={(a) => setPrefs({ appearance: a })} />}
        />
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

      <WorksWith health={health} inLesson={inLesson} />

      <Group label="Setup">
        <Row
          icon={Wrench}
          label={`Set up ${copy.name}`}
          caption="Check permissions and VS Code again."
          right={<QuietButton label="Open setup" onClick={() => void openOnboarding()} />}
        />
        <Row icon={Compass} label="Show me around" caption="A short tour of the pill and the launcher." right={<QuietButton label="Start" onClick={() => startTour()} />} />
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
