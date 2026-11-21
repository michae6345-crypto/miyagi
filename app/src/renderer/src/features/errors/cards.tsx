/**
 * Feature: errors. The cards that grow out of the island (one white primary each, no status hue):
 *
 *   err-engine-offline (72)  "The engine stopped responding."  Restart engine / Copy details     Err-EngineReconnect 02
 *   err-editor-closed (66)   "Your place is saved."  Reopen in VS Code / End lesson for now      Err-VSCodeClosed
 *   err-build-failed (62)    "This video could not become a lesson."  Transcript (if offered), library Err-LessonBuildFailed
 *   err-limit (58)           "You have used today's free checks." (v2Cloud only, flagged)          Err-OfflineAndLimits
 *   err-crash (90)           "miyagi closed unexpectedly last time." (launch only, local only)     Err-CrashConsent
 */
import { useState, type ReactNode } from 'react'
import { ChevronRight, KeyRound } from 'lucide-react'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { canSend, startBuild, useCapability, useCurrentStep, useLesson } from '../../core/lesson'
import { sendAction } from '../../core/shortcuts'
import { setPrefs } from '../../core/prefs'
import { openAccount, openSettings } from '../../core/surfaces'
import { color, copy, fill, font, radius2, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { guard } from './lines'
import { Caption, CardFrame, ErrGlyph, Eyebrow } from './parts'
import { buildDetails, LIBRARY_ID, type DetailFields } from './scrub'
import { closeCard, decideCrash, TRIES, useErrors } from './store'

/** A text-only control (End lesson for now, View report): chrome, no fill. */
function TextButton({ label, onClick, underline }: { label: string; onClick: () => void; underline?: boolean }): ReactNode {
  return (
    <button
      type="button"
      className="cursor-pointer"
      style={{
        minHeight: 44,
        padding: underline ? 0 : '0 16px',
        background: 'transparent',
        border: 'none',
        color: underline ? color.text : color.label,
        fontSize: type2.sm,
        fontWeight: 500,
        textDecoration: underline ? 'underline' : undefined,
        textUnderlineOffset: 3
      }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

/** A rounded row on the card (the video, a file): neutral fill and hairline. */
function Chip({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="flex h-[44px] min-w-0 items-center gap-3" style={{ padding: '0 12px', borderRadius: radius2.card, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
      {children}
    </div>
  )
}

// ---- Copy details ------------------------------------------------------------------------------------------------

type AppInfo = { version?: string; system?: string }

/** Copy details: an allowlisted, scrubbed summary (scrub.ts); main scrubs again and writes the clipboard. */
async function copyDetails(): Promise<boolean> {
  const info = await bridge.invoke<AppInfo | null>('errors:info').catch(() => null)
  const s = useLesson.getState()
  const e = useErrors.getState()
  const index = s.stepId ? s.steps.findIndex((x) => x.id === s.stepId) : -1
  const total = Math.max(s.steps.length, s.lesson?.outline?.count ?? 0)
  const fields: DetailFields = {
    app: info?.version ? `${copy.name} ${info.version}` : copy.name,
    system: info?.system,
    link: e.link ? `${e.link.open ? 'open' : 'closed'}, ${e.link.failures} failed tries` : undefined,
    engine: s.localEngine?.state,
    engineVersion: s.hello?.version,
    contract: s.hello?.contract,
    lesson: s.lesson?.title,
    step: index >= 0 ? `${index + 1} of ${total}` : undefined,
    status: s.engineState,
    lastError: s.error?.message,
    at: new Date().toISOString()
  }
  const ok = await bridge.invoke<boolean>('diagnostics:copy', buildDetails(fields)).catch(() => false)
  return ok === true
}

// ---- engine offline (72) -----------------------------------------------------------------------------------------

export function EngineOfflineCard(): ReactNode {
  const restart = useErrors((s) => s.restart)
  const external = useLesson((s) => s.localEngine?.state === 'external') || restart === 'external'
  const inLesson = useLesson((s) => !!s.lesson)
  const [copied, setCopied] = useState<'yes' | 'no' | undefined>()

  const onRestart = async (): Promise<void> => {
    if (external) {
      bridge.invoke('engine-link:retry').catch(() => undefined)
      return
    }
    useErrors.setState({ restart: 'starting' })
    const r = await bridge.invoke<{ ok?: boolean; state?: string } | null>('engine-local:restart').catch(() => null)
    if (r?.ok) return
    useErrors.setState({ restart: r?.state === 'external' ? 'external' : 'failed' })
  }
  const onCopy = async (): Promise<void> => {
    const ok = await copyDetails()
    setCopied(ok ? 'yes' : 'no')
    setTimeout(() => setCopied(undefined), 2000)
  }

  const foot =
    restart === 'failed'
      ? 'Restart did not work. Quit and reopen miyagi.'
      : external
        ? 'This engine runs in Terminal. Restart it in Terminal.'
        : restart === 'starting'
          ? 'Restarting. This takes a few seconds.'
          : `Tried ${TRIES} times. Restart takes a few seconds.`
  return (
    <CardFrame
      id="err-engine-offline"
      role="alertdialog"
      head={
        <>
          <ErrGlyph g="ring" size={18} />
          <span style={{ fontSize: type2.xs, color: color.label }}>Engine offline</span>
        </>
      }
      title="The engine stopped responding."
      body={inLesson ? 'Your place in the lesson is saved.' : 'Nothing you made is lost.'}
    >
      <div className="flex flex-col gap-2">
        <PrimaryButton size="lg" block label={external ? 'Try again' : 'Restart engine'} busy={restart === 'starting'} disabled={restart === 'starting'} onClick={() => void onRestart()} />
        <QuietButton size="lg" block label={copied === 'yes' ? 'Copied' : copied === 'no' ? 'Could not copy' : 'Copy details'} onClick={() => void onCopy()} />
      </div>
      <Caption>{foot}</Caption>
    </CardFrame>
  )
}

// ---- editor closed (66) ------------------------------------------------------------------------------------------

export function EditorClosedCard(): ReactNode {
  const blocker = useLesson((s) => s.blockers.editor_closed)
  const paused = useLesson((s) => (s.paused?.reason === 'editor_closed' ? s.paused : undefined))
  const step = useCurrentStep()
  const name = copy.editorName()
  const count = step.index >= 0 && step.total > 0 ? `Step ${step.index + 1} of ${step.total}` : undefined
  const fallback = step.title ? `Reopen ${name} and pick up at ${step.title}.` : `Reopen ${name} to keep going.`
  const reopen = (): void => {
    useErrors.setState({ reopening: true, editorDismissed: true })
    sendAction('open_editor')
  }
  const end = (): void => {
    closeCard('err-editor-closed')
    bridge.send(cmd('end_lesson', {}))
  }
  return (
    <CardFrame
      id="err-editor-closed"
      head={
        <>
          <ErrGlyph g="ring" />
          <span className="truncate" style={{ fontSize: type2.sm, fontWeight: 500 }}>
            {guard(blocker?.title ?? paused?.title, `${name} closed. Lesson paused.`)}
          </span>
        </>
      }
      sub={count}
      title="Your place is saved."
      body={guard(paused?.body ?? blocker?.body, fallback)}
    >
      <div className="flex flex-col gap-2">
        <PrimaryButton size="lg" block label={guard(blocker?.action, `Reopen in ${name}`)} onClick={reopen} />
        <TextButton label="End lesson for now" onClick={end} />
      </div>
    </CardFrame>
  )
}

/** The launcher is open (main's signals); main takes only launcher:toggle, so toggle only while it is closed. */
let launcherShown = false
bridge.on('launcher:open', () => void (launcherShown = true))
bridge.on('launcher:closed', () => void (launcherShown = false))
function openLauncher(): void {
  if (!launcherShown) bridge.emit('launcher:toggle')
}

// ---- build failed (62) -------------------------------------------------------------------------------------------

const FAIL_REASON: Record<string, string> = {
  unreadable_code: 'The code on screen is too small to read reliably.',
  no_steps: 'There were no clear steps to follow in it.',
  too_long: 'It is too long to turn into one lesson.',
  no_captions: 'It has no captions to build steps from.',
  network: 'The connection dropped while it was building.',
  provider: 'The AI was too busy to finish it.',
  unknown: 'Something went wrong while it was building.'
}

/** youtube.com/watch?v=... : the link without its scheme, for reading only (never opened from here). */
function shortUrl(url?: string): string | undefined {
  if (!url) return undefined
  try {
    const u = new URL(url)
    if (u.protocol !== 'https:' && u.protocol !== 'http:') return undefined
    return `${u.host.replace(/^www\./, '')}${u.pathname}${u.search}`.slice(0, 60)
  } catch {
    return undefined
  }
}

export function BuildFailedCard(): ReactNode {
  const bf = useLesson((s) => s.buildFailed)
  const libraryOk = useCapability('library.start')
  if (!bf) return null
  const src = bf.source
  const alts = bf.alternatives ?? []
  const transcript = alts.find((a) => a.kind === 'transcript')
  // Only an engine that offers a transcript alternative gets "Try transcript only". No `alternatives`, or none of kind
  // 'transcript', = "Find another video": no engine reads a transcriptOnly flag on its own, so we never guess one.
  const transcriptUrl = transcript ? transcript.url ?? (src?.kind === 'youtube' ? src.url : undefined) : undefined
  const library = libraryOk ? alts.filter((a) => a.kind === 'library' && !!a.id && LIBRARY_ID.test(a.id)).slice(0, 3) : []
  const video = src?.kind === 'youtube' || !src
  const fallbackReason = FAIL_REASON[bf.failCode ?? 'unknown'] || FAIL_REASON.unknown
  const reason = guard(bf.failReason?.trim(), fallbackReason)

  const tryTranscript = (): void => {
    if (!transcriptUrl) return
    closeCard('err-build-failed')
    startBuild()
    bridge.send(cmd('learn_url', { url: transcriptUrl, transcriptOnly: true }))
  }
  const startLibrary = (id: string): void => {
    if (!canSend('library.start')) return
    closeCard('err-build-failed')
    startBuild()
    bridge.send(cmd('library.start', { id }))
  }
  const findAnother = (): void => {
    closeCard('err-build-failed')
    openLauncher()
  }

  return (
    <CardFrame id="err-build-failed" esc title={video ? 'This video could not become a lesson.' : 'This lesson could not be built.'} body={reason}
      head={
        src?.title ? (
          <span className="truncate" style={{ fontSize: type2.xs, color: color.label }}>
            Build stopped
          </span>
        ) : undefined
      }
    >
      {src?.title && (
        <Chip>
          <svg aria-hidden width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
            <rect x="1.5" y="3.5" width="15" height="11" rx="3" fill="none" stroke={color.label} strokeWidth="1.4" />
            <path d="M7.5 6.5 L11.5 9 L7.5 11.5 Z" fill={color.label} />
          </svg>
          <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.text }}>
            {src.title}
          </span>
          {shortUrl(src.url) && (
            <span className="max-w-[45%] truncate" style={{ fontFamily: font.mono, fontSize: type2.micro, color: color.label }}>
              {shortUrl(src.url)}
            </span>
          )}
        </Chip>
      )}
      {transcriptUrl ? (
        <div className="flex flex-col gap-2">
          <PrimaryButton size="lg" block label={guard(transcript?.title?.trim(), 'Try transcript only')} onClick={tryTranscript} />
          <Caption>{guard(transcript?.meta?.trim(), 'Builds steps from what the teacher says. Checks may be looser.')}</Caption>
        </div>
      ) : (
        <PrimaryButton size="lg" block label="Find another video" onClick={findAnother} />
      )}
      {library.length > 0 && (
        <div className="flex flex-col gap-2">
          <Eyebrow>Or start a library lesson</Eyebrow>
          <div className="flex flex-col overflow-hidden" style={{ borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
            {library.map((a, i) => (
              <button
                key={a.id}
                type="button"
                className="flex h-[52px] cursor-pointer items-center gap-3 text-left"
                style={{ padding: '0 16px', background: 'transparent', border: 'none', borderTop: i ? `1px solid ${surface.border}` : 'none', color: color.text }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => startLibrary(a.id!)}
              >
                <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate" style={{ fontSize: type2.sm, fontWeight: 500 }}>
                    {guard(a.title, 'Library lesson')}
                  </span>
                  {a.meta && (
                    <span className="truncate" style={{ fontSize: type2.xs, color: color.label }}>
                      {guard(a.meta, '')}
                    </span>
                  )}
                </span>
                <ChevronRight size={14} strokeWidth={1.8} color={color.label} />
              </button>
            ))}
          </div>
        </div>
      )}
    </CardFrame>
  )
}

// ---- limit (58, v2Cloud only) ------------------------------------------------------------------------------------

export function LimitCard(): ReactNode {
  return (
    <CardFrame
      id="err-limit"
      head={<span style={{ fontSize: type2.xs, color: color.label }}>Free plan</span>}
      title="You have used today's free checks."
      body="Your progress is saved. Free checks reset tomorrow."
    >
      <div className="flex flex-col gap-2">
        <PrimaryButton size="lg" block label="See plans" onClick={() => void openAccount('upgrade')} />
        <QuietButton size="lg" block icon={KeyRound} label="Use your own API key" onClick={() => void openSettings('account')} />
      </div>
      <Caption>Lessons stay free to read. Only checks and help count.</Caption>
    </CardFrame>
  )
}

// ---- crash consent (90) ------------------------------------------------------------------------------------------

const INCLUDES = ['App and macOS version', 'Error log', 'Lesson name and step']
const NEVER = ['Your code or files', 'Screenshots', 'API keys']

export function CrashCard(): ReactNode {
  const report = useErrors((s) => s.crash?.report)
  const [always, setAlways] = useState(false)
  const [view, setView] = useState(false)
  const save = (): void => {
    if (always) setPrefs({ crashReports: 'always' })
    decideCrash(true)
  }
  return (
    <CardFrame
      id="err-crash"
      role="alertdialog"
      esc={false}
      head={
        <>
          <MiyagiMark size={18} />
          <span style={{ fontFamily: font.brand, fontSize: type2.md, fontWeight: 500 }}>{copy.name}</span>
        </>
      }
      title={`${copy.name} closed unexpectedly last time.`}
      body="Save a crash report on this Mac? Nothing is sent."
    >
      <div className="grid grid-cols-2" style={{ borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
        {[
          ['Includes', INCLUDES],
          ['Never', NEVER]
        ].map(([head, items], i) => (
          <div key={head as string} className="flex flex-col" style={{ padding: '12px 16px', gap: 6, borderLeft: i ? `1px solid ${surface.border}` : undefined }}>
            <Eyebrow>{head as string}</Eyebrow>
            {(items as string[]).map((t) => (
              <span key={t} style={{ fontSize: type2.xs, lineHeight: '16px' }}>
                {t}
              </span>
            ))}
          </div>
        ))}
      </div>
      {view && report && (
        <pre
          data-err-report
          className="m-0 max-h-[160px] overflow-auto whitespace-pre-wrap break-words"
          style={{ padding: 12, borderRadius: radius2.card, background: fill.field, fontFamily: font.mono, fontSize: type2.micro, lineHeight: '16px', color: color.label }}
        >
          {report}
        </pre>
      )}
      <label className="flex min-h-[44px] cursor-pointer items-center gap-3" style={{ fontSize: type2.sm, color: color.text }}>
        <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} style={{ width: 18, height: 18, margin: 0, accentColor: color.accent }} />
        Always save without asking
      </label>
      <div className="flex items-center gap-2">
        <span className="mr-auto">
          <TextButton underline label={view ? 'Hide report' : 'View report'} onClick={() => setView((v) => !v)} />
        </span>
        <QuietButton size="lg" label="Don't save" onClick={() => decideCrash(false)} />
        <PrimaryButton size="lg" label="Save report" onClick={save} />
      </div>
      <Caption>Saved on this Mac only.</Caption>
    </CardFrame>
  )
}
