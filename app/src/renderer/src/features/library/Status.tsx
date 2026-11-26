/**
 * Feature: library. The sidebar's status area (Home): is miyagi ready to teach, at a glance.
 *
 *   Setup    the onboarding rows (permissions + companion + engine, features/onboarding read-only): "All set" or
 *            "2 of 4 ready". A click opens guided setup (openOnboarding).
 *   Ready    one calm line for the engine and the cloud access together (features/errors startup.ts + boot.tsx):
 *            "miyagi is getting ready" with a soft progress line, "Ready", and only after a real failure or 45 s
 *            "miyagi couldn't start" with Retry and Copy details. Round 5: it replaced "Engine Connecting" and
 *            "Cloud Waiting", which read like an alarm while everything was simply starting.
 *   Plan     v2Cloud only (mock data in the stage, off in a normal build): the plan and this period's live help.
 *            A click opens the account sheet in the home window (features/shell sheet.ts), the account window elsewhere.
 * Status glyphs are the shared ones: green only when that part is done, the white ring for Not yet, gray otherwise.
 * Reads only; it asks for fresh permissions / health / cloud when the window comes forward. Never prompts.
 */
import { ChevronRight } from 'lucide-react'
import { LayoutGroup, motion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { useLesson } from '../../core/lesson'
import { openOnboarding } from '../../core/surfaces'
import { color, fill, radius2, spring, surface, type2 } from '../../core/theme'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { v2Cloud } from '../account/model'
import { loadAccount, useAccount } from '../account/store'
import { BootRow } from '../errors/boot'
import { useBoot } from '../errors/startup'
import { setupFix } from './homeModel'
import { summarize, useRows } from '../onboarding/rows'
import { refreshCloud, refreshPerms, requestHealth, runAction, useOnboarding } from '../onboarding/store'
import { openAccountSurface } from '../shell/sheet'
import { Press } from './motion'

type Line = { state: StatusState; word: string; detail?: string }

/** The cloud help isn't used on this Mac (it builds with its own key): the plan's help meter would contradict that. */
function useCloudUnused(): boolean {
  const cloud = useOnboarding((s) => s.cloud?.state)
  const status = useLesson((s) => s.keyStatus?.cloud)
  return !status && cloud !== 'ok' && cloud !== 'minting' && cloud !== 'failed'
}

function Row({ label, line, onClick, chevron }: { label: string; line: Line; onClick?: () => void; chevron?: boolean }): ReactNode {
  const body = (
    <>
      <StatusGlyph state={line.state} size={14} />
      <span className="relative min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.text }}>
        {label}
      </span>
      <span className="relative shrink-0 truncate" data-status-word={line.state} style={{ fontSize: type2.xs, color: line.state === 'passed' ? fill.keycapText : line.state === 'notyet' ? color.text : color.label, maxWidth: 96 }}>
        {line.word}
      </span>
      {chevron && <ChevronRight aria-hidden size={13} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.faint }} />}
    </>
  )
  const style = { height: 32, padding: '0 8px', borderRadius: radius2.control, gap: 8 }
  if (!onClick)
    return (
      <div className="flex items-center" style={style} title={line.detail}>
        {body}
      </div>
    )
  return (
    <Press className="flex w-full items-center" style={style} title={line.detail} aria-label={`${label}: ${line.word}. ${line.detail ?? ''}`} onClick={onClick}>
      {body}
    </Press>
  )
}

/** cloudUnused: the help meter counts cloud help, so with the cloud "Not used" it would contradict the row above. */
function PlanRow({ cloudUnused }: { cloudUnused: boolean }): ReactNode {
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  useEffect(() => {
    void loadAccount()
  }, [])
  if (!loaded) return <div aria-hidden style={{ height: 44, margin: '4px 8px 0', borderRadius: radius2.control, background: fill.skeleton }} />
  if (!account?.signedIn)
    return <Row label="Account" line={{ state: 'unknown', word: 'Sign in', detail: 'Sign in to keep your plan on every computer.' }} onClick={() => openAccountSurface('signin')} chevron />
  const help = cloudUnused ? undefined : account.help
  const plan = account.plan === 'pro' ? 'Pro plan' : account.plan === 'teams' ? 'Teams plan' : 'Free plan'
  const f = help && help.limit ? Math.min(1, help.used / help.limit) : 0
  return (
    <Press className="flex w-full flex-col" style={{ padding: '8px 8px', gap: 6, borderRadius: radius2.control }} aria-label={`${plan}${help ? `, ${help.used} of ${help.limit} help used` : ''}`} onClick={() => openAccountSurface('account')}>
      <span className="relative flex w-full items-center" style={{ gap: 8 }}>
        <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.text }}>
          {plan}
        </span>
        {help && (
          <span className="shrink-0 tabular-nums" style={{ fontSize: type2.xs, color: color.label }}>
            {help.used} of {help.limit} help
          </span>
        )}
        <ChevronRight aria-hidden size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.faint }} />
      </span>
      {help && help.limit > 0 && (
        <span className="relative block w-full overflow-hidden" style={{ height: 4, borderRadius: radius2.round, background: fill.hairline }}>
          <span className="absolute inset-0 block origin-left" style={{ background: color.text, transform: `scaleX(${f})`, borderRadius: radius2.round }} />
        </span>
      )}
    </Press>
  )
}

/**
 * `plan`: false when the account chip below shows the plan already (the home window's sidebar).
 * `setup`: false keeps only the ready line (a short window).
 */
export function StatusArea({ plan = true, setup: withSetup = true }: { plan?: boolean; setup?: boolean } = {}): ReactNode {
  const rows = useRows()
  const sum = summarize(rows)
  const cloudUnused = useCloudUnused()
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)
  const known = rows.some((r) => r.state !== 'unknown')

  // Fresh reads when the window opens, comes forward, or the engine (re)connects. None of these prompt.
  useEffect(() => {
    const read = (): void => {
      void refreshPerms()
      refreshCloud()
      requestHealth()
    }
    read()
    addEventListener('focus', read)
    return () => removeEventListener('focus', read)
  }, [connected, hello])

  // One line, never two that disagree: miyagi's own start-up first (starting, or failed with Retry), then the one thing
  // left to fix ("Turn on Accessibility", opens setup), else "Ready".
  const boot = useBoot()
  const fix = known && !sum.canStart ? setupFix(rows) : undefined
  const bootBusy = boot.phase !== 'ready' && boot.phase !== 'limited'
  const one: Line = !known ? { state: 'unknown', word: 'Checking' } : fix ? { state: 'notyet', word: fix.line, detail: sum.hint } : { state: 'passed', word: 'Ready', detail: 'Everything miyagi needs is on.' }

  return (
    <LayoutGroup id="home-status">
      <motion.section layout transition={spring} aria-label="Status" data-home-status className="flex flex-col" style={{ padding: 2 }}>
        {bootBusy ? (
          <motion.div layout="position" transition={spring}>
            <BootRow />
          </motion.div>
        ) : withSetup && fix ? (
          <motion.div layout="position" transition={spring}>
            <Press className="flex w-full items-center" style={{ height: 32, padding: '0 8px', borderRadius: radius2.control, gap: 8 }} title={one.detail} aria-label={fix.restart ? `${one.word}. Restart miyagi.` : `${one.word}. Open setup.`} onClick={() => void (fix.restart ? runAction('relaunch') : openOnboarding())}>
              <StatusGlyph state={one.state} size={14} />
              <span className="relative min-w-0 flex-1 truncate" data-status-word={one.state} style={{ fontSize: type2.sm, color: color.text }}>
                {one.word}
              </span>
              <ChevronRight aria-hidden size={13} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.faint }} />
            </Press>
          </motion.div>
        ) : (
          <div data-status-word={one.state} className="flex items-center" style={{ height: 32, padding: '0 8px', gap: 8 }} title={one.detail}>
            <StatusGlyph state={one.state} size={14} still />
            <span style={{ fontSize: type2.sm, color: one.state === 'passed' ? fill.keycapText : color.label }}>{one.word}</span>
          </div>
        )}
        {v2Cloud && plan && (
          <motion.div layout="position" transition={spring}>
            <div aria-hidden style={{ height: 1, margin: '4px 8px', background: fill.rule }} />
            <PlanRow cloudUnused={cloudUnused} />
          </motion.div>
        )}
      </motion.section>
    </LayoutGroup>
  )
}
