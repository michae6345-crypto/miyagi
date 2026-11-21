/**
 * The launcher, born from the notch island (⌥Space · Ctrl+Shift+Space on Windows · Ctrl+K in the browser stage).
 *
 * It never pops up mid-screen. `launcher:open {from:{w,h}}` carries the island's current size; the
 * panel starts on exactly that shape (top = platform.pillTop, centered, black, radius h/2) and springs
 * DOWN into the launcher (640 wide, height = its content, so it grows as results stream in). Every exit
 * collapses it back into the island before handing over:
 *   Esc / click outside / toggle  → back to the `from` shape, island content fades in → launcher:hidden
 *   Build lesson / pasted link    → onto the 300×34 pill with the pill's "building" content → launcher:built
 *   Ask (during a lesson)         → back to the `from` shape → launcher:hidden; the answer card
 *                                    (card {kind:'answer'}, cards feature) then grows out of the island.
 * The island hides itself while the launcher has it (core), so the two never show at once.
 *
 * Two modes, picked on open (Tab flips them during a lesson):
 *   search : learn {query} → video rows stream in → Build lesson. A pasted YouTube link skips the search
 *            (one row, Enter sends learn_url {url}). Idle shows a few neutral topic suggestions (never the
 *            lesson in progress); a click puts the topic in the field, where the two ways to learn it come up.
 *            Over a search's rows, the first row is always "Just teach me" (the same learn {query, mode:'lesson'}
 *            as the chip below); it is the default pick when the search for what's typed found no video. Only
 *            video rows are listed (the store drops the rest).
 *   ask    : a lesson exists → "Ask about this step" → action {kind:'ask', text}. Under the field, 2-3 suggested questions
 *            about the step (its check, title, concepts: questions.ts); one click asks it (Michael's review A11). The
 *            options (Explain, Hint …) stay in the bar, not repeated here.
 * During a lesson with nothing typed, "Continue <lesson>" is the only row (Enter goes back to the lesson). Ending
 * the lesson is a quiet two-tap "End lesson" link in the footer (Michael's desktop test 3, item 8): no key reaches it,
 * so a stray Enter or ↓ then Enter can't end a lesson.
 * A saved lesson waiting to resume (the engine's card {kind:'resume'} after a restart; the lesson may not be loaded in
 * the app yet) gets the same first row, "Continue <its title>", and Enter sends action resume (item 10).
 *
 * Two ways to learn a typed topic (Michael, Sat 3:23 PM): "Watch a video" (the search flow above) or
 * "Just teach me" (learn {query, mode:"lesson"}: no video, the engine writes the lesson; the panel goes
 * straight into the building pill). A third chip, "Demo" (learn {query, mode:"demo"}), starts the engine's staged
 * neural-net lesson whatever is typed (server/orchestrator/stage.py), the same way as "Just teach me"; the chip is the
 * only place the word appears (its primary says "Start demo"). Demo shows only behind the dev / stage flag
 * (keys.demoEnabled; persona QA). One model for all of them (Michael's review A18): they are buttons. A click starts
 * that way at once; Enter starts the highlighted one, Tab / Shift+Tab move the highlight over them, ⌘/Ctrl+Enter is
 * always "Just teach me". Under the chips one line says what Enter will do (parts.HOW_DESC). The same two names on the
 * chips, the footer's primary, its key hint and the lesson row. The highlight starts on "Just teach me" when the goal
 * reads like building something (isBuildGoal), on "Watch a video" otherwise; never on Demo unless the learner moves it.
 *
 * Nothing typed: the idle list (Continue, the cached lessons, "Try asking") is keyboard navigable. Its first line starts
 * active (the hover tint, never a hue, with the ↵ keycap on it); ↑↓ move it, Enter runs it. Every navigation keycap
 * (↵ ⇥ ↑↓) comes from keys.navKey (bridge.platform.keys first). The grown panel lands below the editor's tabs and
 * toolbar (EDITOR_CHROME), still born from the notch and collapsing back into it.
 *
 * Look: born black like the island, it turns to dark HUD glass (color.glass) with a hairline edge as it
 * grows (Michael's audit A18, mockup 03) and back to black as it collapses. White text at the theme's
 * label/faint levels, low-alpha white fills, one hairline rule; the accent only for the caret and the
 * best result. Footer: key hints (keycap first, "esc Close") and one primary, the white button.
 *
 * Motion: one spring for the shape (width, height, radius together, like the island's own cards);
 * content crossfades (out 80ms; in after 60ms), its sections settling a beat apart. Rows enter
 * y 6 → 0 at least 40ms apart; one highlight glides between them. Reduced motion: crossfades only.
 */
import { AnimatePresence, motion, useReducedMotion, type HTMLMotionProps, type TargetAndTransition, type Transition } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { WifiOff } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { noteLearnMode, useCapability, useLesson, useProgress } from '../../core/lesson'
import { getIslandModes, type IslandMode } from '../../core/registry'
import { sendAction } from '../../core/shortcuts'
import { MiyagiMark } from '../../core/ui/Mark'
import { Keycap } from '../../core/ui/Keycap'
import { Spinner } from '../../core/ui/atoms'
import { color, copy, fill, launcher as launcherTheme, pill, radius, radius2, scrim, shadows, spring, springOut } from '../../core/theme'
import { useCards } from '../cards/store'
import { findPrimer, useStepDetail } from '../drawer/plan'
import { hole, isUsableRect, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'
import { librarySections, libraryMatch, refreshLibrary, startLibraryLesson, useLibrary, type LibraryItem } from './library'
import { Action, EndLink, Hint, HOW_LABEL, HOWS, HowChoice, ListHighlight, modKey, NavKey, QuestionChips, Rise, SectionLabel, SuggestionRows, type How } from './parts'
import { stepQuestions } from './questions'
import { LessonRow, LibraryContinueRow, LinkPreview, MessageRow, READY_H, ReadyRow, ResultRow, ResumeRow, ROW_H, SettingsRow, SkeletonRow } from './Rows'
import { navKey } from './keys'
import { clearResults, markAsked, setLauncherOpen, startSearch, useSearch } from './store'
import { isDuplicateToggle } from './guard'
import { placeClear } from './place'
import { parseYouTube } from './youtube'
import { beat, ease, fade, instant } from '../../core/ui/motion'

type Phase = 'closed' | 'open' | 'closing' | 'building' | 'sending'
type Mode = 'search' | 'ask'
type View = 'idle' | 'link' | 'searching' | 'results' | 'empty' | 'error'
type Size = { w: number; h: number }
/** What Enter (and the footer action) would do right now. Mirrors submit(). */
type Act = 'settings' | 'resume' | 'open' | 'ask' | 'build' | 'teach' | 'demo' | 'search' | 'searching' | 'none'
/** One line of the idle list (nothing typed): what ↑↓ walk and ↵ runs. */
type IdleItem =
  | { kind: 'continue' }
  | { kind: 'lib'; item: LibraryItem }
  | { kind: 'question'; text: string }
  | { kind: 'suggest'; text: string }

/**
 * Room kept for the editor's own chrome under the menu bar (persona QA: the launcher sat over VS Code's title bar, tabs,
 * breadcrumbs and toolbar on a 1440×900 desktop, y 40 to 325). Title bar 35 + tabs 35 + breadcrumbs 22: the grown
 * panel's top sits at least this far under the work area's top. It still grows out of the notch and collapses back
 * into it; it just lands lower, like Spotlight.
 */
const EDITOR_CHROME = 92

/** The footer's End lesson stays armed ("Tap to end") this long for its second click, like the bar's End. */
const END_ARM_MS = 3000

/** Words that lead to Settings. The whole input (3+ letters) must be the start of one: "sett", "keys", "appear". */
const SETTINGS_WORDS = ['settings', 'keys', 'preferences', 'appearance']
const isSettingsQuery = (text: string): boolean => {
  const q = text.trim().toLowerCase()
  return q.length >= 3 && SETTINGS_WORDS.some((w) => w.startsWith(q))
}

/** Launcher width when grown out of the notch. */
const WIDTH = launcherTheme.width
/** Video rows shown (the lesson row comes on top of these). */
const MAX_ROWS = 4
/** `sel` for the "Build a lesson from the internet" row; 0.. are video rows. */
const LESSON = -1
const SKELETONS = 3
/** Minimum gap between two rows' entrances, in seconds. */
const STAGGER = 0.04
/** The pill core's island lands on after Build lesson. */
const PILL: Size = { w: pill.landingWidth, h: pill.height }

/**
 * Idle suggestions ("Try asking"): example asks across fields. A click fills the field. The demo's lesson leads
 * (Michael's test 6).
 */
const SUGGESTIONS: { label: string }[] = [{ label: 'Build a neural network' }, { label: 'Fine-tune an LLM' }, { label: 'Build a ray tracer' }]

/**
 * The goal reads like building something ("build a ray tracer", "write a tokenizer from scratch", "train a GAN"):
 * "Just teach me" is the default way, else "Watch a video" (Michael's review A18). Verbs of making, not topics.
 */
const BUILD_GOAL =
  /\b(build(s|ing)?|mak(e|es|ing)|creat(e|es|ing)|writ(e|es|ing)|cod(e|es|ing)|implement(s|ing)?|develop(s|ing)?|program(s|ming)?|train(s|ing)?|fine-?tun(e|es|ing)|set ?up|from scratch|my own|clone)\b/i
const isBuildGoal = (text: string): boolean => BUILD_GOAL.test(text)

/** Lowercase words only, space-padded, for comparing a suggestion with the lesson in progress. */
const words = (s: string): string => ` ${s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
/** Same topic: the same words, or one contains the other's ("Fine-tune an LLM" vs "Fine-tune an LLM with LoRA"). */
const sameTopic = (a: string, b: string): boolean => {
  const x = words(a)
  const y = words(b)
  return x.trim() !== '' && y.trim() !== '' && (x.includes(y) || y.includes(x))
}

/**
 * The engine's "Continue where you left off?" card (card {kind:'resume'}) says which lesson in its body:
 * "<lesson title> · step 3: <step title>". Split it into the Continue row's title and meta line; any other body is
 * the meta line as it is.
 */
function savedLesson(body: string): { title?: string; where: string } {
  const text = body.trim()
  const m = /^(.*?)\s+·\s+step\s+([^:]*):\s*(.*)$/i.exec(text)
  if (m && m[1].trim()) return { title: m[1].trim(), where: m[3].trim() ? `Step ${m[2].trim()} · ${m[3].trim()}` : `Step ${m[2].trim()}` }
  return { where: text || 'Where you left off' }
}

/** A modifier and a key as one keycap: "⌘↵" on a Mac (glyphs touch), "Ctrl+Enter" on Windows (words take a +). */
const joinKeys = (mod: string, key: string): string => (/[a-z]$/i.test(mod) ? `${mod}+${key}` : `${mod}${key}`)

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? shadows.pill : shadows.card,
  // At the notch: a panel moved clear of the spotlight (see placeClear) collapses back up into the island.
  y: 0,
  // Born black like the island, so the hand-over is seamless; it turns to glass as it grows (see `grown`).
  backgroundColor: color.island
})

/** Exits hand the island back once the shape is within a pixel (no waiting on a sub-pixel settle). */
const settle = { restDelta: 1, restSpeed: 30 }

const contentIn: Transition = { ...fade.in, delay: beat }
const contentOut: Transition = fade.instant

/** Which island mode the island is showing right now (same rule as core/Island, without hover). */
function useIslandMode(): IslandMode | undefined {
  const modes = getIslandModes()
  const wanted = modes.map((m) => m.useActive(false))
  return modes.find((_, i) => wanted[i])
}

export function Launcher({ layout }: { layout: Layout }): ReactNode {
  const [phase, setPhaseState] = useState<Phase>('closed')
  const phaseRef = useRef(phase)
  const setPhase = useCallback((p: Phase) => {
    phaseRef.current = p
    setPhaseState(p)
  }, [])
  const [mode, setMode] = useState<Mode>('search')
  /**
   * "Watch a video", "Just teach me" or "Demo" for the topic being typed (Michael's two ways to learn, plus Demo), when
   * the learner moved the highlight (Tab / Shift+Tab). Unset, the highlight follows what's typed (isBuildGoal), so it
   * never lands on Demo by itself. Cleared with the field and on open.
   */
  const [howPicked, setHowPicked] = useState<How | undefined>(undefined)
  const [from, setFrom] = useState<Size>(PILL)
  /** The island's content is still fading out of the panel (first ~100ms after opening). */
  const [handoff, setHandoff] = useState(false)
  const [gen, setGen] = useState(0)
  const [query, setQuery] = useState('')
  const [question, setQuestion] = useState('')
  const [sel, setSel] = useState(0)
  /**
   * The active line of the idle list (idleItems: Continue, the cached lessons ↑↓ may reach, then "Try asking"), with
   * nothing typed. Its own index over its own rows: it never moves `sel`. It starts on the first line, so ↵ and ↑↓
   * always have an obvious target (persona QA); the hover tint marks it, the pointer and the arrows both move it.
   * Cached lessons join the list only with no lesson running (libKeys), so a key can't swap out a lesson in progress.
   */
  const [idleSel, setIdleSel] = useState(0)
  /** The footer's End lesson got its first click: the next click (within END_ARM_MS) ends the lesson. */
  const [endArmed, setEndArmed] = useState(false)
  const endTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const disarmEnd = useCallback(() => {
    clearTimeout(endTimer.current)
    setEndArmed(false)
  }, [])
  useEffect(() => () => clearTimeout(endTimer.current), [])

  const search = useSearch(useShallow((s) => ({ query: s.query, results: s.results, pending: s.pending, done: s.done, error: s.error })))
  const lesson = useLesson(
    useShallow((s) => ({
      connected: s.connected,
      stepTitle: s.stepTitle,
      hasStep: !!s.stepId,
      hasLesson: !!s.lesson,
      building: s.building,
      title: s.lesson?.title,
      stepId: s.stepId,
      checks: s.checks,
      primer: s.lesson?.primer
    }))
  )
  /** The step's concepts (step.started, kept by the drawer's store), for the suggested questions (review A11). */
  const stepDetail = useStepDetail((s) => s.detail)
  const progress = useProgress()
  /**
   * The engine is waiting on "Continue where you left off?" (after an engine restart it sends card {kind:'resume'},
   * actions resume / end_lesson, and the lesson may not be loaded in the app yet). Michael's desktop test 3, item 10.
   */
  const resumeCard = useCards((c) => (c.card?.kind === 'resume' ? c.card : undefined))
  const saved = resumeCard ? savedLesson(resumeCard.body) : undefined
  const islandMode = useIslandMode()
  /** The spotlight's box (the line being asked about): the panel keeps clear of it (Michael's review A13). */
  const spot = useSpotlight((s) => s.target)
  const reduce = useReducedMotion()
  const input = useRef<HTMLInputElement>(null)
  /** The row Build last sent, so reopening (the preflight card's "Pick another") highlights the next one. */
  const lastPick = useRef<string | undefined>(undefined)
  /** What the lesson being built / in progress was asked as (its query), so the idle chips never offer it again. */
  const topic = useRef<string | undefined>(undefined)
  /** Per-row entrance delays (see delayFor). */
  const delays = useRef(new Map<string, number>())
  const lastEntry = useRef(0)

  // ---- open / close ---------------------------------------------------------------------------

  /** When main last opened the launcher (guard.ts). */
  const openedAt = useRef(0)
  const close = useCallback(() => {
    if (phaseRef.current === 'open') setPhase('closing')
  }, [setPhase])

  /** End of an exit animation (or its safety timer): hand the island back exactly once. */
  const finish = useCallback(
    (exit: Phase) => {
      if (exit === 'open' || exit === 'closed' || phaseRef.current !== exit) return
      setPhase('closed')
      // A sent question stays in the field until its answer card arrives (Michael's desktop test, item 6): if the ask
      // fails, ⌥Space reopens with it selected, ready to send again. See the 'answered' effect below.
      bridge.emit(exit === 'building' ? 'launcher:built' : 'launcher:hidden')
    },
    [setPhase]
  )

  useEffect(
    () =>
      bridge.on('launcher:open', (payload) => {
        const f = (payload as { from?: Size } | undefined)?.from
        openedAt.current = Date.now()
        setFrom(f && f.w > 0 && f.h > 0 ? { w: Math.round(f.w), h: Math.round(f.h) } : PILL)
        const hasLesson = !!useLesson.getState().lesson
        setMode(hasLesson ? 'ask' : 'search')
        // A saved lesson is waiting to resume (item 10): the first decision is Continue, so an old search text left in
        // the field (it outlives an engine restart) must not hide the Continue row.
        if (!hasLesson && useCards.getState().card?.kind === 'resume') setQuery('')
        setHowPicked(undefined)
        disarmEnd()
        setIdleSel(0)
        // The cached lessons can change between opens (a build finished, a lesson moved on): ask again.
        refreshLibrary()
        delays.current.clear()
        // Results stay after Build until a new learn / learn_url. Reopened after a pick ("Pick another"), the
        // highlight starts on the next row, so Enter doesn't rebuild the same tutorial.
        const rows = useSearch.getState().results.slice(0, MAX_ROWS)
        const picked = lastPick.current ? rows.findIndex((r) => r.id === lastPick.current) : -1
        setSel(picked >= 0 && rows.length > 1 ? (picked + 1) % rows.length : 0)
        setHandoff(true)
        setGen((g) => g + 1)
        setPhase('open')
      }),
    [setPhase, disarmEnd]
  )
  useEffect(
    () =>
      bridge.on('launcher:close', () => {
        // Main thinks the panel is open but this renderer isn't showing it (a hot reload remounted it): let main hide
        // the window, or its invisible full-screen panel keeps the keyboard, every click and the island.
        if (phaseRef.current === 'closed') return bridge.emit('launcher:hidden')
        // A second toggle right after the open (double-click, key twice): stay open; main still counts it open.
        if (isDuplicateToggle(Date.now() - openedAt.current)) return
        close()
      }),
    [close]
  )
  useEffect(() => {
    const offs = [
      onUi('dismiss', () => void close()),
      onUi('reset', (p) => {
        if ((p as { scope?: string } | undefined)?.scope === 'lesson') return
        setQuery('')
        setQuestion('')
        setSel(0)
        if (phaseRef.current === 'closed') return
        setPhase('closed')
        bridge.emit('launcher:hidden')
      })
    ]
    return () => offs.forEach((off) => off())
  }, [close, setPhase])

  // The answer card for the last question arrived: the field can let the question go.
  useEffect(
    () =>
      useSearch.subscribe((s, prev) => {
        if (s.answered !== prev.answered) setQuestion('')
      }),
    []
  )

  useEffect(() => setLauncherOpen(phase === 'open'), [phase])

  useEffect(() => {
    if (!handoff) return
    const t = setTimeout(() => setHandoff(false), 160)
    return () => clearTimeout(t)
  }, [handoff, gen])

  // If an exit animation can't finish (e.g. the window stops painting), don't leave the island hidden.
  useEffect(() => {
    if (phase === 'open' || phase === 'closed') return
    const t = setTimeout(() => finish(phase), 1200)
    return () => clearTimeout(t)
  }, [phase, finish])

  // The caret is live the moment the panel appears.
  useEffect(() => {
    if (phase !== 'open') return
    // preventScroll: the panel is still island-sized and clips its content; focusing must not scroll it.
    input.current?.focus({ preventScroll: true })
    if (mode === 'search' || useSearch.getState().askPending) input.current?.select()
  }, [phase, gen, mode])

  // Main takes the keyboard back when another app grabs it mid-typing (an engine editor jump): the caret goes back
  // into the field, with no select(), so the next keystroke adds to the text instead of replacing it.
  useEffect(() => {
    if (phase !== 'open') return
    const refocus = (): void => input.current?.focus({ preventScroll: true })
    window.addEventListener('focus', refocus)
    return () => window.removeEventListener('focus', refocus)
  }, [phase])

  // The keyboard always lives in the field (Michael's test 10: Return on "Build lesson" did nothing). A click on a chip
  // or a row used to leave DOM focus on that button, so the next Enter went to it instead of submit(). The click
  // itself still lands: only focus goes back to the field.
  useEffect(() => {
    if (phase !== 'open') return
    const keep = (e: FocusEvent): void => {
      if (e.target !== input.current) input.current?.focus({ preventScroll: true })
    }
    document.addEventListener('focusin', keep)
    return () => document.removeEventListener('focusin', keep)
  }, [phase])

  // The panel springs to its content's height, so it grows down as rows stream in.
  const content = useRef<HTMLDivElement>(null)
  const [contentH, setContentH] = useState(0)
  const shown = phase !== 'closed'
  useLayoutEffect(() => {
    const el = content.current
    if (!el) return
    const measure = (): void => setContentH(Math.ceil(el.offsetHeight))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [shown, gen])

  // ---- rows: entrance stagger -----------------------------------------------------------------

  /** Each row enters at least STAGGER after the previous one; computed once per row (StrictMode-safe). */
  const delayFor = (id: string): number => {
    let d = delays.current.get(id)
    if (d === undefined) {
      const now = performance.now() / 1000
      const at = Math.max(now, lastEntry.current + STAGGER)
      lastEntry.current = at
      d = at - now
      delays.current.set(id, d)
    }
    return d
  }

  // ---- what to show ---------------------------------------------------------------------------

  const results = search.results
  const visible = results.slice(0, MAX_ROWS)
  const link = mode === 'search' ? parseYouTube(query) : null
  const view: View =
    mode === 'ask'
      ? 'idle'
      : link
        ? 'link'
        : search.error && !results.length
          ? 'error'
          : results.length
            ? 'results'
            : search.pending
              ? 'searching'
              : search.done && search.query
                ? 'empty'
                : 'idle'
  const skeletons = view === 'searching' || (view === 'results' && search.pending) ? Math.max(0, SKELETONS - visible.length) : 0
  const typed = (mode === 'ask' ? question : query).trim()
  /**
   * A topic is typed and Enter would start something new: offer the two ways to learn it, "Watch a video" (today's
   * search flow) or "Just teach me" (learn {mode:"lesson"}, no video). Once the search for exactly what's typed has
   * run, the rows take over (videos under "Build a lesson from the internet"), also when it found no video.
   */
  /** The typed text is a settings word: a single "Settings" row replaces everything else. */
  const settingsRow = !link && isSettingsQuery(typed)
  const choosing = !settingsRow && mode === 'search' && !link && !!typed && (typed !== search.query || view === 'idle')
  /** The highlighted way: the learner's Tab pick, else "Just teach me" for a goal that reads like building something. */
  const how: How = howPicked ?? (isBuildGoal(typed) ? 'lesson' : 'video')
  /** ⌘↵ / Ctrl↵: the modifier comes from the platform's own keys (parts modKey), never typed here. */
  const teachKey = joinKeys(modKey(), navKey('enter'))
  /**
   * During a lesson, with nothing typed: "Continue <lesson>" is the only row, highlighted (Enter goes back to the
   * lesson). Typing replaces it. End lesson is the footer's quiet two-tap link, out of reach of Enter and ↑↓.
   * While the engine waits on a saved lesson (resume card, item 10) the row is there with nothing typed whatever else
   * is on screen (old search rows step aside), and Continue resumes it.
   */
  const resumeRows = !typed && (resumeCard ? true : lesson.hasLesson && (mode === 'ask' || view === 'idle'))
  /** What a text lesson would be about: what's typed, else the query the rows on screen belong to. */
  const goal = typed || (view === 'idle' ? '' : search.query)
  /**
   * "Build a lesson from the internet": the fixed first row over a search's rows (not while the two ways are offered,
   * not for a settings word or a pasted link, not in ask mode, not under Continue). Same request as "Just teach me".
   */
  const lessonRow = mode === 'search' && !link && !settingsRow && !!goal && !choosing && !resumeRows
  /** Video rows (and skeletons, the empty / error row) sit one slot lower under the lesson row. */
  const off = lessonRow ? 1 : 0
  const listed = view === 'idle' ? 0 : view === 'results' || view === 'searching' ? Math.min(MAX_ROWS, visible.length + skeletons) : 1
  const slots = off + listed
  /** The search for exactly what's typed finished without a video: the lesson row is the default pick. */
  /**
   * The search for exactly what's typed ended with no video row: ↵ searches again (an error or offline), unless the
   * lesson row is picked. Only a real "no videos" answer from a connected engine preselects the lesson row: after an
   * error or offline it would fail for the same reason.
   */
  const retry = !choosing && !!typed && typed === search.query && !results.length && !search.pending
  const noVideo = retry && view === 'empty' && lesson.connected
  const onLesson = lessonRow && (sel === LESSON || noVideo)
  const selIndex = Math.min(Math.max(0, sel), Math.max(0, visible.length - 1))
  const highlight = view === 'link' || onLesson ? 0 : view === 'results' ? selIndex + off : -1
  /** The idle topic chips, minus the lesson in progress, being built or waiting to resume: never offer it again. */
  const current = [...(lesson.hasLesson || lesson.building ? [lesson.title, topic.current] : []), saved?.title].filter((t): t is string => !!t)
  const suggestions = SUGGESTIONS.filter((s) => !current.some((t) => sameTopic(s.label, t)))
  /** Ask mode: questions about the step on screen, from its own check, title and concepts (a concept id → its primer title). */
  const concepts =
    stepDetail && stepDetail.stepId === lesson.stepId ? stepDetail.concepts.map((c) => (lesson.primer && findPrimer(lesson.primer, c)?.title) || c) : []
  const questions = mode === 'ask' && lesson.hasStep ? stepQuestions({ title: lesson.stepTitle, concepts, checks: lesson.checks }) : []

  /**
   * Cached lessons (Home-Launcher "Continue", Home-LauncherInContext "Ready to run"), drawn only over what the state
   * machine above already shows with nothing typed: they add rows, never change view / act / sel.
   *   Continue (library) : started on this Mac, no lesson running and no saved lesson waiting (those have their row)
   *   Ready to run       : built and never started; in a lesson too, click only
   */
  const canStartCached = useCapability('library.start')
  const library = useLibrary((s) => s.items)
  const linkMatch = view === 'link' && canStartCached ? libraryMatch(library, link) : undefined
  const sections = librarySections(library, lesson.hasLesson || lesson.building ? lesson.title : saved?.title)
  /** Nothing typed and the idle (or Continue) layout is up: the place for the cached-lesson sections. */
  const homeLayout = canStartCached && !typed && !settingsRow && !choosing && (mode === 'ask' || ((view === 'idle' || resumeRows) && !lessonRow))
  const libCont = homeLayout && mode === 'search' && !lesson.hasLesson && !resumeCard ? sections.cont : []
  const libReady = homeLayout ? sections.ready : []
  const libRows: LibraryItem[] = [...libCont, ...libReady]
  /** ↑↓ / Enter reach the cached lessons only with no lesson running and nothing else to pick (act would be 'none'). */
  const libKeys = mode === 'search' && view === 'idle' && !typed && !settingsRow && !lesson.hasLesson && !resumeCard && libRows.length > 0

  /**
   * The idle list: what ↑↓ walk and ↵ runs with nothing typed (persona QA: ↓ on the empty launcher did nothing).
   * Continue (a lesson open or a saved one waiting) first, then the cached lessons (no lesson running only), then the
   * "Try asking" lines (topics in search mode, the step's questions in ask mode). Ready rows during a lesson stay click-only.
   */
  const idleList = !typed && !settingsRow && !choosing && !lessonRow && (mode === 'ask' || view === 'idle' || resumeRows)
  const asks = mode === 'ask' ? questions : suggestions.map((s) => s.label)
  const idleItems: IdleItem[] = idleList
    ? [
        ...(resumeRows ? [{ kind: 'continue' } as const] : []),
        ...(libKeys ? libRows.map((item) => ({ kind: 'lib', item }) as const) : []),
        ...asks.map((text) => ({ kind: mode === 'ask' ? 'question' : 'suggest', text }) as const)
      ]
    : []
  const active = idleItems.length ? Math.min(Math.max(0, idleSel), idleItems.length - 1) : -1
  const activeItem = active >= 0 ? idleItems[active] : undefined
  const continueOn = resumeRows && active === 0
  const libSel = libKeys && active >= 0 && active < libRows.length ? active : -1
  /** Where the "Try asking" lines start in the idle list. */
  const askBase = (resumeRows ? 1 : 0) + (libKeys ? libRows.length : 0)
  const askActive = activeItem && (activeItem.kind === 'question' || activeItem.kind === 'suggest') ? active - askBase : -1

  // ---- actions --------------------------------------------------------------------------------

  const learn = (q: string): void => {
    lastPick.current = undefined
    startSearch(q)
    delays.current.clear()
    setSel(0)
    noteLearnMode(undefined)
    bridge.send(cmd('learn', { query: q }))
  }

  /**
   * "Just teach me": no video search. The engine researches the topic and writes a text lesson (lesson.mode "lesson"),
   * so there are no rows to pick: the panel goes straight into the building pill, like Build lesson.
   * Only this path sends `mode`: "video" is the contract default, so the video flow's learn stays exactly as it was.
   */
  const teach = (q: string, as: 'lesson' | 'demo' = 'lesson'): void => {
    if (phaseRef.current !== 'open') return
    lastPick.current = undefined
    topic.current = q
    clearResults()
    noteLearnMode(as)
    bridge.send(cmd('learn', { query: q, mode: as }))
    setPhase('building')
  }

  /** The ways are buttons: a click (its press) starts that way at once, whichever is highlighted. */
  const pick = (h: How): void => {
    const q = query.trim()
    if (!q || phaseRef.current !== 'open') return
    setHowPicked(h)
    if (h === 'video') learn(q)
    else teach(q, h)
  }

  const build = (i = selIndex): void => {
    if (phaseRef.current !== 'open') return
    // A link to a video that is already a cached lesson: start that one (zero model calls), never build it twice.
    if (link && linkMatch && startLibraryLesson(linkMatch.id)) {
      lastPick.current = undefined
      topic.current = linkMatch.title
      noteLearnMode(undefined)
      return setPhase('building')
    }
    if (link) {
      lastPick.current = undefined
      topic.current = undefined
      clearResults()
      bridge.send(cmd('learn_url', { url: link.url }))
    } else {
      if (!visible.length) return
      const first = visible[Math.min(i, visible.length - 1)].id
      lastPick.current = first
      topic.current = search.query
      bridge.send(cmd('build_lesson', { resultIds: [first, ...results.map((r) => r.id).filter((id) => id !== first)] }))
    }
    setPhase('building')
  }

  /**
   * Start a cached lesson (Continue / Ready to run): library.start, zero model calls; the engine answers lesson.ready.
   * The panel goes into the pill like Build lesson. A click only during a lesson (no key reaches these rows then).
   */
  const startCached = (item: LibraryItem | undefined): void => {
    if (!item || phaseRef.current !== 'open') return
    if (!startLibraryLesson(item.id)) return
    lastPick.current = undefined
    topic.current = item.title
    noteLearnMode(undefined)
    setPhase('building')
  }

  /** End the lesson (Michael): the engine answers lesson.ended and core resets to idle; the panel goes back into the island. */
  const endLesson = (): void => {
    if (phaseRef.current !== 'open') return
    bridge.send(cmd('end_lesson', {}))
    setPhase('closing')
  }

  /**
   * Continue: back to the lesson. While the engine waits on a saved lesson (resume card) that is action resume (the
   * engine reloads it and the card goes); either way the panel goes back into the island.
   */
  const continueLesson = (): void => {
    if (phaseRef.current !== 'open') return
    if (resumeCard) sendAction('resume')
    close()
  }

  /** The footer's End lesson: the first click arms it ("Tap to end"), a second one within END_ARM_MS ends the lesson. */
  const tapEnd = (): void => {
    if (phaseRef.current !== 'open') return
    clearTimeout(endTimer.current)
    if (!endArmed) {
      setEndArmed(true)
      endTimer.current = setTimeout(() => setEndArmed(false), END_ARM_MS)
      return
    }
    setEndArmed(false)
    endLesson()
  }

  /** Settings has its own window (grown from the island by core); the launcher goes back into the island as usual. */
  const openSettings = (): void => {
    if (phaseRef.current !== 'open') return
    bridge.invoke('settings:open').catch(() => {})
    setPhase('closing')
  }

  /** Ask what's typed, or a suggested question (it goes into the field, which keeps it until the answer arrives). */
  const ask = (text = question.trim()): void => {
    if (!text || phaseRef.current !== 'open') return
    setQuestion(text)
    bridge.send(cmd('action', { kind: 'ask', text }))
    markAsked()
    setPhase('sending')
  }

  /** During a lesson, Tab flips between asking about this step and starting a new lesson. */
  const switchMode = (): void => {
    if (!lesson.hasLesson || phaseRef.current !== 'open') return
    setMode((m) => (m === 'ask' ? 'search' : 'ask'))
  }

  /**
   * A topic chip is only the "what": it fills the field, and the two ways to learn it come up with the default
   * highlighted (Michael's review A18: a chip click used to start a video search at once). Enter or a way starts it.
   */
  const suggest = (text: string): void => {
    if (phaseRef.current !== 'open') return
    disarmEnd()
    setHowPicked(undefined)
    setQuery(text)
  }

  /** Run a line of the idle list (↵ on the active line, or the footer's primary). */
  const runIdle = (item: IdleItem): void => {
    if (item.kind === 'continue') return continueLesson()
    if (item.kind === 'lib') return startCached(item.item)
    if (item.kind === 'question') return ask(item.text)
    suggest(item.text)
  }

  const submit = (): void => {
    if (activeItem) return runIdle(activeItem)
    if (settingsRow) return openSettings()
    // "Continue" goes back into the island and the lesson carries on. Enter never ends a lesson (the footer link does).
    if (resumeRows) return continueLesson()
    if (mode === 'ask') return ask()
    if (link) return build()
    if (onLesson) return teach(goal)
    const q = query.trim()
    if (!q) return
    if (choosing) return how === 'video' ? learn(q) : teach(q, how)
    if (retry) return learn(q)
    build()
  }

  /** ↑↓ over the lesson row and the video rows. Nothing highlighted yet (typing, searching): either key picks the lesson row. */
  const move = (dir: 1 | -1): void => {
    if (onLesson) {
      if (dir === 1 && view === 'results') setSel(0)
    } else if (highlight < 0 || (dir === -1 && selIndex === 0)) {
      if (lessonRow) setSel(LESSON)
    } else {
      setSel(Math.max(0, Math.min(visible.length - 1, selIndex + dir)))
    }
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation() // the stage's Esc would also dismiss cards
      return close()
    }
    // ⌘, (Ctrl+, on Windows): Settings, whatever is typed.
    if (e.key === ',' && (bridge.platform.os === 'mac' ? e.metaKey : e.ctrlKey)) {
      e.preventDefault()
      return openSettings()
    }
    // Nothing typed: ↑↓ walk the idle list (Continue, cached lessons, Try asking; their own slots) and Enter runs the
    // active line. Any other moment these keys belong to the rows above, exactly as before.
    if (idleItems.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const step = e.key === 'ArrowDown' ? 1 : -1
        return setIdleSel(Math.max(0, Math.min(idleItems.length - 1, active + step)))
      }
      if (e.key === 'Enter' && activeItem && !e.nativeEvent.isComposing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        return runIdle(activeItem)
      }
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (e.nativeEvent.isComposing) return
      // ⌘Enter (Ctrl+Enter on Windows) = "Just teach me" straight away, whichever way is highlighted.
      if ((e.metaKey || e.ctrlKey) && mode === 'search' && !link && !settingsRow && typed) return teach(typed)
      return submit()
    }
    if (e.key === 'Tab') {
      e.preventDefault() // focus stays in the field either way
      // While the ways are offered, Tab (Shift+Tab back) moves the highlight over all three; otherwise it flips ask / new lesson.
      if (choosing) return setHowPicked(HOWS[(HOWS.indexOf(how) + (e.shiftKey ? HOWS.length - 1 : 1)) % HOWS.length])
      return switchMode()
    }
    // Continue is the only row: ↑↓ have nothing to move to (End lesson is out of the keys' reach on purpose).
    if (resumeRows && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) return e.preventDefault()
    if (settingsRow || choosing || (view !== 'results' && !lessonRow)) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      move(1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      move(-1)
    }
  }

  // A pasted YouTube link replaces whatever was typed: it is the whole request.
  const onPaste = (e: ClipboardEvent<HTMLInputElement>): void => {
    if (mode !== 'search') return
    const text = e.clipboardData.getData('text')
    if (!parseYouTube(text)) return
    e.preventDefault()
    setQuery(text.trim())
    setSel(0)
  }

  if (phase === 'closed') return null

  // ---- motion targets -------------------------------------------------------------------------

  const exiting = phase === 'closing' || phase === 'building' || phase === 'sending'
  /**
   * Clear of the spotlight's box (Michael's review A13: the ask panel covered the line being asked about): narrower
   * under the notch, or slid down below the box. It still grows out of the notch and collapses back into it.
   */
  const box = spot && isUsableRect(spot.rect) ? hole(toLocal(spot.rect, layout.origin)) : undefined
  const bottom = layout.workArea.y + layout.workArea.height
  const grownH = contentH || from.h
  /** Below the editor's tabs and toolbar (EDITOR_CHROME), unless the panel would then run off the work area. */
  const chromeDy = Math.max(0, Math.min(layout.workArea.y + EDITOR_CHROME - bridge.platform.pillTop, bottom - bridge.platform.pillTop - grownH))
  const place = placeClear({
    box,
    width: WIDTH,
    viewW: layout.width,
    top: bridge.platform.pillTop + chromeDy,
    height: grownH,
    bottom
  })
  /** Grown, the panel is dark HUD glass (color.glass) with a hairline edge (below), like mockup 03, not the island's flat black. */
  const grown: TargetAndTransition = {
    width: place.w,
    height: grownH,
    y: chromeDy + place.dy,
    // Home-Launcher: radius 20 (the v2 panel radius).
    borderRadius: radius2.panel,
    boxShadow: shadows.card,
    backgroundColor: color.glass
  }
  /** Reduced motion: crossfade at full size. Exit targets keep every key (a dropped key ends the animation early). */
  const faded = { ...grown, opacity: 0 }
  let target: TargetAndTransition = { ...grown, opacity: 1 }
  // Reduce Motion: the open panel's height follows its rows at once (MotionConfig doesn't cover sizes); it fades.
  let transition: Transition = reduce ? { ...instant, opacity: fade.in } : spring
  if (phase === 'closing' || phase === 'sending') {
    target = reduce ? faded : { ...shapeOf(from), opacity: 1 }
    transition = reduce ? fade.in : { ...springOut, ...settle }
  } else if (phase === 'building') {
    target = reduce ? faded : { ...shapeOf(PILL), opacity: 1 }
    transition = reduce ? fade.in : { ...spring, ...settle }
  }

  // What the island will show the moment it takes over again: its own content, drawn on the collapsed panel.
  const building = getIslandModes().find((m) => m.id === 'building')
  const returnTo = phase === 'building' ? building : islandMode

  const offline = !lesson.connected
  const inlineError = view === 'results' && !resumeRows && search.error
  // The idle list's active line decides first: Continue, Open (a cached lesson), Ask (a suggested question). A topic
  // line has no primary: ↵ on the line itself only fills the field (its keycap shows on the line).
  const act: Act = activeItem
    ? activeItem.kind === 'continue'
      ? 'resume'
      : activeItem.kind === 'lib'
        ? 'open'
        : activeItem.kind === 'question'
          ? 'ask'
          : 'none'
    : settingsRow
    ? 'settings'
    : resumeRows
    ? 'resume'
    : mode === 'ask'
      ? typed
        ? 'ask'
        : 'none'
      : link
        ? 'build'
        : onLesson
          ? 'teach'
          : !typed
            ? 'none'
            : choosing
              ? how === 'lesson'
                ? 'teach'
                : how === 'demo'
                  ? 'demo'
                  : 'search'
              : retry
                ? 'search'
                : results.length
                  ? 'build'
                  : 'searching'
  const busy = search.pending && mode === 'search' && view !== 'link'
  /**
   * The primary says what Enter does, never a bare "Search" (Michael's audit A19). For the two ways it is the
   * highlighted way's own name, exactly as on its chip and the lesson row (review A18); for Demo, "Start demo".
   */
  const actLabel = {
    settings: 'Settings',
    resume: 'Continue',
    open: 'Open',
    ask: 'Ask',
    // A link that is already a cached lesson builds nothing: Enter starts it (library.start).
    build: linkMatch ? 'Start lesson' : 'Build lesson',
    teach: HOW_LABEL.lesson,
    // The one exception to "the chip's own name" (#121): a bare "Demo" button doesn't say what Enter does.
    demo: 'Start demo',
    search: choosing ? HOW_LABEL.video : 'Try again',
    searching: 'Searching…',
    none: ''
  }[act]
  /** Rows ↑↓ can move between right now: the lesson row plus the video rows (none for Continue, the two ways or Settings). */
  const choices = resumeRows ? 0 : settingsRow || choosing ? 0 : off + (view === 'results' ? visible.length : 0)
  // The footer is keys, not sentences: only the offline / partial-error notes are words.
  const note = offline ? 'Offline' : inlineError ? search.error : undefined
  /** The best row: the one the engine marks "best", else the first. Only it gets a label. */
  const bestIndex = Math.max(0, visible.findIndex((r) => /best/i.test(r.reason)))

  return (
    <div
      key={gen}
      className="absolute inset-0"
      style={{ width: layout.width, height: layout.height }}
      data-launcher={phase}
      data-clear={place.dy ? 'below' : place.w < WIDTH ? 'narrow' : undefined}
    >
      {/* A light dim; click anywhere outside to collapse back into the island. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: scrim.launcher }}
        initial={{ opacity: 0 }}
        animate={{ opacity: phase === 'open' ? 1 : 0 }}
        transition={{ duration: phase === 'open' ? 0.16 : 0.24, ease: ease.out }}
        onClick={close}
      />

      <motion.div
        className="absolute left-1/2 overflow-hidden text-white"
        style={{ top: bridge.platform.pillTop, x: '-50%', transformOrigin: '50% 0%' }}
        initial={reduce ? faded : { ...shapeOf(from), opacity: 1 }}
        animate={target}
        transition={transition}
        onAnimationComplete={() => finish(phase)}
      >
        {/* The island's own content, handed over: fades out as the panel grows… */}
        {handoff && phase === 'open' && !reduce && islandMode && (
          <IslandContent mode={islandMode} initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={contentOut} />
        )}
        {/* …and fades back in as the panel collapses onto the island's shape. */}
        {exiting && !reduce && returnTo && (
          <IslandContent mode={returnTo} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...fade.in, delay: 2 * beat }} />
        )}

        <motion.div
          ref={content}
          // flow-root: the first section's top margin must not collapse through, or the measured height comes up short and the panel clips the footer.
          className="flow-root"
          style={{ width: place.w, marginLeft: `calc(50% - ${place.w / 2}px)` }}
          initial={{ opacity: 0, y: 4 }}
          animate={exiting ? { opacity: 0, y: 0, transition: contentOut } : { opacity: 1, y: 0, transition: contentIn }}
        >
          {/* No title: the placeholder says it. In ask mode, one quiet line says where you are (color.label, so it reads: A20). */}
          {mode === 'ask' && (
            <Rise key="where" i={0} className="truncate px-[24px] pt-[14px] text-[12px] leading-[16px]">
              <span style={{ color: color.label }}>{lesson.hasStep ? `Step ${progress.index + 1} · ${lesson.stepTitle}` : lesson.title}</span>
            </Rise>
          )}

          {/* Home-Launcher's field: a 64 high header row over a hairline. The bonsai stays in the field (brand kit); Esc
              is the platform's own keycap. */}
          <Rise i={1}>
            <div className="flex h-[64px] items-center gap-[16px] px-[24px]" style={{ borderBottom: `1px solid ${fill.hairline}` }}>
              <span className="grid w-[20px] shrink-0 place-items-center" style={{ color: color.label }}>
                {busy ? (
                  <Spinner size={18} c={color.label} />
                ) : (
                  // The bonsai where the mockup had a magnifier (brand kit).
                  <MiyagiMark size={20} />
                )}
              </span>
              <input
                ref={input}
                value={mode === 'ask' ? question : query}
                onChange={(e) => {
                  disarmEnd() // typing hides End lesson; cleared again, it comes back unarmed
                  setIdleSel(0)
                  if (mode === 'ask') setQuestion(e.target.value)
                  else {
                    setQuery(e.target.value)
                    // A cleared field forgets a Tab pick: the next topic gets its own default way.
                    if (!e.target.value.trim()) setHowPicked(undefined)
                  }
                }}
                onKeyDown={onKey}
                onPaste={onPaste}
                readOnly={phase !== 'open'}
                placeholder={mode === 'ask' ? 'Ask about this step' : copy.launcherPlaceholder}
                spellCheck={false}
                autoComplete="off"
                aria-label={mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
                className="h-[40px] min-w-0 flex-1 bg-transparent text-[18px] text-white outline-none placeholder:text-white/30"
                style={{ caretColor: color.accent }}
              />
              <Keycap k="dismiss" />
            </div>
          </Rise>

          <div className="px-[8px] pb-[8px]">
            {resumeRows && (
              <Rise key="resume" i={2}>
                <SectionLabel first>Continue</SectionLabel>
                <div className="relative" style={{ height: ROW_H }}>
                  <ListHighlight at={continueOn ? 0 : -1} count={1} h={ROW_H} />
                  <ResumeRow
                    lessonTitle={saved ? (saved.title ?? lesson.title) : lesson.title}
                    // Where you are, the same in both modes (persona QA: "Step 3 of 6 · Build the model"). A saved
                    // lesson: where the card says.
                    where={
                      saved
                        ? saved.where
                        : lesson.hasStep
                          ? `Step ${progress.index + 1} of ${progress.total} · ${lesson.stepTitle}`
                          : 'Where you left off'
                    }
                    active={continueOn}
                    onHover={() => setIdleSel(0)}
                    onPick={continueLesson}
                  />
                </div>
              </Rise>
            )}

            {settingsRow && (
              <Rise key="settings" i={2} className="pt-[8px]">
                <div className="relative" style={{ height: ROW_H }}>
                  <div className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]" style={{ height: ROW_H, background: fill.highlight }} />
                  <SettingsRow onPick={openSettings} />
                </div>
              </Rise>
            )}

            {settingsRow ? null : choosing ? (
              <Rise key="how" i={2} className="px-[16px] pt-[12px]">
                <HowChoice how={how} onPick={pick} />
              </Rise>
            ) : mode === 'ask' ? (
              <>
                {questions.length > 0 && (
                  <Rise key="ask" i={2}>
                    <SectionLabel first={!resumeRows}>Try asking</SectionLabel>
                    <QuestionChips
                      questions={questions}
                      active={askActive}
                      onHover={(i) => idleList && setIdleSel(askBase + i)}
                      onPick={(q) => ask(q)}
                    />
                  </Rise>
                )}
                {libReady.length > 0 && (
                  <Rise key="ready" i={3}>
                    <SectionLabel first={!resumeRows && !questions.length}>Ready to run</SectionLabel>
                    <ReadyList items={libReady} offset={libCont.length} sel={libSel} onSel={setIdleSel} keys={libKeys} onPick={startCached} />
                  </Rise>
                )}
              </>
            ) : (view === 'idle' || resumeRows) && !lessonRow ? (
              // Under Continue (a saved lesson waiting) the old search rows step aside for the topic rows too.
              <>
                {libCont.length > 0 && (
                  <Rise key="cont" i={2}>
                    <SectionLabel first>Continue</SectionLabel>
                    <div className="relative" style={{ height: libCont.length * ROW_H }}>
                      <SlotHighlight at={libSel} count={libCont.length} h={ROW_H} />
                      {libCont.map((item, i) => (
                        <LibraryContinueRow key={item.id} item={item} slot={i} active={libSel === i} onHover={() => libKeys && setIdleSel(i)} onPick={() => startCached(item)} />
                      ))}
                    </div>
                  </Rise>
                )}
                {libReady.length > 0 && (
                  <Rise key="ready" i={3}>
                    <SectionLabel first={!resumeRows && !libCont.length}>Ready to run</SectionLabel>
                    <ReadyList items={libReady} offset={libCont.length} sel={libSel} onSel={setIdleSel} keys={libKeys} onPick={startCached} />
                  </Rise>
                )}
                {suggestions.length > 0 && (
                  <Rise key="try" i={4}>
                    <SectionLabel first={!resumeRows && !libCont.length && !libReady.length}>Try asking</SectionLabel>
                    <SuggestionRows
                      items={suggestions.map((s) => s.label)}
                      active={askActive}
                      onHover={(i) => idleList && setIdleSel(askBase + i)}
                      onPick={suggest}
                    />
                  </Rise>
                )}
              </>
            ) : view === 'link' && link ? (
              // A pasted link: one clear preview (thumbnail, start time, what Enter does), already the active row.
              <Rise key={`link:${link.videoId}`} i={2}>
                <SectionLabel first>From your link</SectionLabel>
                <LinkPreview link={link} match={linkMatch} onPick={() => build()} />
              </Rise>
            ) : (
              slots > 0 && (
                <div className="pt-[8px]">
                  <div className="relative" style={{ height: slots * ROW_H }}>
                    <motion.div
                      className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]"
                      style={{ height: ROW_H, background: fill.highlight }}
                      initial={false}
                      animate={{ y: Math.max(0, highlight) * ROW_H, opacity: highlight >= 0 ? 1 : 0 }}
                      transition={spring}
                    />
                    <AnimatePresence initial={false}>
                      {lessonRow && <LessonRow key="lesson" onHover={() => setSel(LESSON)} onPick={() => teach(goal)} />}
                      {(view === 'results' || view === 'searching') &&
                        visible.map((r, i) => (
                          <ResultRow
                            key={r.id}
                            slot={i + off}
                            delay={delayFor(r.id)}
                            r={r}
                            best={i === bestIndex}
                            onHover={() => setSel(i)}
                            onPick={() => build(i)}
                          />
                        ))}
                      {Array.from({ length: skeletons }, (_, k) => (
                        <SkeletonRow key={`sk${visible.length + k}`} slot={visible.length + k + off} />
                      ))}
                      {view === 'empty' && (
                        <MessageRow
                          key="empty"
                          slot={off}
                          tone="empty"
                          title={`No videos for “${search.query}”`}
                          detail="Try other words, or paste a YouTube link."
                        />
                      )}
                      {view === 'error' && <MessageRow key="error" slot={off} tone="error" title="Couldn't search right now" detail={search.error ?? ''} />}
                    </AnimatePresence>
                  </div>
                </div>
              )
            )}
          </div>

          {/* Footer (Home-Launcher): a hairline, then the one line that helps ("Paste a YouTube link or type a goal")
              or what is wrong, and the keys that apply right now. One primary at most. */}
          <Rise i={5}>
            <div className="h-px" style={{ background: fill.hairline }} />
            <div className="flex h-[48px] items-center gap-[4px] pl-[18px] pr-[12px]">
              {/* No "New lesson" while a lesson runs (Michael's review A13): the ask panel is about this step, and the
                  footer's End lesson is the way out. Tab still flips to a new search, where "Back to step" (quiet, far
                  left, away from the primary: audit A20) is the way back. */}
              {lesson.hasLesson && mode === 'search' && !choosing && <Action label="Back to step" keycap={navKey('tab')} enabled onClick={switchMode} />}
              {/* End lesson (desktop test 3, item 8): quiet, small, two clicks, on the left away from the primary. No key reaches it. */}
              {lesson.hasLesson && resumeRows && <EndLink armed={endArmed} onClick={tapEnd} />}
              <span className="flex min-w-0 flex-1 items-center gap-[7px] pl-[6px] text-[12px]" style={{ color: note ? color.text : color.label }}>
                {offline && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
                {note ? (
                  <span className="truncate">{note}</span>
                ) : (
                  mode === 'search' &&
                  !typed &&
                  !lesson.hasLesson && (
                    <>
                      <span className="truncate">Paste a YouTube link or type a goal</span>
                      {/* Only when Enter has nothing else to run: with an idle line active, ↵ belongs to that line
                          and the footer's primary, so a second ↵ here would read as "submit my goal". */}
                      {!activeItem && <NavKey>{navKey('enter')}</NavKey>}
                    </>
                  )
                )}
              </span>
              {(choices > 1 || idleItems.length > 1) && <Hint label="Move" keycap={navKey('arrows')} />}
              {choosing && (
                <>
                  <Hint label="Switch" keycap={navKey('tab')} />
                  {/* Each keycap once, here (not inside the chip): ⌘↵ is "Just teach me" whichever way is highlighted; with it highlighted, ↵ already does. */}
                  {how !== 'lesson' && <Hint label={HOW_LABEL.lesson} keycap={teachKey} />}
                </>
              )}
              {act !== 'none' && <Action label={actLabel} keycap={navKey('enter')} enabled={act !== 'searching'} strong onClick={submit} />}
            </div>
          </Rise>
        </motion.div>

        {/* The glass edge: a hairline that follows the shape's radius, in with the content and gone before the island returns. */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 border"
          style={{ borderColor: color.hairline, borderRadius: 'inherit' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: exiting ? 0 : 1 }}
          transition={exiting ? contentOut : contentIn}
        />
      </motion.div>
    </div>
  )
}

/** An island mode's content, positioned exactly as core/Island positions it (top-center of the shape). */
function IslandContent({ mode, ...motionProps }: { mode: IslandMode } & Pick<HTMLMotionProps<'div'>, 'initial' | 'animate' | 'transition'>): ReactNode {
  const { Content } = mode
  return (
    <motion.div className="pointer-events-none absolute left-1/2 top-0" style={{ x: '-50%', width: mode.width ?? 'max-content' }} {...motionProps}>
      <Content />
    </motion.div>
  )
}

/**
 * The cached lessons' own highlight (Continue / Ready to run): slot `at - offset` of this list, hidden when the
 * highlighted cached lesson is in the other list. Never the search rows' highlight.
 */
function SlotHighlight({ at, offset = 0, count, h }: { at: number; offset?: number; count: number; h: number }): ReactNode {
  const i = at - offset
  const on = at >= 0 && i >= 0 && i < count
  return (
    <motion.div
      className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]"
      style={{ height: h, background: fill.highlight }}
      initial={false}
      animate={{ y: Math.max(0, Math.min(count - 1, i)) * h, opacity: on ? 1 : 0 }}
      transition={spring}
    />
  )
}

/**
 * "Ready to run" (Home-LauncherInContext): built, never started, one line each, in a slot range of their own (READY_H
 * rows numbered from 0 here; `offset` maps them onto readySel after the Continue rows). `keys`: the launcher lets ↑↓
 * reach them (no lesson running); otherwise they are click targets only, so no key can swap out a lesson.
 */
function ReadyList({
  items,
  offset,
  sel,
  onSel,
  keys,
  onPick
}: {
  items: LibraryItem[]
  offset: number
  sel: number
  onSel: (i: number) => void
  keys: boolean
  onPick: (item: LibraryItem) => void
}): ReactNode {
  return (
    <div className="relative" style={{ height: items.length * READY_H }}>
      <SlotHighlight at={sel} offset={offset} count={items.length} h={READY_H} />
      {items.map((item, i) => (
        <ReadyRow key={item.id} item={item} slot={i} hover={!keys} active={keys && sel === offset + i} onHover={() => keys && onSel(offset + i)} onPick={() => onPick(item)} />
      ))}
    </div>
  )
}
