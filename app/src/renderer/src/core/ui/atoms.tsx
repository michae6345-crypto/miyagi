/** Small building blocks shared by the pill, cards, launcher and shortcut bar. */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Eye, Lightbulb, MessageSquareText, Play, SquarePlay, Waypoints, X, type LucideIcon } from 'lucide-react'
import { useThinking, type CheckItem, type Status } from '../lesson'
import { emitUi } from '../bus'
import { usePressed } from '../shortcuts'
import { actionTone, brand, color, fill, font, glass, spring, type OptionAction } from '../theme'
import { GlassCheck, GlassSpinner } from './glass'

/** Status dot: gray watching · white ring off track · green passed. Pulses twice when it goes off track. No glow (brand). */
export function StatusDot({ status, size = 7 }: { status: Status; size?: number }): ReactNode {
  const c = status === 'offtrack' ? color.amber : status === 'passed' ? color.green : color.gray
  const ring = status === 'offtrack'
  return (
    <motion.span
      key={status}
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: ring ? 'transparent' : c, boxShadow: ring ? `inset 0 0 0 1.5px ${c}` : undefined }}
      initial={{ scale: 1 }}
      animate={{ scale: status === 'offtrack' ? [1, 1.35, 1, 1.35, 1] : 1 }}
      transition={{ duration: 0.9, ease: 'easeInOut' }}
    />
  )
}

/** Lesson progress ring. The arc advances on the spring. */
export function ProgressRing({ fraction, size = 15, stroke = 2 }: { fraction: number; size?: number; stroke?: number }): ReactNode {
  const r = (size - stroke) / 2
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={fill.track} strokeWidth={stroke} />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color.accent}
        strokeWidth={stroke}
        strokeLinecap="round"
        initial={false}
        animate={{ pathLength: Math.max(0.001, fraction) }}
        transition={spring}
      />
    </svg>
  )
}

/** Spinning arc for "working on it". */
/** `track`: the ring under the arc. Default white 14% (dark surfaces); on a pastel or white tile pass fill.onAccentKey. */
export function Spinner({ size = 18, c = color.accent, track = fill.trackSoft }: { size?: number; c?: string; track?: string }): ReactNode {
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className="shrink-0"
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
    >
      <circle cx="9" cy="9" r="7.5" fill="none" stroke={track} strokeWidth="1.6" />
      <path d="M9 1.5 A7.5 7.5 0 0 1 16.5 9" fill="none" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
    </motion.svg>
  )
}

/**
 * One check: passed = a filled green circle whose tick draws in · not yet (fail) = a hollow white ring, no mark
 * (off track has no hue) · pending = an empty faint ring. `active` = a Check is in flight (useChecking): the
 * spinner, the only time a check row moves.
 */
export function CheckIcon({ status, active }: { status: CheckItem['status']; active: boolean }): ReactNode {
  if (status === 'pass')
    return (
      <motion.svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={spring}>
        <circle cx="9" cy="9" r="9" fill={color.green} />
        <motion.path
          d="M5.2 9.3 L7.8 11.8 L12.9 6.4"
          fill="none"
          stroke={brand.ink}
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.25, ease: 'easeOut', delay: 0.05 }}
        />
      </motion.svg>
    )
  if (active) return <Spinner />
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="8.2" fill="none" stroke={status === 'fail' ? color.amber : fill.ring} strokeWidth={status === 'fail' ? 1.6 : 1.4} />
    </svg>
  )
}

/** The same check icon on a glass panel (theme.glass, follows Settings → Appearance). Colors via style, so var() resolves. */
function GlassCheckIcon({ status, active }: { status: CheckItem['status']; active: boolean }): ReactNode {
  if (status === 'pass') return <GlassCheck />
  if (active) return <GlassSpinner c={glass.text} />
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth={status === 'fail' ? 1.6 : 1.4} style={{ stroke: status === 'fail' ? glass.offTrack : glass.faint }} />
    </svg>
  )
}

/**
 * A Check is in flight: the learner asked for one (action check_step: Check my work, the bar's Check) and the engine
 * is thinking about it. The only time check rows spin; otherwise a pending check is a still, empty ring.
 */
export function useChecking(): boolean {
  const thinking = useThinking()
  const pressed = usePressed((p) => p.kind)
  return thinking && pressed === 'check_step'
}

/**
 * Code inside a sentence: text in backticks, a call `f(x)`, an assignment / comparison `beta=0.1`, a dotted name or
 * file `calculator.py`, snake_case / __dunder__, a flag `--port`. Everything else stays prose.
 */
const CODE_RE =
  /`([^`\n]+)`|[A-Za-z_][\w.]*\((?:[^()\n]|\([^()\n]*\))*\)|[A-Za-z_][\w.[\]]*\s?(?:[=!<>]=|[+-]?=)\s?[^\s,;]+|(?:[\w-]+\/)*[A-Za-z_][\w-]*(?:\.[A-Za-z_]\w*)+|__\w+__|\b[A-Za-z]\w*_\w+|(?<![\w-])--?[A-Za-z][\w-]*/g
/** Dotted words that are prose, not code. */
const NOT_CODE = /^(e\.g|i\.e|a\.m|p\.m|u\.s)$/i

/** Prose with its code tokens in the mono font (check labels and details: "calculator.py exists", "`add(2, 3)` returns 5"). */
export function CodeText({ text }: { text: string }): ReactNode {
  const out: ReactNode[] = []
  let at = 0
  for (const m of text.matchAll(CODE_RE)) {
    const code = m[1] ?? m[0]
    if (m[1] === undefined && NOT_CODE.test(m[0])) continue
    const i = m.index ?? 0
    if (i > at) out.push(text.slice(at, i))
    out.push(
      <code key={i} style={{ fontFamily: font.mono, fontSize: '0.92em' }}>
        {code}
      </code>
    )
    at = i + m[0].length
  }
  if (at === 0) return text
  if (at < text.length) out.push(text.slice(at))
  return out
}

type CheckSurface = 'island' | 'glass'
/** The island's tokens (black, always) or a glass panel's (theme.glass CSS variables). Watching gray is the same on both. */
const CHECK_TONE: Record<CheckSurface, { text: string; label: string; faint: string; pass: string; notYet: string }> = {
  island: { text: color.text, label: color.label, faint: color.faint, pass: color.green, notYet: color.amber },
  glass: { text: glass.text, label: glass.label, faint: glass.faint, pass: glass.pass, notYet: glass.offTrack }
}

/**
 * The step's checks, one row each: the icon, the label (up to two lines, code in mono, the full text on hover), the
 * engine's detail as a faint second line, and ONE status word on the right: Passed (green) · Watching (gray, eye;
 * the whole row gray, an empty ring, never a spinner or a "!") · Not yet (white, no hue). Rows only spin while a
 * Check is in flight (useChecking). `surface="glass"` for glass panels (the drawer); the island and its cards are
 * the default.
 */
export function CheckList({ checks, surface = 'island' }: { checks: CheckItem[]; surface?: CheckSurface }): ReactNode {
  const checking = useChecking()
  const t = CHECK_TONE[surface]
  const Icon = surface === 'glass' ? GlassCheckIcon : CheckIcon
  return (
    <div className="flex flex-col gap-[11px]">
      {checks.map((c) => {
        const active = checking && c.status !== 'pass'
        // Only "Not yet" stands out (white, no hue). Pending is a quiet gray "Watching" row (Michael: a new step's
        // checks stay pending, with no detail, until the learner starts); passed recedes next to its green word.
        const tone = c.status === 'fail' ? t.text : t.label
        return (
          // items-start: a two-line label wraps under itself; the icon and the status word stay on line one.
          <div key={c.id} data-check={c.id} data-check-status={c.status} className="flex items-start gap-3 text-[14px] leading-[18px]">
            <Icon status={c.status} active={active} />
            <div className="min-w-0 flex-1">
              <div className="line-clamp-2 break-words" style={{ color: tone, transition: 'color 200ms ease-out' }} title={c.label}>
                <CodeText text={c.label} />
              </div>
              {c.detail && (
                <div
                  data-part="check-detail"
                  className="mt-[1px] truncate text-[12px] leading-[16px] tabular-nums"
                  style={{ color: c.status === 'fail' ? t.label : t.faint }}
                  title={c.detail}
                >
                  <CodeText text={c.detail} />
                </div>
              )}
            </div>
            <CheckWord status={c.status} tone={t} />
          </div>
        )
      })}
    </div>
  )
}

function CheckWord({ status, tone }: { status: CheckItem['status']; tone: (typeof CHECK_TONE)[CheckSurface] }): ReactNode {
  const word = status === 'pass' ? 'Passed' : status === 'fail' ? 'Not yet' : 'Watching'
  const c = status === 'pass' ? tone.pass : status === 'fail' ? tone.notYet : color.gray
  return (
    <span data-part="check-word" className="flex shrink-0 items-center gap-[4px] whitespace-nowrap text-[12px] font-medium leading-[18px]" style={{ color: c }}>
      {status === 'pending' && <Eye size={12} strokeWidth={1.9} className="shrink-0" />}
      {word}
    </span>
  )
}

/** Keyboard hint chip, e.g. ⌥Space. */
export function Kbd({ children, className = '' }: { children: ReactNode; className?: string }): ReactNode {
  return (
    <span
      className={`inline-flex h-[22px] items-center rounded-[6px] px-[7px] text-[12px] font-medium ${className}`}
      style={{ background: fill.key, color: fill.keyText }}
    >
      {children}
    </span>
  )
}

/** Generated video thumbnail (until the engine sends real ones): a slide with the convection stripes. */
export function Thumb({ w, h, time, src }: { w: number; h: number; time?: string; src?: string }): ReactNode {
  return (
    <div className="relative shrink-0 overflow-hidden" style={{ width: w, height: h, borderRadius: Math.round(h * 0.15) }}>
      {src ? (
        <img src={src} className="h-full w-full object-cover" />
      ) : (
        <div className="absolute inset-0" style={{ background: fill.thumb }}>
          <div className="absolute left-[9%] top-[18%] h-[5%] w-[38%] rounded-full bg-white/50" />
          <div className="absolute left-[9%] top-[32%] h-[4%] w-[26%] rounded-full bg-white/25" />
          <div className="absolute left-[9%] top-[44%] h-[4%] w-[30%] rounded-full bg-white/25" />
          <div
            className="absolute right-[8%] top-[18%] h-[62%] w-[38%] rounded-[3px]"
            style={{ background: fill.thumbArt }}
          />
        </div>
      )}
      <div className="absolute inset-0 grid place-items-center">
        <svg width={h * 0.28} height={h * 0.28} viewBox="0 0 10 10">
          <path d="M2 1 L9 5 L2 9 Z" fill="#fff" />
        </svg>
      </div>
      {time && (
        <span className="absolute bottom-[5px] right-[6px] rounded-[4px] bg-black/70 px-[4px] text-[11px] font-semibold tabular-nums text-white">
          {time}
        </span>
      )}
    </div>
  )
}

export const hairline = { borderColor: color.hairline } as const

const ACTION_ICON: Record<OptionAction, LucideIcon> = { explain: MessageSquareText, diagram: Waypoints, watch: Play, show_me: SquarePlay, hint: Lightbulb }

/**
 * An option (Explain, Diagram, Watch, Show me, Hint): a 30px pill in the action's pastel with ink label and
 * icon, keycap on ink 10%. The same action is the same color everywhere (theme.actionTone). Options only.
 */
export function OptionButton({ action, label, kbd, onClick, icon }: { action: OptionAction; label: string; kbd?: string; onClick: () => void; icon?: LucideIcon }): ReactNode {
  const I = icon ?? ACTION_ICON[action]
  return (
    <motion.button
      type="button"
      className={`flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full pl-[11px] text-[13px] font-medium ${kbd ? 'pr-[4px]' : 'pr-[13px]'}`}
      style={{ backgroundColor: actionTone[action], color: color.onAccent }}
      whileHover={{ filter: 'brightness(1.06)' }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={13} strokeWidth={1.8} className="shrink-0" />
      {label}
      {kbd && (
        <span className="inline-flex h-[22px] items-center rounded-full px-[8px] text-[11px] font-medium" style={{ background: fill.onAccentKey }}>
          {kbd}
        </span>
      )}
    </motion.button>
  )
}

/** The ONE primary action on a surface (Build lesson, Apply fix, Ask, Replay step): white pill, ink text, keycap on ink 10%. */
export function PrimaryButton({ label, kbd, onClick, icon: I, disabled }: { label: string; kbd?: string; onClick: () => void; icon?: LucideIcon; disabled?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      disabled={disabled}
      className={`flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full pl-[13px] text-[13px] font-medium disabled:cursor-default ${kbd ? 'pr-[4px]' : 'pr-[13px]'}`}
      style={{ backgroundColor: color.accent, color: color.onAccent, opacity: disabled ? 0.4 : 1 }}
      whileHover={disabled ? undefined : { filter: 'brightness(0.96)' }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {I && <I size={13} strokeWidth={1.8} className="shrink-0" />}
      {label}
      {kbd && (
        <span className="inline-flex h-[22px] items-center rounded-full px-[8px] text-[11px] font-medium" style={{ background: fill.onAccentKey }}>
          {kbd}
        </span>
      )}
    </motion.button>
  )
}

/**
 * @deprecated Use OptionButton (Explain / Show me / Hint / ...) or PrimaryButton (the one primary action).
 * Kept so older call sites still compile: `primary` = white + ink, otherwise neutral. `tone` is ignored.
 */
export function CardButton({ children, onClick, primary }: { children: ReactNode; onClick: () => void; primary?: boolean; tone?: string }): ReactNode {
  return (
    <motion.button
      className="flex h-[36px] flex-1 cursor-pointer items-center justify-center gap-[7px] rounded-[12px] text-[14px] font-semibold"
      style={primary ? { background: color.accent, color: color.onAccent } : { background: fill.button, color: color.text }}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.09 }}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}

/** Round ✕ that closes whatever card/diagram is open (emits the 'dismiss' UI event, same as Esc). */
export function CloseButton(): ReactNode {
  return (
    <button
      className="grid h-[22px] w-[22px] cursor-pointer place-items-center rounded-full text-white/60 hover:text-white"
      style={{ background: fill.key }}
      onClick={() => emitUi('dismiss')}
      aria-label="Close"
    >
      <X size={12} strokeWidth={2.2} />
    </button>
  )
}
