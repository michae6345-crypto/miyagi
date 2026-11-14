/**
 * Bottom shortcut bar: "Ask Miyagi" + Back / Explain / Diagram / Show me / Hint / Voice.
 * Only visible during a lesson. Sits 24px above the dock / taskbar.
 * Options wear their pastel tile (theme.actionTone, the same color as their buttons everywhere):
 * Explain / Diagram sky, Show me lilac, Hint pink. Back and Voice are chrome: neutral tiles (Voice on = white).
 * The pressed option's glyph becomes a spinner while the engine thinks (never looks dead).
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { AudioLines, Lightbulb, MessageSquareText, RotateCcw, SquarePlay, Waypoints, type LucideIcon } from 'lucide-react'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson, useThinking } from '../../core/lesson'
import { triggerShortcut, usePressed, type ActionShortcut } from '../../core/shortcuts'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { actionTone, color, fill, shadow, spring, type OptionAction } from '../../core/theme'
import { useDiagram } from '../diagrams/store'
import { useVoice } from '../voice/store'

type Btn = { kind: ActionShortcut; label: string; icon: LucideIcon }

const BUTTONS: Btn[] = [
  { kind: 'back', label: 'Back', icon: RotateCcw },
  { kind: 'explain', label: 'Explain', icon: MessageSquareText },
  { kind: 'diagram', label: 'Diagram', icon: Waypoints },
  { kind: 'show_me', label: 'Show me', icon: SquarePlay },
  { kind: 'hint', label: 'Hint', icon: Lightbulb },
  { kind: 'voice_toggle', label: 'Voice', icon: AudioLines }
]

export const BAR_HEIGHT = 88

/** The options among the buttons (the rest is chrome). */
const toneOf = (kind: ActionShortcut): string | undefined => (kind in actionTone ? actionTone[kind as OptionAction] : undefined)


export function ShortcutBar({ bottom }: { bottom: number }): ReactNode {
  const on = useLesson((x) => !!x.lesson)
  const diagramOpen = useDiagram((d) => d.open)
  const voice = useVoice(useShallow((v) => ({ on: v.on, speaking: v.speaking })))
  const s = { on, diagramOpen, voiceOn: voice.on, speaking: voice.speaking }
  const [pressed, setPressed] = useState<string>()
  const thinking = useThinking()
  const sent = usePressed((p) => p.kind)

  // Any shortcut (global key, click, stage key): animate the matching button. Never claims it.
  useEffect(
    () =>
      onUi('shortcut', (kind) => {
        setPressed(kind as string)
        setTimeout(() => setPressed(undefined), 90)
      }),
    []
  )

  return (
    <AnimatePresence>
      {s.on && (
        <motion.div
          className="pointer-events-none absolute inset-x-0 flex justify-center"
          style={{ bottom }}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={spring}
        >
          <div
            data-hit
            className="pointer-events-auto flex items-center gap-[2px] rounded-[26px] border p-[8px]"
            style={{ height: BAR_HEIGHT, background: color.glass, borderColor: color.hairline, boxShadow: shadow, backdropFilter: 'blur(30px) saturate(1.4)' }}
          >
            <button
              className="mr-[6px] flex h-[48px] w-[204px] cursor-pointer items-center gap-[9px] whitespace-nowrap rounded-[24px] border pl-[16px] pr-[8px] text-left"
              style={{ background: fill.field, borderColor: fill.fieldBorder, color: color.label }}
              onClick={() => bridge.emit('launcher:toggle')}
            >
              <MiyagiMark size={15} />
              <span className="flex-1 text-[15px]">Ask Miyagi</span>
              <Kbd>{bridge.platform.keys.launcher}</Kbd>
            </button>
            <div className="mx-[4px] h-[40px] w-px" style={{ background: fill.rule }} />
            {BUTTONS.map(({ kind, label, icon: Icon }) => {
              const lit = kind === 'diagram' && s.diagramOpen
              const voiceOn = kind === 'voice_toggle' && s.voiceOn
              const tone = toneOf(kind)
              const busy = thinking && sent === kind
              // Tile: the option's pastel with an ink glyph; chrome is a neutral tile (Voice on: white, like every toggle).
              const tile = tone ? { background: tone, color: color.onAccent } : voiceOn ? { background: color.accent, color: color.onAccent } : { background: fill.tile, color: color.text }
              return (
                <motion.button
                  key={kind}
                  className="flex h-[72px] w-[84px] cursor-pointer flex-col items-center justify-center rounded-[16px]"
                  animate={{ scale: pressed === kind ? 0.94 : 1, backgroundColor: lit ? fill.button : fill.clear }}
                  whileHover={{ backgroundColor: fill.field }}
                  whileTap={{ scale: 0.94 }}
                  transition={{ duration: 0.09 }}
                  onClick={() => triggerShortcut(kind)}
                >
                  <span className="grid h-[30px] w-[30px] place-items-center rounded-[9px]" style={tile}>
                    {busy ? <Spinner size={14} c={tile.color} /> : voiceOn && s.speaking ? <Equalizer /> : <Icon size={16} strokeWidth={1.8} />}
                  </span>
                  <span className="mt-[6px] text-[12.5px] leading-none" style={{ color: color.text }}>
                    {label}
                  </span>
                  <span className="mt-[4px] text-[11px] leading-none" style={{ color: color.faint }}>
                    {bridge.platform.keys[kind]}
                  </span>
                </motion.button>
              )
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Equalizer(): ReactNode {
  return (
    <span className="flex h-[16px] items-end gap-[2.5px]">
      {[0, 1, 2].map((i) => (
        <motion.i
          key={i}
          className="block w-[2.5px] rounded-full"
          style={{ background: color.onAccent }}
          animate={{ height: [5, 14, 8, 12, 5] }}
          transition={{ repeat: Infinity, duration: 0.9, delay: i * 0.15 }}
        />
      ))}
    </span>
  )
}
