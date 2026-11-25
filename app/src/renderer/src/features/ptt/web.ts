/**
 * Feature: ptt. The browser stage's stand-in for main + the miyagi-listen helper (nothing here runs in Electron).
 *
 * A scripted mock helper prints the same JSON lines the real one does; they go through the REAL parser (main/pttProtocol)
 * and the REAL reducer (common/pttState), then into the store, so the stage shows what Electron would.
 *
 *   ?ptt=<script>   listen | send | tail | wake | happy | short | empty | cancel | stale | error-mic | error-input | error-speech |
 *                   card | card-denied | card-input | idle (helper ready, nothing pressed)
 *   ?ptt-perm=<p>   granted (default) | mic-undetermined | mic-denied | input-denied   (the Settings rows)
 *   ?ptt-hold=1     keep an error up (no 4 s auto-clear), so a shot can catch it
 *   ?ptt=<script>&ptt-at=<ms> start the script later (default 300)
 *
 * Listening / sending scripts HOLD at that state (for shots); happy / short / empty / cancel / stale play through and end at rest.
 * `window.__ptt(name)` plays a script again from the console.
 */
import { PTT_REST, reducePtt, type PttInput, type PttState } from '../../../../common/pttState'
import { parseLine } from '../../../../main/pttProtocol'
import { isElectron, registerWebHandler } from '../../bridge'
import { finalFromHelper, pauseTail, receive, receiveDown, receivePartial } from './store'

type Step = [ms: number, line: object]

const PARTIALS = ['why', 'why does', 'why does the loss', 'why does the loss go down', 'why does the loss go down when the learning rate is smaller']
const SENTENCE = 'why does the loss go down when the learning rate is smaller'
const WAKE_PARTIALS = ['Hey', 'Hey Miyagi', 'Hey Miyagi, what', 'Hey Miyagi, what is this', 'Hey Miyagi, what is this error']

const hold = (id: string, upto: number): Step[] => [
  [0, { type: 'ptt', state: 'down', id }],
  [260, { type: 'listening', id }],
  ...PARTIALS.slice(0, upto).map((t, i): Step => [180 + i * 140, { type: 'partial', id, text: t }])
]

const SCRIPTS: Record<string, Step[]> = {
  idle: [],
  listen: hold('a1', 4),
  send: [...hold('a2', 5), [200, { type: 'ptt', state: 'up', id: 'a2' }]],
  // Release with no final from the helper (an old helper, a lost line): the safety net (tail.ts) sends the last partial SAFETY_MS after the keys come up.
  tail: [...hold('t1', 5), [200, { type: 'ptt', state: 'up', id: 't1' }]],
  // A wake word first: the pill and the ask show only "What is this error".
  wake: [[0, { type: 'ptt', state: 'down', id: 'w1' }], [260, { type: 'listening', id: 'w1' }], ...WAKE_PARTIALS.map((t, i): Step => [180 + i * 140, { type: 'partial', id: 'w1', text: t }]), [200, { type: 'ptt', state: 'up', id: 'w1' }], [150, { type: 'final', id: 'w1', text: 'Hey Miyagi, what is this error?' }]],
  happy: [...hold('a3', 5), [200, { type: 'ptt', state: 'up', id: 'a3' }], [300, { type: 'final', id: 'a3', text: SENTENCE }]],
  short: [[0, { type: 'ptt', state: 'down', id: 'b1' }], [140, { type: 'ptt', state: 'up', id: 'b1' }], [20, { type: 'cancelled', id: 'b1', reason: 'short' }]],
  empty: [[0, { type: 'ptt', state: 'down', id: 'c1' }], [260, { type: 'listening', id: 'c1' }], [600, { type: 'ptt', state: 'up', id: 'c1' }], [300, { type: 'final', id: 'c1', text: '  ' }]],
  cancel: [...hold('d1', 2), [300, { type: 'cancelled', id: 'd1', reason: 'esc' }]],
  // A late event from a session that was already cancelled: it must change nothing.
  stale: [...hold('e1', 2), [200, { type: 'cancelled', id: 'e1', reason: 'keypress' }], [100, { type: 'partial', id: 'e1', text: 'ghost words' }], [100, { type: 'final', id: 'e1', text: 'ghost words' }]],
  'error-mic': [[0, { type: 'error', code: 'mic_denied', message: 'Microphone is off' }]],
  'error-input': [[0, { type: 'ptt', state: 'down', id: 'g1' }], [260, { type: 'error', code: 'input_denied', message: 'Input Monitoring is off' }]],
  // The real helper's first hold with the microphone never asked: an error code of its own, the Allow card (not Open settings).
  'error-mic-undetermined': [[0, { type: 'perm', mic: 'undetermined', input: 'granted', assets: 'installed' }], [100, { type: 'ptt', state: 'down', id: 'g2' }], [260, { type: 'error', code: 'mic_undetermined', message: 'Not asked yet' }]],
  'error-speech': [[0, { type: 'error', code: 'no_stt', message: 'No speech recognizer' }]],
  card: [[0, { type: 'perm', mic: 'undetermined', input: 'granted', assets: 'installed' }], [200, { type: 'ptt', state: 'down', id: 'f1' }]],
  'card-denied': [[0, { type: 'perm', mic: 'denied', input: 'granted', assets: 'installed' }], [200, { type: 'ptt', state: 'down', id: 'f2' }]],
  // No hold can happen without the key listener: the helper says Input Monitoring is off the moment it is enabled.
  'card-input': [[0, { type: 'error', code: 'input_denied', message: 'Input Monitoring is off' }], [10, { type: 'perm', mic: 'granted', input: 'denied', assets: 'installed' }]]
}

const PERMS: Record<string, { mic: string; input: string }> = {
  granted: { mic: 'granted', input: 'granted' },
  'mic-undetermined': { mic: 'undetermined', input: 'granted' },
  'mic-denied': { mic: 'denied', input: 'granted' },
  'input-denied': { mic: 'granted', input: 'denied' }
}

if (!isElectron && typeof location !== 'undefined') {
  const params = new URLSearchParams(location.search)
  const permName = params.get('ptt-perm') ?? 'granted'
  const keepErrors = params.get('ptt-hold') === '1'
  let state: PttState = PTT_REST
  let prefill: string | null = null
  const timers: ReturnType<typeof setTimeout>[] = []
  let errTimer: ReturnType<typeof setTimeout> | undefined

  /** One line from the mock helper, through the real parser and reducer. */
  const emit = (o: object): void => {
    const ev = parseLine(JSON.stringify(o))
    if (ev) apply(ev)
  }
  const apply = (e: PttInput): void => {
    const r = reducePtt(state, e)
    state = r.state
    clearTimeout(errTimer)
    if (state.phase === 'error' && !keepErrors) errTimer = setTimeout(() => apply({ type: 'clear-error' }), 4000)
    receive(state)
    // The same side signals main sends (main/features/ptt.ts): the keys went down, a new partial of the hold in flight.
    if (e.type === 'ptt' && e.state === 'down' && state.id === e.id) receiveDown({ id: e.id })
    if (e.type === 'partial' && state.id === e.id) receivePartial({ id: e.id, text: e.text })
    if (r.final) finalFromHelper(r.final)
  }

  const play = (name: string, at = 0): void => {
    for (const t of timers.splice(0)) clearTimeout(t)
    pauseTail(name === 'send')
    apply({ type: 'reset' })
    let t = at
    for (const [dt, line] of SCRIPTS[name] ?? []) {
      t += dt
      timers.push(setTimeout(() => emit(line), t))
    }
  }

  const p = PERMS[permName] ?? PERMS.granted
  setTimeout(() => {
    emit({ type: 'ready', stt: 'speechanalyzer', locale: 'en-US', chord: 'fn+control' })
    emit({ type: 'perm', mic: p.mic, input: p.input, assets: 'installed' })
    const name = params.get('ptt')
    if (name && SCRIPTS[name]) play(name, Number(params.get('ptt-at') ?? 300))
  }, 50)
  ;(window as unknown as { __ptt: (n: string) => void }).__ptt = (n) => play(n)

  registerWebHandler('ptt:get', () => state)
  registerWebHandler('ptt:config', () => true)
  registerWebHandler('ptt:allow', (which) => {
    console.info(`[tut] stage: would ask the helper for ${String(which)}`)
    emit({ type: 'perm', mic: 'granted', input: 'granted', assets: 'installed' })
    return true
  })
  registerWebHandler('ptt:open-settings', (kind) => {
    console.info(`[tut] stage: would open System Settings (${String(kind)})`)
    return true
  })
  registerWebHandler('ptt:cancel', () => {
    play('idle')
    return true
  })
  registerWebHandler('ptt:prefill', (text) => {
    prefill = typeof text === 'string' ? text : null
    return !!prefill
  })
  registerWebHandler('ptt:prefill-take', () => {
    const t = prefill
    prefill = null
    return t
  })
}
