/**
 * Feature: drawer (v2, A1). The panel's quiet keys line (Les-Anatomy "Keys"): Esc hide, the launcher key "ask miyagi
 * anything", and on the right "Back" with its keycap (persona QA: a bare ← read as nothing), then Voice when it is on.
 * Every keycap comes from bridge.platform.keys (core Keycap); a key the platform lacks drops out. Each item dims a
 * touch on hover and dips when pressed, like the rest of the panel's chrome.
 */
import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import { AudioLines } from 'lucide-react'
import { bridge } from '../../../bridge'
import { triggerShortcut } from '../../../core/shortcuts'
import { copy, fill, radius2, type2 } from '../../../core/theme'
import { Keycap, keyLabel, type KeyName } from '../../../core/ui/Keycap'
import { VOICE_ENABLED } from '../../../../../common/flags'
import { useVoice } from '../../voice/store'
import { Tip, tone } from './ui'

/**
 * Room for "ask miyagi anything" only beside a short key (the mockup's two-glyph key). ⌥Space or Ctrl⇧Space plus Back
 * leave about 60 px, so those read "ask miyagi" and the row never truncates.
 */
const SHORT_KEY = 3

export function KeysRow({ onHide, backDisabled }: { onHide: () => void; backDisabled?: boolean }): ReactNode {
  const voiceOn = useVoice((v) => v.on)
  const launch = keyLabel('launcher')
  const askLabel = launch && launch.length > SHORT_KEY ? copy.ask : copy.launcherPlaceholder
  const keys = bridge.platform.keys
  return (
    <div data-part="panel-keys" className="flex shrink-0 items-center gap-[8px]" style={{ padding: '0 12px 12px 14px', fontSize: type2.xs, color: tone.label }}>
      <div className="flex min-w-0 flex-1 items-center gap-[4px]">
        {keyLabel('dismiss') && <KeyItem k="dismiss" label="hide" onClick={onHide} aria="Hide the lesson panel" />}
        {launch && <KeyItem k="launcher" label={askLabel} onClick={() => bridge.emit('launcher:toggle')} aria="Ask miyagi" grow />}
      </div>
      <div className="flex shrink-0 items-center gap-[4px]">
        <Tip label="Previous step" k="back" side="top">
          <KeyItem k="back" label="Back" onClick={() => triggerShortcut('back')} disabled={backDisabled} aria="Back to the previous step" keyFirst={false} />
        </Tip>
        {/* Voice is off for now (common/flags): no button, no keycap. */}
        {VOICE_ENABLED && (
          <motion.button
            type="button"
            data-key-button="voice"
            aria-label={keys.voice_toggle ? `Voice (${keys.voice_toggle})` : 'Voice'}
            aria-pressed={voiceOn}
            className="grid h-[28px] w-[28px] cursor-pointer place-items-center"
            style={{ borderRadius: radius2.control, background: voiceOn ? fill.navActive : undefined, color: voiceOn ? tone.text : tone.label }}
            whileHover={{ backgroundColor: fill.chipHover }}
            whileTap={{ scale: 0.92 }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => triggerShortcut('voice_toggle')}
          >
            <AudioLines size={14} strokeWidth={1.8} aria-hidden />
          </motion.button>
        )}
      </div>
    </div>
  )
}

/** "[Esc] hide", "[⌥Space] ask miyagi", "Back [⌃⌥←]": a 28 px target with a hover tint and a press dip. */
function KeyItem({
  k,
  label,
  onClick,
  disabled,
  aria,
  grow,
  keyFirst = true
}: {
  k: KeyName
  label: string
  onClick: () => void
  disabled?: boolean
  aria: string
  grow?: boolean
  keyFirst?: boolean
}): ReactNode {
  const key = keyLabel(k)
  return (
    <motion.button
      type="button"
      data-key-button={k}
      aria-label={key ? `${aria} (${key})` : aria}
      disabled={disabled}
      className={`flex h-[28px] cursor-pointer items-center gap-[6px] px-[6px] disabled:cursor-default ${grow ? 'min-w-0' : 'shrink-0'}`}
      style={{ borderRadius: radius2.control, color: tone.label, opacity: disabled ? 0.4 : 1 }}
      whileHover={disabled ? undefined : { backgroundColor: fill.chipHover, color: tone.text }}
      whileTap={disabled ? undefined : { scale: 0.96 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {keyFirst && <Keycap k={k} size="sm" />}
      <span className={grow ? 'truncate' : undefined}>{label}</span>
      {!keyFirst && <Keycap k={k} size="sm" />}
    </motion.button>
  )
}
