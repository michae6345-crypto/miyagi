/**
 * Feature: settings, v4 page (Adrian's ui-next mock, screens settings / settings-apps / settings-data, Nov 23-24).
 * Two columns of groups, every row a setting the app already has. Rows come from the same SETTINGS list the sheet and
 * the search use (rows.tsx), so a row here is never a second copy of a control. Inside `Flat` the shared Group / Row
 * draw as a section head and hairline rows, so ptt's and the buddy's own rows match without their own code changing.
 *
 * Brand over the mock: "Connected" is a white tick and the word, never green (green only means passed); buttons are
 * the quiet outline; nothing pastel. The trim pass is kept: no Language (one option), no "Export my progress" twice.
 */
import { ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { setPrefs, usePrefs } from '../../../core/prefs'
import { openOnboarding } from '../../../core/surfaces'
import { color, copy, type2 } from '../../../core/theme'
import { Keycap, QuietButton, StatusGlyph, Toggle } from '../../../core/ui/atoms'
import { planLabel } from '../../account/model'
import { useAccount } from '../../account/store'
import { useAuth } from '../../auth/store'
import { BuddyPreview, BuddySwatches } from '../../buddy/ColorPicker'
import { words as buddyWords } from '../../buddy/name'
import { PushToTalk } from '../../ptt/SettingsRows'
import { startTour } from '../../tips/tourStore'
import { useUpdates } from '../../updates/store'
import { setPagePanel } from '../nav'
import { useHealth } from '../permissions'
import { FACTS } from '../privacy/facts'
import { SettingRowById } from '../rows'
import { IslandRow } from '../sections/General'
import { Group, OnWord, Plain, Row } from '../ui'
import { APP_GROUPS, APPS, appCaption, askDelete, clearCache, size, tryInvoke, useYourData, type AppRow } from './data'
import { isElectron } from '../../../bridge'
import type { HealthItem } from '../../../../../../../shared/contracts/events'

/** Two columns 56 apart (one under the other when the panel is narrower than two 330 px columns). */
export function Cols({ left, right }: { left: ReactNode; right: ReactNode }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const [two, setTwo] = useState(true)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setTwo(e.contentRect.width >= 720))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} data-v4-cols={two ? 2 : 1} className="grid items-start" style={{ gridTemplateColumns: two ? 'minmax(0,1fr) minmax(0,1fr)' : 'minmax(0,1fr)', columnGap: 56 }}>
      <div className="flex min-w-0 flex-col">{left}</div>
      <div className="flex min-w-0 flex-col">{right}</div>
    </div>
  )
}

/**
 * A quiet button that may say a word after it ran ("Cleared."). `pending`: main has no handler for it yet
 * (apps:connect:<id>, data:open-folder, data:cache-clear; Core request in agents/v4-settings.md), so in Electron it
 * shows disabled with a tooltip instead of answering every click with an error; the stage's stand-ins keep it working.
 */
function RunButton({ label, run, pending = false }: { label: string; run: () => Promise<string> | string | void; pending?: boolean }): ReactNode {
  const [note, setNote] = useState<string>()
  useEffect(() => {
    if (!note) return
    const t = setTimeout(() => setNote(undefined), 2500)
    return () => clearTimeout(t)
  }, [note])
  return (
    <span className="flex shrink-0 items-center gap-[12px]">
      {note && (
        <span role="status" className="whitespace-nowrap" style={{ fontSize: type2.xs, color: color.label }}>
          {note}
        </span>
      )}
      <QuietButton
        label={label}
        disabled={pending && isElectron}
        title={pending && isElectron ? 'Coming in an update.' : undefined}
        onClick={() => {
          void Promise.resolve(run()).then((r) => r && setNote(r))
        }}
      />
    </span>
  )
}

/** "See the list ›": a quiet text link to another panel. */
function PanelLink({ label, to }: { label: string; to: Parameters<typeof setPagePanel>[0] }): ReactNode {
  return (
    <button
      type="button"
      className="mg-press flex shrink-0 cursor-pointer items-center gap-[6px] whitespace-nowrap"
      style={{ fontSize: type2.sm, color: color.label, background: 'none', border: 0, padding: 0 }}
      onClick={() => setPagePanel(to)}
    >
      {label}
      <ChevronRight size={14} strokeWidth={1.8} aria-hidden />
    </button>
  )
}

// ---- General ---------------------------------------------------------------------------------------------------------

function BuddyRow(): ReactNode {
  return (
    <Row
      label={buddyWords.row}
      right={
        <span data-settings-buddy className="flex shrink-0 items-center gap-[10px]">
          <BuddyPreview size={26} />
          <BuddySwatches size={18} gap={7} name={false} />
        </span>
      }
    />
  )
}

function UpdatesRow(): ReactNode {
  const current = useUpdates((u) => u.view?.current)
  return <SettingRowById id="updates" label={current ? `${copy.name} ${current}` : 'Updates'} caption="miyagi also checks on its own." />
}

export function General4(): ReactNode {
  const launchAtLogin = usePrefs((s) => s.launchAtLogin)
  return (
    <Cols
      left={
        <>
          <Group label="Appearance">
            <SettingRowById id="theme" caption="" />
            <SettingRowById id="text-size" caption="" />
            <SettingRowById id="density" caption="How much room each row gets." />
            <SettingRowById id="sidebar-compact" caption="Icons only, at any window size." />
            <SettingRowById id="reduce-motion" caption="" />
            <BuddyRow />
          </Group>
          <Group label="Startup">
            <Row label={`Open ${copy.name}`} caption="From anywhere on this Mac." right={<Keycap k="launcher" />} />
            <Row
              tight
              label="Launch at login"
              caption="miyagi waits in the pill until you need it."
              right={<Toggle label="Launch at login" on={launchAtLogin} onChange={(v) => setPrefs({ launchAtLogin: v })} />}
            />
            <SettingRowById id="start-page" caption="" />
            <IslandRow label={`Where ${copy.name} lives`} />
          </Group>
        </>
      }
      right={
        <>
          <Group label="Sound">
            <SettingRowById id="sounds" />
            <SettingRowById id="sound-taps" caption="" />
          </Group>
          <PushToTalk />
          <Group label="Help as you learn">
            <SettingRowById id="tips" caption="" />
            <SettingRowById id="sidebar-status" caption="The Ready line at the foot of the sidebar." />
            <SettingRowById id="reset-tips" caption="See the first-run tips again." />
            <Row label="Show me around" caption="A short tour of the pill and the launcher." right={<QuietButton label="Start" onClick={() => startTour()} />} />
            <Row label={`Set up ${copy.name}`} caption="Check permissions and VS Code again." right={<QuietButton label="Open setup" onClick={() => void openOnboarding()} />} />
          </Group>
          <Group label="Updates">
            <UpdatesRow />
          </Group>
          <Group label="Reset">
            <SettingRowById id="reset-local" caption="Your lessons and skills stay." />
          </Group>
        </>
      }
    />
  )
}

// ---- Apps ------------------------------------------------------------------------------------------------------------

/**
 * What the engine said, and only that: Connected only when its health item is ok (a white tick and the word, never
 * green). With no health item the row says how miyagi reads the app (Reads exactly / Screen only), never Connected.
 */
function AppStatus({ app, item }: { app: AppRow; item?: HealthItem }): ReactNode {
  if (item?.state === 'ok') return <OnWord>Connected</OnWord>
  if (item?.state === 'checking') return <StatusGlyph state="checking" size={14} />
  if (item && item.state !== 'unknown')
    return (
      <span className="flex shrink-0 items-center gap-[8px] whitespace-nowrap" style={{ fontSize: type2.sm, color: color.text }}>
        <StatusGlyph state="notyet" size={12} />
        Not found
      </span>
    )
  if (app.how === 'connected') return <Plain>Reads exactly</Plain>
  if (app.how === 'connect') return <RunButton label="Connect" pending run={() => tryInvoke(`apps:connect:${app.id}`, 'Connected.')} />
  return <Plain>Screen only</Plain>
}

function AppGroupRows({ group, health }: { group: (typeof APP_GROUPS)[number]; health: Record<string, HealthItem | undefined> }): ReactNode {
  return (
    <Group label={group}>
      {APPS.filter((a) => a.group === group).map((a) => (
        <div key={a.id} data-app={a.id}>
          <Row label={a.name} caption={appCaption(a)} right={<AppStatus app={a} item={health[a.id]} />} />
        </div>
      ))}
    </Group>
  )
}

export function Apps4({ live }: { live: boolean }): ReactNode {
  const health = useHealth(live)
  return (
    <Cols
      left={
        <>
          <AppGroupRows group="Code" health={health} />
          <AppGroupRows group="Sheets and design" health={health} />
        </>
      }
      right={
        <>
          <AppGroupRows group="3D and CAD" health={health} />
          <AppGroupRows group="Games" health={health} />
          <AppGroupRows group="Everything else" health={health} />
        </>
      }
    />
  )
}

// ---- Your data -------------------------------------------------------------------------------------------------------

const fact = (id: string): (typeof FACTS)[number] | undefined => FACTS.find((f) => f.id === id)

export function Data4({ live }: { live: boolean }): ReactNode {
  const d = useYourData(live)
  const share = usePrefs((s) => s.shareTelemetry)
  const account = useAccount((s) => s.account)
  const authEmail = useAuth((s) => s.user?.email)
  const email = account?.email ?? authEmail
  const cache = size(d.cacheBytes)
  return (
    <Cols
      left={
        <>
          <Group label="During a lesson">
            {(['screen', 'code', 'editor'] as const).map((id) => {
              const f = fact(id)
              return f ? <Row key={id} label={f.label} caption={f.line} right={<Plain>{f.where}</Plain>} /> : null
            })}
            <Row label={`Everything ${copy.name} sees`} caption="Each source, and where it goes." right={<PanelLink label="See the list" to="privacy" />} />
          </Group>
          <Group label="On this Mac">
            <Row label="Lesson folder" caption={`${d.folder}${d.lessons ? ` · ${d.lessons} lessons` : ''}`} right={<RunButton label="Open" pending run={() => tryInvoke('data:open-folder', '')} />} />
            <Row
              label="Lesson cache"
              caption={`Built lessons kept so they open fast.${cache ? ` ${cache}.` : ''}`}
              right={d.fromEngine ? d.canClearCache ? <RunButton label="Clear" run={clearCache} /> : undefined : <RunButton label="Clear" pending run={() => tryInvoke('data:cache-clear', 'Cleared.')} />}
            />
          </Group>
        </>
      }
      right={
        <>
          <Group label="Your progress">
            <SettingRowById id="export-progress" label="Lesson history and skills" caption="A file of your skills and finished lessons." />
          </Group>
          <Group label={`Help improve ${copy.name}`}>
            <Row
              tight
              label="Share crash reports and usage"
              caption="Errors and lesson counts. Never your code or screen."
              right={<Toggle label="Share crash reports and usage" on={share === true} onChange={(v) => setPrefs({ shareTelemetry: v })} />}
            />
          </Group>
          <Group label="Account">
            <Row label="Signed in as" caption={email ?? 'Not signed in'} right={account ? <Plain>{planLabel(account.plan)}</Plain> : undefined} />
            <Row
              label="Delete my account"
              caption="Your account, and everything miyagi keeps on this Mac."
              right={
                <QuietButton
                  label="Delete account"
                  onClick={() => {
                    askDelete()
                    setPagePanel('privacy')
                  }}
                />
              }
            />
          </Group>
        </>
      }
    />
  )
}
