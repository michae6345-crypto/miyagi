/**
 * Feature: launcher. Small pieces of the panel: the staggered section entrance, the chips, and the
 * footer items (one keycap style; hints keycap first, "esc Close"). The primary action is the brand's button when it
 * can act: white on the dark panel with ink text (color.accent / color.onAccent), label then keycap; otherwise a quiet label.
 *
 * Colors are set inline on buttons because they animate (hover, enabled ↔ disabled).
 */
import { AnimatePresence, motion, useReducedMotion, type HTMLMotionProps } from 'motion/react'
import { useRef, type CSSProperties, type ReactNode } from 'react'
import { GraduationCap, Play, Presentation, Square, type LucideIcon } from 'lucide-react'
import { bridge } from '../../bridge'
import { color, fill, spring, v4, v4c, v4type } from '../../core/theme'
import { keyLabel as coreKeyLabel, type KeyName } from '../../core/ui/Keycap'
import { demoEnabled, navKey } from './keys'
import { ease, enter, fade, staggerDelay } from '../../core/ui/motion'

/** One section of the panel settling into place a beat after the one above it. */
export function Rise({ i, children, className = '', style }: { i: number; children: ReactNode; className?: string; style?: CSSProperties }): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.07 + i * 0.04
  return (
    <motion.div
      className={className}
      style={style}
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
 * Monochrome chrome, not pastel options and not a second white primary: the highlighted one is a lit chip (the v4
 * selected-row wash, an ink ring, full-strength text), the others quiet v4 buttons (.btn.quiet: a hairline ring). No
 * keycaps on the chips: each key is shown once, in the footer (Michael's audit A19).
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
              className="flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap border pl-[10px] pr-[12px] text-[13.5px] font-medium"
              style={{ borderRadius: v4.radius.control }}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
              animate={{
                opacity: 1,
                y: 0,
                ...(on
                  ? { backgroundColor: v4c.active, borderColor: color.text, color: color.text }
                  : { backgroundColor: v4c.fill, borderColor: v4c.hair2, color: color.label })
              }}
              whileHover={on ? undefined : { backgroundColor: v4c.hover, color: color.text }}
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
            className="absolute inset-x-0 top-0 truncate pl-[2px]"
            style={{ ...v4type.meta, color: color.label }}
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
 * The launcher's room, in the v4 frame's numbers (Adrian's ui-next mock): rows sit PAD_X in from the panel's edge and
 * their text another v4.row.padX in, so the field's bonsai, the section labels and every row's text share one left
 * edge (TEXT_X). A section label is v4's `sec` (12.5 / 550, the label gray), LABEL_TOP above (FIRST_TOP for the first)
 * and LABEL_BOTTOM under; the mock's 30 / 26 / 10 are page numbers, the launcher keeps them tighter.
 */
export const PAD_X = 12
export const TEXT_X = PAD_X + v4.row.padX
const FIRST_TOP = 12
const LABEL_TOP = 18
const LABEL_BOTTOM = 6

/**
 * The launcher's section label ("Continue", "Plans", "Ready to run", "Try asking", "From your link"): v4's section
 * label, sentence case, the label gray, with an optional count in the faint gray ("Ready to run 3").
 */
export function SectionLabel({ children, first = false, count }: { children: ReactNode; first?: boolean; count?: number }): ReactNode {
  return (
    <div
      data-section-label
      className="flex items-center"
      style={{ ...v4type.sec, color: color.label, padding: `${first ? FIRST_TOP : LABEL_TOP}px ${v4.row.padX}px ${LABEL_BOTTOM}px` }}
    >
      {children}
      {count != null && <span style={{ fontWeight: 450, color: color.faint, marginLeft: 6 }}>{count}</span>}
    </div>
  )
}

/** A "Try asking" line is a v4 row (fixed, so the list's one highlight can glide between lines). */
export const ASK_H = v4.row.h

/**
 * One "Try asking" line (Home-Launcher): the words, 44 high (redraft: no arrow). The active line shows the Enter
 * keycap: Enter runs it. No fill of its own: the list draws one highlight (the hover tint, never a hue) under the
 * active line, which the arrow keys and the pointer both move. Lines rise in a beat apart; a press dips on the house
 * spring.
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
      className="relative flex w-full min-w-0 cursor-pointer items-center gap-[12px] text-left"
      style={{ ...v4type.body, height: ASK_H, padding: `0 ${v4.row.padX}px`, borderRadius: v4.radius.row, color: color.text }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={PRESS}
      transition={enter(delay)}
      onMouseMove={onHover}
      onFocus={onHover}
      {...rest}
    >
      <span className="min-w-0 flex-1 truncate">{text}</span>
      <motion.span className="shrink-0" initial={false} animate={{ opacity: active ? 1 : 0 }} transition={fade.tint} aria-hidden>
        <NavKey>{navKey('enter')}</NavKey>
      </motion.span>
    </motion.button>
  )
}

/**
 * The one highlight under a list of `count` equal lines (h each), gliding to line `at` on the spring; -1 = hidden. v4's
 * selected row: the row radius and the `active` wash (one step over the hover wash, so the keyboard's line reads).
 */
export function ListHighlight({ at, count, h }: { at: number; count: number; h: number }): ReactNode {
  const on = at >= 0 && at < count
  return (
    <motion.div
      aria-hidden
      data-list-highlight
      className="pointer-events-none absolute inset-x-0 top-0"
      style={{ height: h, background: v4c.active, borderRadius: v4.radius.row }}
      initial={false}
      animate={{ y: Math.max(0, Math.min(count - 1, at)) * h, opacity: on ? 1 : 0 }}
      transition={{ y: spring, opacity: fade.out }}
    />
  )
}

/**
 * v4's hairlines between rows (`.mg-v4-rows`): one between each pair of the `count` lines (h each), hidden on both
 * edges of the highlighted line `at`, as the Library hides them around a hovered row. They fade, never jump.
 */
export function RowRules({ count, h, at = -1 }: { count: number; h: number; at?: number }): ReactNode {
  if (count < 2) return null
  return (
    <>
      {Array.from({ length: count - 1 }, (_, k) => {
        const i = k + 1
        const hidden = at >= 0 && (i === at || i === at + 1)
        return (
          <motion.span
            key={i}
            aria-hidden
            data-row-rule
            className="pointer-events-none absolute inset-x-0 block h-px"
            style={{ top: i * h, background: v4c.hair }}
            initial={false}
            animate={{ opacity: hidden ? 0 : 1 }}
            transition={fade.tint}
          />
        )
      })}
    </>
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
      <RowRules count={items.length} h={ASK_H} at={active} />
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
      <RowRules count={questions.length} h={ASK_H} at={active} />
      {questions.map((q, i) => (
        <AskLine key={q} text={q} index={i} active={i === active} data={{ 'data-question': true }} onHover={() => onHover(i)} {...press(q)} />
      ))}
    </div>
  )
}

/**
 * The launcher's keycap, the v4 mock's `kbd`: 11 px, 500, 20 high, radius 4, the fill2 wash and the label gray, no
 * ring. Navigation glyphs (↵, ↑↓, ⇥) come from keys.navKey and Esc from the platform's own label (DismissKey), never
 * typed by hand. On the primary button, the mock's `.btn.primary kbd`: ink at 10% (brand), text in the button's ink.
 */
export function NavKey({ children, onAccent = false }: { children: ReactNode; onAccent?: boolean }): ReactNode {
  return (
    <kbd
      data-navkey
      className="inline-flex h-[20px] min-w-[20px] shrink-0 items-center justify-center whitespace-nowrap px-[5px] text-[11px] font-medium tabular-nums"
      style={{
        fontFamily: 'inherit',
        borderRadius: v4.radius.tag,
        ...(onAccent ? { background: fill.onAccentKey, color: color.onAccent } : { background: v4c.fill2, color: color.label })
      }}
    >
      {children}
    </kbd>
  )
}

/** Esc, as the platform names it (bridge.platform.keys.dismiss), in the launcher's keycap. */
export function DismissKey(): ReactNode {
  const label = coreKeyLabel('dismiss')
  return label ? <NavKey>{label}</NavKey> : null
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
    <span className="flex h-[30px] shrink-0 items-center gap-[7px] whitespace-nowrap pl-[4px] pr-[10px] text-[12.5px]" style={{ color: color.label }}>
      {keyName ? <Keycap>{coreKeyLabel(keyName)}</Keycap> : <Keycap>{keycap}</Keycap>}
      {label}
    </span>
  )
}

/**
 * A footer action. `strong` = the primary slot: label then keycap, v4's primary button (radius 8, white on dark, ink on
 * light) when it can act (one per surface), else a faint label. Otherwise a quiet, clickable hint: keycap first like
 * Hint ("⌥⇥ Back to step"), no fill until hovered (the v4 hover wash).
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
      className={`flex h-[30px] shrink-0 cursor-pointer items-center whitespace-nowrap disabled:cursor-default ${
        strong ? `gap-[8px] pr-[5px] text-[13.5px] font-semibold ${solid ? 'pl-[12px]' : 'pl-[10px]'}` : 'gap-[7px] pl-[5px] pr-[10px] text-[12.5px]'
      }`}
      style={{ borderRadius: strong ? v4.radius.control : v4.radius.row }}
      initial={false}
      animate={{
        backgroundColor: solid ? color.accent : fill.clear,
        color: solid ? color.onAccent : enabled ? color.label : color.faint
      }}
      whileHover={enabled ? (solid ? { scale: 1.03 } : { backgroundColor: v4c.hover, color: color.text }) : undefined}
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
 * stray Enter or ↓ then Enter can't end a lesson. No shortcut reaches it (no keycap); Tab walks onto it like every control
 * (Q15), and it still takes two presses there (it keeps focus between them: data-end). Like the bar's End,
 * the first click arms it ("Tap to end", a little brighter) and a second click while armed ends the lesson. Neutral
 * chrome even when armed: the white button stays the one primary (Continue).
 */
/** building: the lesson has not reached step 1 yet (no lesson loaded): the same two clicks read "Stop building". */
export function EndLink({ armed, onClick, building = false }: { armed: boolean; onClick: () => void; building?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="flex h-[26px] shrink-0 cursor-pointer items-center gap-[6px] whitespace-nowrap px-[8px] text-[12.5px]"
      style={{ borderRadius: v4.radius.row }}
      initial={false}
      animate={armed ? { backgroundColor: v4c.fill2, color: color.text } : { backgroundColor: fill.clear, color: color.faint }}
      whileHover={{ color: color.text }}
      whileTap={PRESS}
      transition={{ ...fade.tint, scale: spring }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={building ? (armed ? 'Click again to stop building this lesson' : 'Stop building this lesson') : armed ? 'Click again to end the lesson' : 'End this lesson'}
      data-end
      data-building={building || undefined}
      data-armed={armed || undefined}
    >
      <Square size={10} strokeWidth={2} className="shrink-0" />
      {building ? (armed ? 'Tap to stop' : 'Stop building') : armed ? 'Tap to end' : 'End lesson'}
    </motion.button>
  )
}
