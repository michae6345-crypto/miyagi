/**
 * Feature: shell. The Account page.
 *
 * Shipped (LOGIN_ENABLED, v2Cloud off): the real login (features/auth; main keeps the session, the page only sees
 * {name, email, avatarInitial}):
 *   signed in    who you are, linked accounts, this device, Use your own key (Settings page > Your key), Sign out;
 *                with an answer from miyagi-cloud (features/session, MIC-30) the plan and today's use top the Account
 *                group ("Free plan · $0.42 of $3.00 today · resets 4:00 PM", local time)
 *   signed out   one calm card, "Sign in to sync your progress across Macs"; Sign in opens the sign-in sheet over
 *                this page (AccountSheet.tsx), never a second window
 *   loading      skeleton cards until auth:get answers (no answer reads as signed out)
 * v2Cloud (mock data, stage or a VITE_MIYAGI_V2_CLOUD=1 build): who, the plan card with what it includes, Upgrade (the
 *   one primary, Free only: opens the plans sheet), usage this month (the help meter and a chart of the steps you
 *   passed each day), linked accounts, Use your own key, Sign out (asks first, in the sheet).
 * Login off: miyagi runs on this Mac, with your own key or the cloud setup.
 *
 * Layout: the wide page column, two columns of cards from a 760 pane up (who, plan, usage on the left; linked accounts,
 * this device, keys, sign out on the right), one column under it. Cards rise in on the page's stagger and lift on hover.
 * Nothing here can block a lesson, and nothing is sent from here: main and the sheet do that.
 */
import { Check, ChevronRight, LogOut, type LucideIcon } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../../bridge'
import { color, copy, fill, radius2, type2 } from '../../../core/theme'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { initialOf, planLabel, resetDay, v2Cloud, type Account, type HelpMeter } from '../../account/model'
import { loadAccount, useAccount } from '../../account/store'
import { Avatar } from '../../auth/Avatar'
import { LIVE, PROVIDER_LABEL, authOn, type Provider } from '../../auth/model'
import { loadAuth, useAuth } from '../../auth/store'
import { capsLine, planLabel as sessionPlan } from '../../session/model'
import { loadSession, useSession } from '../../session/store'
import { addDays, dayKey, dayStart } from '../../dashboard/model'
import { useDash } from '../../dashboard/store'
import { SkeletonCard, Tile } from '../../library/motion'
import { useLibrary } from '../../library/store'
import { thisDevice } from '../../onboarding/device'
import { openSheet } from '../sheet'
import { setPage, setSettingsSection } from '../store'
import { CARD, PageColumn, SectionHead } from '../ui'
import { BODY_TOP } from './Column'
import { planFeatures } from './planFeatures'

const caption = { fontSize: type2.sm, lineHeight: '20px', color: color.label } as const

const toYourKey = (): void => {
  setSettingsSection('account')
  setPage('settings')
}

/** The wide page column under the title; the cards inside it sit 16 apart. */
function Wrap({ children }: { children: ReactNode }): ReactNode {
  return (
    <div data-shell-account-page className="w-full">
      <PageColumn wide gap={16} top={BODY_TOP}>
        {children}
      </PageColumn>
    </div>
  )
}

/** Two stacks of cards side by side from a 760 pane up; one stack under it. */
function Cols({ left, right }: { left: ReactNode; right: ReactNode }): ReactNode {
  return (
    <div className="grid grid-cols-1 items-start gap-[16px] @min-[760px]:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-[16px]">{left}</div>
      <div className="flex min-w-0 flex-col gap-[16px]">{right}</div>
    </div>
  )
}

/**
 * One grouped list, rows split by hairlines: a card on the pane (ui.tsx CARD). Light: white, a 1 px border and a soft
 * two-layer lift; dark: one tone step above the pane with a faint top edge. Never a gray fill darker than the page.
 */
function Group({ children, label, i = 0 }: { children: ReactNode; label: string; i?: number }): ReactNode {
  return (
    <Tile i={i}>
      <section aria-label={label} className="flex flex-col overflow-hidden" style={CARD}>
        {children}
      </section>
    </Tile>
  )
}

/** A card with a section head and its own padding (20). */
function Panel({ id, title, i = 0, right, children }: { id: string; title: string; i?: number; right?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <Tile i={i}>
      <section aria-labelledby={id} className="flex flex-col" style={{ ...CARD, padding: 20, gap: 4 }}>
        <SectionHead id={id} right={right}>
          {title}
        </SectionHead>
        {children}
      </section>
    </Tile>
  )
}

/** A row of a group: the label, then its value in gray, then its action (a button, or the whole row opens). */
function Line({ label, value, action, onClick, last, icon: Icon, chevron = true }: { label: string; value?: ReactNode; action?: ReactNode; onClick?: () => void; last?: boolean; icon?: LucideIcon; chevron?: boolean }): ReactNode {
  const inner = (
    <>
      {Icon && <Icon aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.label }} />}
      <span className="relative shrink-0" style={{ fontSize: type2.md, color: color.text }}>
        {label}
      </span>
      <span className="relative min-w-0 flex-1 truncate text-right" style={{ fontSize: type2.sm, color: color.label }}>
        {value}
      </span>
      {action}
      {onClick && !action && chevron && <ChevronRight aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.label, opacity: 0.55 }} />}
    </>
  )
  const style = { minHeight: 52, padding: '8px 14px 8px 16px', borderBottom: last ? undefined : `1px solid ${fill.hairline}` }
  return onClick ? (
    <button type="button" onClick={onClick} className="mg-press relative flex w-full cursor-pointer items-center gap-[12px] text-left outline-offset-[-2px] focus-visible:outline-2 focus-visible:outline-solid" style={{ ...style, outlineColor: color.text }}>
      {inner}
    </button>
  ) : (
    <div className="flex items-center gap-[12px]" style={style}>
      {inner}
    </div>
  )
}

/** Who is signed in: a profile card with the avatar, the name, the email and (when there is one) the plan. */
function Who({ avatar, name, email, plan }: { avatar: ReactNode; name: string; email?: string; plan?: string }): ReactNode {
  return (
    <Tile i={0}>
      <section aria-labelledby="shell-who" data-shell-signed-in className="flex items-center gap-[16px]" style={{ ...CARD, padding: 20 }}>
        {avatar}
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <h2 id="shell-who" className="m-0 truncate font-semibold" style={{ fontSize: type2.xl, lineHeight: '26px', letterSpacing: '-0.2px', color: color.text }}>
            {name}
          </h2>
          {email && (
            <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
              {email}
            </span>
          )}
        </div>
        {plan && (
          <span className="shrink-0" style={{ height: 24, padding: '0 10px', display: 'inline-flex', alignItems: 'center', borderRadius: radius2.round, background: fill.trackSoft, fontSize: type2.xs, color: color.text }}>
            {plan}
          </span>
        )}
      </section>
    </Tile>
  )
}

/** What is on this Mac: where miyagi runs and how many lessons are saved. Real counts from the library. */
function ThisMac({ i = 2 }: { i?: number }): ReactNode {
  const saved = useLibrary((s) => s.items.length)
  const loaded = useLibrary((s) => s.loaded)
  return (
    <Group label="This device" i={i}>
      <Line label="Runs on" value={`${thisDevice()}, ${bridge.platform.os === 'mac' ? 'macOS' : 'Windows'}`} />
      <Line label="Lessons saved" value={loaded ? `${saved}` : 'Counting'} last />
    </Group>
  )
}

/** Sign out: its own one-row group under the account (round 3: no bordered button floating under the list). */
function SignOut({ i = 4 }: { i?: number }): ReactNode {
  return (
    <Group label="Sign out" i={i}>
      <Line icon={LogOut} label="Sign out" onClick={() => openSheet('signout')} chevron={false} last />
    </Group>
  )
}

function Skeleton(): ReactNode {
  return (
    <div aria-busy aria-label="Loading your account" className="grid grid-cols-1 gap-[16px] @min-[760px]:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-[16px]">
        <SkeletonCard h={88} />
        <SkeletonCard h={180} lines={3} />
      </div>
      <div className="flex flex-col gap-[16px]">
        <SkeletonCard h={120} lines={2} />
        <SkeletonCard h={104} />
      </div>
    </div>
  )
}

/** "across Macs" on a Mac, "across computers" elsewhere. */
const acrossMachines = (): string => (bridge.platform.os === 'mac' ? 'across Macs' : 'across computers')

/** Signed out: one line, one button, on a card. */
function SignIn(): ReactNode {
  return (
    <Tile i={0}>
      <section aria-labelledby="shell-signin" data-shell-signin className="flex flex-col items-start gap-[8px]" style={{ ...CARD, padding: 24 }}>
        <h2 id="shell-signin" className="m-0 font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
          Sign in to sync your progress {acrossMachines()}
        </h2>
        <p className="m-0" style={caption}>
          {copy.name} works without an account too.
        </p>
        <div style={{ marginTop: 8 }}>
          <PrimaryButton label="Sign in" onClick={() => openSheet('signin')} />
        </div>
      </section>
    </Tile>
  )
}

/** MIC-30: the plan and today's use, from POST /v1/session. Nothing when signed out or before the cloud answered. */
function PlanLine(): ReactNode {
  const view = useSession((s) => s.view)
  if (!view?.signedIn || (!view.plan && !view.caps)) return null
  return (
    <div data-session-plan className="flex flex-col gap-[2px]" style={{ padding: '10px 16px', borderBottom: `1px solid ${fill.hairline}` }}>
      <span style={{ fontSize: type2.md, color: color.text }}>{sessionPlan(view.plan)}</span>
      {view.caps && <span style={{ fontSize: type2.sm, color: color.label }}>{capsLine(view.caps)}</span>}
    </div>
  )
}

function KeyLine({ last = true }: { last?: boolean }): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  return <Line label="Your own key" value={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={toYourKey} last={last} />
}

/**
 * Linked accounts: the providers you can sign in with. Google is the live one and shows the address you signed in
 * with; the others are marked Soon (muted, nothing to press), as on the sign-in sheet.
 */
function Linked({ email, i = 1 }: { email?: string; i?: number }): ReactNode {
  const order: Provider[] = ['google', 'apple', 'github']
  return (
    <Panel id="shell-linked" title="Linked accounts" i={i}>
      <ul className="m-0 flex list-none flex-col p-0">
        {order.map((p, k) => (
          <li key={p} data-linked={p} className="flex items-center gap-[12px]" style={{ minHeight: 44, borderTop: k ? `1px solid ${fill.hairline}` : undefined, opacity: LIVE[p] ? 1 : 0.55 }}>
            <span aria-hidden className="inline-flex shrink-0 items-center justify-center font-medium" style={{ width: 28, height: 28, borderRadius: radius2.control, background: fill.trackSoft, fontSize: type2.xs, color: color.text }}>
              {PROVIDER_LABEL[p][0]}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span style={{ fontSize: type2.md, color: color.text }}>{PROVIDER_LABEL[p]}</span>
              {LIVE[p] && email && (
                <span className="truncate" style={{ fontSize: type2.xs, color: color.label }}>
                  {email}
                </span>
              )}
            </span>
            <span className="shrink-0" style={{ fontSize: type2.xs, color: color.label }}>
              {LIVE[p] ? 'Connected' : 'Soon'}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
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

  if (!loaded)
    return (
      <Wrap>
        <Skeleton />
      </Wrap>
    )
  if (!user)
    return (
      <Wrap>
        <Cols
          left={<SignIn />}
          right={
            <>
              <Group label="Keys" i={1}>
                <KeyLine />
              </Group>
              <ThisMac />
            </>
          }
        />
      </Wrap>
    )
  return (
    <Wrap>
      <Who avatar={<Avatar initial={user.avatarInitial} size={56} />} name={user.name ?? user.email ?? 'Signed in'} email={user.name ? user.email : undefined} />
      <Cols
        left={
          <>
            <Linked email={user.email} i={1} />
            <SignOut i={2} />
          </>
        }
        right={
          <>
            <Group label="Account" i={1}>
              <PlanLine />
              <KeyLine />
            </Group>
            <ThisMac />
          </>
        }
      />
    </Wrap>
  )
}

function NoCloud(): ReactNode {
  return (
    <>
      <Tile i={0}>
        <section aria-labelledby="shell-local" data-shell-local className="flex flex-col gap-[6px]" style={{ ...CARD, padding: 24 }}>
          <h2 id="shell-local" className="m-0 font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
            No account needed
          </h2>
          <p className="m-0" style={caption}>
            {copy.name} runs on {thisDevice()}. Your lessons and progress stay here.
          </p>
        </section>
      </Tile>
      <Cols
        left={
          <Group label="Keys" i={1}>
            <KeyLine />
          </Group>
        }
        right={<ThisMac />}
      />
    </>
  )
}

/** What is left this month, the number that helps a decision ("6 left"), never "14 of 20". */
function helpLeft(help: HelpMeter): string {
  const left = Math.max(0, help.limit - help.used)
  const day = resetDay(help.resetsAt)
  return [left === 0 ? 'None left' : `${left} left`, day ? `resets ${day}` : ''].filter(Boolean).join(' · ')
}

const DAYS_SHOWN = 30

/** The steps you passed on each of the last 30 days (the engine's own activity), as slim bars; a quiet day is a stub. */
function StepsChart(): ReactNode {
  const activity = useDash((s) => s.data?.activity)
  const now = Date.now()
  const map = new Map((activity ?? []).map((d) => [d.date, d.reps]))
  const days = Array.from({ length: DAYS_SHOWN }, (_, k) => {
    const t = addDays(dayStart(now), k - DAYS_SHOWN + 1)
    return { key: dayKey(t), reps: map.get(dayKey(t)) ?? 0 }
  })
  const max = Math.max(...days.map((d) => d.reps), 1)
  const total = days.reduce((n, d) => n + d.reps, 0)
  return (
    <div className="flex flex-col" style={{ gap: 8, marginTop: 12 }}>
      <div role="img" aria-label={`Steps passed each day over the last ${DAYS_SHOWN} days: ${total} in all`} className="flex items-end" style={{ gap: 3, height: 64 }}>
        {days.map((d) => (
          <span key={d.key} className="block flex-1" style={{ height: Math.max(4, Math.round((d.reps / max) * 64)), borderRadius: radius2.keycap, background: d.reps > 0 ? color.text : fill.track }} />
        ))}
      </div>
      <div className="flex items-center justify-between" style={{ fontSize: type2.xs, color: color.label }}>
        <span>30 days ago</span>
        <span>{total > 0 ? `${total} ${total === 1 ? 'step' : 'steps'} passed` : 'Today'}</span>
        {total > 0 && <span>Today</span>}
      </div>
    </div>
  )
}

/** Usage this month: the help meter (what is used, what is left) over a chart of the days you practiced. */
function Usage({ help, i = 2 }: { help?: HelpMeter; i?: number }): ReactNode {
  const used = help && help.limit ? Math.max(0, Math.min(1, help.used / help.limit)) : 0
  return (
    <Panel id="shell-usage" title="Usage this month" i={i}>
      {help ? (
        <>
          <div className="flex items-baseline justify-between" style={{ marginTop: 4 }}>
            <span className="font-semibold" style={{ fontSize: type2.xxl, lineHeight: '32px', letterSpacing: '-0.4px', color: color.text, fontVariantNumeric: 'tabular-nums' }}>
              {help.used}
              {/* label, not faint: faint read 4.15:1 on the dark card (QA R4-06). */}
              <span className="font-normal" style={{ fontSize: type2.lg, color: color.label }}>
                {' '}
                / {help.limit}
              </span>
            </span>
            <span style={{ fontSize: type2.xs, color: color.label }}>{helpLeft(help)}</span>
          </div>
          <div role="progressbar" aria-label="Live help used this month" aria-valuemin={0} aria-valuemax={help.limit} aria-valuenow={help.used} style={{ height: 6, marginTop: 8, borderRadius: radius2.round, background: fill.hairline }}>
            <div style={{ width: `${used * 100}%`, height: 6, borderRadius: radius2.round, background: color.text }} />
          </div>
          <span style={{ fontSize: type2.xs, color: color.label, marginTop: 8 }}>Live help used. Checks never count.</span>
        </>
      ) : (
        <span style={{ fontSize: type2.sm, color: color.label }}>Checks never count against your help.</span>
      )}
      <StepsChart />
    </Panel>
  )
}

/** The plan: its name and Upgrade (or See plans) on one line, then what it includes. */
function PlanCard({ account, i = 1 }: { account: Account; i?: number }): ReactNode {
  const free = account.plan === 'free'
  const feats = planFeatures(account.plan, account.catalog)
  return (
    <Panel id="shell-plan" title="Plan" i={i} right={<QuietButton label={free ? 'Upgrade' : 'See plans'} onClick={() => openSheet('plans')} />}>
      <span className="font-semibold" style={{ fontSize: type2.xl, lineHeight: '28px', letterSpacing: '-0.2px', color: color.text }}>
        {planLabel(account.plan)}
      </span>
      <ul className="m-0 flex list-none flex-col p-0" style={{ gap: 8, marginTop: 12 }}>
        {feats.map((f) => (
          <li key={f} className="flex items-start gap-[10px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.text }}>
            <Check aria-hidden size={14} strokeWidth={2} className="shrink-0" style={{ color: color.label, marginTop: 3 }} />
            {f}
          </li>
        ))}
      </ul>
    </Panel>
  )
}

/** v2Cloud: the plans, pricing and usage mock (features/account). */
function CloudAccount(): ReactNode {
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  const note = useAccount((s) => s.note)
  useEffect(() => {
    void loadAccount()
  }, [])

  if (!loaded)
    return (
      <Wrap>
        <Skeleton />
      </Wrap>
    )
  if (!account?.signedIn)
    return (
      <Wrap>
        <SignIn />
      </Wrap>
    )

  return (
    <Wrap>
      <Who
        avatar={<Avatar initial={initialOf(account.name ?? account.email)} size={56} />}
        name={account.name ?? account.email ?? 'Signed in'}
        email={account.email && account.name ? account.email : undefined}
        plan={planLabel(account.plan)}
      />
      <Cols
        left={
          <>
            <PlanCard account={account} i={1} />
            <Usage help={account.help} i={2} />
          </>
        }
        right={
          <>
            <Linked email={account.email} i={1} />
            <ThisMac i={2} />
            <Group label="Keys" i={3}>
              <KeyLine />
            </Group>
            <SignOut i={4} />
          </>
        }
      />
      {note && (
        <p role="status" className="m-0" style={{ fontSize: type2.xs, color: color.label }}>
          {note}
        </p>
      )}
    </Wrap>
  )
}

export function AccountPage(): ReactNode {
  if (v2Cloud) return <CloudAccount />
  if (authOn) return <LoginAccount />
  return (
    <Wrap>
      <NoCloud />
    </Wrap>
  )
}
