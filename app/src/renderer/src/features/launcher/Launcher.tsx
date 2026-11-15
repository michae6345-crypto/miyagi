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
 *            lesson in progress); one click searches.
 *            Over a search's rows, the first row is always "Build a lesson from the internet" (the same
 *            learn {query, mode:'lesson'} as "Just teach me" below); it is the default pick when the search
 *            for what's typed found no video. Only video rows are listed (the store drops the rest).
 *   ask    : a lesson exists → "Ask about this step" → action {kind:'ask', text}.
 * During a lesson with nothing typed, "Continue <lesson>" is the first row (Enter goes back to the lesson)
 * and "End lesson" sits under it (↓ then Enter sends end_lesson).
 *
 * Two ways to learn a typed topic (Michael, Sat 3:23 PM): "Watch a video" (the search flow above) or
 * "Just teach me" (learn {query, mode:"lesson"}: no video, the engine writes the lesson; the panel goes
 * straight into the building pill). Tab switches while they're offered, Enter picks, ⌘/Ctrl+Enter teaches.
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
import { Aperture, Bot, Mic, Waves, WifiOff, type LucideIcon } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson, useProgress } from '../../core/lesson'
import { getIslandModes, type IslandMode } from '../../core/registry'
import { triggerShortcut } from '../../core/shortcuts'
import { MiyagiMark } from '../../core/ui/Mark'
import { OptionButton, Spinner } from '../../core/ui/atoms'
import { color, copy, fill, launcher as launcherTheme, pill, radius, scrim, shadows, spring, springOut } from '../../core/theme'
import { Action, Chip, Hint, HowChoice, Rise, type How } from './parts'
import { EndRow, LessonRow, LinkRow, MessageRow, ResultRow, ResumeRow, ROW_H, SettingsRow, SkeletonRow } from './Rows'
import { clearResults, markAsked, setLauncherOpen, startSearch, useSearch } from './store'
import { parseYouTube } from './youtube'

type Phase = 'closed' | 'open' | 'closing' | 'building' | 'sending'
type Mode = 'search' | 'ask'
type View = 'idle' | 'link' | 'searching' | 'results' | 'empty' | 'error'
type Size = { w: number; h: number }
/** What Enter (and the footer action) would do right now. Mirrors submit(). */
type Act = 'settings' | 'resume' | 'end' | 'ask' | 'build' | 'teach' | 'search' | 'searching' | 'none'

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

/** Idle suggestions: example asks across fields (never the demo lesson's topic). One click searches. */
const SUGGESTIONS: { icon: LucideIcon; label: string }[] = [
  { icon: Bot, label: 'Fine-tune an LLM' },
  { icon: Aperture, label: 'Build a ray tracer' },
  { icon: Waves, label: 'Train a diffusion model' }
]

/** Lowercase words only, space-padded, for comparing a suggestion with the lesson in progress. */
const words = (s: string): string => ` ${s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
/** Same topic: the same words, or one contains the other's ("Fine-tune an LLM" vs "Fine-tune an LLM with LoRA"). */
const sameTopic = (a: string, b: string): boolean => {
  const x = words(a)
  const y = words(b)
  return x.trim() !== '' && y.trim() !== '' && (x.includes(y) || y.includes(x))
}

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? shadows.pill : shadows.card,
  // Born black like the island, so the hand-over is seamless; it turns to glass as it grows (see `grown`).
  backgroundColor: color.island
})

/** Exits hand the island back once the shape is within a pixel (no waiting on a sub-pixel settle). */
const settle = { restDelta: 1, restSpeed: 30 }

const contentIn: Transition = { duration: 0.2, delay: 0.06, ease: 'easeOut' }
const contentOut: Transition = { duration: 0.08 }

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
  /** "Watch a video" or "Just teach me" for the topic being typed (Michael's two ways to learn). */
  const [how, setHow] = useState<How>('video')
  const [from, setFrom] = useState<Size>(PILL)
  /** The island's content is still fading out of the panel (first ~100ms after opening). */
  const [handoff, setHandoff] = useState(false)
  const [gen, setGen] = useState(0)
  const [query, setQuery] = useState('')
  const [question, setQuestion] = useState('')
  const [sel, setSel] = useState(0)
  /** During a lesson with nothing typed: the "End lesson" row is picked instead of "Continue" (↓ or hover). */
  const [pickEnd, setPickEnd] = useState(false)

  const search = useSearch(useShallow((s) => ({ query: s.query, results: s.results, pending: s.pending, done: s.done, error: s.error })))
  const lesson = useLesson(
    useShallow((s) => ({
      connected: s.connected,
      stepTitle: s.stepTitle,
      hasStep: !!s.stepId,
      hasLesson: !!s.lesson,
      building: s.building,
      title: s.lesson?.title
    }))
  )
  const progress = useProgress()
  const islandMode = useIslandMode()
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
        setFrom(f && f.w > 0 && f.h > 0 ? { w: Math.round(f.w), h: Math.round(f.h) } : PILL)
        setMode(useLesson.getState().lesson ? 'ask' : 'search')
        setHow('video')
        setPickEnd(false)
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
    [setPhase]
  )
  useEffect(
    () =>
      bridge.on('launcher:close', () => {
        // Main thinks the panel is open but this renderer isn't showing it (a hot reload remounted it): let main hide
        // the window, or its invisible full-screen panel keeps the keyboard, every click and the island.
        if (phaseRef.current === 'closed') return bridge.emit('launcher:hidden')
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
  const teachKey = bridge.platform.os === 'mac' ? '⌘↵' : 'Ctrl↵'
  /** What a text lesson would be about: what's typed, else the query the rows on screen belong to. */
  const goal = typed || (view === 'idle' ? '' : search.query)
  /**
   * "Build a lesson from the internet": the fixed first row over a search's rows (not while the two ways are offered,
   * not for a settings word or a pasted link, not in ask mode). Same request as "Just teach me".
   */
  const lessonRow = mode === 'search' && !link && !settingsRow && !!goal && !choosing
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
  /**
   * During a lesson, with nothing typed: "Continue <lesson>" is the first row, highlighted (Enter goes back to the
   * lesson), and "End lesson" sits under it (↓ then Enter). Typing replaces both.
   */
  const resumeRows = lesson.hasLesson && !typed && (mode === 'ask' || view === 'idle')
  const highlight = view === 'link' || onLesson ? 0 : view === 'results' ? selIndex + off : -1
  /** The idle topic chips, minus the lesson in progress (or being built): never offer it again. */
  const current = lesson.hasLesson || lesson.building ? [lesson.title, topic.current].filter((t): t is string => !!t) : []
  const suggestions = SUGGESTIONS.filter((s) => !current.some((t) => sameTopic(s.label, t)))

  // ---- actions --------------------------------------------------------------------------------

  const learn = (q: string): void => {
    lastPick.current = undefined
    startSearch(q)
    delays.current.clear()
    setSel(0)
    bridge.send(cmd('learn', { query: q }))
  }

  /**
   * "Just teach me": no video search. The engine researches the topic and writes a text lesson (lesson.mode "lesson"),
   * so there are no rows to pick: the panel goes straight into the building pill, like Build lesson.
   * Only this path sends `mode`: "video" is the contract default, so the video flow's learn stays exactly as it was.
   */
  const teach = (q: string): void => {
    if (phaseRef.current !== 'open') return
    lastPick.current = undefined
    topic.current = q
    clearResults()
    bridge.send(cmd('learn', { query: q, mode: 'lesson' }))
    setPhase('building')
  }

  /** A click on one of the two ways picks it and starts it. */
  const pick = (h: How): void => {
    const q = query.trim()
    if (!q || phaseRef.current !== 'open') return
    setHow(h)
    if (h === 'lesson') teach(q)
    else learn(q)
  }

  const build = (i = selIndex): void => {
    if (phaseRef.current !== 'open') return
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

  /** End the lesson (Michael): the engine answers lesson.ended and core resets to idle; the panel goes back into the island. */
  const endLesson = (): void => {
    if (phaseRef.current !== 'open') return
    bridge.send(cmd('end_lesson', {}))
    setPhase('closing')
  }

  /** Settings has its own window (grown from the island by core); the launcher goes back into the island as usual. */
  const openSettings = (): void => {
    if (phaseRef.current !== 'open') return
    bridge.invoke('settings:open').catch(() => {})
    setPhase('closing')
  }

  const ask = (): void => {
    const text = question.trim()
    if (!text || phaseRef.current !== 'open') return
    bridge.send(cmd('action', { kind: 'ask', text }))
    markAsked()
    setPhase('sending')
  }

  /** During a lesson, Tab flips between asking about this step and starting a new lesson. */
  const switchMode = (): void => {
    if (!lesson.hasLesson || phaseRef.current !== 'open') return
    setMode((m) => (m === 'ask' ? 'search' : 'ask'))
  }

  const quick = (kind: 'explain' | 'hint'): void => {
    close()
    triggerShortcut(kind)
  }

  const suggest = (text: string): void => {
    if (phaseRef.current !== 'open') return
    setQuery(text)
    learn(text)
  }

  const submit = (): void => {
    if (settingsRow) return openSettings()
    // "Continue" goes back into the island and the lesson carries on; only a picked "End lesson" ends it.
    if (resumeRows) return pickEnd ? endLesson() : close()
    if (mode === 'ask') return ask()
    if (link) return build()
    if (onLesson) return teach(goal)
    const q = query.trim()
    if (!q) return
    if (choosing) return how === 'lesson' ? teach(q) : learn(q)
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
    if (e.key === 'Enter') {
      e.preventDefault()
      if (e.nativeEvent.isComposing) return
      // ⌘Enter (Ctrl+Enter on Windows) = "Just teach me" straight away, whichever way is highlighted.
      if ((e.metaKey || e.ctrlKey) && mode === 'search' && !link && !settingsRow && typed) return teach(typed)
      return submit()
    }
    if (e.key === 'Tab') {
      e.preventDefault() // focus stays in the field either way
      // While the two ways are offered, Tab switches between them; otherwise it flips ask / new lesson.
      if (choosing) return setHow((h) => (h === 'video' ? 'lesson' : 'video'))
      return switchMode()
    }
    // Continue / End lesson: ↓ picks End lesson, ↑ goes back to Continue.
    if (resumeRows && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      return setPickEnd(e.key === 'ArrowDown')
    }
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
  /** Grown, the panel is dark HUD glass (color.glass) with a hairline edge (below), like mockup 03, not the island's flat black. */
  const grown: TargetAndTransition = {
    width: WIDTH,
    height: contentH || from.h,
    borderRadius: radius.launcher,
    boxShadow: shadows.card,
    backgroundColor: color.glass
  }
  /** Reduced motion: crossfade at full size. Exit targets keep every key (a dropped key ends the animation early). */
  const faded = { ...grown, opacity: 0 }
  let target: TargetAndTransition = { ...grown, opacity: 1 }
  let transition: Transition = spring
  if (phase === 'closing' || phase === 'sending') {
    target = reduce ? faded : { ...shapeOf(from), opacity: 1 }
    transition = reduce ? { duration: 0.2 } : { ...springOut, ...settle }
  } else if (phase === 'building') {
    target = reduce ? faded : { ...shapeOf(PILL), opacity: 1 }
    transition = reduce ? { duration: 0.2 } : { ...spring, ...settle }
  }

  // What the island will show the moment it takes over again: its own content, drawn on the collapsed panel.
  const building = getIslandModes().find((m) => m.id === 'building')
  const returnTo = phase === 'building' ? building : islandMode

  const offline = !lesson.connected
  const inlineError = view === 'results' && search.error
  const act: Act = settingsRow
    ? 'settings'
    : resumeRows
    ? pickEnd
      ? 'end'
      : 'resume'
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
                : 'search'
              : retry
                ? 'search'
                : results.length
                  ? 'build'
                  : 'searching'
  const busy = search.pending && mode === 'search' && view !== 'link'
  /** The primary says what Enter does: named after the picked way to learn (Michael's audit A19), never a bare "Search". */
  const actLabel = {
    settings: 'Settings',
    resume: 'Continue',
    end: 'End lesson',
    ask: 'Ask',
    build: 'Build lesson',
    teach: 'Teach me',
    search: choosing ? 'Find videos' : 'Try again',
    searching: 'Searching…',
    none: ''
  }[act]
  /** Rows ↑↓ can move between right now: Continue / End lesson, or the lesson row plus the video rows (none while the two ways or Settings show). */
  const choices = resumeRows ? 2 : settingsRow || choosing ? 0 : off + (view === 'results' ? visible.length : 0)
  // The footer is keys, not sentences: only the offline / partial-error notes are words.
  const note = offline ? 'Offline' : inlineError ? search.error : undefined
  /** The best row: the one the engine marks "best", else the first. Only it gets a label. */
  const bestIndex = Math.max(0, visible.findIndex((r) => /best/i.test(r.reason)))

  return (
    <div key={gen} className="absolute inset-0" style={{ width: layout.width, height: layout.height }} data-launcher={phase}>
      {/* A light dim; click anywhere outside to collapse back into the island. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: scrim.launcher }}
        initial={{ opacity: 0 }}
        animate={{ opacity: phase === 'open' ? 1 : 0 }}
        transition={{ duration: phase === 'open' ? 0.16 : 0.24, ease: 'easeOut' }}
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
          <IslandContent mode={returnTo} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.14, delay: 0.12, ease: 'easeOut' }} />
        )}

        <motion.div
          ref={content}
          // flow-root: the first section's top margin must not collapse through, or the measured height comes up short and the panel clips the footer.
          className="flow-root"
          style={{ width: WIDTH, marginLeft: `calc(50% - ${WIDTH / 2}px)` }}
          initial={{ opacity: 0, y: 4 }}
          animate={exiting ? { opacity: 0, y: 0, transition: contentOut } : { opacity: 1, y: 0, transition: contentIn }}
        >
          {/* No title: the placeholder says it. In ask mode, one quiet line says where you are (color.label, so it reads: A20). */}
          {mode === 'ask' && (
            <Rise key="where" i={0} className="truncate px-[26px] pt-[16px] text-[12.5px] leading-[16px]">
              <span style={{ color: color.label }}>{lesson.hasStep ? `Step ${progress.index + 1} · ${lesson.stepTitle}` : lesson.title}</span>
            </Rise>
          )}

          <Rise i={1} className={`mx-[20px] ${mode === 'ask' ? 'mt-[10px]' : 'mt-[20px]'}`}>
            <div
              className="flex h-[52px] items-center gap-[12px] rounded-[14px] border px-[16px]"
              style={{ background: fill.field, borderColor: fill.fieldBorder }}
            >
              <span className="grid w-[17px] shrink-0 place-items-center" style={{ color: color.label }}>
                {busy ? (
                  <Spinner size={16} c={color.label} />
                ) : (
                  // The bonsai where the mockup had a sparkle (brand kit).
                  <MiyagiMark size={17} />
                )}
              </span>
              <input
                ref={input}
                value={mode === 'ask' ? question : query}
                onChange={(e) => {
                  setPickEnd(false) // cleared again, the rows come back on "Continue"
                  if (mode === 'ask') setQuestion(e.target.value)
                  else setQuery(e.target.value)
                }}
                onKeyDown={onKey}
                onPaste={onPaste}
                readOnly={phase !== 'open'}
                placeholder={mode === 'ask' ? 'Ask about this step' : copy.launcherPlaceholder}
                spellCheck={false}
                autoComplete="off"
                aria-label={mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
                className="h-full min-w-0 flex-1 bg-transparent text-[17px] text-white outline-none placeholder:text-white/30"
                style={{ caretColor: color.accent }}
              />
              {/* Decorative until voice queries land (see Notes). */}
              <Mic size={16} strokeWidth={1.6} className="shrink-0" style={{ color: color.faint }} />
            </div>
          </Rise>

          {resumeRows && (
            <Rise key="resume" i={2} className="pt-[8px]">
              <div className="relative mx-[20px]" style={{ height: 2 * ROW_H }}>
                <motion.div
                  className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]"
                  style={{ height: ROW_H, background: fill.highlight }}
                  initial={false}
                  animate={{ y: pickEnd ? ROW_H : 0 }}
                  transition={spring}
                />
                <ResumeRow
                  lessonTitle={lesson.title}
                  // Ask mode already names the step in the line above the field.
                  where={mode === 'search' && lesson.hasStep ? `Step ${progress.index + 1} of ${progress.total} · ${lesson.stepTitle}` : 'Where you left off'}
                  onHover={() => setPickEnd(false)}
                  onPick={close}
                />
                <EndRow slot={1} onHover={() => setPickEnd(true)} onPick={endLesson} />
              </div>
            </Rise>
          )}

          {settingsRow && (
            <Rise key="settings" i={2} className="pt-[8px]">
              <div className="relative mx-[20px]" style={{ height: ROW_H }}>
                <div className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]" style={{ height: ROW_H, background: fill.highlight }} />
                <SettingsRow onPick={openSettings} />
              </div>
            </Rise>
          )}

          {settingsRow ? null : choosing ? (
            <Rise key="how" i={2} className="px-[20px] pt-[12px]">
              <HowChoice how={how} onPick={pick} />
            </Rise>
          ) : mode === 'ask' ? (
            <Rise key="ask" i={2} className="flex flex-wrap gap-[8px] px-[20px] pt-[12px]">
              <OptionButton action="explain" label="Explain this step" kbd={bridge.platform.keys.explain} onClick={() => quick('explain')} />
              <OptionButton action="hint" label="Give me a hint" kbd={bridge.platform.keys.hint} onClick={() => quick('hint')} />
            </Rise>
          ) : view === 'idle' && !lessonRow ? (
            suggestions.length > 0 && (
              <Rise key="try" i={2} className="flex flex-wrap gap-[8px] px-[20px] pt-[12px]">
                {suggestions.map((s) => (
                  <Chip key={s.label} icon={s.icon} label={s.label} onClick={() => suggest(s.label)} />
                ))}
              </Rise>
            )
          ) : (
            slots > 0 && (
              <div className="pt-[8px]">
                <div className="relative mx-[20px]" style={{ height: slots * ROW_H }}>
                  <motion.div
                    className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]"
                    style={{ height: ROW_H, background: fill.highlight }}
                    initial={false}
                    animate={{ y: Math.max(0, highlight) * ROW_H, opacity: highlight >= 0 ? 1 : 0 }}
                    transition={spring}
                  />
                  <AnimatePresence initial={false}>
                    {view === 'link' && link && <LinkRow key={`link:${link.videoId}`} link={link} onPick={() => build()} />}
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

          {/* Footer: the keys that apply right now. Words only when something is wrong. */}
          <Rise i={3}>
            <div className="mt-[16px] h-px" style={{ background: fill.rule }} />
            <div className="flex h-[48px] items-center gap-[4px] pl-[18px] pr-[12px]">
              {/* Ask ↔ new lesson is navigation, not the action: quiet and on the far left, away from the primary, so a
                  lesson isn't restarted by accident (Michael's audit A20). */}
              {/* During a lesson the ask panel doesn't offer "New lesson" (Michael's tests 2-3, A13); Tab still flips to it. */}
              {lesson.hasLesson && !choosing && mode === 'search' && <Action label="Back to step" keycap="⇥" enabled onClick={switchMode} />}
              <span className="flex min-w-0 flex-1 items-center gap-[7px] pl-[6px] text-[13px]" style={{ color: color.text }}>
                {offline && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
                {note && <span className="truncate">{note}</span>}
              </span>
              {choices > 1 && <Hint label="Choose" keycap="↑↓" />}
              {choosing && (
                <>
                  <Hint label="Switch" keycap="⇥" />
                  {/* Each keycap once, here (not inside the chip): ⌘↵ teaches whichever way is picked; with "Just teach me" picked, ↵ already does. */}
                  {how === 'video' && <Hint label="Teach me" keycap={teachKey} />}
                </>
              )}
              {act === 'none' ? (
                // Nothing to do yet: no dimmed primary, just the way out.
                <Hint label="Close" keycap="esc" />
              ) : (
                <Action label={actLabel} keycap="↵" enabled={act !== 'searching'} strong onClick={submit} />
              )}
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
