/**
 * Feature: demo. The presenter's walkthrough: one beat per press (→, Space, PageDown or a clicker), each doing
 * what a learner would do on the real UI. The scripted engine answers exactly like the real one, so a person can
 * take over at any beat with the normal keys and buttons.
 *
 * Silent checks: in the real product the engine watches the screen and passes checks on its own. Here the mock
 * can only answer commands, so after the ghost learner types, the walkthrough sends check_step straight to the
 * engine (no button press, no spinner): that stands in for "the engine saw the code".
 */
import { create } from 'zustand'
import { cmd, devReset } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { emitUi, onUi } from '../../core/bus'
import { triggerShortcut } from '../../core/shortcuts'
import { Cancelled, dismiss, findButton, findText, lesson, openLauncher, press, sleep, typeInto, until } from './drive'
import { resetDesk, runInTerminal, typeStep } from './store'

export type Beat = {
  title: string
  /** The presenter's line (shown small in the demo control). */
  say: string
  run: (alive: () => boolean) => Promise<void>
}

/** Keycaps as this platform shows them (⌥E on a Mac, Alt+E on Windows). */
const keys = bridge.platform.keys

const silentCheck = (): void => bridge.send(cmd('action', { kind: 'check_step' }))
const at = (stepId: string, alive: () => boolean, ms = 12000): Promise<boolean> => until(() => lesson().stepId === stepId, ms, alive)
const passed = (stepId: string, alive: () => boolean, ms = 12000): Promise<boolean> => until(() => lesson().passed.includes(stepId), ms, alive)

/** Cards and diagrams close with Esc, which also closes the drawer: put the drawer back. */
async function closeCards(alive: () => boolean): Promise<void> {
  dismiss()
  await sleep(350)
  if (!alive()) throw new Cancelled()
  const tab = document.querySelector<HTMLElement>('[data-part="drawer-tab"]')
  tab?.click()
  await sleep(250)
}

async function typeAndPass(stepId: string, alive: () => boolean): Promise<void> {
  await at(stepId, alive)
  await sleep(300)
  await typeStep(stepId)
  if (!alive()) throw new Cancelled()
  await sleep(250)
  silentCheck()
  await passed(stepId, alive)
}

export const BEATS: Beat[] = [
  {
    title: 'Ask miyagi',
    say: 'Say what you want to learn. Here: a neural net from scratch.',
    async run(alive) {
      const input = await openLauncher(alive)
      if (input) await typeInto(input, 'build a neural net from scratch', alive)
    }
  },
  {
    title: 'Just teach me',
    say: 'Any video becomes a graded lab, or miyagi just teaches you. Claude writes the lesson.',
    async run(alive) {
      const input = (await openLauncher(alive))!
      press(input, 'Tab')
      await sleep(900)
      press(input, 'Enter')
      await at('nn1', alive, 15000)
    }
  },
  {
    title: 'Before you start',
    say: "What we're building, the five ideas it rests on, and a six-step plan.",
    async run(alive) {
      await sleep(200)
      findText('Before you start')?.click()
      await sleep(400)
    }
  },
  {
    title: 'Step 1 · the data',
    say: 'It points at where to type and watches the screen. Right code, checks go green.',
    async run(alive) {
      // Fold "Before you start" back up so the step and its checks are in view.
      if (findText('Matrix multiply')) findText('Before you start')?.click()
      await typeAndPass('nn1', alive)
    }
  },
  {
    title: 'Step 2 · a shortcut',
    say: 'I take a shortcut: zeros instead of random weights. Shapes are right, so it passes.',
    run: (alive) => typeAndPass('nn2', alive)
  },
  {
    title: 'Step 3 · forward pass',
    say: 'The forward pass: two layers of weighted sums and sigmoids.',
    async run(alive) {
      await at('nn3', alive)
      await sleep(300)
      await typeStep('nn3')
    }
  },
  {
    title: 'Ask anything',
    say: 'Stuck mid-step? Ask. The answer is about this step, not a generic chatbot reply.',
    async run(alive) {
      const input = await openLauncher(alive)
      if (!input) return
      await typeInto(input, 'why sigmoid and not relu?', alive, 40)
      await sleep(300)
      press(input, 'Enter')
      await until(() => !!findText('Sigmoid or ReLU?'), 5000, alive)
    }
  },
  {
    title: 'Step 4 · backprop, explained',
    say: `The hard part. ${keys.explain} explains the chain rule in terms of this exact code.`,
    async run(alive) {
      await closeCards(alive)
      silentCheck()
      await at('nn4', alive)
      await sleep(900)
      triggerShortcut('explain')
      await sleep(1200)
    }
  },
  {
    title: 'Diagram',
    say: `${keys.diagram} draws it: forward makes a guess, backward sends the error back.`,
    async run(alive) {
      await closeCards(alive)
      triggerShortcut('diagram')
      await sleep(1500)
    }
  },
  {
    title: 'Step 4 · type it',
    say: 'Now it makes sense, so we type it. Green.',
    async run(alive) {
      await closeCards(alive)
      await typeAndPass('nn4', alive)
    }
  },
  {
    title: 'Step 5 · train',
    say: "Train for 5,000 epochs. Every check passed so far, but watch the loss.",
    async run(alive) {
      await at('nn5', alive)
      await sleep(300)
      await typeStep('nn5')
      await sleep(300)
      await runInTerminal()
      silentCheck()
      await until(() => lesson().offtrack?.level === 2, 9000, alive)
    }
  },
  {
    title: 'Off track',
    say: "Stuck at 0.25 while the tutorial's falls. It asks a question first, not the answer.",
    async run() {
      await sleep(200)
    }
  },
  {
    title: 'Hint',
    say: `Still stuck? ${keys.hint} climbs the hint ladder: now the exact line, and Fix it.`,
    async run(alive) {
      triggerShortcut('hint')
      await until(() => lesson().offtrack?.level === 3, 5000, alive)
    }
  },
  {
    title: 'Fix it',
    say: 'Fix it edits the file and retrains. The loss falls like the tutorial. Back on track.',
    async run(alive) {
      findButton('Fix it')?.click()
      await passed('nn5', alive, 15000)
    }
  },
  {
    title: 'Step 6 · test it',
    say: 'Last line: it predicts 0 1 1 0. A neural net from scratch, every step checked.',
    async run(alive) {
      await at('nn6', alive, 12000)
      await sleep(300)
      await typeStep('nn6')
      await sleep(250)
      await runInTerminal()
      silentCheck()
      await passed('nn6', alive, 12000)
    }
  },
  {
    title: 'What you learned',
    say: 'Everything you built today, and where it leads next.',
    async run(alive) {
      await sleep(1500)
      await closeCards(alive)
      triggerShortcut('diagram')
      await sleep(1200)
    }
  }
]

type Walk = {
  /** Beats done so far (0 = nothing yet; BEATS.length = finished). */
  done: number
  running: boolean
  auto: boolean
}

export const useWalk = create<Walk>(() => ({ done: 0, running: false, auto: false }))

let gen = 0

/** Run the next beat (ignored while one is running). */
export async function nextBeat(): Promise<void> {
  const { done, running } = useWalk.getState()
  if (running || done >= BEATS.length) return
  const mine = ++gen
  const alive = (): boolean => mine === gen
  useWalk.setState({ running: true })
  try {
    await BEATS[done].run(alive)
  } catch (err) {
    if (!(err instanceof Cancelled)) console.error('[demo] beat failed', err)
  }
  if (!alive()) return
  useWalk.setState({ done: done + 1, running: false })
  if (useWalk.getState().auto) scheduleAuto()
}

let autoTimer: ReturnType<typeof setTimeout> | undefined
function scheduleAuto(): void {
  clearTimeout(autoTimer)
  const { done } = useWalk.getState()
  if (done >= BEATS.length) return
  // Long enough to read the line out loud.
  autoTimer = setTimeout(() => void nextBeat(), 2600 + BEATS[done].say.length * 25)
}

export function setAuto(on: boolean): void {
  useWalk.setState({ auto: on })
  if (on && !useWalk.getState().running) scheduleAuto()
  else clearTimeout(autoTimer)
}

/** Back to the empty desktop: end the lesson, reset every surface, start the beats over. */
export function restart(): void {
  gen++
  clearTimeout(autoTimer)
  useWalk.setState({ done: 0, running: false })
  dismiss()
  // The same reset the stage's Reset button does, then a clean desktop.
  emitUi('reset')
  bridge.send(devReset)
  resetDesk()
}

onUi('reset', () => {
  // A reset from elsewhere (the dev HUD) also rewinds the walkthrough.
  if (useWalk.getState().done || useWalk.getState().running) {
    gen++
    clearTimeout(autoTimer)
    useWalk.setState({ done: 0, running: false })
  }
})
