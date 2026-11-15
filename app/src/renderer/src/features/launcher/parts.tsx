/**
 * Feature: launcher. Small pieces of the panel: the staggered section entrance, the chips, and the
 * footer items (one keycap style; hints keycap first, "esc Close"). The primary action is the brand's button when it
 * can act: white on the dark panel with ink text (color.accent / color.onAccent), label then keycap; otherwise a quiet label.
 *
 * Colors are set inline on buttons because they animate (hover, enabled ↔ disabled).
 */
import { motion, useReducedMotion, type HTMLMotionProps } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { GraduationCap, MessageCircleQuestion, Play, Presentation, Square, type LucideIcon } from 'lucide-react'
import { bridge } from '../../bridge'
import { color, fill, spring } from '../../core/theme'

/** One section of the panel settling into place a beat after the one above it. */
export function Rise({ i, children, className = '' }: { i: number; children: ReactNode; className?: string }): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.07 + i * 0.04
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ y: { ...spring, delay }, opacity: { duration: 0.2, delay, ease: 'easeOut' } }}
    >
      {children}
    </motion.div>
  )
}

/**
 * A topic suggestion chip: always a quiet neutral chip. Topics are not options, so they never take the action pastels
 * (Michael's audit A18). A topic is only the "what": a click puts it in the field, and the two ways to learn it come
 * up with the default highlighted (review A18: a topic click no longer starts a video search at once).
 * Colors are inline because they animate on hover.
 */
export function Chip({ icon: I, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] pr-[13px] text-[13px]"
      style={{ backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText }}
      whileHover={{ backgroundColor: fill.chipHover, color: color.text }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.faint }} />
      {label}
    </motion.button>
  )
}

/**
 * How the learner wants to learn the topic they typed (Michael, "two ways to learn"), plus "Demo": the staged
 * neural-net lesson for any topic (learn {mode:"demo"}, the engine's stage.py), for presenting.
 */
export type How = 'video' | 'lesson' | 'demo'
/** Tab's order over the chips. */
export const HOWS: How[] = ['video', 'lesson', 'demo']

/**
 * The ways' names: the chips, the footer's primary and its key hint all use these (Michael's review A18). Demo's
 * primary says "Start demo" (a bare "Demo" button doesn't say what Enter does); "Demo" itself is only on its chip.
 */
export const HOW_LABEL: Record<How, string> = { video: 'Watch a video', lesson: 'Just teach me', demo: 'Demo' }

/**
 * A chip that acts on the press, not the release (Michael's desktop test 5: a click on "Just teach me" closed the
 * launcher and sent nothing, while ⌘Return started the lesson). Between press and release the launcher can be told to
 * close (a focus change during the press reaches main's blur handler, which sends launcher:close), and the click then
 * found the panel already closing. Acting on pointerdown starts first, exactly like the keys; the click that follows
 * is skipped. A click with no press before it (assistive tech) still acts. The caret stays in the field.
 */
function usePress<T>(onPick: (v: T) => void): (v: T) => Pick<HTMLMotionProps<'button'>, 'onPointerDown' | 'onMouseDown' | 'onClick'> {
  /** The chip a press already picked, so its click doesn't act a second time. */
  const pressed = useRef<T | undefined>(undefined)
  return (v) => ({
    onPointerDown: (e) => {
      if (e.button !== 0) return
      pressed.current = v
      onPick(v)
    },
    onMouseDown: (e) => e.preventDefault(),
    onClick: () => {
      const skip = pressed.current === v
      pressed.current = undefined
      if (!skip) onPick(v)
    }
  })
}

/**
 * The ways to learn, under the query: "Watch a video" (search, preflight, gated player), "Just teach me" (no video: a
 * text lesson over the full-screen editor) and "Demo" (the staged neural-net lesson, for presenting).
 *
 * One model (Michael's review A18): they are buttons. A click (the press, see usePress) starts that way at once; Enter
 * starts the highlighted one, Tab / Shift+Tab move the highlight over all three (HOWS), ⌘/Ctrl+Enter is always "Just
 * teach me". The highlighted one is the default for what's typed (the launcher picks it: "Just teach me" for a goal
 * that reads like building something, else "Watch a video", never Demo), and the footer's primary carries its name.
 * Monochrome chrome, not pastel options and not a second white primary: the highlighted one is a lit chip (brighter
 * fill, ring border, full-white text), the others quiet chips. No keycaps on the chips: each key is shown once, in the
 * footer (Michael's audit A19).
 */
export function HowChoice({ how, onPick }: { how: How; onPick: (h: How) => void }): ReactNode {
  const options: { id: How; Icon: LucideIcon }[] = [
    { id: 'video', Icon: Play },
    { id: 'lesson', Icon: GraduationCap },
    { id: 'demo', Icon: Presentation }
  ]
  const press = usePress(onPick)
  const mod = bridge.platform.os === 'mac' ? 'Meta' : 'Control'
  return (
    <div className="flex flex-wrap gap-[8px]" role="group" aria-label="How do you want to learn this?">
      {options.map(({ id, Icon }) => {
        const on = id === how
        return (
          <motion.button
            key={id}
            type="button"
            tabIndex={-1}
            data-how={id}
            data-default={on || undefined}
            aria-keyshortcuts={on ? 'Enter' : id === 'lesson' ? `${mod}+Enter` : undefined}
            className="flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] pr-[13px] text-[13px] font-medium"
            initial={false}
            animate={
              on
                ? { backgroundColor: fill.chipHover, borderColor: fill.ring, color: color.text }
                : { backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText }
            }
            whileHover={on ? undefined : { backgroundColor: fill.chipHover, color: color.text }}
            whileTap={{ scale: 0.97 }}
            transition={{ duration: 0.14 }}
            {...press(id)}
          >
            <Icon size={13} strokeWidth={1.8} className="shrink-0" />
            {HOW_LABEL[id]}
          </motion.button>
        )
      })}
    </div>
  )
}

/**
 * The ask panel's suggested questions about the current step (Michael's review A11; see questions.ts). The same model
 * as the two ways: a question is a whole request, so a click (its press, usePress) asks it at once; the field shows it
 * until the answer card arrives. Quiet neutral chips like the topics: the white "Ask" stays the one primary, and the
 * pastel options (Explain / Hint …) stay in the bar.
 */
export function QuestionChips({ questions, onPick }: { questions: string[]; onPick: (q: string) => void }): ReactNode {
  const press = usePress(onPick)
  return (
    <div className="flex flex-wrap gap-[8px]" role="group" aria-label="Suggested questions">
      {questions.map((q) => (
        <motion.button
          key={q}
          type="button"
          tabIndex={-1}
          data-question
          title={q}
          className="flex h-[30px] min-w-0 max-w-full cursor-pointer items-center gap-[7px] rounded-full border pl-[11px] pr-[13px] text-[13px]"
          style={{ backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText }}
          whileHover={{ backgroundColor: fill.chipHover, color: color.text }}
          whileTap={{ scale: 0.97 }}
          transition={{ duration: 0.12 }}
          {...press(q)}
        >
          <MessageCircleQuestion size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.faint }} />
          <span className="truncate">{q}</span>
        </motion.button>
      ))}
    </div>
  )
}

/**
 * The launcher's one keycap (Michael's audit A20): 22px tall, round, 12px glyph, in every footer item. On the dark
 * panel it is the core keycap's look (fill.key / fill.keyText); on the white primary, ink at 10% (brand).
 */
function Keycap({ children, onAccent = false }: { children: ReactNode; onAccent?: boolean }): ReactNode {
  return (
    <span
      className="inline-flex h-[22px] min-w-[24px] shrink-0 items-center justify-center rounded-full px-[6px] text-[12px] font-medium"
      style={onAccent ? { background: fill.onAccentKey, color: color.onAccent } : { background: fill.key, color: fill.keyText }}
    >
      {children}
    </span>
  )
}

/** A passive key hint in the footer, keycap first: "↑↓ Choose", "esc Close". Not clickable. color.label, so it reads (A19). */
export function Hint({ label, keycap }: { label: string; keycap: string }): ReactNode {
  return (
    <span className="flex h-[30px] shrink-0 items-center gap-[7px] whitespace-nowrap pl-[4px] pr-[10px] text-[13px]" style={{ color: color.label }}>
      <Keycap>{keycap}</Keycap>
      {label}
    </span>
  )
}

/**
 * A footer action. `strong` = the primary slot: label then keycap, the white button when it can act (one per surface),
 * else a faint label. Otherwise a quiet, clickable hint: keycap first like Hint ("⇥ New lesson"), no fill until hovered.
 */
export function Action({
  label,
  keycap,
  enabled,
  strong = false,
  onClick
}: {
  label: string
  keycap: string
  enabled: boolean
  strong?: boolean
  onClick: () => void
}): ReactNode {
  const solid = strong && enabled
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      disabled={!enabled}
      className={`flex h-[30px] shrink-0 cursor-pointer items-center whitespace-nowrap rounded-full text-[13px] disabled:cursor-default ${
        strong ? `gap-[8px] pr-[4px] font-medium ${solid ? 'pl-[12px]' : 'pl-[10px]'}` : 'gap-[7px] pl-[4px] pr-[10px]'
      }`}
      initial={false}
      animate={{
        backgroundColor: solid ? color.accent : fill.clear,
        color: solid ? color.onAccent : enabled ? color.label : color.faint
      }}
      whileHover={enabled ? (solid ? { scale: 1.03 } : { backgroundColor: fill.chip, color: color.text }) : undefined}
      whileTap={enabled ? { scale: 0.97 } : undefined}
      transition={{ duration: 0.14 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {strong ? (
        <>
          {label}
          <Keycap onAccent={solid}>{keycap}</Keycap>
        </>
      ) : (
        <>
          <Keycap>{keycap}</Keycap>
          {label}
        </>
      )}
    </motion.button>
  )
}

/**
 * End lesson during a lesson (Michael's desktop test 3, item 8): a small quiet link in the footer, never a row, so a
 * stray Enter or ↓ then Enter can't end a lesson. No key reaches it (not a focus stop, no keycap). Like the bar's End,
 * the first click arms it ("Tap to end", a little brighter) and a second click while armed ends the lesson. Neutral
 * chrome even when armed: the white button stays the one primary (Continue).
 */
export function EndLink({ armed, onClick }: { armed: boolean; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="flex h-[26px] shrink-0 cursor-pointer items-center gap-[6px] whitespace-nowrap rounded-full px-[9px] text-[12px]"
      initial={false}
      animate={armed ? { backgroundColor: fill.chip, color: color.text } : { backgroundColor: fill.clear, color: color.faint }}
      whileHover={{ color: color.text }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.14 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={armed ? 'Click again to end the lesson' : 'End this lesson'}
      data-armed={armed || undefined}
    >
      <Square size={10} strokeWidth={2} className="shrink-0" />
      {armed ? 'Tap to end' : 'End lesson'}
    </motion.button>
  )
}
