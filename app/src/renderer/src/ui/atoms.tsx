/** Small building blocks shared by the pill, cards, launcher and shortcut bar. */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { CheckItem, Status } from '../store'
import { color, spring } from '../theme'

/** Status dot: gray watching · amber off-track · green passed. Pulses twice when it turns amber. */
export function StatusDot({ status, size = 7 }: { status: Status; size?: number }): ReactNode {
  const c = status === 'offtrack' ? color.amber : status === 'passed' ? color.green : color.gray
  return (
    <motion.span
      key={status}
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: c, boxShadow: status === 'watching' ? 'none' : `0 0 8px ${c}` }}
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
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.18)" strokeWidth={stroke} />
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
export function Spinner({ size = 18, c = color.accent }: { size?: number; c?: string }): ReactNode {
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className="shrink-0"
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
    >
      <circle cx="9" cy="9" r="7.5" fill="none" stroke="rgba(255,255,255,.14)" strokeWidth="1.6" />
      <path d="M9 1.5 A7.5 7.5 0 0 1 16.5 9" fill="none" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
    </motion.svg>
  )
}

/** One check: filled green circle whose checkmark draws its stroke on pass. */
export function CheckIcon({ status, active }: { status: CheckItem['status']; active: boolean }): ReactNode {
  if (status === 'pass')
    return (
      <motion.svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={spring}>
        <circle cx="9" cy="9" r="9" fill={color.green} />
        <motion.path
          d="M5.2 9.3 L7.8 11.8 L12.9 6.4"
          fill="none"
          stroke="#04210f"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.25, ease: 'easeOut', delay: 0.05 }}
        />
      </motion.svg>
    )
  if (status === 'fail')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="8.2" fill="none" stroke={color.amber} strokeWidth="1.6" />
        <path d="M9 5 V10" stroke={color.amber} strokeWidth="1.7" strokeLinecap="round" />
        <circle cx="9" cy="12.8" r="1" fill={color.amber} />
      </svg>
    )
  if (active) return <Spinner />
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="8.2" fill="none" stroke="rgba(255,255,255,.28)" strokeWidth="1.4" />
    </svg>
  )
}

export function CheckList({ checks }: { checks: CheckItem[] }): ReactNode {
  const activeId = checks.find((c) => c.status === 'pending')?.id
  return (
    <div className="flex flex-col gap-[11px]">
      {checks.map((c) => {
        const active = c.id === activeId
        const tone = c.status === 'pass' ? color.label : c.status === 'fail' || active ? '#fff' : color.faint
        return (
          <div key={c.id} className="flex items-center gap-3 text-[14px] leading-[18px]">
            <CheckIcon status={c.status} active={active} />
            <motion.span className="flex-1 truncate" animate={{ color: tone }} transition={{ duration: 0.2 }}>
              {c.label}
            </motion.span>
            {c.detail && (
              <span className="shrink-0 text-[12px] tabular-nums" style={{ color: c.status === 'fail' ? color.amber : color.faint }}>
                {c.detail}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Keyboard hint chip, e.g. ⌥Space. */
export function Kbd({ children, className = '' }: { children: ReactNode; className?: string }): ReactNode {
  return (
    <span
      className={`inline-flex h-[22px] items-center rounded-[6px] px-[7px] text-[12px] font-medium ${className}`}
      style={{ background: 'rgba(255,255,255,.1)', color: 'rgba(255,255,255,.62)' }}
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
        <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg,#0f1630,#151a33 60%,#1b1636)' }}>
          <div className="absolute left-[9%] top-[18%] h-[5%] w-[38%] rounded-full bg-white/50" />
          <div className="absolute left-[9%] top-[32%] h-[4%] w-[26%] rounded-full bg-white/25" />
          <div className="absolute left-[9%] top-[44%] h-[4%] w-[30%] rounded-full bg-white/25" />
          <div
            className="absolute right-[8%] top-[18%] h-[62%] w-[38%] rounded-[3px]"
            style={{ background: 'repeating-linear-gradient(135deg,#7a3cff 0 3px,#d9445a 3px 6px)' }}
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
