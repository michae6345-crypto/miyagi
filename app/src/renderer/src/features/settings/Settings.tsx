/**
 * Feature: settings. The Settings sheet, born from the notch island (its own focusable window, route `settings`).
 * Two sections: General (General.tsx: appearance, read aloud, open at login; applied at once through core
 * prefs) and Keys (below; applied on Save). The sheet stays black in every appearance, like the island. It
 * never grows past the screen: past that, the key rows scroll inside it.
 *
 * Opening: `settings:open {from}` (main) / requestOpen (browser stage) carries the island's current size. The
 * sheet starts on exactly that shape (top = platform.pillTop, centered, black, shadows.pill or .card) and
 * springs down into the sheet; the island hides once the sheet has painted (island:yield). Every exit
 * (Esc, ✕, click outside, the window losing focus) collapses it onto the island's CURRENT size (it may have
 * shrunk from the overview card back to the pill meanwhile), fades the island's content back in, then
 * island:return + settings:hidden. Typed, unsaved values are dropped on close.
 *
 * Keys never come back from main: each row shows `•••• last4`. An empty field = unchanged; Clear marks the
 * key for removal (Undo until Save). Save sends only what changed; main merges, encrypts and sends the FULL
 * config.keys. Status per key comes from config.status (useLesson keyStatus): white dot = your key, gray dot
 * "From engine" = the engine's .env, ring = missing, "Invalid" in white. Never green or amber here.
 * Test re-sends config.keys and waits for config.status (spinner, 3 s → "No answer from Miyagi").
 */
import { motion, useReducedMotion, type HTMLMotionProps, type TargetAndTransition, type Transition } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { WifiOff, X } from 'lucide-react'
import type { KeyState } from '../../../../../../shared/contracts/events'
import type { Layout } from '../../../../preload/api'
import { bridge, isElectron } from '../../bridge'
import { onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { getIslandModes, type IslandMode } from '../../core/registry'
import { PrimaryButton, Spinner } from '../../core/ui/atoms'
import { color, fill, pill, radius, scrim, shadows, spring, springOut } from '../../core/theme'
import { General, SectionLabel } from './General'
import { KEY_NAMES, REQUIRED, type KeyInfo, type KeyName, type KeysView, type SavePatch } from './keys'
import { nextStatus, useSettings, type Size } from './store'

type Phase = 'closed' | 'open' | 'closing'

/** The island's widest card. */
const WIDTH = pill.maxCardWidth
const PILL: Size = { w: pill.landingWidth, h: pill.height }

const LABEL: Record<KeyName, string> = {
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  brightdata: 'Bright Data',
  elevenlabs: 'ElevenLabs',
  tigerUrl: 'Tiger Data URL'
}

const isRequired = (k: KeyName): boolean => REQUIRED.includes(k)

/** Rows shown in the sheet. ElevenLabs is hidden: voice speaks with the computer's own voice now (Adrian, Sat),
 * but the key name stays in storage and in config.keys so the engine contract is unchanged. */
const SHOWN = KEY_NAMES.filter((k) => k !== 'elevenlabs')

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? shadows.pill : shadows.card
})
const validSize = (s: unknown): s is Size => !!s && typeof s === 'object' && (s as Size).w > 0 && (s as Size).h > 0
const round = (s: Size): Size => ({ w: Math.round(s.w), h: Math.round(s.h) })

/** Exits hand the island back once the shape is within a pixel. */
const settle = { restDelta: 1, restSpeed: 30 }
const contentIn: Transition = { duration: 0.2, delay: 0.06, ease: 'easeOut' }
const contentOut: Transition = { duration: 0.08 }
/** Test's spinner shows at least this long, so a fast answer still reads as "checked". */
const MIN_SPIN = 450

const NO_ANSWER = 'No answer from Miyagi'
/** Space kept free under the sheet when it would otherwise reach the bottom of the screen. */
const BOTTOM_MARGIN = 24

/** Which island mode the island is showing right now (core/Island's rule, without hover). */
function useIslandMode(): IslandMode | undefined {
  const modes = getIslandModes()
  const wanted = modes.map((m) => m.useActive(false))
  return modes.find((_, i) => wanted[i])
}

export function Settings({ layout }: { layout: Layout }): ReactNode {
  const [phase, setPhaseState] = useState<Phase>('closed')
  const phaseRef = useRef(phase)
  const setPhase = useCallback((p: Phase) => {
    phaseRef.current = p
    setPhaseState(p)
  }, [])
  const [from, setFrom] = useState<Size>(PILL)
  /** Where the collapse lands: the island's size when closing started. */
  const [to, setTo] = useState<Size>(PILL)
  const [gen, setGen] = useState(0)
  const [handoff, setHandoff] = useState(false)

  const [view, setView] = useState<KeysView>()
  const [drafts, setDrafts] = useState<Partial<Record<KeyName, string>>>({})
  const [cleared, setCleared] = useState<KeyName[]>([])
  const [saving, setSaving] = useState(false)
  /** Rows whose new value went out and whose config.status hasn't come back yet. */
  const [waiting, setWaiting] = useState<KeyName[]>([])
  const [testing, setTesting] = useState(false)
  const [note, setNote] = useState<string>()

  const engineStatus = useLesson((s) => s.keyStatus)
  const connected = useLesson((s) => s.connected)
  const status = engineStatus ?? view?.status
  const openReq = useSettings((s) => s.open)
  const closeReq = useSettings((s) => s.close)
  const islandMode = useIslandMode()
  const reduce = useReducedMotion()
  const inputs = useRef<Partial<Record<KeyName, HTMLInputElement | null>>>({})

  // ---- open / close ---------------------------------------------------------------------------

  useEffect(() => {
    if (!openReq.seq || phaseRef.current !== 'closed') return
    const f = validSize(openReq.from) ? round(openReq.from) : PILL
    setFrom(f)
    setTo(f)
    setDrafts({})
    setCleared([])
    setWaiting([])
    setSaving(false)
    setTesting(false)
    setNote(undefined)
    setHandoff(true)
    setGen((g) => g + 1)
    setPhase('open')
    bridge
      .invoke<KeysView>('settings:get')
      .then(setView)
      .catch(() => {})
  }, [openReq, setPhase])

  const close = useCallback(() => {
    if (phaseRef.current !== 'open') return
    // Land on the island as it is now; fall back to where we came from.
    const land = (s: unknown): void => {
      if (phaseRef.current !== 'open') return
      setTo(validSize(s) ? round(s) : from)
      setPhase('closing')
    }
    bridge.invoke<Size | undefined>('settings:island').then(land, () => land(undefined))
  }, [from, setPhase])

  /** End of the collapse (or its safety timer): hand the island back exactly once. */
  const finish = useCallback(() => {
    if (phaseRef.current !== 'closing') return
    setPhase('closed')
    setDrafts({})
    setCleared([])
    bridge.emit('island:return')
    bridge.invoke('settings:hidden').catch(() => {})
  }, [setPhase])

  useEffect(() => {
    if (closeReq) close()
  }, [closeReq]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const offs = [
      onUi('dismiss', () => void close()),
      onUi('reset', (p) => {
        if ((p as { scope?: string } | undefined)?.scope !== 'lesson') close()
      })
    ]
    return () => offs.forEach((off) => off())
  }, [close])

  // The island hides once the sheet has painted on top of it (rAF doesn't run in a hidden tab: timer fallback).
  useEffect(() => {
    if (phase !== 'open') return
    let done = false
    const yieldIsland = (): void => {
      if (done) return
      done = true
      bridge.emit('island:yield')
    }
    const t = setTimeout(yieldIsland, 50)
    const raf = requestAnimationFrame(() => requestAnimationFrame(yieldIsland))
    return () => {
      clearTimeout(t)
      cancelAnimationFrame(raf)
    }
  }, [phase, gen])

  useEffect(() => {
    if (!handoff) return
    const t = setTimeout(() => setHandoff(false), 160)
    return () => clearTimeout(t)
  }, [handoff, gen])

  // If the collapse can't finish (the window stops painting), don't leave the island hidden.
  useEffect(() => {
    if (phase !== 'closing') return
    const t = setTimeout(finish, 1200)
    return () => clearTimeout(t)
  }, [phase, finish])

  // Electron: Esc anywhere in this window. (The stage's own Esc emits 'dismiss'.)
  useEffect(() => {
    if (!isElectron || phase !== 'open') return
    const onKey = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape') close()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [phase, close])

  // The caret goes where a key is needed first: a required key with no source, else the first row.
  useEffect(() => {
    if (phase !== 'open') return
    const first = KEY_NAMES.find((k) => isRequired(k) && status?.[k] === 'missing') ?? KEY_NAMES[0]
    inputs.current[first]?.focus({ preventScroll: true })
  }, [phase, gen]) // eslint-disable-line react-hooks/exhaustive-deps

  // The sheet springs to its content's height.
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

  // ---- actions --------------------------------------------------------------------------------

  const dirty = KEY_NAMES.some((k) => drafts[k]?.trim()) || cleared.length > 0

  const save = async (): Promise<void> => {
    if (!dirty || saving || phaseRef.current !== 'open') return
    const patch: SavePatch = {}
    for (const k of KEY_NAMES) {
      const d = drafts[k]?.trim()
      if (d) patch[k] = d
      else if (cleared.includes(k)) patch[k] = null
    }
    const changed = Object.keys(patch) as KeyName[]
    const since = useSettings.getState().statusSeq
    setSaving(true)
    setNote(undefined)
    try {
      const v = await bridge.invoke<KeysView>('settings:save', patch)
      setView(v)
      setDrafts({})
      setCleared([])
      if (v.error) setNote(v.error)
    } catch {
      setSaving(false)
      setNote('Couldn’t save')
      return
    }
    setWaiting(changed)
    const answered = await nextStatus(since)
    setWaiting([])
    setSaving(false)
    if (!answered) setNote(NO_ANSWER)
  }

  const test = async (): Promise<void> => {
    if (testing || phaseRef.current !== 'open') return
    const since = useSettings.getState().statusSeq
    const started = performance.now()
    setTesting(true)
    setNote(undefined)
    bridge.invoke('settings:test').catch(() => {})
    const answered = await nextStatus(since)
    await new Promise((r) => setTimeout(r, Math.max(0, MIN_SPIN - (performance.now() - started))))
    setTesting(false)
    if (!answered) setNote(NO_ANSWER)
  }

  const setDraft = (k: KeyName, v: string): void => {
    setDrafts((d) => ({ ...d, [k]: v }))
    if (v) setCleared((c) => c.filter((x) => x !== k))
  }

  const toggleClear = (k: KeyName): void => {
    setDrafts((d) => ({ ...d, [k]: '' }))
    setCleared((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]))
    inputs.current[k]?.focus({ preventScroll: true })
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation() // the stage's Esc would also dismiss cards
      return close()
    }
    if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.target instanceof HTMLInputElement) {
      e.preventDefault()
      void save()
    }
  }

  if (phase === 'closed') return null

  // ---- motion targets -------------------------------------------------------------------------

  const exiting = phase === 'closing'
  const grown: TargetAndTransition = { width: WIDTH, height: contentH || from.h, borderRadius: radius.island, boxShadow: shadows.card }
  /** Reduced motion: crossfade at full size. Exit targets keep every key (a dropped key ends the animation early). */
  const faded = { ...grown, opacity: 0 }
  const target: TargetAndTransition = exiting ? (reduce ? faded : { ...shapeOf(to), opacity: 1 }) : { ...grown, opacity: 1 }
  const transition: Transition = exiting ? (reduce ? { duration: 0.2 } : { ...springOut, ...settle }) : spring

  const footNote = note ?? (view && !view.secure ? 'Not saved: no secure storage' : !connected ? 'Offline' : undefined)
  /** The sheet never grows past the screen: below the pill, with a margin at the bottom. */
  const maxHeight = Math.max(240, layout.height - bridge.platform.pillTop - BOTTOM_MARGIN)

  return (
    <div key={gen} className="absolute inset-0" data-settings={phase}>
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
        role="dialog"
        aria-label="Settings"
        className="absolute left-1/2 overflow-hidden text-white"
        style={{ top: bridge.platform.pillTop, x: '-50%', background: color.island, transformOrigin: '50% 0%' }}
        initial={reduce ? faded : { ...shapeOf(from), opacity: 1 }}
        animate={target}
        transition={transition}
        onAnimationComplete={() => exiting && finish()}
        onKeyDown={onKey}
      >
        {/* The island's own content, handed over: fades out as the sheet grows… */}
        {handoff && phase === 'open' && !reduce && islandMode && (
          <IslandContent mode={islandMode} initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={contentOut} />
        )}
        {/* …and back in as the sheet collapses onto the island's shape. */}
        {exiting && !reduce && islandMode && (
          <IslandContent mode={islandMode} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.14, delay: 0.12, ease: 'easeOut' }} />
        )}

        <motion.div
          ref={content}
          // A column whose height never passes the screen: past maxHeight only the key rows shrink and scroll.
          className="flex flex-col"
          style={{ width: WIDTH, marginLeft: `calc(50% - ${WIDTH / 2}px)`, maxHeight }}
          initial={{ opacity: 0, y: 4 }}
          animate={exiting ? { opacity: 0, y: 0, transition: contentOut } : { opacity: 1, y: 0, transition: contentIn }}
        >
          <div className="flex h-[52px] shrink-0 items-center pl-[24px] pr-[14px]">
            <span className="flex-1 text-[15px] font-semibold" style={{ color: color.text }}>
              Settings
            </span>
            <button
              type="button"
              className="grid h-[22px] w-[22px] cursor-pointer place-items-center rounded-full"
              style={{ background: fill.key, color: fill.keyText }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={close}
              aria-label="Close"
            >
              <X size={12} strokeWidth={2.2} />
            </button>
          </div>

          <div className="shrink-0 pb-[10px]">
            <SectionLabel>General</SectionLabel>
            <General />
          </div>

          <div className="shrink-0 pt-[8px]">
            <SectionLabel>Keys</SectionLabel>
          </div>
          <div className="min-h-0 shrink overflow-y-auto pb-[6px]" style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
            {SHOWN.map((k) => (
              <KeyRow
                key={k}
                name={k}
                info={view?.keys[k]}
                state={status?.[k]}
                busy={waiting.includes(k)}
                draft={drafts[k] ?? ''}
                cleared={cleared.includes(k)}
                readOnly={phase !== 'open'}
                inputRef={(el) => {
                  inputs.current[k] = el
                }}
                onDraft={(v) => setDraft(k, v)}
                onClear={() => toggleClear(k)}
              />
            ))}
          </div>

          <div className="h-px shrink-0" style={{ background: fill.rule }} />
          <div className="flex h-[52px] shrink-0 items-center gap-[8px] pl-[24px] pr-[12px]">
            <span className="flex min-w-0 flex-1 items-center gap-[7px] text-[13px]" style={{ color: color.label }}>
              {!note && !connected && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
              {footNote && <span className="truncate">{footNote}</span>}
            </span>
            <NeutralButton label="Test" busy={testing} onClick={() => void test()} />
            <PrimaryButton label="Save" kbd="↵" disabled={!dirty || saving} onClick={() => void save()} />
          </div>
        </motion.div>
      </motion.div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------

function KeyRow({
  name,
  info,
  state,
  busy,
  draft,
  cleared,
  readOnly,
  inputRef,
  onDraft,
  onClear
}: {
  name: KeyName
  info?: KeyInfo
  state?: KeyState
  busy: boolean
  draft: string
  cleared: boolean
  readOnly: boolean
  inputRef: (el: HTMLInputElement | null) => void
  onDraft: (v: string) => void
  onClear: () => void
}): ReactNode {
  const optional = !isRequired(name)
  const sub =
    state === 'invalid' ? { text: 'Invalid', c: color.text } : state === 'env' ? { text: 'From engine', c: color.label } : optional ? { text: 'Optional', c: color.faint } : undefined
  const set = !!info?.set && !cleared
  const placeholder = cleared ? 'Cleared' : set ? `•••• ${info?.last4 ?? ''}`.trim() : name === 'tigerUrl' ? 'Paste URL' : 'Paste key'
  /** Clear (or Undo) sits inside the field, only when there's a stored key and nothing typed over it. */
  const clearable = (set || cleared) && !draft

  return (
    <div className="flex h-[52px] items-center gap-[12px] px-[24px]">
      <span className="grid w-[12px] shrink-0 place-items-center">{busy ? <Spinner size={12} c={color.label} /> : <KeyDot state={state} />}</span>
      <span className="flex w-[124px] shrink-0 flex-col justify-center">
        <span className="truncate text-[14px] leading-[18px]" style={{ color: color.text }}>
          {LABEL[name]}
        </span>
        {sub && (
          <span className="truncate text-[12px] leading-[15px]" style={{ color: sub.c }}>
            {sub.text}
          </span>
        )}
      </span>
      <div
        className={`flex h-[34px] min-w-0 flex-1 items-center gap-[8px] rounded-[10px] border pl-[12px] ${clearable ? 'pr-[4px]' : 'pr-[12px]'}`}
        style={{ background: fill.field, borderColor: fill.fieldBorder }}
      >
        <input
          ref={inputRef}
          type="password"
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          readOnly={readOnly}
          placeholder={placeholder}
          aria-label={`${LABEL[name]} ${name === 'tigerUrl' ? 'URL' : 'key'}`}
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="off"
          data-1p-ignore
          className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-white outline-none placeholder:text-(--ph)"
          style={{ caretColor: color.accent, ['--ph' as string]: set ? color.label : color.faint }}
        />
        {clearable && <NeutralButton small label={cleared ? 'Undo' : 'Clear'} onClick={onClear} />}
      </div>
    </div>
  )
}

/** ok = white dot · env = gray dot · missing / invalid = ring · no answer yet = faint ring. No green, no amber, no glow. */
function KeyDot({ state }: { state?: KeyState }): ReactNode {
  if (state === 'ok' || state === 'env')
    return <span className="block h-[7px] w-[7px] rounded-full" style={{ background: state === 'ok' ? color.text : color.gray }} />
  return <span className="block h-[8px] w-[8px] rounded-full border-[1.5px]" style={{ borderColor: state ? color.label : fill.track }} />
}

/** A neutral (chrome) button: Test, Clear, Undo. */
function NeutralButton({ label, onClick, busy, small }: { label: string; onClick: () => void; busy?: boolean; small?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      className={`flex shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full font-medium ${small ? 'h-[24px] px-[10px] text-[12px]' : 'h-[30px] px-[13px] text-[13px]'}`}
      style={{ backgroundColor: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      aria-busy={busy || undefined}
    >
      {busy && <Spinner size={13} c={color.text} />}
      {label}
    </motion.button>
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
