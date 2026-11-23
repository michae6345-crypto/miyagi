/**
 * Feature: shell. The Account page.
 *
 * Shipped (LOGIN_ENABLED, v2Cloud off): the real login (features/auth; main keeps the session, the page only sees
 * {name, email, avatarInitial}):
 *   signed in    the avatar initial, name and email, Sign out; Use your own key (Settings page › Your key)
 *   signed out   one calm card, "Sign in to sync your progress across Macs"; Sign in opens the sign-in sheet over
 *                this page (AccountSheet.tsx), never a second window
 *   loading      a skeleton card until auth:get answers (no answer reads as signed out)
 * v2Cloud (mock data, stage or a VITE_MIYAGI_V2_CLOUD=1 build): who, the plan, this month's help meter, Upgrade (the
 *   one primary, Free only: opens the plans sheet), Use your own key, Sign out (asks first, in the sheet).
 * Login off: miyagi runs on this Mac, with your own key or the cloud setup.
 * Nothing here can block a lesson, and nothing is sent from here: main and the sheet do that.
 */
import { ChevronRight, LogOut, type LucideIcon } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../../bridge'
import { color, copy, fill, radius2, type2 } from '../../../core/theme'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { initialOf, planLabel, resetDay, v2Cloud, type HelpMeter } from '../../account/model'
import { loadAccount, useAccount } from '../../account/store'
import { Avatar } from '../../auth/Avatar'
import { authOn } from '../../auth/model'
import { loadAuth, useAuth } from '../../auth/store'
import { openSheet } from '../sheet'
import { setPage, setSettingsSection } from '../store'
import { thisDevice } from '../../onboarding/device'
import { useLibrary } from '../../library/store'
import { CARD, PageBody } from '../ui'
import { BODY_TOP, SECTION_GAP } from './Column'

const caption = { fontSize: type2.sm, lineHeight: '20px', color: color.label } as const

const toYourKey = (): void => {
  setSettingsSection('account')
  setPage('settings')
}

/**
 * Redraft (Adrian, Nov 21; Michael's audit: "a small card floating in a huge empty area", "14 of 20 is a stray
 * number"): the page is a header (who you are) and one grouped list, as in Settings. No floating cards.
 */
function Wrap({ children }: { children: ReactNode }): ReactNode {
  // The shared page column (ui.tsx PageBody), centered under the title. The groups fill it, as Settings' do, so the
  // cards keep the same left and right edges when you switch between the two pages; sections sit SECTION_GAP apart.
  return (
    <div data-shell-account-page className="w-full">
      <PageBody gap={SECTION_GAP} style={{ paddingTop: BODY_TOP }}>{children}</PageBody>
    </div>
  )
}

/**
 * One grouped list, rows split by hairlines: a card on the pane (ui.tsx CARD). Light: white, a 1 px border and a soft
 * two-layer lift; dark: one tone step above the pane with a faint top edge. Never a gray fill darker than the page.
 */
function Group({ children, label }: { children: ReactNode; label: string }): ReactNode {
  return (
    <section aria-label={label} className="flex flex-col overflow-hidden" style={CARD}>
      {children}
    </section>
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
  )
}

/** What is on this Mac: where miyagi runs and how many lessons are saved. Real counts from the library. */
function ThisMac(): ReactNode {
  const saved = useLibrary((s) => s.items.length)
  const loaded = useLibrary((s) => s.loaded)
  return (
    <Group label="This device">
      <Line label="Runs on" value={thisDevice()} />
      <Line label="Lessons saved" value={loaded ? String(saved) : undefined} last />
    </Group>
  )
}

/** Sign out: its own one-row group under the account (round 3: no bordered button floating under the list). */
function SignOut(): ReactNode {
  return (
    <Group label="Sign out">
      <Line icon={LogOut} label="Sign out" onClick={() => openSheet('signout')} chevron={false} last />
    </Group>
  )
}

function Skeleton(): ReactNode {
  return (
    <div aria-busy aria-label="Loading your account" className="flex flex-col gap-[16px]">
      <div className="flex items-center gap-[14px]">
        <div style={{ width: 44, height: 44, borderRadius: radius2.round, background: fill.skeleton }} />
        <div className="flex flex-1 flex-col gap-[8px]">
          <div style={{ width: '40%', height: 14, borderRadius: radius2.round, background: fill.skeleton }} />
          <div style={{ width: '28%', height: 10, borderRadius: radius2.round, background: fill.skeleton }} />
        </div>
      </div>
      <div style={{ height: 104, borderRadius: CARD.borderRadius, background: fill.skeleton }} />
    </div>
  )
}

/** "across Macs" on a Mac, "across computers" elsewhere. */
const acrossMachines = (): string => (bridge.platform.os === 'mac' ? 'across Macs' : 'across computers')

/** Signed out: one line, one button, on the page (no box). */
function SignIn(): ReactNode {
  return (
    <section aria-labelledby="shell-signin" data-shell-signin className="flex flex-col items-start gap-[8px]">
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
  )
}

function KeyLine({ last = true }: { last?: boolean }): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  return <Line label="Your own key" value={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={toYourKey} last={last} />
}

/** The shipped page: the real login (features/auth). */
function LoginAccount(): ReactNode {
  const user = useAuth((s) => s.user)
  const loaded = useAuth((s) => s.loaded)
  useEffect(() => {
    void loadAuth()
    void loadAccount() // only for the "Your own key" On / Off (settings:get); account:get is null here
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
        <SignIn />
        <Group label="Keys">
          <KeyLine />
        </Group>
        <ThisMac />
      </Wrap>
    )
  return (
    <Wrap>
      <Who avatar={<Avatar initial={user.avatarInitial} size={56} />} name={user.name ?? user.email ?? 'Signed in'} email={user.name ? user.email : undefined} />
      <Group label="Account">
        <KeyLine />
      </Group>
      <ThisMac />
      <SignOut />
    </Wrap>
  )
}

function NoCloud(): ReactNode {
  return (
    <>
      <section aria-labelledby="shell-local" data-shell-local className="flex flex-col gap-[6px]">
        <h2 id="shell-local" className="m-0 font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
          No account needed
        </h2>
        <p className="m-0" style={caption}>
          {copy.name} runs on {thisDevice()}. Your lessons and progress stay here.
        </p>
      </section>
      <Group label="Keys">
        <KeyLine />
      </Group>
      <ThisMac />
    </>
  )
}

/** What is left this month, the number that helps a decision ("6 left"), never "14 of 20". */
function helpLeft(help: HelpMeter): string {
  const left = Math.max(0, help.limit - help.used)
  const day = resetDay(help.resetsAt)
  return [left === 0 ? 'None left' : `${left} left`, day ? `resets ${day}` : ''].filter(Boolean).join(' · ')
}

/** What is left, with a slim meter of what is used (the same reading as the account sheet's meter). */
function HelpValue({ help }: { help: HelpMeter }): ReactNode {
  const used = help.limit ? Math.max(0, Math.min(1, help.used / help.limit)) : 0
  return (
    <span className="inline-flex items-center justify-end gap-[10px]">
      <span aria-hidden className="relative block shrink-0 overflow-hidden" style={{ width: 56, height: 4, borderRadius: radius2.round, background: fill.hairline }}>
        <span className="absolute inset-y-0 left-0 block" style={{ width: `${used * 100}%`, background: color.label, borderRadius: radius2.round }} />
      </span>
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{helpLeft(help)}</span>
    </span>
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

  const help = account.help
  const free = account.plan === 'free'
  return (
    <Wrap>
      <Who
        avatar={<Avatar initial={initialOf(account.name ?? account.email)} size={56} />}
        name={account.name ?? account.email ?? 'Signed in'}
        email={account.email && account.name ? account.email : undefined}
        plan={planLabel(account.plan)}
      />
      <Group label="Plan">
        <Line
          label="Plan"
          value={planLabel(account.plan)}
          action={<QuietButton label={free ? 'Upgrade' : 'See plans'} onClick={() => openSheet('plans')} />}
        />
        {help ? <Line label="Help this month" value={<HelpValue help={help} />} /> : <Line label="Help this month" value="Checks never count" />}
        <KeyLine />
      </Group>
      <ThisMac />
      <SignOut />
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
