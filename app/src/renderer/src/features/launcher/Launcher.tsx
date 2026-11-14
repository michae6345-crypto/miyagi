/**
 * Spotlight-style launcher (⌥Space · Ctrl+Shift+Space on Windows · Ctrl+K in the browser stage).
 *
 * Two modes, picked when it opens:
 *   search : "What do you want to learn?" → learn {query} → rows stream in → Build lesson.
 *            A pasted YouTube link skips the search: one row, Enter sends learn_url {url}.
 *   ask    : during a lesson, "Ask about this step" → action {kind:'ask', text}. The answer comes
 *            back as card {kind:'answer'} (the cards feature renders it), so the launcher closes.
 *
 * Motion (FRONTEND-HANDOFF.md → Animation spec):
 *   open     backdrop dims 0 → .35 over 160ms; panel scale .96 → 1, y -8 → 0, opacity on the spring.
 *   rows     y 6 → 0 + fade, at least 40ms apart (a batch staggers; a stream just flows in).
 *   select   one highlight glides between rows (↑↓ / hover) on the spring.
 *   build    THE signature transition: the panel itself morphs onto the pill's exact rect
 *            (top = platform.pillTop, 300×34, radius 17, black, pill shadow) while its content fades
 *            and the pill's own "building" content fades in. Then main swaps windows
 *            (launcher:built → pill:receive) and the island continues from the same pixels.
 *   ask      the panel flies into the pill and fades out (the answer card then grows out of it).
 */
import { AnimatePresence, motion, useReducedMotion, type TargetAndTransition, type Transition } from 'motion/react'
import { useCallback, useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, CornerDownLeft, Lightbulb, MessageCircle, Mic, Sparkles, WifiOff, type LucideIcon } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson, useProgress } from '../../core/lesson'
import { islandModes } from '../../core/registry'
import { triggerShortcut } from '../../core/shortcuts'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { clock, color, launcher as L, pill, radius, shadow, spring } from '../../core/theme'
import { LinkRow, MessageRow, ResultRow, ROW_H, SkeletonRow } from './Rows'
import { setLauncherOpen, startSearch, useSearch, type SearchResult } from './store'
import { tint } from './tint'
import { parseYouTube } from './youtube'

type Phase = 'closed' | 'open' | 'closing' | 'building' | 'sending'
type Mode = 'search' | 'ask'
type View = 'idle' | 'link' | 'searching' | 'results' | 'empty' | 'error'

const MAX_ROWS = 4
const SKELETONS = 3
/** "Top results" label block above the rows. */
const LABEL_H = 40
/** Minimum gap between two rows' entrances, in seconds. */
const STAGGER = 0.04
/** Inner width (the panel has a 1px border). */
const INNER = L.width - 2

export function Launcher({ layout, openOnMount = false }: { layout: Layout; openOnMount?: boolean }): ReactNode {
  const [phase, setPhaseState] = useState<Phase>(openOnMount ? 'open' : 'closed')
  const phaseRef = useRef(phase)
  const setPhase = useCallback((p: Phase) => {
    phaseRef.current = p
    setPhaseState(p)
  }, [])
  const [mode, setMode] = useState<Mode>('search')
  const [gen, setGen] = useState(0)
  const [query, setQuery] = useState('')
  const [question, setQuestion] = useState('')
  const [sel, setSel] = useState(0)

  const search = useSearch(useShallow((s) => ({ query: s.query, results: s.results, pending: s.pending, done: s.done, error: s.error })))
  const lesson = useLesson(useShallow((s) => ({ connected: s.connected, stepTitle: s.stepTitle, hasStep: !!s.stepId, title: s.lesson?.title })))
  const progress = useProgress()
  const reduce = useReducedMotion()
  const input = useRef<HTMLInputElement>(null)
  /** Per-row entrance delays (see delayFor). */
  const delays = useRef(new Map<string, number>())
  const lastEntry = useRef(0)

  // ---- open / close ---------------------------------------------------------------------------

  const close = useCallback(() => {
    if (phaseRef.current === 'open') setPhase('closing')
  }, [setPhase])

  /** End of an exit animation (or its safety timer): hand back to main exactly once. */
  const finish = useCallback(
    (from: Phase) => {
      if (from === 'open' || from === 'closed' || phaseRef.current !== from) return
      setPhase('closed')
      if (from === 'sending') setQuestion('')
      bridge.emit(from === 'building' ? 'launcher:built' : 'launcher:hidden')
    },
    [setPhase]
  )

  useEffect(
    () =>
      bridge.on('launcher:open', () => {
        setMode(useLesson.getState().lesson ? 'ask' : 'search')
        delays.current.clear()
        setSel(0)
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

  // If an exit animation can't finish (e.g. the window stops painting), don't leave the launcher stuck.
  useEffect(() => {
    if (phase === 'open' || phase === 'closed') return
    const t = setTimeout(() => finish(phase), phase === 'closing' ? 400 : 1200)
    return () => clearTimeout(t)
  }, [phase, finish])

  // The caret is live the moment the panel appears.
  useEffect(() => {
    if (phase !== 'open') return
    input.current?.focus()
    if (mode === 'search') input.current?.select()
  }, [phase, gen, mode])

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

  const top = Math.round(layout.height * L.topRatio)
  const exiting = phase === 'building' || phase === 'sending'
  const panelOpen = { opacity: 1, scale: 1, y: 0, top, width: L.width, borderRadius: radius.launcher, backgroundColor: color.glass, borderColor: color.hairline, boxShadow: shadow }
  /** The pill's exact pixels (core/Island.tsx lands at pill.landingWidth × pill.height). */
  const onPill = {
    scale: 1,
    y: 0,
    top: bridge.platform.pillTop,
    width: pill.landingWidth,
    height: pill.height,
    borderRadius: pill.height / 2,
    backgroundColor: color.island,
    borderColor: tint.clear,
    boxShadow: tint.pillShadow
  }
  /** Reduced motion: crossfade only. Keep every key of the open target (a dropped key settles instantly and ends the animation early). */
  const fadeOut = { ...panelOpen, opacity: 0 }
  let target: TargetAndTransition = panelOpen
  let transition: Transition = spring
  if (phase === 'closing') {
    target = { ...panelOpen, opacity: 0, scale: 0.96, y: -8 }
    transition = { duration: 0.14, ease: 'easeIn' }
  } else if (phase === 'building') {
    target = reduce ? fadeOut : { ...onPill, opacity: 1 }
    transition = reduce ? { duration: 0.2 } : spring
  } else if (phase === 'sending') {
    target = reduce ? fadeOut : { ...onPill, opacity: 0 }
    transition = reduce ? { duration: 0.2 } : { ...spring, opacity: { duration: 0.16, delay: 0.2, ease: 'easeIn' } }
  }

  // What the pill shows while building, so the landed panel and the island are the same pixels.
  const Landing = islandModes.find((m) => m.id === 'building')?.Content ?? BuildingFallback

  const minutes = estimateMinutes(results)
  const offline = !lesson.connected
  const inlineError = view === 'results' && search.error
  const hint = offline
    ? 'Engine offline · reconnecting…'
    : inlineError
      ? search.error
      : mode === 'ask'
        ? 'The answer appears under the pill'
        : {
            idle: 'Press ↵ to search · or paste a YouTube link',
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
      {/* Backdrop: dims (and, where the platform allows, blurs) the desktop. Click to dismiss. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: tint.dim, backdropFilter: 'blur(14px) saturate(1.1)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: phase === 'open' ? 1 : 0 }}
        transition={{ duration: phase === 'open' ? 0.16 : exiting ? 0.36 : 0.14, ease: 'easeOut' }}
        onClick={close}
      />

      <motion.div
        className="absolute left-1/2 overflow-hidden border"
        style={{ x: '-50%', transformOrigin: '50% 0%' }}
        initial={{ ...panelOpen, opacity: 0, scale: 0.96, y: -8 }}
        animate={target}
        transition={transition}
        onAnimationComplete={() => finish(phase)}
      >
        <motion.div
          style={{ width: INNER, marginLeft: `calc(50% - ${INNER / 2}px)`, transformOrigin: '50% 0%' }}
          initial={false}
          animate={exiting ? { opacity: 0, scale: 0.97 } : { opacity: 1, scale: 1 }}
          transition={{ duration: exiting ? 0.12 : 0.2, ease: 'easeOut' }}
        >
          <div className="pt-[30px] text-center text-[28px] font-semibold leading-[34px] tracking-[-0.02em] text-white">
            {mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
          </div>
          {mode === 'ask' && (
            <div className="mt-[6px] truncate px-[40px] text-center text-[13px]" style={{ color: color.faint }}>
              {lesson.hasStep ? (
                <>
                  Step {progress.index + 1} of {progress.total} · <span style={{ color: color.label }}>{lesson.stepTitle}</span>
                </>
              ) : (
                lesson.title
              )}
            </div>
          )}

          <div className="mx-[26px] mt-[22px] flex h-[60px] items-center gap-[14px] rounded-[16px] border px-[20px]" style={{ background: tint.field, borderColor: tint.fieldBorder }}>
            {mode === 'ask' ? (
              <MessageCircle size={20} strokeWidth={1.6} className="shrink-0 text-white/85" />
            ) : (
              <Sparkles size={20} strokeWidth={1.6} className="shrink-0 text-white/85" />
            )}
            <input
              ref={input}
              value={mode === 'ask' ? question : query}
              onChange={(e) => (mode === 'ask' ? setQuestion(e.target.value) : setQuery(e.target.value))}
              onKeyDown={onKey}
              onPaste={onPaste}
              readOnly={phase !== 'open'}
              placeholder={mode === 'ask' ? 'Ask anything about this step…' : 'Train a PINN, fine-tune Llama, build a ray tracer…'}
              spellCheck={false}
              autoComplete="off"
              aria-label={mode === 'ask' ? 'Ask about this step' : 'What do you want to learn?'}
              className="h-full min-w-0 flex-1 bg-transparent text-[20px] text-white outline-none placeholder:text-white/30"
              style={{ caretColor: color.accent }}
            />
            <Mic size={18} strokeWidth={1.6} className="shrink-0 text-white/45" />
          </div>

          {mode === 'ask' ? (
            <div className="flex gap-[8px] px-[26px] pt-[14px]">
              <QuickChip icon={BookOpen} label="Explain this step" kbd={bridge.platform.keys.explain} onClick={() => quick('explain')} />
              <QuickChip icon={Lightbulb} label="Give me a hint" kbd={bridge.platform.keys.hint} onClick={() => quick('hint')} />
            </div>
          ) : (
            <motion.div className="overflow-hidden" initial={false} animate={{ height: slots ? LABEL_H + slots * ROW_H : 0 }} transition={spring}>
              <div className="flex items-end gap-[8px] px-[36px] pb-[6px] text-[13px] font-medium" style={{ height: LABEL_H, color: color.faint }}>
                {label}
                {search.pending && view !== 'link' && <Spinner size={12} />}
              </div>
              <div className="relative mx-[26px]" style={{ height: Math.max(1, slots) * ROW_H }}>
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
            </motion.div>
          )}

          <div className="flex items-center gap-[12px] pb-[21px] pl-[38px] pr-[32px] pt-[18px]">
            <span className="flex min-w-0 flex-1 items-center gap-[7px] text-[13px]" style={{ color: offline || inlineError ? color.amber : color.faint }}>
              {offline && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
              <span className="truncate">{hint}</span>
            </span>
            <motion.button
              type="button"
              tabIndex={-1}
              className="flex h-[40px] shrink-0 cursor-pointer items-center gap-[10px] rounded-[20px] pl-[18px] pr-[8px] text-[16px] font-semibold text-white disabled:cursor-default"
              style={{ background: color.accent, boxShadow: tint.accentGlow }}
              animate={{ opacity: canGo ? 1 : 0.35 }}
              whileTap={canGo ? { scale: 0.96 } : undefined}
              disabled={!canGo}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => (mode === 'ask' ? ask() : build())}
            >
              {mode === 'ask' ? 'Ask' : 'Build lesson'}
              <span className="grid h-[24px] w-[28px] place-items-center rounded-[12px]" style={{ background: tint.onAccent }}>
                <CornerDownLeft size={13} strokeWidth={2.2} />
              </span>
            </motion.button>
          </div>
        </motion.div>

        {/* Landing: the pill's own content fades in as the panel reaches the pill's rect. */}
        {phase === 'building' && !reduce && (
          <motion.div
            className="pointer-events-none absolute inset-0 flex items-center justify-center text-white"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.16, delay: 0.2, ease: 'easeOut' }}
          >
            <Landing />
          </motion.div>
        )}
      </motion.div>
    </div>
  )
}

function QuickChip({ icon: I, label, kbd, onClick }: { icon: LucideIcon; label: string; kbd: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="flex h-[34px] cursor-pointer items-center gap-[8px] rounded-[17px] pl-[12px] pr-[6px] text-[13px] font-medium text-white/85"
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

/** Same as the pill's building state, in case no feature registers one. */
function BuildingFallback(): ReactNode {
  const msg = useLesson((s) => s.buildingMessage)
  return (
    <div className="flex h-[34px] items-center gap-[9px] whitespace-nowrap px-[14px] text-[13px] font-medium">
      <Spinner size={14} />
      <span className="text-white/85">{msg ?? 'Building your lesson'}</span>
    </div>
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
