/**
 * Feature: onboarding. The setup app window (route `onboarding`, kind 'app'; BUILD-PLAN decision 4).
 *
 *   intro      the first launch only: the branded intro (Intro.tsx, ~2.5 s, any key or click skips), then setup
 *   setup      guided setup, one step per screen (Guided.tsx): Screen Recording, Accessibility, VS Code, engine
 *   ready      "You're ready" and Start (Ready.tsx), once nothing the learner can fix is left
 *   checklist  Review setup (Checklist.tsx): every row on one sheet; Settings and a later run open this
 *
 * Which one it opens with (window args `view`, store.ts OnbView): checklist → Review setup; intro / welcome → the intro
 * unless it played already on this Mac (then setup); setup → setup; nothing → Review setup once setup is done, else
 * setup (with the intro the first time). A reopen with new args switches view; a reopen with none keeps the walk.
 *
 * Live, never prompting: permissions are watched only while this window is focused (main polls only then), health is
 * asked for on open and every HEALTH_MS while focused, and only when the engine said it understands health.get.
 * Setup is done once every row is green (onboarding.json in userData).
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence } from 'motion/react'
import type { Layout } from '../../../../preload/api'
import { isElectron } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { useWindowArgs } from '../../core/surfaces'
import { color, copy, font } from '../../core/theme'
import { Checklist } from './Checklist'
import { Guided } from './Guided'
import { Intro } from './Intro'
import { Ready } from './Ready'
import { summarize, useRows } from './rows'
import { markDone, markIntroSeen, refreshCloud, refreshPerms, requestHealth, useOnboarding, watchPerms, type OnbView } from './store'

const HEALTH_MS = 4000
/** How long the window waits for its open args before it decides from the done flag alone. */
const ARGS_WAIT_MS = 250

type Phase = 'intro' | 'setup' | 'ready' | 'checklist'

/** Live, never prompting: watch permissions and ask for health while this window is focused (also the flow layer's). */
export function useLive(): void {
  const hello = useLesson((s) => !!s.hello)
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined
    const focus = (): void => {
      watchPerms('window', true)
      requestHealth()
      refreshCloud()
      clearInterval(timer)
      timer = setInterval(() => {
        requestHealth()
        // Cloud access finishing (minting) also arrives as feat:cloud; asking again costs nothing.
        refreshCloud()
      }, HEALTH_MS)
    }
    const blur = (): void => {
      // The stage is one page: it never "leaves" the window.
      if (!isElectron) return
      watchPerms('window', false)
      clearInterval(timer)
      timer = undefined
    }
    void refreshPerms()
    if (!isElectron || document.hasFocus()) focus()
    window.addEventListener('focus', focus)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('focus', focus)
      window.removeEventListener('blur', blur)
      clearInterval(timer)
      watchPerms('window', false)
    }
  }, [hello])
}

const VIEWS: readonly OnbView[] = ['intro', 'setup', 'welcome', 'checklist']
const asView = (v: unknown): OnbView | undefined => VIEWS.find((x) => x === v)

function phaseFor(view: OnbView | undefined, done: boolean, introSeen: boolean, forceIntro: boolean): Phase {
  if (view === 'checklist') return 'checklist'
  if (view === 'setup') return 'setup'
  if (view === 'intro' || view === 'welcome') return forceIntro || !introSeen ? 'intro' : 'setup'
  if (done) return 'checklist'
  return introSeen ? 'setup' : 'intro'
}

export function Onboarding({ layout }: { layout: Layout }): ReactNode {
  useLive()
  const args = useWindowArgs('onboarding')
  const loaded = useOnboarding((s) => s.loaded)
  const rows = useRows()
  const sum = useMemo(() => summarize(rows), [rows])
  const [phase, setPhase] = useState<Phase | undefined>(undefined)
  const [fromIntro, setFromIntro] = useState(false)
  const [argsWaited, setArgsWaited] = useState(false)
  const view = asView(args?.view)
  /** The stage's ?onb=intro: the intro holds its last frame (and plays even when seen). */
  const hold = args?.hold === true

  useEffect(() => {
    const t = setTimeout(() => setArgsWaited(true), ARGS_WAIT_MS)
    return () => clearTimeout(t)
  }, [])

  // The first decision, once the done flag is known and the open args had their moment.
  useEffect(() => {
    if (phase || !loaded || (!args && !argsWaited)) return
    const s = useOnboarding.getState()
    setPhase(phaseFor(view, s.done, s.introSeen, hold))
  }, [phase, loaded, args, argsWaited, view, hold])

  // A reopen with new args (Review setup from Settings while the walk is up, or the reverse).
  const lastView = useRef(view)
  useEffect(() => {
    if (lastView.current === view) return
    lastView.current = view
    if (!phase || !view) return
    const s = useOnboarding.getState()
    const next = phaseFor(view, s.done, true, false)
    if (next !== phase && !(phase === 'ready' && next === 'setup')) setPhase(next)
  }, [view, phase])

  useEffect(() => {
    if (sum.allOk) markDone()
  }, [sum.allOk])

  useEffect(() => {
    // The window's title is the product's name, always lowercase (the page title is what macOS shows).
    if (document.title !== copy.name) document.title = copy.name
  }, [])

  const endIntro = (): void => {
    markIntroSeen()
    setFromIntro(true)
    setPhase('setup')
  }

  // Review setup with every row green, or the walk's end: You're ready. The walk's end with something left that the
  // learner can fix shows the checklist instead (never "ready" when it isn't).
  const shown: Phase | undefined = phase === 'checklist' && sum.allOk ? 'ready' : phase === 'ready' && !sum.canStart ? 'checklist' : phase

  return (
    <div data-onb-window data-phase={shown} className="relative flex h-full w-full select-none overflow-hidden" style={{ background: color.window, color: color.text, fontFamily: font.ui }}>
      <AnimatePresence>{shown === 'intro' && <Intro key="intro" onDone={endIntro} hold={hold} />}</AnimatePresence>
      {shown === 'setup' && <Guided rows={rows} width={layout.width} height={layout.height} enterDelay={fromIntro ? 0.24 : 0} onFinish={() => setPhase('ready')} />}
      {shown === 'ready' && <Ready rows={rows} sum={sum} />}
      {shown === 'checklist' && <Checklist rows={rows} sum={sum} onGuide={() => setPhase('setup')} />}
    </div>
  )
}
