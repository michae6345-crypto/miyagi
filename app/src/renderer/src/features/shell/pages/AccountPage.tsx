/**
 * Feature: shell. The Account page, v4 (Adrian's ui-next mock: the Settings pages, settings / settings-data, Nov 24).
 * Account is the first row of Settings' own list, so the page is drawn exactly like a Settings panel: the v4 PageFrame
 * (the 1040 column), a 32 px title, then two columns of flat groups (a 15 px section head over a hairline, hairline
 * rows with a label, a gray caption and the row's control on the right). No cards, no tiles: the settings feature's
 * own Group / Row inside its `Flat` context, so a row here is pixel for pixel a Settings row. While the page is on
 * show the shell's sidebar shows Settings' list with Account lit ("one sidebar on screen").
 *
 * Shipped (LOGIN_ENABLED, v2Cloud off): the real login (features/auth; main keeps the session, the page only sees
 * {name, email, avatarInitial}):
 *   signed in    Profile (who you are, signed in with Google), Plan and usage (the plan and today's use from
 *                miyagi-cloud, features/session MIC-30: "$0.42 of $3.00 today · resets 4:00 PM", local time, with a
 *                4 px bar; Your own key), This Mac, Your account (Sign out asks first in the sheet; Delete my account
 *                keeps its in-place two-step confirm, settings/sections/Privacy DeleteAccount)
 *   signed out   "Sign in to sync your progress across Macs", one primary (Sign in opens the sheet over this page)
 *   loading      the same groups as quiet skeleton lines until auth:get answers (no answer reads as signed out)
 * v2Cloud (mock data, stage or a VITE_MIYAGI_V2_CLOUD=1 build): the same page with the plan's name and what it
 *   includes (Upgrade or See plans opens the plans sheet), and the live help used this month.
 * Login off: miyagi runs on this Mac, with your own key or the cloud setup.
 *
 * Brand: neutral chrome only. "Connected" is the white tick and the word (never green); buttons are the quiet outline;
 * the one primary is Sign in, signed out. Nothing here can block a lesson, and nothing is sent from here: main and
 * the sheet do that.
 */
import { ChevronRight } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../../bridge'
import { color, copy, type2 } from '../../../core/theme'
import { PrimaryButtonV2, QuietButton, Skeleton } from '../../../core/ui/atoms'
import { initialOf, planLabel, resetDay, v2Cloud, type Account, type HelpMeter } from '../../account/model'
import { loadAccount, useAccount } from '../../account/store'
import { Avatar } from '../../auth/Avatar'
import { LIVE, PROVIDER_LABEL, authOn, type Provider } from '../../auth/model'
import { loadAuth, useAuth } from '../../auth/store'
import { capsLine, planLabel as sessionPlan, type Caps } from '../../session/model'
import { loadSession, useSession } from '../../session/store'
import { useLibrary } from '../../library/store'
import { thisDevice } from '../../onboarding/device'
import { setPagePanel } from '../../settings/nav'
import type { PanelId } from '../../settings/panels'
import { DeleteAccount } from '../../settings/sections/Privacy'
import { OWN_KEY } from '../../settings/words'
import { Flat, Group, OnWord, Plain, Row } from '../../settings/ui'
import { FOOT4, NAV4 } from '../../settings/v4/PageNav'
import { Cols } from '../../settings/v4/Panels'
import { openSheet } from '../sheet'
import { setPage, setSettingsSection, useShell } from '../store'
import { Bar, PageFrame, PageHeader, setSidebarList, type SidebarList } from '../ui'
import { planFeatures } from './planFeatures'

const toYourKey = (): void => {
  setSettingsSection('account')
  setPage('settings')
}

/** "across Macs" on a Mac, "across computers" elsewhere. */
const acrossMachines = (): string => (bridge.platform.os === 'mac' ? 'across Macs' : 'across computers')

/**
 * Settings' list in the sidebar, Account lit, while this page is on show (the Settings page does the same for its
 * panels). A pick switches to the Settings page on that panel; a Settings page mounting for the first time sets its
 * own panel from the shell's section on mount, so the panel is set again once it has.
 */
function useSettingsSidebar(): void {
  const on = useShell((s) => s.page === 'account')
  useEffect(() => {
    if (!on) return
    const list: SidebarList = {
      back: { label: 'Settings', onClick: () => setPage('home') },
      groups: NAV4.map((g) => ({ label: g.label, items: g.items.map((i) => ({ id: i.id, label: i.label, icon: i.icon })) })),
      foot: [{ id: FOOT4.id, label: FOOT4.label, icon: FOOT4.icon }],
      active: 'account-page',
      onPick: (id) => {
        if (id === 'account-page') return
        const mounted = useShell.getState().visited.includes('settings')
        setPagePanel(id as PanelId)
        setPage('settings')
        if (!mounted) setTimeout(() => setPagePanel(id as PanelId), 0)
      }
    }
    setSidebarList(list)
    return () => setSidebarList(null)
  }, [on])
}

/** The page: the v4 frame, the title, then the two columns of groups (Settings' Cols, one column when narrow). */
function Page({ left, right, foot }: { left: ReactNode; right: ReactNode; foot?: ReactNode }): ReactNode {
  useSettingsSidebar()
  return (
    <PageFrame data={{ 'data-shell-account-page': true }}>
      <PageHeader title="Account" />
      <Flat.Provider value>
        <Cols left={left} right={right} />
      </Flat.Provider>
      {foot}
    </PageFrame>
  )
}

/** A quiet value that opens another page ("Off ›"), the way Settings links to a panel. */
function LinkValue({ label, onClick, aria }: { label: ReactNode; onClick: () => void; aria: string }): ReactNode {
  return (
    <button
      type="button"
      aria-label={aria}
      className="mg-press flex shrink-0 cursor-pointer items-center gap-[6px] whitespace-nowrap outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{ fontSize: type2.sm, color: color.label, background: 'none', border: 0, padding: 0, minHeight: 24, outlineColor: color.text, borderRadius: 4 }}
      onClick={onClick}
    >
      {label}
      <ChevronRight size={14} strokeWidth={1.8} aria-hidden />
    </button>
  )
}

/** Who is signed in: the avatar, the name and the email, on one flat row. */
function ProfileRow({ initial, name, email }: { initial?: string; name: string; email?: string }): ReactNode {
  return (
    <div data-shell-signed-in className="flex items-center gap-[14px]" style={{ minHeight: 72, padding: '12px 0' }}>
      <Avatar initial={initial} size={40} />
      <div className="flex min-w-0 flex-1 flex-col gap-[1px]">
        <span className="truncate" style={{ fontSize: type2.md, fontWeight: 520, color: color.text }}>
          {name}
        </span>
        {email && (
          <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
            {email}
          </span>
        )}
      </div>
    </div>
  )
}

/** The provider you signed in with (Google is the live one; the email is on the profile row above, once). The others
 * are left out until they are live. */
function LinkedRows(): ReactNode[] {
  return (['google', 'apple', 'github'] as Provider[])
    .filter((p) => LIVE[p])
    .map((p) => (
      <div key={p} data-linked={p}>
        <Row label={`Signed in with ${PROVIDER_LABEL[p]}`} right={<OnWord>Connected</OnWord>} />
      </div>
    ))
}

/** Today's use as a 4 px bar beside the line (only when there is a daily cap to measure against). */
function capsBar(caps?: Caps): ReactNode {
  if (!caps?.dailyUsd) return undefined
  return <Bar value={caps.usedUsd / caps.dailyUsd} width={96} label={`${Math.round(Math.min(1, caps.usedUsd / caps.dailyUsd) * 100)} percent of today's use`} />
}

/** MIC-30: the plan and today's use, from POST /v1/session. Nothing when signed out or before the cloud answered. */
function SessionPlanRow(): ReactNode {
  const view = useSession((s) => s.view)
  if (!view?.signedIn || (!view.plan && !view.caps)) return null
  return (
    <div data-session-plan>
      <Row label={sessionPlan(view.plan)} caption={capsLine(view.caps) ?? undefined} right={capsBar(view.caps)} />
    </div>
  )
}

function KeyRow(): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  const word = ownKey === undefined ? 'Set up' : ownKey ? 'On' : 'Off'
  return <Row label={OWN_KEY} caption="Bring your own API key." right={<LinkValue label={word} aria={`${OWN_KEY}: ${word}`} onClick={toYourKey} />} />
}

/** What is on this Mac: where miyagi runs and how many lessons are saved. Real counts from the library. */
function ThisMac(): ReactNode {
  const saved = useLibrary((s) => s.items.length)
  const loaded = useLibrary((s) => s.loaded)
  return (
    <Group label="This Mac" title={bridge.platform.os === 'mac' ? 'This Mac' : 'This computer'}>
      <Row label="Runs on" right={<Plain>{`${thisDevice()}, ${bridge.platform.os === 'mac' ? 'macOS' : 'Windows'}`}</Plain>} />
      <Row label="Lessons saved" right={<Plain>{loaded ? `${saved}` : 'Counting'}</Plain>} />
    </Group>
  )
}

/** Sign out (asks first, in the sheet) and Delete my account (its in-place two-step confirm). Signed in only. */
function YourAccount(): ReactNode {
  return (
    <Group label="Your account">
      <Row label="Sign out" caption={`Your lessons and progress stay on ${thisDevice()}.`} right={<QuietButton label="Sign out" onClick={() => openSheet('signout')} />} />
      <DeleteAccount label="Delete my account" row={`Your account, and everything ${copy.name} keeps on this Mac.`} button="Delete account" />
    </Group>
  )
}

/** Signed out: one line, one button. */
function SignInGroup(): ReactNode {
  return (
    <Group label="Sync">
      <div data-shell-signin>
        <Row label={`Sign in to sync your progress ${acrossMachines()}`} caption={`${copy.name} works without an account too.`} right={<PrimaryButtonV2 label="Sign in" onClick={() => openSheet('signin')} />} />
      </div>
    </Group>
  )
}

/** Loading: the groups' shape in quiet skeleton lines (no cards), until auth:get or account:get answers. */
function Loading(): ReactNode {
  const group = (rows: number): ReactNode => (
    <div className="flex flex-col" style={{ marginTop: 34 }}>
      <Skeleton width={120} height={14} />
      <div style={{ marginTop: 14 }}>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex flex-col justify-center gap-[6px]" style={{ minHeight: 58 }}>
            <Skeleton width="42%" height={12} />
            <Skeleton width="64%" height={10} />
          </div>
        ))}
      </div>
    </div>
  )
  return (
    <div aria-busy aria-label="Loading your account">
      <Page left={group(3)} right={group(2)} />
    </div>
  )
}

/** The shipped page: the real login (features/auth). */
function LoginAccount(): ReactNode {
  const user = useAuth((s) => s.user)
  const loaded = useAuth((s) => s.loaded)
  useEffect(() => {
    void loadAuth()
    void loadAccount() // only for the "Your own key" On / Off (settings:get); account:get is null here
    void loadSession() // MIC-30: main refreshes from the cloud in the background when its answer is old
  }, [])

  if (!loaded) return <Loading />
  if (!user)
    return (
      <Page
        left={
          <>
            <SignInGroup />
            <Group label="Keys">
              <KeyRow />
            </Group>
          </>
        }
        right={<ThisMac />}
      />
    )
  return (
    <Page
      left={
        <>
          <Group label="Profile">
            <ProfileRow initial={user.avatarInitial} name={user.name ?? user.email ?? 'Signed in'} email={user.name ? user.email : undefined} />
            {LinkedRows()}
          </Group>
          <Group label="Plan and usage">
            <SessionPlanRow />
            <KeyRow />
          </Group>
        </>
      }
      right={
        <>
          <ThisMac />
          <YourAccount />
        </>
      }
    />
  )
}

function NoCloud(): ReactNode {
  return (
    <Page
      left={
        <>
          <Group label="Account">
            <div data-shell-local>
              <Row label="No account needed" caption={`${copy.name} runs on ${thisDevice()}. Your lessons and progress stay here.`} />
            </div>
          </Group>
          <Group label="Keys">
            <KeyRow />
          </Group>
        </>
      }
      right={<ThisMac />}
    />
  )
}

/** "14 of 20 used · 6 left · resets December 1": what is left helps a decision, so it is said. */
function helpLine(help: HelpMeter): string {
  const left = Math.max(0, help.limit - help.used)
  const day = resetDay(help.resetsAt)
  return [`${help.used} of ${help.limit} used`, left === 0 ? 'none left' : `${left} left`, day ? `resets ${day}` : ''].filter(Boolean).join(' · ')
}

/** v2Cloud: the plan (its name, what it includes, Upgrade or See plans) and the live help used this month. */
function CloudPlanRows({ account }: { account: Account }): ReactNode[] {
  const free = account.plan === 'free'
  const feats = planFeatures(account.plan, account.catalog)
  const help = account.help
  return [
    <div key="plan" data-shell-plan>
      <Row
        label={`${planLabel(account.plan)} plan`}
        caption={
          <span className="flex flex-col gap-[2px]" style={{ marginTop: 2 }}>
            {feats.map((f) => (
              <span key={f}>{f}</span>
            ))}
          </span>
        }
        right={<QuietButton label={free ? 'Upgrade' : 'See plans'} onClick={() => openSheet('plans')} />}
      />
    </div>,
    <div key="usage" data-shell-usage>
      <Row
        label="Live help this month"
        caption={help ? helpLine(help) : 'Checks never count against your help.'}
        right={help ? <Bar value={help.used / help.limit} width={96} label={`Live help used this month: ${help.used} of ${help.limit}`} /> : undefined}
      />
    </div>
  ]
}

/** v2Cloud: the plans, pricing and usage mock (features/account). */
function CloudAccount(): ReactNode {
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  const note = useAccount((s) => s.note)
  useEffect(() => {
    void loadAccount()
  }, [])

  if (!loaded) return <Loading />
  if (!account?.signedIn) return <Page left={<SignInGroup />} right={<ThisMac />} />
  return (
    <Page
      left={
        <>
          <Group label="Profile">
            <ProfileRow initial={initialOf(account.name ?? account.email)} name={account.name ?? account.email ?? 'Signed in'} email={account.email && account.name ? account.email : undefined} />
            {LinkedRows()}
          </Group>
          <Group label="Plan and usage">
            {CloudPlanRows({ account })}
            <KeyRow />
          </Group>
        </>
      }
      right={
        <>
          <ThisMac />
          <YourAccount />
        </>
      }
      foot={
        note && (
          <p role="status" className="m-0" style={{ fontSize: type2.xs, color: color.label, marginTop: 24 }}>
            {note}
          </p>
        )
      }
    />
  )
}

export function AccountPage(): ReactNode {
  if (v2Cloud) return <CloudAccount />
  if (authOn) return <LoginAccount />
  return <NoCloud />
}
