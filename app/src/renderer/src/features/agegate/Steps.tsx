/**
 * Feature: agegate. The three screens of the age step (AgeFirst.tsx runs them, before the sign-in):
 *
 *   Birthday   "When's your birthday?" with month, day and year pickers. Neutral (COPPA-style): nothing picked at the
 *              start, no default year, no hint of an age that matters, no "I'm over 13" box. Continue stays off until
 *              the three make a real day that isn't in the future. "By continuing you agree to the Terms and Privacy".
 *   Guardian   13 to 17: "Ask a parent or guardian to read the Terms and Privacy with you." and the box "My parent or
 *              guardian agrees", which starts unchecked and must be checked to continue. Back.
 *   Blocked    under 13 (Blocked.tsx): "miyagi is for people 13 and up" and one kind line. Final: nothing sent, no
 *              way past it; Quit miyagi, and Delete my account when signed in.
 *
 * The picked date lives only in Birthday's own state (gone when it unmounts): it is never stored, sent or logged;
 * only the result leaves (AgeFirst → store.saveAge). Neutral chrome only (BRAND.md): white primary, no hue.
 */
import { motion } from 'motion/react'
import { ChevronDown } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { color, font, radius2, spring, surface, type2, v4type } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { TextLink } from '../account/ui'
import { openLegal } from '../auth/store'
import { MARK_ID } from '../onboarding/Intro'
import { daysIn, OLDEST, realDay, validBirth, type Birth, type Day } from './age'

export const COPY = {
  title: 'When’s your birthday?',
  line: 'miyagi doesn’t save your birthday.',
  future: 'That day hasn’t come yet.',
  notReal: 'That day isn’t on the calendar.',
  agree: { lead: 'By continuing you agree to the ', terms: 'Terms', and: ' and ', privacy: 'Privacy', end: '.' },
  guardianTitle: 'Before you sign in',
  guardianLead: 'Ask a parent or guardian to read the ',
  guardianEnd: ' with you.',
  guardianBox: 'My parent or guardian agrees',
  blockedTitle: 'miyagi is for people 13 and up',
  blockedLine: 'Thanks for stopping by. Keep being curious.',
  continue: 'Continue',
  back: 'Back'
} as const

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] as const

/**
 * The room under a frame: more than above it, so the step sits on the window's middle line (the same rule as the setup
 * pages, onboarding/v4.tsx SetupPage), above the fine print at the foot.
 */
const FRAME_BOTTOM = 'calc(88px + 4vh)'

/** The screens' shared frame: the bonsai (shared element), the title and its line, centered like the login. */
export function Frame({ title, line, children, footer }: { title: string; line?: ReactNode; children?: ReactNode; footer?: ReactNode }): ReactNode {
  return (
    <section aria-labelledby="age-title" className="absolute inset-0 flex flex-col items-center justify-center" style={{ padding: `24px 40px ${FRAME_BOTTOM}` }}>
      <div className="flex w-full max-w-[400px] flex-col items-center">
        <motion.div layoutId={MARK_ID} transition={spring}>
          <MiyagiMark size={48} />
        </motion.div>
        <h1 id="age-title" className="m-0 mt-[18px] text-center" style={{ ...v4type.title, color: color.text }}>
          {title}
        </h1>
        {line && (
          <p className="m-0 mt-[6px] text-center" style={{ ...v4type.lede, color: color.label }}>
            {line}
          </p>
        )}
        {children}
      </div>
      {footer && <div className="absolute bottom-[28px] left-0 right-0 flex flex-col items-center gap-[10px]">{footer}</div>}
    </section>
  )
}

function Agree(): ReactNode {
  return (
    <span data-age-agree style={{ fontSize: type2.xs, color: color.label }}>
      {COPY.agree.lead}
      <TextLink onClick={() => openLegal('terms')}>{COPY.agree.terms}</TextLink>
      {COPY.agree.and}
      <TextLink onClick={() => openLegal('privacy')}>{COPY.agree.privacy}</TextLink>
      {COPY.agree.end}
    </span>
  )
}

function Picker({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: readonly { v: string; t: string }[] }): ReactNode {
  return (
    <label className="relative flex min-w-0 flex-1">
      <span className="sr-only">{label}</span>
      <select
        data-age-pick={label.toLowerCase()}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-[44px] w-full min-w-0 cursor-pointer appearance-none pl-[14px] pr-[34px] outline-none"
        style={{
          borderRadius: radius2.row,
          background: surface.well,
          boxShadow: `inset 0 0 0 1px ${surface.border}`,
          fontSize: type2.body,
          color: value ? color.text : color.label,
          fontFamily: font.ui
        }}
      >
        {/* The empty first choice: nothing is picked until the learner picks it. */}
        <option value="" disabled>
          {label}
        </option>
        {options.map((o) => (
          <option key={o.v} value={o.v}>
            {o.t}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden size={14} strokeWidth={1.8} className="pointer-events-none absolute right-[12px] top-1/2 -translate-y-1/2" style={{ color: color.label }} />
    </label>
  )
}

const num = (s: string): number | undefined => (s === '' ? undefined : Number(s))

/** Birthday: month, day, year. onDone gets the date only to decide; AgeFirst never keeps it. */
export function Birthday({ today, onDone }: { today: Day; onDone: (b: Birth) => void }): ReactNode {
  const [m, setM] = useState('')
  const [d, setD] = useState('')
  const [y, setY] = useState('')
  const pick = { y: num(y), m: num(m), d: num(d) }
  const full = pick.y !== undefined && pick.m !== undefined && pick.d !== undefined
  const ok = validBirth(pick, today)
  const why = full && !ok ? (realDay(pick) ? COPY.future : COPY.notReal) : undefined

  const months = useMemo(() => MONTHS.map((t, i) => ({ v: String(i + 1), t })), [])
  // Days follow the month (and Feb 29 the year) once they are picked; until then all 31, so no order is forced.
  const dayCount = pick.m ? daysIn(pick.y ?? 2000, pick.m) : 31
  const days = useMemo(() => Array.from({ length: 31 }, (_, i) => ({ v: String(i + 1), t: String(i + 1) })).slice(0, Math.max(dayCount, num(d) ?? 0)), [dayCount, d])
  // Newest first, no year chosen for them (no default year).
  const years = useMemo(() => Array.from({ length: OLDEST + 1 }, (_, i) => String(today.y - i)).map((v) => ({ v, t: v })), [today.y])

  return (
    <Frame title={COPY.title} line={COPY.line} footer={<Agree />}>
      <form
        className="mt-[32px] flex w-full flex-col items-center gap-[14px]"
        onSubmit={(e) => {
          e.preventDefault()
          if (ok) onDone(pick as Birth)
        }}
      >
        <div data-age-pickers className="flex w-full gap-[8px]">
          <Picker label="Month" value={m} onChange={setM} options={months} />
          <span className="flex w-[84px] shrink-0">
            <Picker label="Day" value={d} onChange={setD} options={days} />
          </span>
          <span className="flex w-[104px] shrink-0">
            <Picker label="Year" value={y} onChange={setY} options={years} />
          </span>
        </div>
        <span data-age-why aria-live="polite" className="min-h-[18px]" style={{ fontSize: type2.sm, color: color.text }}>
          {why ?? ''}
        </span>
        <span data-age-continue={ok ? 'on' : 'off'} className="w-full">
          <PrimaryButton size="lg" block label={COPY.continue} disabled={!ok} onClick={() => ok && onDone(pick as Birth)} />
        </span>
      </form>
    </Frame>
  )
}

/** 13 to 17: the parent or guardian step. The box starts unchecked. */
/** Back is the window's top bar (AgeFirst registers it), not a link here. */
export function Guardian({ onDone }: { onDone: () => void }): ReactNode {
  const [agreed, setAgreed] = useState(false)
  const id = useId()
  return (
    <Frame
      title={COPY.guardianTitle}
      line={
        <>
          {COPY.guardianLead}
          <TextLink onClick={() => openLegal('terms')}>Terms</TextLink> and <TextLink onClick={() => openLegal('privacy')}>Privacy</TextLink>
          {COPY.guardianEnd}
        </>
      }
      footer={<Agree />}
    >
      <div className="mt-[28px] flex w-full flex-col items-center gap-[18px]">
        <label htmlFor={id} data-age-guardian className="flex min-h-[44px] w-full cursor-pointer items-center gap-[12px] px-[16px]" style={{ borderRadius: radius2.row, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.body, color: color.text }}>
          <input id={id} type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} style={{ width: 18, height: 18, margin: 0, accentColor: color.accent }} />
          {COPY.guardianBox}
        </label>
        <span data-age-continue={agreed ? 'on' : 'off'} className="w-full">
          <PrimaryButton size="lg" block label={COPY.continue} disabled={!agreed} onClick={() => agreed && onDone()} />
        </span>
      </div>
    </Frame>
  )
}
