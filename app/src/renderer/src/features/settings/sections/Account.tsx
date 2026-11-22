/**
 * Feature: settings. Your own key (Plan-OwnKey as a section, Set-Account's BYOK block). The real safeStorage path:
 * the flow is account.ts, main owns the keys, this view only ever sees {set, last4}.
 *
 * One row per key (Anthropic; Gemini as optional only when GEMINI_ENABLED, hidden at launch by D1; ElevenLabs stays
 * hidden), each a password field
 * (autocomplete off, spellcheck off, cleared after Save) with Clear / Undo inside it and the key's status as words
 * under its name (no bare dots, persona QA): "Works" with a white tick, "Using miyagi's key" (the engine's own),
 * "Saved", "Not set" (ring), "Not yet. Check the key." (ring). No green: green only means a step passed.
 * Save key is the section's one primary (live the moment a field changes, then "Saved to Keychain"); Test is quiet
 * and needs a key to test. The plan card and meter (Set-Account) show only with an account (v2Cloud): never this push.
 */
import { motion } from 'motion/react'
import { Check, ExternalLink, Lock, WifiOff } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import type { KeyState } from '../../../../../../../shared/contracts/events'
import { GEMINI_ENABLED } from '../../../../../common/flags'
import { bridge } from '../../../bridge'
import { useLesson } from '../../../core/lesson'
import { PrimaryButtonV2, QuietButton, Spinner } from '../../../core/ui/atoms'
import { fade, pressMotion } from '../../../core/ui/motion'
import { color, copy, fill, radius2, type2 } from '../../../core/theme'
import type { KeyFlow } from '../account'
import { KEY_LABEL, REQUIRED, SHOWN, type KeyInfo, type KeyName } from '../keys'
import { useSettings } from '../store'
import { Group, Note, PageHeader } from '../ui'
import { OWN_KEY } from '../words'

/** The Windows build says the same about its own machine: "this computer", never "this Mac" or the Keychain. */
const ON_MAC = bridge.platform.os === 'mac'

const isRequired = (k: KeyName): boolean => REQUIRED.includes(k)

/** Where to get each key (main/safeOpen.ts allowlists these hosts). */
const KEY_HELP = 'https://console.anthropic.com/settings/keys'
/** Names the providers the sheet shows: Anthropic only at launch (D1, common/flags.ts GEMINI_ENABLED). */
const OWN_KEY_CAPTION =GEMINI_ENABLED ? 'Paste an Anthropic or Gemini key. Calls then bill your own account.' : 'Paste an Anthropic key. Calls then bill your own account.'
/** The footer line that says why Test is off. */
const TEST_WHY = 'settings-key-test-why'

export function Account({ flow, live }: { flow: KeyFlow; live: boolean }): ReactNode {
  const connected = useLesson((s) => s.connected)
  const inputs = useRef<Partial<Record<KeyName, HTMLInputElement | null>>>({})
  const { view, status } = flow

  // The caret goes where a key is needed first: a required key with no source, else the first row. On open (the limit
  // card's "Your own key", or the sheet opening here) and on a click it does, even though the sidebar focused its tab
  // first. Not when the learner arrived with ↑ / ↓ in the sidebar: focus stays on the list so the arrows keep working.
  useEffect(() => {
    if (useSettings.getState().via === 'keys') return
    const first = SHOWN.find((k) => isRequired(k) && status?.[k] === 'missing') ?? SHOWN[0]
    inputs.current[first]?.focus({ preventScroll: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.target instanceof HTMLInputElement) {
      e.preventDefault()
      void flow.save()
    }
  }

  const footNote = flow.note ?? (!connected ? 'Offline' : undefined)
  // Test re-sends the stored keys: with nothing stored (and nothing from the engine) there is nothing to test.
  const testable = SHOWN.some((k) => !!view?.keys[k]?.set || status?.[k] === 'env' || status?.[k] === 'ok')

  return (
    <>
      <PageHeader title={OWN_KEY} caption={OWN_KEY_CAPTION} />

      <div onKeyDown={onKey}>
        <Group label="Your keys">
          {SHOWN.map((k) => (
            <KeyRow
              key={k}
              name={k}
              info={view?.keys[k]}
              state={status?.[k]}
              busy={flow.waiting.includes(k) || (flow.testing && !!view?.keys[k]?.set)}
              draft={flow.drafts[k] ?? ''}
              cleared={flow.cleared.includes(k)}
              readOnly={!live}
              inputRef={(el) => {
                inputs.current[k] = el
              }}
              onDraft={(v) => flow.setDraft(k, v)}
              onClear={() => {
                flow.toggleClear(k)
                inputs.current[k]?.focus({ preventScroll: true })
              }}
            />
          ))}
        </Group>
      </div>

      <Note icon={Lock}>{view && !view.secure ? 'Not saved: no secure storage. Kept for this run only.' : ON_MAC ? 'Kept in your Mac’s Keychain, never on our servers.' : 'Kept encrypted on this computer, never on our servers.'}</Note>

      <div className="flex min-h-[36px] items-center gap-[8px]">
        <span className="flex min-w-0 flex-1 items-center gap-[7px]" style={{ fontSize: type2.xs, color: color.label }}>
          {!flow.note && !connected && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
          {footNote && <span className="truncate">{footNote}</span>}
          {!footNote && flow.saved && (
            <motion.span
              role="status"
              className="flex min-w-0 items-center gap-[6px]"
              style={{ color: color.text }}
              initial={{ opacity: 0, y: 2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={fade.in}
            >
              <Check size={13} strokeWidth={1.8} aria-hidden className="shrink-0" />
              <span className="truncate">{flow.saved}</span>
            </motion.span>
          )}
          {/* Why Test is off, said out loud: a disabled button's tooltip rarely shows and screen readers never read it. */}
          {!footNote && !flow.saved && !testable && live && (
            <span id={TEST_WHY} className="min-w-0 truncate" data-test-why>
              Save a key to test it.
            </span>
          )}
          {!footNote && !flow.saved && <HelpLink label="Where do I find my key?" onClick={() => bridge.invoke('open:external', KEY_HELP).catch(() => {})} />}
        </span>
        {/* The title sits on a wrapper: hover on a disabled button never reaches its own title. */}
        <span className="flex shrink-0" title={testable ? undefined : 'Save a key first, then test it'}>
          <QuietButton label="Test" busy={flow.testing} disabled={!testable || flow.testing || !live} onClick={() => void flow.test()} />
        </span>
        <PrimaryButtonV2 label="Save key" busy={flow.saving} disabled={!flow.dirty || flow.saving} onClick={() => void flow.save()} />
      </div>
    </>
  )
}

type Sub = { text: string; c: string; glyph?: 'tick' | 'ring' | 'spin' }

function statusOf(state: KeyState | undefined, set: boolean, optional: boolean, busy: boolean): Sub | undefined {
  if (busy) return { text: 'Checking', c: color.label, glyph: 'spin' }
  if (state === 'ok') return { text: 'Works', c: color.text, glyph: 'tick' }
  if (state === 'invalid') return { text: 'Not yet. Check the key.', c: color.text, glyph: 'ring' }
  if (state === 'env') return { text: `Using ${copy.name}'s key`, c: color.label, glyph: 'tick' }
  if (set) return { text: 'Saved', c: color.label, glyph: 'tick' }
  if (optional) return { text: 'Optional', c: color.faint }
  return { text: 'Not set', c: color.label, glyph: 'ring' }
}

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
  const set = !!info?.set && !cleared
  const sub = statusOf(state, set, optional, busy)
  const placeholder = cleared ? 'Cleared' : set ? `•••• ${info?.last4 ?? ''}`.trim() : 'Paste your key'
  /** Clear (or Undo) sits inside the field, only when there's a stored key and nothing typed over it. */
  const clearable = (set || cleared) && !draft

  return (
    <div className="flex min-h-[60px] items-center gap-[12px] px-[16px]">
      <span className="flex w-[156px] shrink-0 flex-col justify-center gap-[2px]">
        <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
          {KEY_LABEL[name]}
        </span>
        {sub && (
          <span data-key-status className="flex min-w-0 items-center gap-[5px]" style={{ fontSize: type2.xs, color: sub.c }}>
            {sub.glyph === 'spin' ? (
              <Spinner size={11} c={color.label} />
            ) : sub.glyph === 'tick' ? (
              <Check size={12} strokeWidth={1.8} aria-hidden className="shrink-0" />
            ) : sub.glyph === 'ring' ? (
              <Ring />
            ) : null}
            <span className="truncate">{sub.text}</span>
          </span>
        )}
      </span>
      <div
        className={`flex h-[36px] min-w-0 flex-1 items-center gap-[8px] pl-[12px] ${clearable ? 'pr-[4px]' : 'pr-[12px]'}`}
        style={{ borderRadius: radius2.control, background: fill.segmentTrack, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}
      >
        <input
          ref={inputRef}
          type="password"
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          readOnly={readOnly}
          placeholder={placeholder}
          aria-label={`${KEY_LABEL[name]} key`}
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          data-1p-ignore
          className="h-full min-w-0 flex-1 bg-transparent outline-none placeholder:text-(--ph)"
          style={{ color: color.text, fontFamily: 'var(--font-mono)', fontSize: type2.xs, caretColor: color.accent, ['--ph' as string]: set ? color.label : color.faint }}
        />
        {clearable && <SmallButton label={cleared ? 'Undo' : 'Clear'} onClick={onClear} />}
      </div>
    </div>
  )
}

/** Not set / not working: the hollow ring (no hue). */
function Ring(): ReactNode {
  return <span aria-hidden className="block h-[10px] w-[10px] shrink-0 rounded-full border-[1.5px]" style={{ borderColor: color.label }} />
}

/** A link out (the provider's key page): underlined, with the external-link glyph. */
function HelpLink({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <button
      type="button"
      className="flex h-[32px] shrink-0 cursor-pointer items-center gap-[5px] whitespace-nowrap font-medium underline decoration-1 underline-offset-[3px] transition-colors hover:text-(--hover)"
      style={{ fontSize: type2.xs, color: fill.chipText, ['--hover' as string]: color.text }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
      <ExternalLink size={12} strokeWidth={1.8} aria-hidden />
    </button>
  )
}

/** Clear / Undo inside a field: neutral chrome. Polish: hover is the .mg-press tint, not an animated fill. */
function SmallButton({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      {...pressMotion()}
      className="mg-press flex h-[26px] shrink-0 cursor-pointer items-center whitespace-nowrap px-[10px] font-medium"
      style={{ borderRadius: radius2.keycap, backgroundColor: fill.button, color: color.text, fontSize: type2.xs }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}
