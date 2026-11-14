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
 * Two modes, picked on open:
 *   search : learn {query} → rows stream in → Build lesson. A pasted YouTube link skips the search
 *            (one row, Enter sends learn_url {url}).
 *   ask    : a lesson exists → "Ask about this step" → action {kind:'ask', text}.
 *
 * Motion: one spring for the shape (width, height, radius together, like the island's own cards);
 * content crossfades (out 80ms; in after 60ms, rising 4px). Rows enter y 6 → 0 at least 40ms apart;
 * one highlight glides between them. Reduced motion: crossfades only.
 */
import { AnimatePresence, motion, useReducedMotion, type HTMLMotionProps, type TargetAndTransition, type Transition } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, CornerDownLeft, Lightbulb, MessageCircle, Mic, Sparkles, WifiOff, type LucideIcon } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson, useProgress } from '../../core/lesson'
import { getIslandModes, type IslandMode } from '../../core/registry'
import { triggerShortcut } from '../../core/shortcuts'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { clock, color, pill, radius, spring, springOut } from '../../core/theme'
import { LinkRow, MessageRow, ResultRow, ROW_H, SkeletonRow } from './Rows'
import { setLauncherOpen, startSearch, useSearch, type SearchResult } from './store'
import { tint } from './tint'
import { parseYouTube } from './youtube'

type Phase = 'closed' | 'open' | 'closing' | 'building' | 'sending'
type Mode = 'search' | 'ask'
type View = 'idle' | 'link' | 'searching' | 'results' | 'empty' | 'error'
type Size = { w: number; h: number }

/** Launcher width when grown out of the notch (theme.launcher.width is still the old 720: see Core requests). */
const WIDTH = 640
const MAX_ROWS = 4
const SKELETONS = 3
/** "Top results" label block above the rows. */
const LABEL_H = 34
/** Minimum gap between two rows' entrances, in seconds. */
const STAGGER = 0.04
/** The pill core's island lands on after Build lesson. */
const PILL: Size = { w: pill.landingWidth, h: pill.height }

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? tint.pillShadow : tint.cardShadow
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
  const [from, setFrom] = useState<Size>(PILL)
  /** The island's content is still fading out of the panel (first ~100ms after opening). */
  const [handoff, setHandoff] = useState(false)
  const [gen, setGen] = useState(0)
  const [query, setQuery] = useState('')
  const [question, setQuestion] = useState('')
  const [sel, setSel] = useState(0)

  const search = useSearch(useShallow((s) => ({ query: s.query, results: s.results, pending: s.pending, done: s.done, error: s.error })))
  const lesson = useLesson(useShallow((s) => ({ connected: s.connected, stepTitle: s.stepTitle, hasStep: !!s.stepId, hasLesson: !!s.lesson, title: s.lesson?.title })))
  const progress = useProgress()
  const islandMode = useIslandMode()
  const reduce = useReducedMotion()
  const input = useRef<HTMLInputElement>(null)
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
        delays.current.clear()
        setSel(0)
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
      onUi('reset', () => {
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
  const highlight = view === 'link' ? 0 : view === 'results' ? selIndex : -1

  // ---- actions --------------------------------------------------------------------------------

  const learn = (q: string): void => {
    startSearch(q)
    delays.current.clear()
    setSel(0)
    bridge.send(cmd('learn', { query: q }))
  }

  const build = (i = selIndex): void => {
    if (phaseRef.current !== 'open') return
    if (link) bridge.send(cmd('learn_url', { url: link.url }))
    else {
      if (!visible.length) return
      const first = visible[Math.min(i, visible.length - 1)].id
      bridge.send(cmd('build_lesson', { resultIds: [first, ...results.map((r) => r.id).filter((id) => id !== first)] }))
    }
    setPhase('building')
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

  const submit = (): void => {
    if (mode === 'ask') return ask()
    if (link) return build()
    const q = query.trim()
    if (!q) return
    if (q !== search.query || (!results.length && !search.pending)) learn(q)
    else build()
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation() // the stage's Esc would also dismiss cards
      return close()
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (!e.nativeEvent.isComposing) submit()
      return
    }
    if (e.key === 'Tab') {
      e.preventDefault() // focus stays in the field either way
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
  const grown: TargetAndTransition = { width: WIDTH, height: contentH || from.h, borderRadius: radius.launcher, boxShadow: tint.cardShadow }
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

  const minutes = estimateMinutes(results)
  const offline = !lesson.connected
  const inlineError = view === 'results' && search.error
  const hint = offline
    ? 'Engine offline · reconnecting…'
    : inlineError
      ? search.error
      : mode === 'ask'
        ? 'The answer appears in the island'
        : {
            idle: lesson.hasLesson ? 'A new lesson replaces this one' : 'Press ↵ to search · or paste a YouTube link',
            link: link?.start ? `Builds a lesson from ${clock(link.start)} on · each step auto-checked` : 'Builds a lesson straight from this video',
            searching: 'Finding the best tutorial…',
            results: `${minutes ? `about ${minutes} min · ` : ''}each step auto-checked`,
            empty: 'Try other words, or paste a YouTube link',
            error: 'Press ↵ to try again'
          }[view]
  const label = { idle: '', link: 'YouTube link', searching: 'Searching', results: search.pending ? 'Searching' : 'Top results', empty: 'No results', error: 'Search failed' }[view]
  const canGo = mode === 'ask' ? question.trim().length > 0 : view === 'link' || (view === 'results' && visible.length > 0)

  return (
    <div key={gen} className="absolute inset-0" style={{ width: layout.width, height: layout.height }} data-launcher={phase}>
      {/* A light dim; click anywhere outside to collapse back into the island. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: tint.dim }}
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
          style={{ width: WIDTH, marginLeft: `calc(50% - ${WIDTH / 2}px)` }}
          initial={{ opacity: 0, y: 4 }}
          animate={exiting ? { opacity: 0, y: 0, transition: contentOut } : { opacity: 1, y: 0, transition: contentIn }}
        >
          <motion.div
            key={mode}
            className="px-[28px] pt-[26px] text-center text-[22px] font-semibold leading-[28px] tracking-[-0.01em]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
          >
            {mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
          </motion.div>
          {mode === 'ask' && (
            <div className="mt-[4px] truncate px-[40px] text-center text-[13px]" style={{ color: color.faint }}>
              {lesson.hasStep ? (
                <>
                  Step {progress.index + 1} of {progress.total} · <span style={{ color: color.label }}>{lesson.stepTitle}</span>
                </>
              ) : (
                lesson.title
              )}
            </div>
          )}

          <div className="mx-[20px] mt-[16px] flex h-[54px] items-center gap-[12px] rounded-[14px] border px-[16px]" style={{ background: tint.field, borderColor: tint.fieldBorder }}>
            {mode === 'ask' ? (
              <MessageCircle size={18} strokeWidth={1.6} className="shrink-0 text-white/85" />
            ) : (
              <Sparkles size={18} strokeWidth={1.6} className="shrink-0 text-white/85" />
            )}
            <input
              ref={input}
              value={mode === 'ask' ? question : query}
              onChange={(e) => (mode === 'ask' ? setQuestion(e.target.value) : setQuery(e.target.value))}
              onKeyDown={onKey}
              onPaste={onPaste}
              readOnly={phase !== 'open'}
              placeholder={mode === 'ask' ? 'Ask anything about this step…' : 'Search a topic, or paste a YouTube link'}
              spellCheck={false}
              autoComplete="off"
              aria-label={mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
              className="h-full min-w-0 flex-1 bg-transparent text-[18px] text-white outline-none placeholder:text-white/30"
              style={{ caretColor: color.accent }}
            />
            <Mic size={17} strokeWidth={1.6} className="shrink-0 text-white/45" />
          </div>

          {mode === 'ask' ? (
            <div className="flex gap-[8px] px-[20px] pt-[12px]">
              <QuickChip icon={BookOpen} label="Explain this step" kbd={bridge.platform.keys.explain} onClick={() => quick('explain')} />
              <QuickChip icon={Lightbulb} label="Give me a hint" kbd={bridge.platform.keys.hint} onClick={() => quick('hint')} />
            </div>
          ) : (
            slots > 0 && (
              <div>
                <div className="flex items-end gap-[8px] px-[32px] pb-[6px] text-[12px] font-medium" style={{ height: LABEL_H, color: color.faint }}>
                  {label}
                  {search.pending && view !== 'link' && <Spinner size={11} />}
                </div>
                <div className="relative mx-[20px]" style={{ height: slots * ROW_H }}>
                  <motion.div
                    className="pointer-events-none absolute inset-x-0 top-0 rounded-[14px] border"
                    style={{ height: ROW_H, background: tint.highlight, borderColor: tint.highlightBorder }}
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
                          best={i === 0 || /best/i.test(r.reason)}
                          onHover={() => setSel(i)}
                          onPick={() => build(i)}
                        />
                      ))}
                    {Array.from({ length: skeletons }, (_, k) => (
                      <SkeletonRow key={`sk${visible.length + k}`} slot={visible.length + k} />
                    ))}
                    {view === 'empty' && <MessageRow key="empty" tone="empty" title={`Nothing found for “${search.query}”`} detail="No video, notebook or paper matched." />}
                    {view === 'error' && <MessageRow key="error" tone="error" title="Couldn't search right now" detail={search.error ?? ''} />}
                  </AnimatePresence>
                </div>
              </div>
            )
          )}

          <div className="flex items-center gap-[12px] pb-[18px] pl-[32px] pr-[20px] pt-[14px]">
            <span className="flex min-w-0 flex-1 items-center gap-[7px] text-[13px]" style={{ color: offline || inlineError ? color.amber : color.faint }}>
              {offline && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
              <span className="truncate">{hint}</span>
            </span>
            {lesson.hasLesson && (
              <button
                type="button"
                tabIndex={-1}
                className="flex h-[36px] shrink-0 cursor-pointer items-center gap-[8px] rounded-[18px] pl-[12px] pr-[6px] text-[13px] font-medium text-white/75 hover:text-white"
                onMouseDown={(e) => e.preventDefault()}
                onClick={switchMode}
              >
                {mode === 'ask' ? 'New lesson' : 'Ask about this step'}
                <Kbd className="!h-[22px] !rounded-[11px]">⇥</Kbd>
              </button>
            )}
            <motion.button
              type="button"
              tabIndex={-1}
              className="flex h-[36px] shrink-0 cursor-pointer items-center gap-[9px] rounded-[18px] pl-[16px] pr-[6px] text-[15px] font-semibold text-white disabled:cursor-default"
              style={{ background: color.accent, boxShadow: tint.accentGlow }}
              animate={{ opacity: canGo ? 1 : 0.35 }}
              whileTap={canGo ? { scale: 0.96 } : undefined}
              disabled={!canGo}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => (mode === 'ask' ? ask() : build())}
            >
              {mode === 'ask' ? 'Ask' : 'Build lesson'}
              <span className="grid h-[24px] w-[26px] place-items-center rounded-[12px]" style={{ background: tint.onAccent }}>
                <CornerDownLeft size={12} strokeWidth={2.2} />
              </span>
            </motion.button>
          </div>
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

function QuickChip({ icon: I, label, kbd, onClick }: { icon: LucideIcon; label: string; kbd: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="flex h-[32px] cursor-pointer items-center gap-[8px] rounded-[16px] pl-[12px] pr-[5px] text-[13px] font-medium text-white/85"
      style={{ background: tint.icon }}
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.09 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={14} strokeWidth={1.7} />
      {label}
      <Kbd className="!h-[22px] !rounded-[11px]">{kbd}</Kbd>
    </motion.button>
  )
}

/** "about 45 min": ~2.4× the best video's length, rounded to 5. */
function estimateMinutes(results: SearchResult[]): number | undefined {
  const v = results.find((r) => r.kind === 'video')
  const m = v?.meta.match(/(\d+):(\d{2})(?!.*\d+:\d{2})/)
  if (!m) return
  const mins = Number(m[1]) + Number(m[2]) / 60
  return Math.max(5, Math.round((mins * 2.4) / 5) * 5)
}
