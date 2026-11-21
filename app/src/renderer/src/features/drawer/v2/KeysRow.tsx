/**
 * Feature: drawer (v2, A1). The panel's quiet keys line (Les-Anatomy "Keys"): Esc hide, the launcher key "ask miyagi
 * anything", and on the right Back and Voice, which moved here from the shortcut bar (decision 3; the bar hides while
 * the panel is open). Every keycap comes from bridge.platform.keys (core Keycap); a key the platform lacks drops out.
 * Back and Voice show their keys in their tooltips (no room for four keycaps in 320 px).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { ArrowLeft, AudioLines } from 'lucide-react'
import { bridge } from '../../../bridge'
import { triggerShortcut } from '../../../core/shortcuts'
import { copy, fill, radius2, type2 } from '../../../core/theme'
import { pressMotion } from '../../../core/ui/motion'
import { Keycap, keyLabel } from '../../../core/ui/Keycap'
import { useVoice } from '../../voice/store'
import { tone } from './ui'

/**
 * Room for "ask miyagi anything" only beside a short key (the mockup's two-glyph key). ⌥Space or Ctrl⇧Space plus Back
 * and Voice leave about 60 px, so those read "ask miyagi" and the row never truncates.
 */
const SHORT_KEY = 3

export function KeysRow({ onHide, backDisabled }: { onHide: () => void; backDisabled?: boolean }): ReactNode {
  const voiceOn = useVoice((v) => v.on)
  const launch = keyLabel('launcher')
  const askLabel = launch && launch.length > SHORT_KEY ? copy.ask : copy.launcherPlaceholder
  const keys = bridge.platform.keys
  return (
    <div data-part="panel-keys" className="flex shrink-0 items-center gap-[16px]" style={{ padding: '0 20px 16px', fontSize: type2.xs, color: tone.label }}>
      <div className="flex min-w-0 flex-1 items-center gap-[16px]">
        {keyLabel('dismiss') && (
          <button type="button" className="flex shrink-0 cursor-pointer items-center gap-[6px]" onMouseDown={(e) => e.preventDefault()} onClick={onHide}>
            <Keycap k="dismiss" size="sm" />
            <span>hide</span>
          </button>
        )}
        {launch && (
          <button type="button" className="flex min-w-0 cursor-pointer items-center gap-[6px]" onMouseDown={(e) => e.preventDefault()} onClick={() => bridge.emit('launcher:toggle')}>
            <Keycap k="launcher" size="sm" />
            <span className="truncate">{askLabel}</span>
          </button>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-[4px]">
        <IconKey label="Back" keyText={keys.back} disabled={backDisabled} onClick={() => triggerShortcut('back')}>
          <ArrowLeft size={14} strokeWidth={1.8} aria-hidden />
        </IconKey>
        <IconKey label={voiceOn ? 'Voice on' : 'Voice'} keyText={keys.voice_toggle} pressed={voiceOn} onClick={() => triggerShortcut('voice_toggle')}>
          <AudioLines size={14} strokeWidth={1.8} aria-hidden />
        </IconKey>
      </div>
    </div>
  )
}

function IconKey({ label, keyText, pressed, disabled, onClick, children }: { label: string; keyText?: string; pressed?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }): ReactNode {
  const tip = keyText ? `${label} (${keyText})` : label
  return (
    <motion.button
      type="button"
      data-key-button={label.toLowerCase()}
      aria-label={tip}
      aria-pressed={pressed}
      title={tip}
      disabled={disabled}
      // Polish: the core hover tint and press dip (.mg-press, pressMotion) instead of a Tailwind background hover.
      className="mg-press grid h-[28px] w-[28px] cursor-pointer place-items-center disabled:cursor-default"
      style={{
        borderRadius: radius2.control,
        background: pressed ? fill.navActive : undefined,
        color: pressed ? tone.text : tone.label,
        opacity: disabled ? 0.4 : 1
      }}
      {...pressMotion(disabled)}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}
