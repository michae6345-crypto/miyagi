/**
 * Feature: ptt. Settings > General rows for push to talk, drawn into General's own groups (neutral chrome, no hue):
 *
 *   Push to talk   toggle, "Hold to ask. Speech stays on this Mac."
 *   Shortcut       Fn + Control (default) or Control + Option (keyboards without Fn); keycaps from bridge.platform.keys
 *   Microphone / Input monitoring   the state from the helper's perm events. Allow raises the macOS prompt (an explicit
 *                  click: mic, then input); when macOS says denied the way back is the Privacy pane (Open settings).
 *
 * Only on macOS with PTT_ENABLED. The rows read the same PttState main broadcasts (store.ts).
 */
import { Keyboard, Mic } from 'lucide-react'
import type { ReactNode } from 'react'
import { PTT_ENABLED } from '../../../../common/flags'
import type { PttChord } from '../../../../common/prefs'
import { bridge } from '../../bridge'
import { setPrefs, usePrefs } from '../../core/prefs'
import { keyLabel } from '../../core/ui/Keycap'
import { QuietButton, Segmented, StatusGlyph, Toggle } from '../../core/ui/atoms'
import { color, type2 } from '../../core/theme'
import { Group, OnWord, Row } from '../settings/ui'
import { usePtt } from './store'

export const pttAvailable = (): boolean => PTT_ENABLED && bridge.platform.os === 'mac'

type Perm = 'granted' | 'denied' | 'undetermined' | 'unknown'

function PermWord({ state, onAllow, pane }: { state: Perm; onAllow: () => void; pane: 'mic' | 'input' }): ReactNode {
  if (state === 'unknown') return null
  if (state === 'granted') return <OnWord />
  return (
    <span className="flex shrink-0 items-center gap-[12px]">
      <span className="flex items-center gap-[8px] whitespace-nowrap" style={{ fontSize: type2.xs, color: color.text }}>
        <StatusGlyph state="notyet" size={12} />
        Not yet
      </span>
      {/* Input monitoring reads "denied" before it was ever asked, so it keeps Allow beside Open settings; a denied microphone only has the pane. */}
      {/* A microphone that reads denied may be a stale grant from an older install: Allow resets miyagi's row and asks again. */}
      <QuietButton label="Allow" onClick={onAllow} />
      {state === 'denied' && <QuietButton label="Open settings" onClick={() => void bridge.invoke('ptt:open-settings', pane).catch(() => undefined)} />}
    </span>
  )
}

/** The Push to talk group for General (null where it doesn't apply). */
export function PushToTalk(): ReactNode {
  const ptt = usePrefs((s) => s.ptt)
  const perms = usePtt((s) => s.ptt.perms)
  const available = usePtt((s) => s.ptt.available)
  if (!pttAvailable()) return null
  const chords: { value: PttChord; label: string }[] = [
    { value: 'fn+control', label: keyLabel('ptt') ?? '' },
    { value: 'control+option', label: keyLabel('ptt_alt') ?? '' }
  ]
  const allow = (which: 'mic' | 'input' | 'both'): void => void bridge.invoke('ptt:allow', which).catch(() => undefined)
  return (
    <Group label="Push to talk">
      <Row
        tight
        icon={Mic}
        label="Push to talk"
        caption="Hold to ask. Speech stays on this Mac."
        right={<Toggle label="Push to talk" on={ptt.enabled} onChange={(v) => setPrefs({ ptt: { ...ptt, enabled: v } })} />}
      />
      {ptt.enabled && (
        <Row
          icon={Keyboard}
          label="Shortcut"
          caption="Use Control and Option if your keyboard has no Fn."
          right={<Segmented label="Push to talk shortcut" options={chords} value={ptt.chord} onChange={(chord) => setPrefs({ ptt: { ...ptt, chord } })} />}
        />
      )}
      {ptt.enabled && ptt.chord === 'fn+control' && (
        <Row label="Fn key" caption="If Fn opens emoji or dictation, set the Globe key to Do Nothing in System Settings, Keyboard." right={null} />
      )}
      {ptt.enabled && !available && perms.input === 'unknown' && <Row label="Listener" caption="Not running. Quit and reopen miyagi to start it." right={null} />}
      {ptt.enabled && <Row label="Microphone" caption="To hear your question." right={<PermWord pane="mic" state={perms.mic} onAllow={() => allow(perms.input === 'granted' ? 'mic' : 'both')} />} />}
      {ptt.enabled && <Row label="Input monitoring" caption="To notice the shortcut in any app." right={<PermWord pane="input" state={perms.input} onAllow={() => allow('input')} />} />}
    </Group>
  )
}
