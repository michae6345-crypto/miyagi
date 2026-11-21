/**
 * Plan-Upgrade: this month's free help is used up. It never blocks the lesson: the copy says the lesson stays open and
 * checks keep working, and Not now (Esc) just closes it. Upgrade is the one primary (it opens Pricing); Use my own key
 * opens Settings › Account.
 */
import type { ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { GlassCard } from '../../core/ui/GlassCard'
import { openSettings } from '../../core/surfaces'
import { color, type2 } from '../../core/theme'
import type { Account, View } from './model'
import { MeterGroup } from './ui'

export function Upgrade({ account, go, close }: { account: Account | null; go: (v: View) => void; close: () => void }): ReactNode {
  const help = account?.help
  const price = account?.catalog?.pro?.monthly
  return (
    <GlassCard surface="panel" width={440} padding={24} style={{ display: 'flex' }}>
      <section role="dialog" aria-labelledby="account-up-title" className="flex w-full flex-col gap-[24px]">
        <div className="flex flex-col gap-[8px]">
          <h2 id="account-up-title" className="m-0 font-semibold" style={{ fontSize: type2.xl, lineHeight: '24px', letterSpacing: '-0.01em', color: color.text }}>
            {"You've used this month's free help."}
          </h2>
          <p className="m-0" style={{ fontSize: type2.md, lineHeight: '20px', color: color.label }}>
            Your lesson stays open. Checks keep working.
          </p>
        </div>

        {help && <MeterGroup help={help} padding={16} title="Help requests" count={`${help.used} of ${help.limit} used`} label="Help requests used" resetsDot />}

        <div className="flex flex-col gap-[8px]">
          <PrimaryButton size="lg" block label={price ? `Upgrade to Pro, ${price} a month` : 'Upgrade to Pro'} onClick={() => go('pricing')} />
          <div className="grid grid-cols-2 gap-[8px]">
            <QuietButton size="lg" block label="Use my own key" onClick={() => void openSettings('account')} />
            <QuietButton size="lg" block label="Not now" keyName="dismiss" onClick={close} />
          </div>
        </div>
      </section>
    </GlassCard>
  )
}
