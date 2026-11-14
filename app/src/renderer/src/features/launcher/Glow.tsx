/**
 * Feature: launcher. The launcher's light: the edge that travels around the search field, the soft
 * aurora behind the title, the primary button, and the chips. All decoration is pointer-transparent
 * and lives inside the panel's content, so it fades with it and the collapsed panel is pure island.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { CornerDownLeft, type LucideIcon } from 'lucide-react'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { color, spring } from '../../core/theme'
import { tint } from './tint'

/** One section of the panel rising into place, a beat after the one above it. */
export function Rise({ i, children, className = '' }: { i: number; children: ReactNode; className?: string }): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.08 + i * 0.045
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        y: { ...spring, delay },
        opacity: { duration: 0.22, delay, ease: 'easeOut' }
      }}
    >
      {children}
    </motion.div>
  )
}

/** Slow aurora behind the title. Sits under the content (negative z) and drifts. */
export function Ambient(): ReactNode {
  const reduce = useReducedMotion()
  const blobs = [
    { left: 70, top: 70, drift: 36 },
    { left: 230, top: 50, drift: -28 },
    { left: 380, top: 85, drift: 22 }
  ]
  return (
    <div aria-hidden className="pointer-events-none absolute left-1/2 top-[-170px] -z-10 h-[320px] w-[640px] -translate-x-1/2">
      {blobs.map((b, i) => (
        <motion.div
          key={i}
          className="absolute h-[170px] w-[300px] rounded-full"
          style={{
            left: b.left,
            top: b.top,
            background: tint.ambient[i],
            filter: 'blur(64px)'
          }}
          animate={
            reduce
              ? undefined
              : {
                  x: [0, b.drift, 0],
                  y: [0, i % 2 ? -10 : 10, 0],
                  opacity: [0.75, 1, 0.75]
                }
          }
          transition={{
            duration: 7 + i * 1.7,
            repeat: Infinity,
            ease: 'easeInOut'
          }}
        />
      ))}
    </div>
  )
}

/** The conic light, rotating forever; clipped by whoever holds it. */
function Sweep(): ReactNode {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className="absolute left-1/2 top-1/2 aspect-square w-[150%]"
      style={{ x: '-50%', y: '-50%', background: tint.ring }}
      animate={reduce ? undefined : { rotate: 360 }}
      transition={{ duration: 4.5, repeat: Infinity, ease: 'linear' }}
    />
  )
}

/**
 * The search field's living edge: a comet of accent → violet → pink light running around a hairline,
 * with a soft halo outside it. `live` (something typed) brightens it; `busy` (searching) brightest.
 */
export function AuroraField({ live, busy, children }: { live: boolean; busy: boolean; children: ReactNode }): ReactNode {
  const level = busy ? 1 : live ? 0.8 : 0.5
  return (
    <div className="relative">
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -inset-[2px] overflow-hidden rounded-[19px]"
        style={{ filter: 'blur(14px)' }}
        initial={false}
        animate={{ opacity: level * 0.75 }}
        transition={{ duration: 0.4 }}
      >
        <Sweep />
      </motion.div>
      <div className="relative overflow-hidden rounded-[17px] p-[1.5px]" style={{ background: tint.fieldEdge }}>
        <motion.div aria-hidden className="absolute inset-0" initial={false} animate={{ opacity: level }} transition={{ duration: 0.4 }}>
          <Sweep />
        </motion.div>
        <div
          className="relative rounded-[15.5px]"
          style={{
            background: tint.fieldSolid,
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,.05)'
          }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

/**
 * The primary action. Solid (lit accent, glowing, an occasional sheen when `sheen`) when it can act;
 * a quiet ghost when it can't, so a disabled state never reads as a broken button.
 */
export function PrimaryButton({
  label,
  solid,
  busy = false,
  sheen = false,
  onClick
}: {
  label: string
  solid: boolean
  busy?: boolean
  sheen?: boolean
  onClick: () => void
}): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="relative flex h-[38px] w-[158px] shrink-0 cursor-pointer items-center justify-between overflow-hidden rounded-[19px] pl-[16px] pr-[6px] text-[14.5px] font-semibold disabled:cursor-default"
      style={{ background: tint.ghost }}
      initial={false}
      animate={{ boxShadow: solid ? tint.buttonGlow : tint.buttonGlowOff }}
      whileHover={solid ? { scale: 1.02 } : undefined}
      whileTap={solid ? { scale: 0.96 } : undefined}
      transition={{ duration: 0.2 }}
      disabled={!solid}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <motion.span
        aria-hidden
        className="absolute inset-0"
        style={{ background: tint.button, boxShadow: tint.buttonInset }}
        initial={false}
        animate={{ opacity: solid ? 1 : 0 }}
        transition={{ duration: 0.22 }}
      />
      {solid && sheen && (
        <motion.span
          aria-hidden
          className="absolute inset-y-0 left-0 w-[56px]"
          style={{ background: tint.sheen, skewX: -20 }}
          initial={{ x: -90 }}
          animate={{ x: 230 }}
          transition={{
            duration: 1.1,
            repeat: Infinity,
            repeatDelay: 2.6,
            ease: 'easeInOut',
            delay: 0.5
          }}
        />
      )}
      <span className="relative flex items-center gap-[8px] transition-colors duration-200" style={{ color: solid ? '#fff' : color.faint }}>
        {busy && <Spinner size={13} />}
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={label}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.13, ease: 'easeOut' }}
          >
            {label}
          </motion.span>
        </AnimatePresence>
      </span>
      <span
        className="relative grid h-[26px] w-[28px] place-items-center rounded-[13px] transition-colors duration-200"
        style={{
          background: solid ? tint.onAccent : tint.ghost,
          color: solid ? '#fff' : color.faint
        }}
      >
        <CornerDownLeft size={12} strokeWidth={2.2} />
      </span>
    </motion.button>
  )
}

/** A rounded chip: a suggestion to search, or a quick action. */
export function Chip({ icon: I, tone, label, kbd, onClick }: { icon: LucideIcon; tone: string; label: string; kbd?: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className={`flex h-[34px] cursor-pointer items-center gap-[8px] whitespace-nowrap rounded-full border pl-[12px] text-[13px] font-medium text-white/70 transition-colors duration-150 hover:text-white ${kbd ? 'pr-[5px]' : 'pr-[14px]'}`}
      style={{ backgroundColor: tint.chip, borderColor: tint.chipBorder }}
      whileHover={{ y: -1, backgroundColor: tint.chipHover }}
      whileTap={{ scale: 0.95 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={14} strokeWidth={1.8} style={{ color: tone }} className="shrink-0" />
      {label}
      {kbd && <Kbd className="!h-[24px] !rounded-full !px-[9px]">{kbd}</Kbd>}
    </motion.button>
  )
}
