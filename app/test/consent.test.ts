/**
 * Consent before capture (launch register R05 and R06), offline:
 *   record   common/consent.ts: the {version, at} record, what reads as current, what reads as none
 *   prefs    prefs.consent survives sanitizePrefs; a renderer's prefs:set can never write it (main/prefs.ts fromRenderer)
 *   gate     main/features/onboarding.ts: no Screen Recording or Accessibility prompt and no capture before consent, the
 *            gate's consent part stays closed (even with the login and "Set up later"), onboarding:agree stamps this
 *            build's version and main's time, and an older version asks again
 *   flow     the first run's order (shell/flow/phases.ts): consent always before setup
 *   copy     the consent screen's lines (onboarding/consentCopy.ts): what they must say, the brand's copy rules,
 *            Anthropic only (D1), and every miyagi.study link in app/src is a page that exists
 * Run from app/: node --import tsx --import ./test/setup.mjs --test test/consent.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, test } from 'node:test'
import { CONSENT_VERSION, CONTACT_EMAIL, LEGAL_URL, cleanConsent, consentCurrent, makeConsent } from '../src/common/consent'
import { GEMINI_ENABLED } from '../src/common/flags'
import { sanitizePrefs } from '../src/common/prefs'
import type { MainContext } from '../src/main/context'
import onboarding from '../src/main/features/onboarding'
import { gateIsOpen, gateView, resetGateForTests, setGatePart } from '../src/main/gate'
import { fromRenderer, getPrefs, patchPrefs, resetPrefsForTests } from '../src/main/prefs'
import { AGREE, AGREE_LINE, CONSENT_ROWS, CONSENT_TITLE, CONTINUE } from '../src/renderer/src/features/onboarding/consentCopy'
import { phaseAfter } from '../src/renderer/src/features/shell/flow/phases'
import { promptCalls } from './fakes/electron'

// ---- a launch of the onboarding feature over a temp userData -------------------------------------------------------

type Run = { invoke: (channel: string, ...a: unknown[]) => Promise<unknown>; broadcasts: [string, unknown][] }

function launch(dir: string): Run {
  const handlers = new Map<string, (...a: unknown[]) => unknown>()
  const broadcasts: [string, unknown][] = []
  const win = { isDestroyed: () => false, setTitle: () => undefined, on: () => undefined, once: () => undefined, show: () => undefined, focus: () => undefined }
  const ctx = {
    app: { isPackaged: false, getPath: () => dir, getLoginItemSettings: () => ({ wasOpenedAtLogin: false }), relaunch: () => undefined, quit: () => undefined },
    overlay: { isDestroyed: () => false, webContents: { once: () => undefined } },
    broadcast: (c: string, p: unknown) => broadcasts.push([c, p]),
    handle: (c: string, fn: (...a: unknown[]) => unknown) => handlers.set(c, fn),
    openWindow: () => win,
    appWindow: () => undefined
  } as unknown as MainContext
  onboarding.setup(ctx)
  return {
    broadcasts,
    invoke: async (c, ...a) => {
      const fn = handlers.get(c)
      if (!fn) throw new Error(`no handler ${c}`)
      return fn(...a)
    }
  }
}

/** The prompts only run on a Mac: pretend to be one, so a refusal is the consent guard and not the platform check. */
const platform = Object.getOwnPropertyDescriptor(process, 'platform')
const onMac = (): void => void Object.defineProperty(process, 'platform', { value: 'darwin', configurable: true })

let dir: string
let skipBefore: string | undefined
beforeEach(() => {
  skipBefore = process.env.MIYAGI_SKIP_ONBOARDING
  delete process.env.MIYAGI_SKIP_ONBOARDING
  dir = mkdtempSync(join(tmpdir(), 'miyagi-consent-'))
  promptCalls.length = 0
  resetGateForTests()
  resetPrefsForTests()
  onMac()
})
afterEach(() => {
  if (platform) Object.defineProperty(process, 'platform', platform)
  if (skipBefore === undefined) delete process.env.MIYAGI_SKIP_ONBOARDING
  else process.env.MIYAGI_SKIP_ONBOARDING = skipBefore
  resetGateForTests()
  resetPrefsForTests()
  rmSync(dir, { recursive: true, force: true })
})

// ---- the record ----------------------------------------------------------------------------------------------------

describe('the consent record (common/consent.ts)', () => {
  test('makeConsent stamps this build version and an ISO time; it reads back as current', () => {
    const at = new Date('2026-11-21T20:15:00.000Z')
    const c = makeConsent(at)
    assert.deepEqual(c, { version: CONSENT_VERSION, at: '2026-11-21T20:15:00.000Z' })
    assert.deepEqual(cleanConsent(c), c)
    assert.equal(consentCurrent(c), true)
  })

  test('an older version, or none, is not current: a newer policy asks again', () => {
    assert.equal(consentCurrent({ version: '2025-01-01', at: '2025-01-01T00:00:00.000Z' }), false)
    assert.equal(consentCurrent(undefined), false)
    assert.equal(consentCurrent(null), false)
    assert.equal(consentCurrent(makeConsent(new Date(), '2027-02-01'), '2027-02-01'), true)
  })

  test('malformed records read as no consent', () => {
    const at = '2026-11-21T20:15:00.000Z'
    for (const raw of [undefined, null, 'yes', true, 1, [], {}, { version: CONSENT_VERSION }, { at }, { version: 1, at }, { version: '', at }, { version: CONSENT_VERSION, at: 'yesterday' }, { version: CONSENT_VERSION, at: 5 }, { version: 'x'.repeat(40), at }, { version: '../../x', at }]) {
      assert.equal(cleanConsent(raw), undefined, JSON.stringify(raw))
      assert.equal(consentCurrent(raw), false, JSON.stringify(raw))
    }
    assert.deepEqual(cleanConsent({ version: CONSENT_VERSION, at, by: 'someone' }), { version: CONSENT_VERSION, at }, 'extra fields are dropped')
  })
})

describe('prefs.consent (common/prefs.ts, main/prefs.ts)', () => {
  test('sanitizePrefs keeps a valid record and drops a malformed one', () => {
    const c = makeConsent()
    assert.deepEqual(sanitizePrefs({ consent: c }).consent, c)
    assert.equal('consent' in sanitizePrefs({ consent: { version: CONSENT_VERSION, at: 'soon' } }), false)
  })

  test("a renderer's prefs:set can't write consent, even a valid one; other prefs still go through", () => {
    const patch = fromRenderer({ consent: makeConsent(), appearance: 'dark' })
    assert.equal('consent' in patch, false)
    assert.equal(patch.appearance, 'dark')
  })

  test('patchPrefs (main) writes it and tells the listeners', () => {
    assert.equal(getPrefs().consent, undefined)
    const c = makeConsent()
    patchPrefs({ consent: c })
    assert.deepEqual(getPrefs().consent, c)
  })
})

// ---- the gate ------------------------------------------------------------------------------------------------------

describe('no capture and no permission prompt before consent (main/features/onboarding.ts)', () => {
  test('a first launch: the consent part is closed, and both prompts are refused with nothing asked or captured', async () => {
    const run = launch(dir)
    assert.equal(gateView().consent, false)
    const got = (await run.invoke('onboarding:get')) as { consent: boolean; consentVersion: string; gate: { consent: boolean } }
    assert.equal(got.consent, false)
    assert.equal(got.consentVersion, CONSENT_VERSION)
    assert.equal(got.gate.consent, false)

    assert.equal(await run.invoke('onboarding:prompt', 'screen'), false)
    assert.equal(await run.invoke('onboarding:prompt', 'accessibility'), false)
    assert.deepEqual(promptCalls, [], 'no getMediaAccessStatus, no desktopCapturer thumbnail, no isTrustedAccessibilityClient')
  })

  test('the login and "Set up later" never open the gate without consent', async () => {
    const run = launch(dir)
    setGatePart('login', true)
    await run.invoke('onboarding:later')
    assert.equal(gateView().setup, true)
    assert.equal(gateIsOpen(), false, 'no overlay, launcher or lesson before consent')
    await run.invoke('onboarding:agree')
    assert.equal(gateIsOpen(), true)
  })

  test('onboarding:agree stores this version with a time from main, opens the consent part, and the prompts work', async () => {
    const run = launch(dir)
    const before = Date.now()
    assert.equal(await run.invoke('onboarding:agree'), true)
    const after = Date.now()

    const c = getPrefs().consent
    assert.ok(c, 'prefs.consent is written')
    assert.equal(c.version, CONSENT_VERSION)
    const t = Date.parse(c.at)
    assert.ok(t >= before - 1000 && t <= after + 1000, `at is now: ${c.at}`)
    assert.match(c.at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    assert.equal(gateView().consent, true)
    const gates = run.broadcasts.filter(([ch]) => ch === 'onboarding:gate').map(([, v]) => v as { consent: boolean })
    assert.equal(gates.at(-1)?.consent, true, 'every window hears the consent part open')
    assert.equal(((await run.invoke('onboarding:get')) as { consent: boolean }).consent, true)

    // Now (on a Mac) the Screen Recording click asks macOS: the status read and the 1x1 capture that makes it ask.
    assert.equal(await run.invoke('onboarding:prompt', 'screen'), true)
    assert.deepEqual(promptCalls, ['media-status:screen', 'capture'])
  })

  test('agreeing again keeps the first record', async () => {
    const run = launch(dir)
    await run.invoke('onboarding:agree')
    const first = getPrefs().consent
    await new Promise((r) => setTimeout(r, 5))
    await run.invoke('onboarding:agree')
    assert.deepEqual(getPrefs().consent, first)
  })

  test('a record for an older policy version closes the gate again and is replaced on agree', async () => {
    patchPrefs({ consent: { version: '2025-01-01', at: '2025-01-01T00:00:00.000Z' } })
    const run = launch(dir)
    setGatePart('login', true)
    setGatePart('setup', true)
    assert.equal(gateIsOpen(), false)
    assert.equal(await run.invoke('onboarding:prompt', 'screen'), false)
    assert.deepEqual(promptCalls, [])
    await run.invoke('onboarding:agree')
    assert.equal(getPrefs().consent?.version, CONSENT_VERSION)
    assert.equal(gateIsOpen(), true)
  })

  test('a record already in prefs.json (this version) opens the consent part at launch', () => {
    patchPrefs({ consent: makeConsent() })
    launch(dir)
    assert.equal(gateView().consent, true)
  })
})

// ---- the flow ------------------------------------------------------------------------------------------------------

describe('the first run asks for consent before setup (shell/flow/phases.ts)', () => {
  test('after the intro: the login first, then consent, then setup', () => {
    assert.equal(phaseAfter('intro', { login: true, consent: true }), 'login')
    assert.equal(phaseAfter('login', { login: false, consent: true }), 'consent')
    assert.equal(phaseAfter('intro', { login: false, consent: true }), 'consent')
    assert.equal(phaseAfter('login', { login: false, consent: false }), 'setup')
  })

  test('setup (and its prompts) never comes while consent is needed', () => {
    for (const at of ['intro', 'login'] as const) for (const login of [true, false]) assert.notEqual(phaseAfter(at, { login, consent: true }), 'setup')
  })

  test("the renderer's row buttons ask for nothing before consent (onboarding/store.ts runAction)", () => {
    const store = readFileSync(join(__dirname, '../src/renderer/src/features/onboarding/store.ts'), 'utf8')
    const body = store.slice(store.indexOf('export async function runAction'), store.indexOf('switch (a)', store.indexOf('export async function runAction')))
    assert.match(body, /\(a === 'allow-screen' \|\| a === 'open-accessibility'\) && !get\(\)\.consent\) return/)
  })
})

// ---- the copy ------------------------------------------------------------------------------------------------------

describe('the consent screen copy (onboarding/consentCopy.ts)', () => {
  const lines = [CONSENT_TITLE, ...CONSENT_ROWS.flatMap((r) => [r.line, r.detail]), AGREE_LINE, CONTINUE]
  const all = lines.join(' ')
  const words = (s: string): number => s.trim().split(/\s+/).length
  const EM_DASH = String.fromCharCode(0x2014)
  const CAPITAL_BRAND = new RegExp(String.fromCharCode(77) + 'iyagi')

  test('says what R05 needs: screen and code to Anthropic (Claude), during a lesson, private apps, AI can be wrong', () => {
    assert.match(all, /Your screen and your code go to Anthropic \(Claude\)\./)
    assert.match(all, /during a lesson/i)
    assert.match(all, /build lessons and check your work/)
    assert.match(all, /Close private apps and tabs first\./)
    assert.match(all, /miyagi is AI and can be wrong\./)
  })

  test('D1: Anthropic only while Gemini is off', () => {
    if (GEMINI_ENABLED) return assert.match(all, /Google \(Gemini\)/)
    assert.doesNotMatch(all, /google|gemini/i)
    assert.deepEqual(
      CONSENT_ROWS.map((r) => r.id),
      ['screen', 'private', 'ai']
    )
  })

  test('the "I agree" line links the terms and the privacy policy, and the button matches it', () => {
    assert.equal(AGREE_LINE, 'By continuing you agree to the terms and privacy policy.')
    assert.equal(AGREE.terms, 'terms')
    assert.equal(AGREE.privacy, 'privacy policy')
    assert.equal(CONTINUE, 'Continue')
    assert.ok(AGREE_LINE.startsWith('By continuing'), 'the one primary is Continue, as the sentence says')
    assert.deepEqual(LEGAL_URL, { terms: 'https://miyagi.study/terms', privacy: 'https://miyagi.study/privacy' })
  })

  test('brand copy rules: 12 words a line at most, lowercase miyagi, no em dash, no emoji, no exclamation', () => {
    for (const s of lines) {
      assert.ok(words(s) <= 12, `too long: ${s}`)
      assert.ok(!CAPITAL_BRAND.test(s), `brand is lowercase: ${s}`)
      assert.ok(!s.includes(EM_DASH), `em dash: ${s}`)
      assert.ok(!/\p{Extended_Pictographic}/u.test(s), `emoji: ${s}`)
      assert.ok(!s.includes('!'), `exclamation: ${s}`)
    }
  })

  test('never describes push to talk (#226) or the coach web search (#227)', () => {
    assert.doesNotMatch(all, /talk|voice|microphone|listen|web search|search the web|searches/i)
  })
})

describe('links (R06): every miyagi.study page the app opens exists or is about to', () => {
  test('app/src links only to the home page, /privacy and /terms (no /pricing, /teams or /account 404s)', () => {
    const src = join(__dirname, '../src')
    const found = new Set<string>()
    const walk = (d: string): void => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const p = join(d, e.name)
        if (e.isDirectory()) walk(p)
        else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
          for (const m of readFileSync(p, 'utf8').matchAll(/https:\/\/miyagi\.study(\/[A-Za-z0-9/_-]*)?/g)) found.add(m[1] ?? '/')
        }
      }
    }
    walk(src)
    for (const path of found) assert.ok(['/', '/privacy', '/terms'].includes(path), `a link to https://miyagi.study${path}`)
    assert.ok(found.has('/privacy') && found.has('/terms'))
    assert.equal(CONTACT_EMAIL, 'hello@miyagi.study')
  })
})
