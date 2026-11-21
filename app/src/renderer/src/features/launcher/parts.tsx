/**
 * Feature: launcher. Small pieces of the panel: the staggered section entrance, the chips, and the
 * footer items (one keycap style; hints keycap first, "esc Close"). The primary action is the brand's button when it
 * can act: white on the dark panel with ink text (color.accent / color.onAccent), label then keycap; otherwise a quiet label.
 *
 * Colors are set inline on buttons because they animate (hover, enabled ↔ disabled).
 */
import { AnimatePresence, motion, useReducedMotion, type HTMLMotionProps } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { ArrowRight, GraduationCap, Play, Presentation, Square, type LucideIcon } from 'lucide-react'
import { bridge } from '../../bridge'
import { color, fill, radius2, spring } from '../../core/theme'
import { Keycap as CoreKeycap, keyLabel as coreKeyLabel, type KeyName } from '../../core/ui/Keycap'
import { demoEnabled, navKey } from './keys'
import { ease, enter, fade, staggerDelay } from '../../core/ui/motion'

/** One section of the panel settling into place a beat after the one above it. */
export function Rise({ i, children, className = '' }: { i: number; children: ReactNode; className?: string }): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.07 + i * 0.04
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={enter(delay)}
    >
      {children}
    </motion.div>
  )
}

/**
 * How the learner wants to learn the topic they typed (Michael, "two ways to learn"), plus "Demo": the staged
 * neural-net lesson for any topic (learn {mode:"demo"}, the engine's stage.py), for presenting. Demo is offered only
 * behind the dev / stage flag (keys.demoEnabled): a first-timer can't tell what it does (persona QA).
 */
export type How = 'video' | 'lesson' | 'demo'
/** Tab's order over the chips: every way, Demo last and only when the flag is on. */
export const HOWS: How[] = demoEnabled ? ['video', 'lesson', 'demo'] : ['video', 'lesson']

/**
 * The ways' names: the chips, the footer's primary and its key hint all use these (Michael's review A18). Demo's
 * primary says "Start demo" (a bare "Demo" button doesn't say what Enter does); "Demo" itself is only on its chip.
 */
export const HOW_LABEL: Record<How, string> = { video: 'Watch a video', lesson: 'Just teach me', demo: 'Demo' }

/** One line under the chips: what Enter does with the highlighted way (persona QA: the chips had no explanation). */
export const HOW_DESC: Record<How, string> = {
  video: 'Finds a video and pauses it at each step',
  lesson: 'Steps only, no video',
  demo: 'Plays the staged demo lesson, for presenting'
}

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

/** The press dip: 0.97 on the house spring (UI-POLISH-SPEC 3), so a fast click still completes it. */
export const PRESS = { scale: 0.97, transition: spring }

/**
 * The ways to learn, under the query: "Watch a video" (search, preflight, gated player), "Just teach me" (no video: a
 * text lesson over the full-screen editor) and, behind the flag, "Demo" (the staged neural-net lesson, for presenting).
 *
 * One model (Michael's review A18): they are buttons. A click (the press, see usePress) starts that way at once; Enter
 * starts the highlighted one, Tab / Shift+Tab move the highlight over them (HOWS), ⌘/Ctrl+Enter is always "Just
 * teach me". The highlighted one is the default for what's typed (the launcher picks it: "Just teach me" for a goal
 * that reads like building something, else "Watch a video", never Demo), and the footer's primary carries its name.
 * Under the chips, one line says what Enter will do with the highlighted way (HOW_DESC); it crossfades as Tab moves.
 * Monochrome chrome, not pastel options and not a second white primary: the highlighted one is a lit chip (brighter
 * fill, ring border, full-white text), the others quiet chips. No keycaps on the chips: each key is shown once, in the
 * footer (Michael's audit A19).
 */
export function HowChoice({ how, onPick }: { how: How; onPick: (h: How) => void }): ReactNode {
  const all: { id: How; Icon: LucideIcon }[] = [
    { id: 'video', Icon: Play },
    { id: 'lesson', Icon: GraduationCap },
    { id: 'demo', Icon: Presentation }
  ]
  const options = all.filter((o) => HOWS.includes(o.id))
  const press = usePress(onPick)
  const reduce = useReducedMotion()
  const mod = bridge.platform.os === 'mac' ? 'Meta' : 'Control'
  return (
    <div>
      <div className="flex flex-wrap gap-[8px]" role="group" aria-label="How do you want to learn this?">
        {options.map(({ id, Icon }, i) => {
          const on = id === how
          return (
            <motion.button
              key={id}
              type="button"
              tabIndex={-1}
              data-how={id}
              data-default={on || undefined}
              aria-pressed={on}
              aria-keyshortcuts={on ? 'Enter' : id === 'lesson' ? `${mod}+Enter` : undefined}
              className="flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] pr-[13px] text-[13px] font-medium"
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
              animate={{
                opacity: 1,
                y: 0,
                ...(on
                  ? { backgroundColor: fill.chipHover, borderColor: fill.ring, color: color.text }
                  : { backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText })
              }}
              whileHover={on ? undefined : { backgroundColor: fill.chipHover, color: color.text }}
              whileTap={PRESS}
              transition={{ ...fade.tint, y: { ...spring, delay: staggerDelay(i) }, opacity: { ...fade.in, delay: staggerDelay(i) } }}
              {...press(id)}
            >
              <Icon size={13} strokeWidth={1.8} className="shrink-0" />
              {HOW_LABEL[id]}
            </motion.button>
          )
        })}
      </div>
      {/* What Enter will do: one quiet line, crossfading (a 4 px rise) as the highlight moves. */}
      <div className="relative mt-[10px] h-[18px] overflow-hidden" aria-live="polite">
        <AnimatePresence initial={false}>
          <motion.div
            key={how}
            data-how-desc={how}
            className="absolute inset-x-0 top-0 truncate pl-[2px] text-[12.5px] leading-[18px]"
            style={{ color: color.label }}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
            transition={{ y: spring, opacity: fade.in }}
          >
            {HOW_DESC[how]}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}

/**
 * Home-Launcher's section label ("From your link", "Continue", "Try asking", "Ready to run"): 11 px, semibold,
 * uppercase, the label gray. Words only where the mockup has them; the rows under it carry the rest.
 */
export function SectionLabel({ children, first = false }: { children: ReactNode; first?: boolean }): ReactNode {
  return (
    <div
      data-section-label
      className={`px-[24px] pb-[8px] text-[11px] font-semibold uppercase tracking-[0.04em] ${first ? 'pt-[8px]' : 'pt-[16px]'}`}
      style={{ color: color.label }}
    >
      {children}
    </div>
  )
}

/** A "Try asking" line is this tall (fixed, so the list's one highlight can glide between lines). */
export const ASK_H = 44

/**
 * One "Try asking" line (Home-Launcher): an arrow and the words, 44 high. No fill of its own: the list draws one
 * highlight (the hover tint, never a hue) under the active line, which the arrow keys and the pointer both move. The
 * active line shows the Enter keycap: Enter runs it. Lines rise in a beat apart; a press dips on the house spring.
 */
function AskLine({
  text,
  index,
  active,
  data,
  onHover,
  ...rest
}: { text: string; index: number; active: boolean; data?: Record<string, true>; onHover?: () => void } & Pick<
  HTMLMotionProps<'button'>,
  'onPointerDown' | 'onMouseDown' | 'onClick'
>): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.1 + index * 0.04
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      title={text}
      {...data}
      data-active={active || undefined}
      aria-selected={active}
      role="option"
      className="relative flex w-full min-w-0 cursor-pointer items-center gap-[16px] rounded-[12px] px-[16px] text-left text-[14px]"
      style={{ height: ASK_H, color: color.text }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={PRESS}
      transition={enter(delay)}
      onMouseMove={onHover}
      {...rest}
    >
      <ArrowRight size={16} strokeWidth={1.8} className="shrink-0" style={{ color: active ? color.text : color.label }} />
      <span className="min-w-0 flex-1 truncate">{text}</span>
      <motion.span className="shrink-0" initial={false} animate={{ opacity: active ? 1 : 0 }} transition={fade.tint} aria-hidden>
        <NavKey>{navKey('enter')}</NavKey>
      </motion.span>
    </motion.button>
  )
}

/** The one highlight under a list of `count` equal lines (h each), gliding to line `at` on the spring; -1 = hidden. */
export function ListHighlight({ at, count, h }: { at: number; count: number; h: number }): ReactNode {
  const on = at >= 0 && at < count
  return (
    <motion.div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]"
      style={{ height: h, background: fill.highlight }}
      initial={false}
      animate={{ y: Math.max(0, Math.min(count - 1, at)) * h, opacity: on ? 1 : 0 }}
      transition={{ y: spring, opacity: fade.out }}
    />
  )
}

/**
 * Idle "Try asking" (Home-Launcher): example goals, one per line. A topic is only the "what" (review A18): a click, or
 * Enter on the active line, puts it in the field, where the ways to learn it come up with the default highlighted.
 * Never starts anything by itself. `active` = the line the arrow keys are on (-1 = none here).
 */
export function SuggestionRows({
  items,
  active,
  onHover,
  onPick
}: {
  items: string[]
  active: number
  onHover: (i: number) => void
  onPick: (text: string) => void
}): ReactNode {
  return (
    <div className="relative flex flex-col" role="listbox" aria-label="Try asking">
      <ListHighlight at={active} count={items.length} h={ASK_H} />
      {items.map((t, i) => (
        <AskLine
          key={t}
          text={t}
          index={i}
          active={i === active}
          data={{ 'data-suggestion': true }}
          onHover={() => onHover(i)}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onPick(t)}
        />
      ))}
    </div>
  )
}

/**
 * The ask panel's suggested questions about the current step (Michael's review A11; see questions.ts), as "Try asking"
 * lines. A question is a whole request, so a click (its press, usePress) or Enter on the active line asks it at once;
 * the field shows it until the answer card arrives. Neutral lines: the white "Ask" stays the one primary, and the
 * pastel options (Explain / Hint …) stay in the bar.
 */
export function QuestionChips({
  questions,
  active,
  onHover,
  onPick
}: {
  questions: string[]
  active: number
  onHover: (i: number) => void
  onPick: (q: string) => void
}): ReactNode {
  const press = usePress(onPick)
  return (
    <div className="relative flex flex-col" role="listbox" aria-label="Suggested questions">
      <ListHighlight at={active} count={questions.length} h={ASK_H} />
      {questions.map((q, i) => (
        <AskLine key={q} text={q} index={i} active={i === active} data={{ 'data-question': true }} onHover={() => onHover(i)} {...press(q)} />
      ))}
    </div>
  )
}

/**
 * The launcher's keycap for navigation glyphs (↵, ↑↓, ⇥), drawn like core/ui/Keycap (Home-Launcher .kc: 20 high,
 * radius 6, 11 px, a hairline). Global shortcuts and Esc never come through here: they are core Keycaps with the
 * platform's own label (bridge.platform.keys). On the white primary, ink at 10% (brand).
 */
export function NavKey({ children, onAccent = false }: { children: ReactNode; onAccent?: boolean }): ReactNode {
  return (
    <span
      className="inline-flex h-[20px] min-w-[20px] shrink-0 items-center justify-center whitespace-nowrap px-[6px] text-[11px] font-medium"
      style={
        onAccent
          ? { background: fill.onAccentKey, color: color.onAccent, borderRadius: radius2.round }
          : { background: fill.keycap, color: fill.keycapText, boxShadow: `inset 0 0 0 1px ${fill.keycapBorder}`, borderRadius: radius2.keycap }
      }
    >
      {children}
    </span>
  )
}
const Keycap = NavKey

/**
 * The platform's modifier for ⌘↵ / Ctrl↵ ("Just teach me"), read off its own Settings key (⌘, on a Mac, Ctrl+, on
 * Windows) so no key label is typed by hand. Core request: a `teach` key name in platform.keys.
 */
export function modKey(): string {
  const s = coreKeyLabel('settings') ?? ''
  return s.replace(/\+?,$/, '')
}

/**
 * A passive key hint in the footer, keycap first: "↑↓ Move", "Esc Close". Not clickable. color.label, so it reads
 * (A19). `keyName` renders the platform's own keycap (Esc); `keycap` a navigation glyph.
 */
export function Hint({ label, keycap, keyName }: { label: string; keycap?: string; keyName?: KeyName }): ReactNode {
  return (
    <span className="flex h-[30px] shrink-0 items-center gap-[8px] whitespace-nowrap pl-[4px] pr-[10px] text-[12px]" style={{ color: color.label }}>
      {keyName ? <CoreKeycap k={keyName} size="sm" /> : <Keycap>{keycap}</Keycap>}
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
      whileTap={enabled ? PRESS : undefined}
      transition={{ ...fade.tint, scale: spring }}
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
      whileTap={PRESS}
      transition={{ ...fade.tint, scale: spring }}
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
