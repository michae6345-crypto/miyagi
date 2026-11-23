/**
 * Plan-AccountMenu: who is signed in, the plan, this month's help meter, Upgrade (the one primary, Free only), then
 * My lessons, Settings (keycap from the platform), Use your own key (opens Settings › Account), Sign out.
 */
import type { ReactNode } from 'react'
import { Folder, KeyRound, LogOut, Settings } from 'lucide-react'
import { PrimaryButton } from '../../core/ui/buttons'
import { GlassCard } from '../../core/ui/GlassCard'
import { openLibrary, openSettings } from '../../core/surfaces'
import { color, fill, layer, radius2, type2 } from '../../core/theme'
import { planLabel, type Account, type View } from './model'
import { signOut, useAccount } from './store'
import { Chip, MenuRow, MeterGroup, PersonGlyph, Rule, WINDOW_CARD_SHADOW } from './ui'

export function Menu({ account, go }: { account: Account; go: (v: View) => void }): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  const help = account.help
  return (
    <GlassCard surface="panel" width={340} padding={16} className="flex flex-col gap-[12px]" style={{ display: 'flex', background: layer.overlay.background, boxShadow: WINDOW_CARD_SHADOW }}>
      <section role="menu" aria-label="Account" className="flex flex-col gap-[12px]">
        <div className="flex items-center gap-[12px]" style={{ padding: '0 4px' }}>
          <span className="flex shrink-0 items-center justify-center" style={{ width: 40, height: 40, borderRadius: radius2.round, background: fill.navActive, color: color.text }}>
            <PersonGlyph />
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <span className="truncate font-semibold" style={{ fontSize: type2.md, lineHeight: '18px', color: color.text }}>
              {account.name ?? account.email ?? 'Signed in'}
            </span>
            {account.email && account.name && (
              <span className="truncate" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
                {account.email}
              </span>
            )}
          </div>
          <Chip>{planLabel(account.plan)}</Chip>
        </div>

        {help && <MeterGroup help={help} title="Help this month" count={`${help.used} of ${help.limit}`} label="Help requests used this month" />}

        {account.plan === 'free' && <PrimaryButton size="lg" block label="Upgrade to Pro" onClick={() => go('pricing')} />}

        <Rule inset={4} />

        <div className="flex flex-col">
          <MenuRow icon={Folder} label="My lessons" onClick={() => void openLibrary()} />
          <MenuRow icon={Settings} label="Settings" keyName="settings" onClick={() => void openSettings()} />
          <MenuRow icon={KeyRound} label="Use your own key" right={ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'} onClick={() => void openSettings('account')} />
          <MenuRow
            icon={LogOut}
            label="Sign out"
            onClick={() => {
              signOut()
              go('signin')
            }}
          />
        </div>
      </section>
    </GlassCard>
  )
}
