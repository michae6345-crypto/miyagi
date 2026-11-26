/**
 * Feature: shell / flow. The first run as one full-window layer inside the home window (route `library`), over the
 * sidebar, from the intro to the moment home slides in (store.ts phases):
 *
 *   top      the slim step strip (Strip.tsx) with the bonsai's slot; "Set up later" at the right during setup and on
 *            Review setup (whose Start stays off while something is left, so it is never a dead end). Below
 *            COMPACT_W (the window's minimum is 560) the strip shows only the current step's label, the others as
 *            ticks and dots, so it never runs into "Set up later".
 *   body     intro (the whole window) → Sign in → consent (what miyagi sends, "By continuing you agree"; R05, R06)
 *            → guided setup → You're ready (or Review setup when something the learner can fix is left). Consent
 *            has no "Set up later": no prompt and no capture come before it.
 *
 * The views are the features' own (onboarding Intro / Guided / Ready / Checklist, auth Login), in flow mode: no
 * header of their own, and the end hands over to home instead of opening another window.
 * Live like the setup window: permissions watched while the window is on screen, health asked for while it is focused (useLive).
 * Leaving (Shell.tsx runs the arrival), in two beats: this layer's screen fades out first (screenOut), leaving only its
 * plain paper; then the paper fades (layerOut) while the sidebar slides in over it, the bonsai glides from the strip
 * into the sidebar's logo and Home rises underneath. Two screens are never drawn over each other.
 * Again (store.ts reopenFlow, setup asked for from home): the layer fades in over home (layerIn) and the bonsai stays
 * in the sidebar (the strip shows no tree, its slot stays balanced); the end fades back to home. Never a trap: a quiet
 * "Back to home" with its Esc keycap sits at the strip's right in every phase (in place of "Set up later") and Esc
 * does the same; You're ready / Review setup end on Done, which only hands back to home (store.ts leaveAgain: no
 * lesson is started, nothing is put off).
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import { cmd } from '../../../../../common/wire'
import { bridge } from '../../../bridge'
import { canSend } from '../../../core/lesson'
import { color, type2, v4c } from '../../../core/theme'
import { beat, fade } from '../../../core/ui/motion'
import { Keycap } from '../../../core/ui/Keycap'
import { Login } from '../../auth/Login'
import { Checklist } from '../../onboarding/Checklist'
import { Consent } from '../../onboarding/Consent'
import { Guided } from '../../onboarding/Guided'
import { Intro } from '../../onboarding/Intro'
import { useLive } from '../../onboarding/Onboarding'
import { Ready } from '../../onboarding/Ready'
import { summarize, useRows } from '../../onboarding/rows'
import { markDone, noteSetupShown, useOnboarding } from '../../onboarding/store'
import { arriveDelay, layerIn, layerOut, leave, screenOut } from './motion'
import { Strip } from './Strip'
import './web'
import { backToSetup, endConsent, endIntro, endLogin, finishFlow, flowCovers, leaveAgain, toReady, useFlow } from './store'

/** Below this window width the strip is compact (current label, ticks and dots). */
const COMPACT_W = 760
/*
 * Setup and You're ready (v4, Nov 24): the views lay themselves out (features/onboarding v4.tsx SetupPage: Adrian's
 * ui-next onboard pages, a 1000 column with the step on the left and a quiet rail on the right, top-anchored under
 * the strip, one column under 860), so the flow hands them the whole body.
 */

/** One phase's view: absolutely placed so the old one can fade while the new one arrives. */
function View({ id, children }: { id: string; children: ReactNode }): ReactNode {
  return (
    <motion.div data-flow-view={id} className="absolute inset-0" initial={{ opacity: 1 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -6, transition: leave }}>
      {children}
    </motion.div>
  )
}

/** The strip's right-hand link: quiet text in the label gray, fading in a beat after the strip. */
const linkIn = { ...fade.in, delay: 5 * beat }

/** Start on You're ready: the lesson it shows (the engine's suggestion, zero model calls) when there is one, and home. */
function start(): void {
  const pick = useOnboarding.getState().suggestion
  if (pick && canSend('library.start')) bridge.send(cmd('library.start', { id: pick.id }))
  finishFlow(true)
}

export function FlowLayer({ width, height }: { width: number; height: number }): ReactNode {
  useLive()
  const live = useFlow((s) => s.phase)
  const again = useFlow((s) => s.again)
  // Leaving: this layer keeps its last screen mounted while it hands over (only the bonsai leaves it, for the
  // sidebar), instead of emptying itself first; the screen fades out before the paper does.
  const last = useRef(live)
  if (flowCovers(live)) last.current = live
  const phase = last.current
  const leaving = !flowCovers(live)
  const resume = useFlow((s) => s.resume)
  const step = useOnboarding((s) => s.step)
  const skipped = useOnboarding((s) => s.skippedSteps)
  const rows = useRows()
  const sum = useMemo(() => summarize(rows), [rows])

  // Setup counts as done the moment every row is green (as in the setup window), even before Start. Only once the
  // setup walk shows: the login screen (a later launch, setup long done) never marks anything.
  const walking = phase === 'setup' || phase === 'ready'
  useEffect(() => {
    if (!walking) return
    noteSetupShown()
    if (sum.allOk) markDone()
  }, [sum.allOk, walking])

  // Setup again: Esc hands back to home, before anything under the layer (a preview, the search) sees the key.
  useEffect(() => {
    if (!again) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing) return
      e.preventDefault()
      e.stopPropagation()
      leaveAgain()
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [again])

  const intro = phase === 'intro'
  const done = again ? () => leaveAgain(true) : start
  return (
    <motion.div
      data-flow={phase}
      data-flow-again={again || undefined}
      role="presentation"
      className="absolute inset-0 z-[2] overflow-hidden"
      style={{ background: v4c.page, color: color.text }}
      initial={again ? { opacity: 0 } : false}
      animate={{ opacity: 1, transition: layerIn }}
      exit={{ opacity: 0, transition: layerOut }}
    >
      <motion.div data-flow-screen className="flex h-full w-full select-none flex-col" initial={false} animate={{ opacity: leaving ? 0 : 1 }} transition={screenOut}>
        <header data-drag className="mg-flow-head relative flex shrink-0 items-center justify-center">
          {!intro && <Strip phase={phase} step={phase === 'setup' ? step : undefined} rows={rows} skipped={skipped} mark={!leaving && !again} compact={width < COMPACT_W} />}
          <AnimatePresence>
            {again ? (
              <motion.button
                key="home"
                type="button"
                data-no-drag
                data-flow-home
                className="absolute right-[24px] top-1/2 flex cursor-pointer items-center gap-[8px]"
                style={{ y: '-50%', fontSize: type2.xs, color: color.label }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={linkIn}
                onClick={() => leaveAgain()}
              >
                Back to home
                <Keycap k="dismiss" size="sm" />
              </motion.button>
            ) : (
              // Review setup too: its Start waits on something left (VS Code skipped, say), so this is its way home.
              (phase === 'setup' || (phase === 'ready' && !sum.canStart)) && (
                <motion.button
                  key="later"
                  type="button"
                  data-no-drag
                  data-flow-later
                  className="absolute right-[24px] top-1/2 cursor-pointer"
                  style={{ y: '-50%', fontSize: type2.xs, color: color.label }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={linkIn}
                  onClick={() => finishFlow(false)}
                >
                  Set up later
                </motion.button>
              )
            )}
          </AnimatePresence>
        </header>

        <div className="relative min-h-0 flex-1">
          <AnimatePresence>
            {phase === 'login' && (
              <View key="login" id="login">
                <Login onContinue={endLogin} />
              </View>
            )}
            {phase === 'consent' && (
              <View key="consent" id="consent">
                <Consent chrome="flow" enterDelay={arriveDelay} onDone={endConsent} />
              </View>
            )}
            {phase === 'setup' && (
              <View key="setup" id="setup">
                <div data-flow-column className="h-full w-full">
                  <Guided chrome="flow" rows={rows} width={width} height={height - 64} enterDelay={arriveDelay} resumeAt={resume} onFinish={toReady} />
                </div>
              </View>
            )}
            {phase === 'ready' && (
              <View key={sum.canStart ? 'ready' : 'checklist'} id={sum.canStart ? 'ready' : 'checklist'}>
                {/* The same top-anchored v4 page as setup: You're ready (and the checklist) sit under the strip. */}
                <div data-flow-column className="h-full w-full">
                  {sum.canStart ? (
                    <Ready rows={rows} sum={sum} mark={false} again={again} onStart={done} onTour={() => finishFlow(true)} />
                  ) : (
                    <Checklist rows={rows} sum={sum} mark={false} again={again} onGuide={backToSetup} onStart={again ? () => leaveAgain() : start} />
                  )}
                </div>
              </View>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {/* The intro takes the whole window (the strip waits until it is over). */}
      <AnimatePresence>{intro && <Intro key="intro" onDone={endIntro} />}</AnimatePresence>
    </motion.div>
  )
}
