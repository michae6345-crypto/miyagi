/**
 * Bottom shortcut bar: "Ask anything" + Back / Explain / Diagram / Show me / Hint / Voice.
 * Only visible during a lesson. Sits 24px above the dock / taskbar.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { AudioLines, Lightbulb, MessageSquareText, RotateCcw, Search, SquarePlay, Waypoints, type LucideIcon } from 'lucide-react'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { triggerShortcut, type ActionShortcut } from '../../core/shortcuts'
import { color, spring } from '../../core/theme'
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


export function ShortcutBar({ bottom }: { bottom: number }): ReactNode {
  const on = useLesson((x) => !!x.lesson)
  const diagramOpen = useDiagram((d) => d.open)
  const voice = useVoice(useShallow((v) => ({ on: v.on, speaking: v.speaking })))
  const s = { on, diagramOpen, voiceOn: voice.on, speaking: voice.speaking }
  const [pressed, setPressed] = useState<string>()

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
            style={{ height: BAR_HEIGHT, background: color.glass, borderColor: color.hairline, boxShadow: '0 20px 60px rgba(0,0,0,.45)', backdropFilter: 'blur(30px) saturate(1.4)' }}
          >
            <button
              className="mr-[6px] flex h-[48px] w-[204px] cursor-pointer items-center gap-[9px] whitespace-nowrap rounded-[24px] border pl-[16px] pr-[8px] text-left"
              style={{ background: 'rgba(255,255,255,.06)', borderColor: 'rgba(255,255,255,.1)' }}
              onClick={() => bridge.emit('launcher:toggle')}
            >
              <Search size={15} className="text-white/55" />
              <span className="flex-1 text-[15px] text-white/55">Ask anything</span>
              <span className="rounded-[7px] px-[7px] py-[3px] text-[11.5px] text-white/55" style={{ background: 'rgba(255,255,255,.1)' }}>
                {bridge.platform.keys.launcher}
              </span>
            </button>
            <div className="mx-[4px] h-[40px] w-px" style={{ background: 'rgba(255,255,255,.1)' }} />
            {BUTTONS.map(({ kind, label, icon: Icon }) => {
              const lit = (kind === 'diagram' && s.diagramOpen) || (kind === 'voice_toggle' && s.voiceOn)
              const blue = kind === 'voice_toggle' && s.voiceOn
              return (
                <motion.button
                  key={kind}
                  className="flex h-[72px] w-[84px] cursor-pointer flex-col items-center justify-center rounded-[16px]"
                  animate={{ scale: pressed === kind ? 0.94 : 1, background: lit ? 'rgba(255,255,255,.09)' : 'rgba(255,255,255,0)' }}
                  whileHover={{ background: 'rgba(255,255,255,.06)' }}
                  whileTap={{ scale: 0.94 }}
                  transition={{ duration: 0.09 }}
                  onClick={() => triggerShortcut(kind)}
                >
                  {blue && s.speaking ? <Equalizer /> : <Icon size={19} strokeWidth={1.6} style={{ color: blue ? color.accent : lit ? color.accent : '#fff' }} />}
                  <span className="mt-[5px] text-[13px] leading-none text-white/90">{label}</span>
                  <span className="mt-[5px] text-[11px] leading-none text-white/42">{bridge.platform.keys[kind]}</span>
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
    <span className="flex h-[19px] items-end gap-[3px]">
      {[0, 1, 2].map((i) => (
        <motion.i
          key={i}
          className="block w-[3px] rounded-full"
          style={{ background: color.accent }}
          animate={{ height: [6, 17, 9, 15, 6] }}
          transition={{ repeat: Infinity, duration: 0.9, delay: i * 0.15 }}
        />
      ))}
    </span>
  )
}
