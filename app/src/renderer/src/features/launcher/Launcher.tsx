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
 *   search : learn {query} → rows stream in → Build lesson. A pasted YouTube link skips the search
 *            (one row, Enter sends learn_url {url}). Idle shows a few suggestions; one click searches.
 *   ask    : a lesson exists → "Ask about this step" → action {kind:'ask', text}.
 *
 * Two ways to learn a typed topic (Michael, Sat 3:23 PM): "Watch a video" (the search flow above) or
 * "Just teach me" (learn {query, mode:"lesson"}: no video, the engine writes the lesson; the panel goes
 * straight into the building pill). Tab switches while they're offered, Enter picks, ⌘/Ctrl+Enter teaches.
 *
 * Look: the island's own language. Black, white text at the theme's label/faint levels, low-alpha
 * white fills, one hairline rule; the accent only for the caret and the best result. Footer actions
 * are label + keycap (Spotlight-style), not filled buttons.
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
import { EndRow, LinkRow, MessageRow, ResultRow, ROW_H, SkeletonRow } from './Rows'
import { clearResults, setLauncherOpen, startSearch, useSearch } from './store'
import { chipTones } from './tint'
import { parseYouTube } from './youtube'

type Phase = 'closed' | 'open' | 'closing' | 'building' | 'sending'
type Mode = 'search' | 'ask'
type View = 'idle' | 'link' | 'searching' | 'results' | 'empty' | 'error'
type Size = { w: number; h: number }
/** What Enter (and the footer action) would do right now. Mirrors submit(). */
type Act = 'end' | 'ask' | 'build' | 'search' | 'searching' | 'none'

/** Launcher width when grown out of the notch. */
const WIDTH = launcherTheme.width
const MAX_ROWS = 4
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

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? shadows.pill : shadows.card
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

  const search = useSearch(useShallow((s) => ({ query: s.query, results: s.results, pending: s.pending, done: s.done, error: s.error })))
  const lesson = useLesson(
    useShallow((s) => ({ connected: s.connected, stepTitle: s.stepTitle, hasStep: !!s.stepId, hasLesson: !!s.lesson, title: s.lesson?.title }))
  )
  const progress = useProgress()
  const islandMode = useIslandMode()
  const reduce = useReducedMotion()
  const input = useRef<HTMLInputElement>(null)
  /** The row Build last sent, so reopening (the preflight card's "Pick another") highlights the next one. */
  const lastPick = useRef<string | undefined>(undefined)
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
      if (exit === 'sending') setQuestion('')
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
  useEffect(() => bridge.on('launcher:close', close), [close])
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
    if (mode === 'search') input.current?.select()
  }, [phase, gen, mode])

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
  const slots = view === 'idle' ? 0 : view === 'results' || view === 'searching' ? Math.min(MAX_ROWS, visible.length + skeletons) : 1
  const selIndex = Math.min(sel, Math.max(0, visible.length - 1))
  const typed = (mode === 'ask' ? question : query).trim()
  /** During a lesson, with nothing typed: "End lesson" is the first row, highlighted. Typing replaces it. */
  const endRow = lesson.hasLesson && !typed && (mode === 'ask' || view === 'idle')
  /**
   * A topic is typed and Enter would start something new (not build a result already listed): offer the two ways
   * to learn it, "Watch a video" (today's search flow) or "Just teach me" (learn {mode:"lesson"}, no video).
   */
  const choosing = mode === 'search' && !link && !!typed && (typed !== search.query || (!results.length && !search.pending))
  const teachKey = bridge.platform.os === 'mac' ? '⌘↵' : 'Ctrl↵'
  const highlight = view === 'link' ? 0 : view === 'results' ? selIndex : -1

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
      clearResults()
      bridge.send(cmd('learn_url', { url: link.url }))
    } else {
      if (!visible.length) return
      const first = visible[Math.min(i, visible.length - 1)].id
      lastPick.current = first
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

  const ask = (): void => {
    const text = question.trim()
    if (!text || phaseRef.current !== 'open') return
    bridge.send(cmd('action', { kind: 'ask', text }))
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
    if (endRow) return endLesson()
    if (mode === 'ask') return ask()
    if (link) return build()
    const q = query.trim()
    if (!q) return
    if (choosing) return how === 'lesson' ? teach(q) : learn(q)
    build()
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation() // the stage's Esc would also dismiss cards
      return close()
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (e.nativeEvent.isComposing) return
      // ⌘Enter (Ctrl+Enter on Windows) = "Just teach me" straight away, whichever way is highlighted.
      if ((e.metaKey || e.ctrlKey) && mode === 'search' && !link && typed) return teach(typed)
      return submit()
    }
    if (e.key === 'Tab') {
      e.preventDefault() // focus stays in the field either way
      // While the two ways are offered, Tab switches between them; otherwise it flips ask / new lesson.
      if (choosing) return setHow((h) => (h === 'video' ? 'lesson' : 'video'))
      return switchMode()
    }
    if (view !== 'results') return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSel(Math.min(visible.length - 1, selIndex + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSel(Math.max(0, selIndex - 1))
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
  const grown: TargetAndTransition = { width: WIDTH, height: contentH || from.h, borderRadius: radius.launcher, boxShadow: shadows.card }
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
  const act: Act = endRow
    ? 'end'
    : mode === 'ask'
      ? typed
        ? 'ask'
        : 'none'
      : link
        ? 'build'
        : !typed
          ? 'none'
          : typed !== search.query || (!results.length && !search.pending)
            ? 'search'
            : results.length
              ? 'build'
              : 'searching'
  const busy = search.pending && mode === 'search' && view !== 'link'
  const actLabel = {
    end: 'End lesson',
    ask: 'Ask',
    build: 'Build lesson',
    search: how === 'lesson' ? 'Start lesson' : 'Search',
    searching: 'Searching…',
    none: mode === 'ask' ? 'Ask' : 'Search'
  }[act]
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
        style={{ top: bridge.platform.pillTop, x: '-50%', background: color.island, transformOrigin: '50% 0%' }}
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
          {/* No title: the placeholder says it. In ask mode, one faint line says where you are. */}
          {mode === 'ask' && (
            <Rise key="where" i={0} className="truncate px-[26px] pt-[16px] text-[12.5px] leading-[16px]">
              <span style={{ color: color.faint }}>{lesson.hasStep ? `Step ${progress.index + 1} · ${lesson.stepTitle}` : lesson.title}</span>
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
                onChange={(e) => (mode === 'ask' ? setQuestion(e.target.value) : setQuery(e.target.value))}
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

          {endRow && (
            <Rise key="end" i={2} className="pt-[8px]">
              <div className="relative mx-[20px]" style={{ height: ROW_H }}>
                <div className="pointer-events-none absolute inset-x-0 top-0 rounded-[12px]" style={{ height: ROW_H, background: fill.highlight }} />
                <EndRow lessonTitle={lesson.title} onPick={endLesson} />
              </div>
            </Rise>
          )}

          {choosing ? (
            <Rise key="how" i={2} className="px-[20px] pt-[12px]">
              <HowChoice how={how} teachKey={teachKey} onPick={pick} />
            </Rise>
          ) : mode === 'ask' ? (
            <Rise key="ask" i={2} className="flex flex-wrap gap-[8px] px-[20px] pt-[12px]">
              <OptionButton action="explain" label="Explain this step" kbd={bridge.platform.keys.explain} onClick={() => quick('explain')} />
              <OptionButton action="hint" label="Give me a hint" kbd={bridge.platform.keys.hint} onClick={() => quick('hint')} />
            </Rise>
          ) : view === 'idle' ? (
            <Rise key="try" i={2} className="flex flex-wrap gap-[8px] px-[20px] pt-[12px]">
              {SUGGESTIONS.map((s, i) => (
                <Chip key={s.label} icon={s.icon} label={s.label} tone={chipTones[i % chipTones.length]} onClick={() => suggest(s.label)} />
              ))}
            </Rise>
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
                    {(view === 'results' || view === 'searching') &&
                      visible.map((r, i) => (
                        <ResultRow
                          key={r.id}
                          slot={i}
                          delay={delayFor(r.id)}
                          r={r}
                          best={i === bestIndex}
                          onHover={() => setSel(i)}
                          onPick={() => build(i)}
                        />
                      ))}
                    {Array.from({ length: skeletons }, (_, k) => (
                      <SkeletonRow key={`sk${visible.length + k}`} slot={visible.length + k} />
                    ))}
                    {view === 'empty' && (
                      <MessageRow key="empty" tone="empty" title={`Nothing found for “${search.query}”`} detail="Try other words, or paste a YouTube link." />
                    )}
                    {view === 'error' && <MessageRow key="error" tone="error" title="Couldn't search right now" detail={search.error ?? ''} />}
                  </AnimatePresence>
                </div>
              </div>
            )
          )}

          {/* Footer: the keys that apply right now. Words only when something is wrong. */}
          <Rise i={3}>
            <div className="mt-[16px] h-px" style={{ background: fill.rule }} />
            <div className="flex h-[48px] items-center gap-[4px] pl-[24px] pr-[12px]">
              <span className="flex min-w-0 flex-1 items-center gap-[7px] text-[13px]" style={{ color: color.text }}>
                {offline && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
                {note && <span className="truncate">{note}</span>}
              </span>
              {view === 'results' && visible.length > 1 && <Hint label="Choose" keycap="↑↓" />}
              {choosing ? (
                <Hint label="Switch" keycap="⇥" />
              ) : (
                lesson.hasLesson && (
                  <>
                    <Action label={mode === 'ask' ? 'New lesson' : 'Back to step'} keycap="⇥" enabled onClick={switchMode} />
                    <span className="mx-[4px] h-[16px] w-px shrink-0" style={{ background: fill.rule }} />
                  </>
                )
              )}
              <Action label={actLabel} keycap="↵" enabled={act === 'end' || act === 'ask' || act === 'build' || act === 'search'} strong onClick={submit} />
            </div>
          </Rise>
        </motion.div>
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
