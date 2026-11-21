/**
 * Feature: settings. Account (Plan-OwnKey as a section, Set-Account's BYOK block). The real safeStorage path: the
 * flow is account.ts (moved from the old sheet), main owns the keys, this view only ever sees {set, last4}.
 *
 * One row per key (Anthropic, and Gemini as optional; ElevenLabs stays hidden), each a password field
 * (autocomplete off, spellcheck off, cleared after Save) with Clear / Undo inside it and the key's status:
 * white dot = your key, gray dot "From engine" = the engine's .env, ring = missing, "Invalid" in white. No green.
 * Save key is the section's one primary; Test is quiet. The plan card and meter (Set-Account) show only with an
 * account (v2Cloud): never this push.
 */
import { motion } from 'motion/react'
import { Lock, WifiOff } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import type { KeyState } from '../../../../../../../shared/contracts/events'
import { bridge } from '../../../bridge'
import { useLesson } from '../../../core/lesson'
import { PrimaryButtonV2, QuietButton, Spinner } from '../../../core/ui/atoms'
import { pressMotion } from '../../../core/ui/motion'
import { color, fill, radius2, type2 } from '../../../core/theme'
import type { KeyFlow } from '../account'
import { KEY_LABEL, REQUIRED, SHOWN, type KeyInfo, type KeyName } from '../keys'
import { Group, Note, PageHeader, TextButton } from '../ui'

const isRequired = (k: KeyName): boolean => REQUIRED.includes(k)

/** Where to get each key (main/safeOpen.ts allowlists these hosts). */
const KEY_HELP = 'https://console.anthropic.com/settings/keys'

export function Account({ flow, live }: { flow: KeyFlow; live: boolean }): ReactNode {
  const connected = useLesson((s) => s.connected)
  const inputs = useRef<Partial<Record<KeyName, HTMLInputElement | null>>>({})
  const { view, status } = flow

  // The caret goes where a key is needed first: a required key with no source, else the first row.
  useEffect(() => {
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

  return (
    <>
      <PageHeader title="Use your own key" caption="miyagi works without a key. Our cloud covers it. Your own key bills your own account." />

      <div onKeyDown={onKey}>
        <Group label="Your keys">
          {SHOWN.map((k) => (
            <KeyRow
              key={k}
              name={k}
              info={view?.keys[k]}
              state={status?.[k]}
              busy={flow.waiting.includes(k)}
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

      <Note icon={Lock}>{view && !view.secure ? 'Not saved: no secure storage. Kept for this run only.' : 'Kept in your Mac’s Keychain, never on our servers.'}</Note>

      <div className="flex items-center gap-[8px]">
        <span className="flex min-w-0 flex-1 items-center gap-[7px]" style={{ fontSize: type2.xs, color: color.label }}>
          {!flow.note && !connected && <WifiOff size={13} strokeWidth={1.8} className="shrink-0" />}
          {footNote && <span className="truncate">{footNote}</span>}
          {!footNote && <TextButton label="Where do I find my key?" onClick={() => bridge.invoke('open:external', KEY_HELP).catch(() => {})} />}
        </span>
        <QuietButton label="Test" busy={flow.testing} onClick={() => void flow.test()} />
        <PrimaryButtonV2 label="Save key" busy={flow.saving} disabled={!flow.dirty || flow.saving} onClick={() => void flow.save()} />
      </div>
    </>
  )
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
  const sub =
    state === 'invalid' ? { text: 'Invalid', c: color.text } : state === 'env' ? { text: 'From engine', c: color.label } : optional ? { text: 'Optional', c: color.faint } : undefined
  const set = !!info?.set && !cleared
  const placeholder = cleared ? 'Cleared' : set ? `•••• ${info?.last4 ?? ''}`.trim() : 'Paste your key'
  /** Clear (or Undo) sits inside the field, only when there's a stored key and nothing typed over it. */
  const clearable = (set || cleared) && !draft

  return (
    <div className="flex min-h-[56px] items-center gap-[12px] px-[16px]">
      <span className="grid w-[12px] shrink-0 place-items-center">{busy ? <Spinner size={12} c={color.label} /> : <KeyDot state={state} />}</span>
      <span className="flex w-[124px] shrink-0 flex-col justify-center">
        <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
          {KEY_LABEL[name]}
        </span>
        {sub && (
          <span className="truncate" style={{ fontSize: type2.xs, color: sub.c }}>
            {sub.text}
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
          className="h-full min-w-0 flex-1 bg-transparent text-white outline-none placeholder:text-(--ph)"
          style={{ fontFamily: 'var(--font-mono)', fontSize: type2.xs, caretColor: color.accent, ['--ph' as string]: set ? color.label : color.faint }}
        />
        {clearable && <SmallButton label={cleared ? 'Undo' : 'Clear'} onClick={onClear} />}
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
