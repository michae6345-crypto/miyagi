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
import { KeyRound, LogOut } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../../bridge'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { MiyagiMark } from '../../../core/ui/Mark'
import { planLabel, v2Cloud } from '../../account/model'
import { loadAccount, useAccount } from '../../account/store'
import { Chip, MenuRow, MeterGroup, PersonGlyph, Rule } from '../../account/ui'
import { Avatar } from '../../auth/Avatar'
import { authOn } from '../../auth/model'
import { loadAuth, useAuth } from '../../auth/store'
import { openSheet } from '../sheet'
import { setPage, setSettingsSection } from '../store'

const card = { borderRadius: radius2.panel, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}, ${surface.shadowSmall}` } as const
const caption = { fontSize: type2.sm, lineHeight: '20px', color: color.label } as const

const toYourKey = (): void => {
  setSettingsSection('account')
  setPage('settings')
}

function Wrap({ children }: { children: ReactNode }): ReactNode {
  return (
    <div data-shell-account-page className="flex flex-col items-start" style={{ padding: '8px 40px 40px' }}>
      <div className="flex w-full flex-col gap-[16px]" style={{ maxWidth: 460 }}>
        {children}
      </div>
    </div>
  )
}

function Skeleton(): ReactNode {
  return (
    <div aria-busy aria-label="Loading your account" className="flex flex-col gap-[12px]" style={{ ...card, padding: 24 }}>
      <div className="flex items-center gap-[12px]">
        <div style={{ width: 48, height: 48, borderRadius: radius2.round, background: fill.skeleton }} />
        <div className="flex flex-1 flex-col gap-[8px]">
          <div style={{ width: '50%', height: 14, borderRadius: radius2.round, background: fill.skeleton }} />
          <div style={{ width: '35%', height: 10, borderRadius: radius2.round, background: fill.skeleton }} />
        </div>
      </div>
      <div style={{ height: 56, borderRadius: radius2.card, background: fill.skeleton }} />
    </div>
  )
}

/** "across Macs" on a Mac, "across computers" elsewhere. */
const acrossMachines = (): string => (bridge.platform.os === 'mac' ? 'across Macs' : 'across computers')

function SignInCard(): ReactNode {
  return (
    <section aria-labelledby="shell-signin" data-shell-signin className="flex flex-col items-center gap-[12px] text-center" style={{ ...card, padding: 32 }}>
      <MiyagiMark size={40} />
      <h2 id="shell-signin" className="m-0 font-semibold" style={{ fontSize: type2.xl, lineHeight: '26px', letterSpacing: '-0.01em', color: color.text, maxWidth: 320 }}>
        Sign in to sync your progress {acrossMachines()}
      </h2>
      <p className="m-0" style={caption}>
        {copy.name} works without an account too.
      </p>
      <div style={{ marginTop: 8 }}>
        <PrimaryButton size="lg" label="Sign in" onClick={() => openSheet('signin')} />
      </div>
    </section>
  )
}

function KeyRow(): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  return (
    <section aria-label="Account actions" className="flex flex-col" style={{ ...card, padding: 8 }}>
      <MenuRow icon={KeyRound} label="Use your own key" right={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={toYourKey} />
    </section>
  )
}

/** The shipped page: the real login (features/auth). */
function LoginAccount(): ReactNode {
  const user = useAuth((s) => s.user)
  const loaded = useAuth((s) => s.loaded)
  useEffect(() => {
    void loadAuth()
    void loadAccount() // only for the "Use your own key" On / Off (settings:get); account:get is null here
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
        <SignInCard />
        <KeyRow />
      </Wrap>
    )
  return (
    <Wrap>
      <section aria-labelledby="shell-who" data-shell-signed-in className="flex flex-col gap-[16px]" style={{ ...card, padding: 24 }}>
        <div className="flex items-center gap-[14px]">
          <Avatar initial={user.avatarInitial} size={48} />
          <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <h2 id="shell-who" className="m-0 truncate font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
              {user.name ?? user.email}
            </h2>
            {user.name && user.email && (
              <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
                {user.email}
              </span>
            )}
          </div>
        </div>
        <div>
          <QuietButton icon={LogOut} label="Sign out" onClick={() => openSheet('signout')} />
        </div>
      </section>
      <KeyRow />
    </Wrap>
  )
}

function NoCloud(): ReactNode {
  return (
    <section aria-labelledby="shell-local" data-shell-local className="flex flex-col gap-[12px]" style={{ ...card, padding: 24 }}>
      <div className="flex items-center gap-[12px]">
        <MiyagiMark size={28} />
        <h2 id="shell-local" className="m-0 font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
          No account needed
        </h2>
      </div>
      <p className="m-0" style={caption}>
        {copy.name} runs on this Mac. Your lessons and progress stay here.
      </p>
      <Rule />
      <div className="flex flex-col">
        <MenuRow icon={KeyRound} label="Use your own key" onClick={toYourKey} />
      </div>
    </section>
  )
}

/** v2Cloud: the plans, pricing and usage mock (features/account). */
function CloudAccount(): ReactNode {
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  const ownKey = useAccount((s) => s.ownKey)
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
        <SignInCard />
      </Wrap>
    )

  const help = account.help
  return (
    <Wrap>
      <section aria-labelledby="shell-who" data-shell-signed-in className="flex flex-col gap-[16px]" style={{ ...card, padding: 24 }}>
        <div className="flex items-center gap-[14px]">
          <span className="flex shrink-0 items-center justify-center" style={{ width: 48, height: 48, borderRadius: radius2.round, background: fill.navActive, color: color.text }}>
            <PersonGlyph size={24} />
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <h2 id="shell-who" className="m-0 truncate font-semibold" style={{ fontSize: type2.lg, color: color.text }}>
              {account.name ?? account.email ?? 'Signed in'}
            </h2>
            {account.email && account.name && (
              <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
                {account.email}
              </span>
            )}
          </div>
          <Chip>{planLabel(account.plan)}</Chip>
        </div>
        {help ? (
          <MeterGroup help={help} title="Help this month" count={`${help.used} of ${help.limit}`} label="Help requests used this month" />
        ) : (
          <span style={caption}>Checks never count. Only live help does.</span>
        )}
        {account.plan === 'free' ? (
          <PrimaryButton size="lg" block label="Upgrade to Pro" onClick={() => openSheet('plans')} />
        ) : (
          <QuietButton label="See plans" onClick={() => openSheet('plans')} />
        )}
      </section>
      <section aria-label="Account actions" className="flex flex-col" style={{ ...card, padding: 8 }}>
        <MenuRow icon={KeyRound} label="Use your own key" right={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={toYourKey} />
        <MenuRow icon={LogOut} label="Sign out" onClick={() => openSheet('signout')} />
      </section>
      {note && (
        <p role="status" className="m-0 text-center" style={{ fontSize: type2.xs, color: color.label }}>
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
