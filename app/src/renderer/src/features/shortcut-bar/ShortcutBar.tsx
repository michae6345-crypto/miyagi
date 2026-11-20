/**
 * Bottom shortcut bar: "Ask Miyagi" + the commands. Only visible during a lesson. Sits 24px above the dock / taskbar.
 *
 * Pass 3 (Adrian: "simpler"): each tile is its glyph + label + keycap; hover or ⌥ held brightens the keycap (Tile.tsx).
 * Options wear their pastel (theme.actionTone): Explain / Diagram sky, Show me lilac, Hint pink, ink glyphs.
 * Back and Voice are neutral chrome (Voice on = glass.button). Step controls after one hairline: Check is the one
 * primary, Skip step / End lesson are quiet. (Adrian picked this over a "More" menu for Back / Skip / End, Sat.)
 * A card with its own step controls (Yes / Skip step / Can I move on?) quiets Check too; while the launcher is open
 * the Ask field collapses to the tree, so there's one primary and one ask field on screen (audit A17).
 * The bar is a glass panel: theme.glass tokens, so it follows Settings → Appearance (light / dark).
 * Thinking: the pressed tile's glyph is the Spinner (Busy.tsx). Any trigger dips its tile for 90 ms (press.ts).
 * Voice speaking: the equalizer (Equalizer.tsx). Diagram open: its tile stays lit.
 * Folded (review A12 / A8, fold.ts + front.ts): a thin handle over the middle of the status bar while the pointer has
 * been off the bar for a few seconds, or while another app is in front. The pointer on the handle brings it back.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowLeft, AudioLines, Check, Lightbulb, MessageSquareText, RotateCcw, SkipForward, Square, SquarePlay, Waypoints, type LucideIcon } from 'lucide-react'
import { cmd } from '../../../../common/wire'
import { bridge, registerWebHandler } from '../../bridge'
import { emitUi } from '../../core/bus'
import { useLesson, useProgress } from '../../core/lesson'
import { useAppearance } from '../../core/prefs'
import { sendAction, triggerShortcut, type ActionKind, type ActionShortcut } from '../../core/shortcuts'
import { MiyagiMark } from '../../core/ui/Mark'
import { actionTone, copy, glass, spring, type OptionAction } from '../../core/theme'
import { useCards } from '../cards/store'
import { useComplete } from '../complete/store'
import { useDiagram, useUnseen } from '../diagrams/store'
import { useLauncherOpen } from '../launcher/store'
import { toggleVoice } from '../voice/store'
import { Equalizer, useVoiceTile } from './Equalizer'
import { holdWhile, pointerLeft, reveal, useFold } from './fold'
import { useFront, wake } from './front'
import { usePress } from './press'
import { GlassKey, hoverCls, look, Tile } from './Tile'

type Btn = { kind: ActionShortcut; label: string; icon: LucideIcon }

const BUTTONS: Btn[] = [
  { kind: 'back', label: 'Back', icon: RotateCcw },
  { kind: 'explain', label: 'Explain', icon: MessageSquareText },
  { kind: 'diagram', label: 'Diagram', icon: Waypoints },
  { kind: 'show_me', label: 'Show me', icon: SquarePlay },
  { kind: 'hint', label: 'Hint', icon: Lightbulb },
  { kind: 'voice_toggle', label: 'Voice', icon: AudioLines }
]

/**
 * Step controls, always reachable in every lesson (video or "Just teach me"): Check = "Can I move on?" (engine re-runs
 * the checks + Claude reads the screen), Skip = leave this step unfinished, End = stop the lesson. Michael, Sat.
 */
type StepBtn = { id: 'check' | 'skip' | 'end'; label: string; icon: LucideIcon; kind?: ActionKind; title: string }
const STEP_BUTTONS: StepBtn[] = [
  { id: 'check', label: 'Check my work', icon: Check, kind: 'check_step', title: 'Check my work: can I move on?' },
  { id: 'skip', label: 'Skip step', icon: SkipForward, kind: 'skip_step', title: 'Skip this step' },
  { id: 'end', label: 'End lesson', icon: Square, title: 'End this lesson' }
]

/** Skip: repeat presses inside this window are ignored (Michael's desktop test: one tap could skip twice). */
const SKIP_LOCK_MS = 1000
/** End: the first tap arms it ("Tap to end"); a second tap inside this window ends the lesson. No one-tap loss. */
const END_ARM_MS = 4000

/** After End on a finished lesson: how long to wait for the engine's lesson.ended before closing the lesson UI here. */
const END_FALLBACK_MS = 1500
/** Every step of a complete lesson passed (skipped steps count: they're in `passed` too). */
function lessonDone(): boolean {
  const s = useLesson.getState()
  return !!s.lesson && s.complete && s.steps.length > 0 && s.steps.every((x) => s.passed.includes(x.id))
}

/** Step-control state: the Skip lock and the End confirm, each cleared by its own timer. */
function useStepControls(): { skipping: boolean; armed: boolean; run: (id: StepBtn['id']) => void } {
  const [skipping, setSkipping] = useState(false)
  const [armed, setArmed] = useState(false)
  const timers = useRef<{ skip?: ReturnType<typeof setTimeout>; end?: ReturnType<typeof setTimeout> }>({})
  useEffect(() => () => (clearTimeout(timers.current.skip), clearTimeout(timers.current.end)), [])
  const run = (id: StepBtn['id']): void => {
    if (id === 'check') return sendAction('check_step')
    if (id === 'skip') {
      if (skipping) return
      setSkipping(true)
      sendAction('skip_step')
      timers.current.skip = setTimeout(() => setSkipping(false), SKIP_LOCK_MS)
      return
    }
    clearTimeout(timers.current.end)
    // The lesson is finished (every step passed): nothing to lose, so End is one tap. If the engine doesn't answer
    // with lesson.ended (it ignored end_lesson once a lesson was done, Michael's test 5), close the drawer, cards and
    // bar here anyway, so the learner is never stuck on a finished lesson.
    if (lessonDone()) {
      setArmed(false)
      const shown = useLesson.getState().lesson
      bridge.send(cmd('end_lesson', {}))
      timers.current.end = setTimeout(() => {
        if (shown && useLesson.getState().lesson === shown) emitUi('reset', { scope: 'lesson', reason: 'end_lesson' })
      }, END_FALLBACK_MS)
      return
    }
    if (!armed) {
      setArmed(true)
      timers.current.end = setTimeout(() => setArmed(false), END_ARM_MS)
      return
    }
    setArmed(false)
    bridge.send(cmd('end_lesson', {}))
  }
  return { skipping, armed, run }
}

/** 8 px padding around the 62 px tiles (glyph, label, keycap). lift.ts reads it. */
export const BAR_HEIGHT = 78

const isOption = (kind: ActionShortcut): kind is ActionShortcut & OptionAction => kind in actionTone

/** Re-raise the overlay at most this often while the pointer comes and goes over the bar. */
const RAISE_EVERY_MS = 1500
let lastRaise = 0
/**
 * Another app's always-on-top window at the overlay's level (Wispr Flow's "Status") can sit over the bar
 * (Michael's desktop test, item 8): main moves the overlay back on top (main/features/overlay-raise.ts).
 */
function raiseOverlay(): void {
  const now = Date.now()
  if (now - lastRaise < RAISE_EVERY_MS) return
  lastRaise = now
  try {
    bridge.invoke('overlay:raise').catch(() => {})
  } catch {
    // browser stage without a handler: nothing to raise
  }
}
registerWebHandler('overlay:raise', () => true)

/**
 * Card buttons that are step controls ("Looks done?" Yes, Skip step, Can I move on?). While a card carries one, the
 * card owns the step's primary: the bar's Check and Skip step go quiet, so the screen never shows two white
 * primaries or two Skip buttons at once (Michael's audit A17).
 */
const CARD_STEP_ACTIONS = new Set<string>(['confirm', 'skip_step', 'check_step'])

/**
 * The Ask field's width. It keeps it while the launcher is open (only its words fade, so the launcher is the one ask
 * field on screen): collapsing it made every bar button slide left and back (Michael's tests 2-3, A13).
 */
const ASK_W = 196

/** How far the bar drops as it folds into its handle (transform only). */
const FOLD_Y = 28

/**
 * The folded bar: a short glass pill with a faint grip, centered over the status bar's empty middle. Its hit area is
 * taller than the pill (up to where the bar's lower edge sits), so the pointer on its way up lands on it.
 */
function Handle({ bottom, height, onReach }: { bottom: number; height: number; onReach: () => void }): ReactNode {
  return (
    <motion.div
      className="pointer-events-none absolute inset-x-0 flex justify-center"
      style={{ bottom }}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={spring}
    >
      <div
        data-hit
        data-shortcut-handle
        role="button"
        aria-label="Show the shortcut bar"
        className="pointer-events-auto flex w-[168px] cursor-pointer items-end justify-center pb-[3px]"
        style={{ height }}
        onPointerEnter={onReach}
        onClick={onReach}
      >
        <span
          className="flex h-[12px] w-[128px] items-center justify-center rounded-full border"
          style={{ background: glass.bg, borderColor: glass.hairline, boxShadow: glass.shadow }}
        >
          <span className="h-[4px] w-[56px] rounded-full" style={{ background: glass.faint }} />
        </span>
      </div>
    </motion.div>
  )
}

/**
 * bottom: the bar's lower edge above the display's bottom (above the status bar band); dock: the Dock / taskbar's
 * height (the handle sits just above it); lift: px above the spotlight's hole (lift.ts).
 */
export function ShortcutBar({ bottom, dock = 0, lift = 0 }: { bottom: number; dock?: number; lift?: number }): ReactNode {
  // Michael's test 8: no Hint / Skip / Check my work under the lesson-complete panel (it has its own End lesson).
  const completing = useComplete((c) => !!c.card)
  const on = useLesson((x) => !!x.lesson) && !completing
  const hasStep = useLesson((x) => !!x.stepId)
  const diagramOpen = useDiagram((d) => d.open)
  // The step has a diagram the learner hasn't opened: a small neutral dot on the Diagram tile (nothing opens by itself).
  const diagramWaiting = useUnseen()
  const voice = useVoiceTile()
  const appearance = useAppearance()
  // Any shortcut (click, global key, stage key, launcher chip): the matching tile dips for 90 ms (press.ts).
  const pressed = usePress((p) => p.kind)
  const stepTiles = hasStep ? STEP_BUTTONS : []
  const step = useStepControls()
  const cardSteps = useCards((c) => !!c.card?.actions?.some((a) => CARD_STEP_ACTIONS.has(a)))
  const askCollapsed = useLauncherOpen()
  // Text lessons ("Just teach me"): Back goes to the previous step, so it's an arrow, and there's none before step 1.
  // Video lessons keep the replay glyph (Back rewinds the video). Audit A22.
  const textLesson = useLesson((x) => x.lesson?.mode === 'lesson')
  const firstStep = useProgress().index === 0
  // A12 / A8: folded while the pointer has been off it a while, or while another app is in front. During a step it
  // stays up while the lesson's app is in front: Hint and Show me were hard to find folded (Michael's test 6).
  const idle = useFold((f) => f.idle)
  const away = useFront((f) => f.away)
  const folded = away || (idle && !hasStep)
  const busy = useRef(false)
  busy.current = step.armed || step.skipping
  useEffect(() => holdWhile(() => busy.current), [])
  const unfold = (): void => {
    if (useFront.getState().away) wake()
    reveal()
  }
  const handleBottom = dock + 2

  return (
    <AnimatePresence>
      {on && folded && <Handle key="handle" bottom={handleBottom} height={Math.max(20, bottom - handleBottom)} onReach={unfold} />}
      {on && !folded && (
        <motion.div
          key="bar"
          className="pointer-events-none absolute inset-x-0 flex justify-center"
          style={{ bottom }}
          initial={{ opacity: 0, y: FOLD_Y }}
          animate={{ opacity: 1, y: -lift }}
          exit={{ opacity: 0, y: FOLD_Y }}
          transition={spring}
        >
          <div
            data-hit
            data-shortcut-bar
            onPointerEnter={raiseOverlay}
            onPointerLeave={pointerLeft}
            className="pointer-events-auto flex items-center gap-[2px] rounded-[24px] border p-[8px]"
            style={{ height: BAR_HEIGHT, background: glass.bg, borderColor: glass.hairline, boxShadow: glass.shadow, backdropFilter: 'blur(30px) saturate(1.4)' }}
          >
            {/* While the launcher is open it is the ask field: this one keeps its width but shows only the tree (A13). */}
            <motion.button
              className={`mr-[8px] flex h-[44px] shrink-0 cursor-pointer items-center gap-[9px] overflow-hidden whitespace-nowrap rounded-[22px] border pl-[14px] pr-[8px] text-left ${hoverCls}`}
              style={{ width: ASK_W, borderColor: glass.hairline, color: glass.label }}
              aria-label={copy.ask}
              data-collapsed={askCollapsed ? '' : undefined}
              onClick={() => bridge.emit('launcher:toggle')}
            >
              <span className="flex shrink-0">
                <MiyagiMark size={15} tone={appearance === 'light' ? 'light' : 'dark'} />
              </span>
              <motion.span className="flex flex-1 items-center gap-[9px]" initial={false} animate={{ opacity: askCollapsed ? 0 : 1 }} transition={{ duration: 0.12 }} aria-hidden={askCollapsed || undefined}>
                <span className="flex-1 text-[14.5px]">{copy.ask}</span>
                <GlassKey text={bridge.platform.keys.launcher} />
              </motion.span>
            </motion.button>
            {BUTTONS.map(({ kind, label, icon }) => {
              const voiceOn = kind === 'voice_toggle' && voice.on
              const l = isOption(kind) ? look.option(kind) : voiceOn ? look.primary : look.neutral
              // Back is the previous step in every lesson now (engine 14f55e7, Michael Nov 15): an arrow everywhere,
              // disabled on step 1 of a text lesson (a video's step 1 still rewinds its clip).
              const back = kind === 'back'
              return (
                <Tile
                  key={kind}
                  label={label}
                  icon={back ? ArrowLeft : icon}
                  look={l}
                  disabled={back && textLesson && firstStep}
                  keycap={bridge.platform.keys[kind]}
                  busyKind={kind}
                  dip={pressed === kind}
                  lit={kind === 'diagram' && diagramOpen}
                  dot={kind === 'diagram' && diagramWaiting}
                  pressed={kind === 'diagram' ? diagramOpen : kind === 'voice_toggle' ? voice.on : undefined}
                  glyph={voiceOn && voice.speaking ? <Equalizer tone={l.color} size={16} /> : undefined}
                  onClick={() => (kind === 'voice_toggle' ? toggleVoice() : triggerShortcut(kind))}
                />
              )
            })}
            {stepTiles.length > 0 && <div className="mx-[6px] h-[34px] w-px" style={{ background: glass.rule }} />}
            {stepTiles.map(({ id, label, icon, kind, title }) => {
              const shown = id === 'skip' && step.skipping ? 'Skipping…' : id === 'end' && step.armed ? 'Tap to end' : label
              const tip = id === 'end' && step.armed ? 'Tap again to end the lesson' : title
              // Check is the bar's one primary, unless a card with its own step controls is up (A17): then it's quiet.
              const primary = (id === 'check' && !cardSteps) || (id === 'end' && step.armed)
              return <Tile key={id} label={shown} icon={icon} look={primary ? look.primary : look.quiet} busyKind={kind} title={tip} onDown={id === 'end'} onClick={() => step.run(id)} />
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
