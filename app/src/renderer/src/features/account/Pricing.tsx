/**
 * Plan-Pricing, on the paper tokens (theme.paper): ink text, ink primary, ink meter, no hue. Four plans: Free, Pro
 * (the one primary, outlined in ink), Teams, Bring your own key (dashed). Prices come from the catalog the account
 * carries; with no catalog a paid plan shows no number (never invented). No payments here: Upgrade, Talk to us and
 * Restore open main's fixed miyagi.study links in the browser; Add a key opens Settings › Account.
 *
 * Four columns from 1100 px (the mockup's 1200 window), two below (the account window's 720), scrolling if needed.
 */
import { useState, type ReactNode } from 'react'
import { Check } from 'lucide-react'
import { bridge } from '../../bridge'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Segmented } from '../../core/ui/controls'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { openSettings } from '../../core/surfaces'
import { paper, radius2, type2 } from '../../core/theme'
import type { Account, PlanId } from './model'
import { openLink } from './store'
import { Chip, Meter, Rule, TextLink } from './ui'

type Period = 'monthly' | 'yearly'

type PlanCard = {
  id: PlanId | 'byok'
  name: string
  price?: string
  per: string
  blurb: string
  features: string[]
  action: ReactNode
  look: 'plain' | 'featured' | 'dashed'
  badge?: string
}

const H1 = 40

export function Pricing({ account, width }: { account: Account | null; width: number }): ReactNode {
  const [period, setPeriod] = useState<Period>('monthly')
  const cat = account?.catalog
  const current = account?.plan ?? 'free'
  const help = account?.help
  const wide = width >= 1100
  const pad = wide ? 40 : 32

  const helpLine = (n?: number): string => (n ? `${n} help requests a month` : 'Help requests every month')
  const currentButton = <QuietButton surface="paper" size="lg" block disabled label="Your current plan" onClick={() => undefined} />

  const cards: PlanCard[] = [
    {
      id: 'free',
      name: 'Free',
      price: '$0',
      per: 'forever',
      blurb: 'For trying your first lessons.',
      features: [helpLine(cat?.free?.help), 'Every shared lesson', 'Checks on your real work', 'VS Code and Jupyter'],
      action: current === 'free' ? currentButton : <QuietButton surface="paper" size="lg" block disabled label="Included" onClick={() => undefined} />,
      look: 'plain'
    },
    {
      id: 'pro',
      name: 'Pro',
      price: period === 'monthly' ? cat?.pro?.monthly : cat?.pro?.yearly,
      per: period === 'monthly' ? 'per month' : 'per month, billed yearly',
      blurb: 'For learning something every week.',
      features: [helpLine(cat?.pro?.help), 'Turn any YouTube tutorial into a lesson', 'Diagram and Watch on every step', 'Everything in Free'],
      action: current === 'pro' ? currentButton : <PrimaryButton surface="paper" size="lg" block label="Upgrade to Pro" onClick={() => openLink('upgrade')} />,
      look: 'featured',
      badge: 'Recommended'
    },
    {
      id: 'teams',
      name: 'Teams',
      price: period === 'monthly' ? cat?.teams?.monthly : cat?.teams?.yearly,
      per: period === 'monthly' ? 'per seat, monthly' : 'per seat, billed yearly',
      blurb: 'For classrooms, courses and onboarding.',
      features: ['Publish your tutorials as lessons', 'Progress for every learner', 'Seats and billing in one place', 'Everything in Pro'],
      action: current === 'teams' ? currentButton : <QuietButton surface="paper" size="lg" block label="Talk to us" onClick={() => openLink('teams')} />,
      look: 'plain'
    },
    {
      id: 'byok',
      name: 'Bring your own key',
      price: '$0',
      per: 'plus your model bill',
      blurb: 'Use your own model key. Pay your provider.',
      features: ['No monthly help limit', bridge.platform.os === 'mac' ? "Key kept in your Mac's Keychain" : 'Key kept in secure storage', 'Every shared lesson', cat?.providers ? `Works with ${cat.providers} keys` : 'Works with your provider key'],
      action: <QuietButton surface="paper" size="lg" block label="Add a key" onClick={() => void openSettings('account')} />,
      look: 'dashed'
    }
  ]

  const save = cat?.yearlySavePct
  return (
    <div data-surface="paper" className="flex min-h-full w-full flex-col" style={{ background: paper.bg, color: paper.ink, padding: `${pad}px ${pad}px 32px`, gap: wide ? 32 : 24 }}>
      <header className="flex items-center justify-between gap-[16px]" style={{ minHeight: 28 }}>
        <div className="flex items-center gap-[8px]">
          <MiyagiMark size={28} tone="light" />
          <MiyagiWordmark height={22} tone="light" />
        </div>
        <div className="flex min-w-0 items-center gap-[24px]" style={{ fontSize: type2.sm, color: paper.muted }}>
          {account?.signedIn && account.email && <span className="truncate">{`Signed in as ${account.email}`}</span>}
          <TextLink tone="paper" weight={500} onClick={() => openLink('restore')}>
            Restore a purchase
          </TextLink>
        </div>
      </header>

      <section className={`flex justify-between gap-[24px] ${wide ? 'items-end' : 'flex-col items-start'}`}>
        <div className="flex flex-col gap-[8px]">
          <h1 className="m-0 font-semibold" style={{ fontSize: wide ? H1 : type2.xxl, lineHeight: wide ? '44px' : '34px', letterSpacing: '-0.025em' }}>
            Pick a plan
          </h1>
          <p className="m-0" style={{ fontSize: type2.body, lineHeight: '22px', color: paper.muted }}>
            Lessons are built once and shared. Plans cover live help.
          </p>
        </div>
        <Segmented
          surface="paper"
          label="Billing period"
          value={period}
          onChange={setPeriod}
          options={[
            { value: 'monthly', label: 'Monthly' },
            { value: 'yearly', label: save ? `Yearly, save ${save}%` : 'Yearly' }
          ]}
        />
      </section>

      <section className="grid gap-[16px]" style={{ gridTemplateColumns: wide ? 'repeat(4, minmax(0, 1fr))' : 'repeat(2, minmax(0, 1fr))' }}>
        {cards.map((c) => (
          <Plan key={c.id} card={c} />
        ))}
      </section>

      {help && (
        <footer
          className={`flex justify-between gap-[16px] ${wide ? 'items-center' : 'flex-col items-start'}`}
          style={{ minHeight: 56, padding: wide ? '0 24px' : '14px 20px', background: paper.surface, boxShadow: `inset 0 0 0 1px ${paper.hairline}`, borderRadius: radius2.chip, fontSize: type2.sm }}
        >
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-[16px] gap-y-[6px]">
            <span className="whitespace-nowrap font-semibold">This month</span>
            <Meter help={help} tone="paper" width={wide ? 200 : 140} label="Free help requests used" />
            <span className="whitespace-nowrap" style={{ color: paper.muted }}>{`${help.used} of ${help.limit} ${current === 'free' ? 'free ' : ''}help requests used`}</span>
          </div>
          <span className="whitespace-nowrap" style={{ color: paper.label }}>
            Checks on your work never count. Cancel anytime.
          </span>
        </footer>
      )}
    </div>
  )
}

function Plan({ card }: { card: PlanCard }): ReactNode {
  const featured = card.look === 'featured'
  const dashed = card.look === 'dashed'
  return (
    <article
      className="flex flex-col gap-[16px]"
      style={{
        padding: 24,
        borderRadius: radius2.panel,
        background: dashed ? 'transparent' : paper.surface,
        border: featured ? `1.5px solid ${paper.ink}` : dashed ? `1px dashed ${paper.border}` : `1px solid ${paper.hairline}`,
        boxShadow: featured ? paper.shadow : undefined
      }}
    >
      <div className="flex flex-col gap-[8px]">
        <div className="flex items-center justify-between gap-[8px]">
          <h2 className="m-0 font-semibold" style={{ fontSize: type2.body, lineHeight: '20px' }}>
            {card.name}
          </h2>
          {card.badge && <Chip tone="paper">{card.badge}</Chip>}
        </div>
        <div className="flex flex-wrap items-baseline gap-x-[6px]" style={{ minHeight: 40 }}>
          {card.price && (
            <span className="font-semibold tabular-nums" style={{ fontSize: 32, lineHeight: '40px', letterSpacing: '-0.02em' }}>
              {card.price}
            </span>
          )}
          <span style={{ fontSize: type2.sm, color: paper.label }}>{card.price ? card.per : 'Price coming soon'}</span>
        </div>
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: paper.muted }}>
          {card.blurb}
        </p>
      </div>
      {card.action}
      <Rule tone="paper" />
      <ul className="m-0 flex list-none flex-col gap-[12px] p-0" style={{ fontSize: type2.sm, lineHeight: '18px' }}>
        {card.features.map((f) => (
          <li key={f} className="flex gap-[8px]">
            <Check size={16} strokeWidth={1.8} className="mt-px shrink-0" style={{ color: paper.ink }} aria-hidden />
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </article>
  )
}
