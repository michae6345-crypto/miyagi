/**
 * Feature: shell. The Account page (features/account, mock data behind the v2Cloud flag):
 *
 *   signed in    who, the plan, this month's help meter, Upgrade (the one primary, Free only: opens Pricing in the
 *                account window), Use your own key (Settings page › Your key), Sign out
 *   signed out   one calm sign-in card; Sign in opens the login view (features/auth in the account window)
 *   no cloud     a normal build has no accounts yet: miyagi runs on this Mac, with your own key or the cloud setup
 *   loading      a skeleton card; an unanswered account:get reads as signed out (nothing to show is not an error)
 * Nothing here can block a lesson, and nothing is sent: the account window and main's fixed links do that.
 */
import { KeyRound, LogOut } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { openAccount, openWindow } from '../../../core/surfaces'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { PrimaryButton, QuietButton } from '../../../core/ui/buttons'
import { MiyagiMark } from '../../../core/ui/Mark'
import { planLabel, v2Cloud } from '../../account/model'
import { loadAccount, signOut, useAccount } from '../../account/store'
import { Chip, MenuRow, MeterGroup, PersonGlyph, Rule } from '../../account/ui'
import { setPage, setSettingsSection } from '../store'

const card = { borderRadius: radius2.panel, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}, ${surface.shadowSmall}` } as const
const caption = { fontSize: type2.sm, lineHeight: '20px', color: color.label } as const

const toYourKey = (): void => {
  setSettingsSection('account')
  setPage('settings')
}

function Wrap({ children }: { children: ReactNode }): ReactNode {
  return (
    <div data-shell-account-page className="flex flex-col items-center" style={{ padding: '40px 32px' }}>
      <div className="flex w-full flex-col gap-[16px]" style={{ maxWidth: 460 }}>
        {children}
      </div>
    </div>
  )
}

function SignInCard(): ReactNode {
  return (
    <section aria-labelledby="shell-signin" data-shell-signin className="flex flex-col items-center gap-[12px] text-center" style={{ ...card, padding: 32 }}>
      <MiyagiMark size={40} />
      <h2 id="shell-signin" className="m-0 font-semibold" style={{ fontSize: type2.xl, letterSpacing: '-0.01em', color: color.text }}>
        Sign in to {copy.name}
      </h2>
      <p className="m-0" style={caption}>
        Keep your lessons and progress on every Mac.
      </p>
      <div style={{ marginTop: 8 }}>
        {/* The login view lives in the account window until core adds an auth route (features/auth). */}
        <PrimaryButton size="lg" label="Sign in" onClick={() => void openWindow('account', { view: 'login' })} />
      </div>
      <p className="m-0" style={{ fontSize: type2.xs, color: color.label }}>
        {copy.name} works without an account too.
      </p>
    </section>
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

export function AccountPage(): ReactNode {
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  const ownKey = useAccount((s) => s.ownKey)
  const note = useAccount((s) => s.note)
  useEffect(() => {
    if (v2Cloud) void loadAccount()
  }, [])

  if (!v2Cloud)
    return (
      <Wrap>
        <NoCloud />
      </Wrap>
    )
  if (!loaded)
    return (
      <Wrap>
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
          <PrimaryButton size="lg" block label="Upgrade to Pro" onClick={() => void openAccount('pricing')} />
        ) : (
          <QuietButton label="See plans" onClick={() => void openAccount('pricing')} />
        )}
      </section>
      <section aria-label="Account actions" className="flex flex-col" style={{ ...card, padding: 8 }}>
        <MenuRow icon={KeyRound} label="Use your own key" right={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={toYourKey} />
        <MenuRow icon={LogOut} label="Sign out" onClick={signOut} />
      </section>
      {note && (
        <p role="status" className="m-0 text-center" style={{ fontSize: type2.xs, color: color.label }}>
          {note}
        </p>
      )}
    </Wrap>
  )
}
