/**
 * Feature: shell / flow. The first run as one full-window layer inside the home window (route `library`), over the
 * sidebar, from the intro to the moment home slides in (store.ts phases):
 *
 *   top      the slim step strip (Strip.tsx) with the bonsai's slot; "Set up later" at the right during setup
 *   body     intro (the whole window) → Sign in → guided setup → You're ready (or Review setup when something the
 *            learner can fix is left)
 *
 * The views are the features' own (onboarding Intro / Guided / Ready / Checklist, auth Login), in flow mode: no
 * header of their own, and the end hands over to home instead of opening another window.
 * Live like the setup window: permissions watched and health asked for while the window is focused (useLive).
 * Leaving (Shell.tsx runs the arrival): this layer fades out on top of home while the sidebar slides in over it and
 * the bonsai glides from the strip into the sidebar's logo.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import { cmd } from '../../../../../common/wire'
import { bridge } from '../../../bridge'
import { canSend } from '../../../core/lesson'
import { color, type2 } from '../../../core/theme'
import { Login } from '../../auth/Login'
import { Checklist } from '../../onboarding/Checklist'
import { Guided } from '../../onboarding/Guided'
import { Intro } from '../../onboarding/Intro'
import { useLive } from '../../onboarding/Onboarding'
import { Ready } from '../../onboarding/Ready'
import { summarize, useRows } from '../../onboarding/rows'
import { markDone, useOnboarding } from '../../onboarding/store'
import { arriveDelay, layerOut, leave } from './motion'
import { Strip } from './Strip'
import './web'
import { backToSetup, endIntro, endLogin, finishFlow, flowCovers, toReady, useFlow } from './store'

/** One phase's view: absolutely placed so the old one can fade while the new one arrives. */
function View({ id, children }: { id: string; children: ReactNode }): ReactNode {
  return (
    <motion.div data-flow-view={id} className="absolute inset-0" initial={{ opacity: 1 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -6, transition: leave }}>
      {children}
    </motion.div>
  )
}

/** Start on You're ready: the engine's first lesson when it offers one (zero model calls), and home either way. */
function start(): void {
  const pick = useOnboarding.getState().suggestion
  if (pick && canSend('library.start')) bridge.send(cmd('library.start', { id: pick.id }))
  finishFlow(true)
}

export function FlowLayer({ width, height }: { width: number; height: number }): ReactNode {
  useLive()
  const live = useFlow((s) => s.phase)
  // Leaving: this layer keeps showing its last screen while it fades over home (only the bonsai leaves it, for the
  // sidebar), instead of emptying itself first.
  const last = useRef(live)
  if (flowCovers(live)) last.current = live
  const phase = last.current
  const leaving = !flowCovers(live)
  const resume = useFlow((s) => s.resume)
  const step = useOnboarding((s) => s.step)
  const skipped = useOnboarding((s) => s.skippedSteps)
  const rows = useRows()
  const sum = useMemo(() => summarize(rows), [rows])

  // Setup counts as done the moment every row is green (as in the setup window), even before Start.
  useEffect(() => {
    if (sum.allOk) markDone()
  }, [sum.allOk])

  const intro = phase === 'intro'
  return (
    <motion.div
      data-flow={phase}
      role="presentation"
      className="absolute inset-0 z-[2] flex select-none flex-col overflow-hidden"
      style={{ background: color.window, color: color.text }}
      initial={false}
      exit={{ opacity: 0, transition: layerOut }}
    >
      <header data-drag className="relative flex h-[64px] shrink-0 items-center justify-center">
        {!intro && <Strip phase={phase} step={phase === 'setup' ? step : undefined} rows={rows} skipped={skipped} mark={!leaving} />}
        <AnimatePresence>
          {phase === 'setup' && (
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
              transition={{ duration: 0.18, delay: 0.3 }}
              onClick={() => finishFlow(false)}
            >
              Set up later
            </motion.button>
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
          {phase === 'setup' && (
            <View key="setup" id="setup">
              <Guided chrome="flow" rows={rows} width={width} height={height - 64} enterDelay={arriveDelay} resumeAt={resume} onFinish={toReady} />
            </View>
          )}
          {phase === 'ready' && (
            <View key={sum.canStart ? 'ready' : 'checklist'} id={sum.canStart ? 'ready' : 'checklist'}>
              {sum.canStart ? <Ready rows={rows} sum={sum} mark={false} onStart={start} /> : <Checklist rows={rows} sum={sum} mark={false} onGuide={backToSetup} onStart={start} />}
            </View>
          )}
        </AnimatePresence>
      </div>

      {/* The intro takes the whole window (the strip waits until it is over). */}
      <AnimatePresence>{intro && <Intro key="intro" onDone={endIntro} />}</AnimatePresence>
    </motion.div>
  )
}
