/**
 * Feature: ptt. The island's two push-to-talk faces (both on the notch black, neutral tokens only: no hue, no glow).
 *
 *   ListeningPill   pill-sized (34 px). A small ring that breathes while the mic is open, then the live words on ONE line,
 *                   truncated from the LEFT (the newest words stay in view). On release the ring becomes the core
 *                   Spinner for the moment the text is on its way ("Sending"), then the island is at rest again.
 *                   With reduced motion the ring holds still.
 *   AllowCard       the first-use card: "Allow the microphone to ask by voice" with ONE primary button. Pressing the
 *                   chord never raises a system prompt by itself; this explicit Allow does. When the answer was No it
 *                   says so and the button opens the right Privacy pane instead.
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { useInNotch } from '../../core/notchContext'
import { usePrefs } from '../../core/prefs'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { color, duration, ease, pill, type2 } from '../../core/theme'
import { closeCard, declineInputCard, usePtt } from './store'
import { stripWake } from './wake'

/** Fixed, so the pill doesn't change width with every partial. */
export const PILL_W = 300
export const CARD_W = 340

/** The notch's right ear while listening: the same ring, or the spinner once sent. */
export function NotchRing(): ReactNode {
  const sending = usePtt((s) => s.ptt.phase === 'sending')
  return <Ring live={!sending} />
}

function Ring({ live }: { live: boolean }): ReactNode {
  const reduce = useReducedMotion()
  return (
    <span aria-hidden className="relative grid h-[16px] w-[16px] shrink-0 place-items-center">
      {live ? (
        <>
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ boxShadow: `inset 0 0 0 1.5px ${color.text}` }}
            initial={false}
            animate={reduce ? { opacity: 0.35, scale: 1 } : { opacity: [0.55, 0, 0.55], scale: [0.7, 1.25, 0.7] }}
            transition={reduce ? { duration: 0 } : { duration: 1.8, ease: 'easeInOut', repeat: Infinity }}
          />
          <span className="h-[6px] w-[6px] rounded-full" style={{ background: color.text }} />
        </>
      ) : (
        <Spinner size={14} />
      )}
    </span>
  )
}

export function ListeningPill(): ReactNode {
  const { phase, text } = usePtt((s) => s.ptt)
  const sending = phase === 'sending'
  const words = stripWake(text) // "hey miyagi" is not shown: only the question (wake.ts)
  // In the notch the ears carry the ring: the line under it is just the words.
  const inNotch = useInNotch()
  return (
    <div data-ui data-ptt={phase} className="flex items-center gap-[10px]" style={{ width: PILL_W, height: pill.height, padding: '0 16px' }} role="status" aria-live="polite">
      {!inNotch && <Ring live={!sending} />}
      {/* Newest words stay in view: the line is laid out right-to-left so the ellipsis lands on the left; the text itself reads left-to-right. */}
      <span className="block min-w-0 flex-1 overflow-hidden whitespace-nowrap" style={{ direction: 'rtl', textAlign: 'left', textOverflow: 'ellipsis', fontSize: type2.sm, color: words ? color.text : color.label }}>
        <span style={{ direction: 'ltr', unicodeBidi: 'embed' }}>{words || (sending ? 'Sending' : 'Listening')}</span>
      </span>
    </div>
  )
}

const WORDS = {
  mic: { title: 'Allow the microphone to ask by voice', primary: 'Allow' },
  'mic-denied': { title: 'The microphone is off for miyagi', primary: 'Open settings' },
  input: { title: 'Allow keyboard access to hear the shortcut', primary: 'Allow' }
} as const

export function AllowCard(): ReactNode {
  const card = usePtt((s) => s.card) ?? 'mic'
  const perms = usePtt((s) => s.ptt.perms)
  const chord = usePrefs((s) => s.ptt.chord)
  // Allowed from somewhere else (System Settings, the Settings row): the card has nothing left to ask.
  const done = card === 'mic' ? perms.mic === 'granted' && perms.input !== 'denied' : card === 'input' ? perms.input === 'granted' : perms.mic === 'granted'
  useEffect(() => {
    if (done) closeCard()
  }, [done])
  const w = WORDS[card]
  const act = (): void => {
    if (card === 'mic-denied') bridge.invoke('ptt:open-settings', 'mic').catch(() => undefined)
    else if (card === 'input') bridge.invoke('ptt:allow', 'input').catch(() => undefined)
    else bridge.invoke('ptt:allow', perms.input === 'granted' ? 'mic' : 'both').catch(() => undefined)
    closeCard()
  }
  return (
    <motion.div data-ptt-card={card} style={{ padding: '16px 20px 18px' }} initial={false} transition={{ duration: duration.base, ease: ease.out }}>
      <div className="flex items-center gap-[8px]" style={{ fontSize: type2.md, color: color.text, fontWeight: 500 }}>
        {w.title}
      </div>
      <div className="mt-[6px] flex items-center gap-[8px]" style={{ fontSize: type2.xs, color: color.label }}>
        Hold <Keycap k={chord === 'control+option' ? 'ptt_alt' : 'ptt'} size="sm" /> to ask. Speech stays on this Mac.
      </div>
      <div className="mt-[14px] flex items-center justify-end gap-[8px]">
        <QuietButton label="Not now" onClick={card === 'input' ? declineInputCard : closeCard} />
        {/* macOS only asks once: after a No (or a stale grant from an older install) the pane is the way in. */}
        {card === 'input' && <QuietButton label="Open settings" onClick={() => { bridge.invoke('ptt:open-settings', 'input').catch(() => undefined); closeCard() }} />}
        {card === 'mic-denied' && <QuietButton label="Ask again" onClick={() => { bridge.invoke('ptt:allow', 'mic').catch(() => undefined); closeCard() }} />}
        <PrimaryButton label={w.primary} onClick={act} />
      </div>
    </motion.div>
  )
}
