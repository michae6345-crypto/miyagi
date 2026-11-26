/**
 * Feature: settings. The building blocks every section shares (Set-* mockups): the page header, a grouped block of
 * rows with hairlines, a row (icon tile, label and caption, a control on the right), an outline badge, a small note
 * and the On word. Neutral chrome only: no pastel, no green (green means passed).
 */
import type { LucideIcon } from 'lucide-react'
import { Check, Info } from 'lucide-react'
import { motion } from 'motion/react'
import { createContext, useContext, useId, Fragment, type ReactNode } from 'react'
import { color, elevation, fill, highlight, radius2, spring, type2 } from '../../core/theme'
import { Segmented } from '../../core/ui/atoms'
import { ROW_HEIGHT, useLocal } from './local'

/** True inside the home window's Settings page (features/shell): there the page title and the section control already
 * name the section, so a section's own header keeps only its right-hand actions. */
export const InlineSettings = createContext(false)

/** True inside the v4 Settings page (features/shell, Nov 24): groups lose their card and become a section head with a
 * hairline under it, and rows lose their icon tile and side padding (Adrian's ui-next settings mock). The pill-born
 * sheet keeps the cards. Every group drawn through Group / Row (ptt, buddy, reminders too) follows it. */
export const Flat = createContext(false)

/**
 * A segmented control sized for where it sits: core's Segmented (32 tall, 16 px sides, sized for the sheet's cards),
 * or inside `Flat` the v4 page's 26 tall one with 10 px sides and 12.5 px labels (Adrian's settings mock). Same look
 * and keys otherwise; the settings feature's own size, never a restyle of the core control.
 */
export function Seg<T extends string>({ options, value, onChange, label }: { options: ReadonlyArray<{ value: T; label: string }>; value: T; onChange: (v: T) => void; label?: string }): ReactNode {
  const flat = useContext(Flat)
  const group = useId()
  if (!flat) return <Segmented label={label} options={options} value={value} onChange={onChange} />
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex shrink-0 items-center p-[2px]" style={{ background: fill.segmentTrack, borderRadius: radius2.control, border: `1px solid ${fill.hairline}` }}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            className="relative cursor-pointer whitespace-nowrap px-[10px]"
            style={{ height: 26, fontSize: 12.5, fontWeight: on ? 500 : 400, color: on ? color.text : fill.chipText, borderRadius: radius2.keycap }}
            onClick={() => onChange(o.value)}
          >
            {on && <motion.span layoutId={`seg4-${group}`} className="absolute inset-0" style={{ background: fill.segmentOn, borderRadius: radius2.keycap, boxShadow: `${highlight.top}, ${elevation.raised}` }} transition={spring} />}
            <span className="relative">{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}

/** A v4 section head: 15 px, a hairline under it. */
export function SectionHead({ children }: { children: ReactNode }): ReactNode {
  return (
    <h3 className="m-0 font-semibold" style={{ fontSize: 15, color: color.text, paddingBottom: 10, marginTop: 34, boxShadow: `inset 0 -1px 0 ${fill.hairline}` }}>
      {children}
    </h3>
  )
}

export function PageHeader({ title, caption, right, lead }: { title: string; caption?: ReactNode; right?: ReactNode; lead?: ReactNode }): ReactNode {
  const inline = useContext(InlineSettings)
  if (inline) return right ? <header className="flex items-center justify-end gap-[12px]">{right}</header> : null
  return (
    <header className="flex items-end gap-[16px]">
      {lead}
      <div className="flex min-w-0 flex-1 flex-col gap-[4px]">
        <h1 className="m-0 font-semibold" style={{ fontSize: 22, letterSpacing: -0.2, color: color.text }}>
          {title}
        </h1>
        {caption && (
          <p className="m-0" style={{ fontSize: type2.sm, color: color.label }}>
            {caption}
          </p>
        )}
      </div>
      {right}
    </header>
  )
}

/** A rounded block of rows; a hairline between rows, indented past the icon tile when the rows have one. */
export function Group({ label, children, inset = 16, title, caption }: { label: string; children: ReactNode; inset?: number; title?: string; caption?: string }): ReactNode {
  const rows = (Array.isArray(children) ? children : [children]).flat().filter(Boolean)
  const flat = useContext(Flat)
  if (flat)
    return (
      <section aria-label={label} data-flat-group>
        <SectionHead>{title ?? label}</SectionHead>
        {caption && (
          <p className="m-0 pt-[8px]" style={{ fontSize: type2.sm, color: color.label }}>
            {caption}
          </p>
        )}
        {rows.map((r, i) => (
          <div key={i} style={{ boxShadow: `inset 0 -1px 0 ${fill.hairline}` }}>
            {r}
          </div>
        ))}
      </section>
    )
  return (
    <section aria-label={label} style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }}>
      {title && (
        <div className="flex flex-col gap-[2px] px-[16px] pb-[4px] pt-[16px]">
          <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
            {title}
          </span>
          {caption && <span style={{ fontSize: type2.sm, color: color.label }}>{caption}</span>}
        </div>
      )}
      {rows.map((r, i) => (
        <Fragment key={i}>
          {i > 0 && <div className="h-px" style={{ marginLeft: inset, background: fill.hairline }} />}
          {r}
        </Fragment>
      ))}
    </section>
  )
}

export function Row({
  icon: I,
  label,
  caption,
  right,
  minH,
  tight,
  mono
}: {
  icon?: LucideIcon
  label: ReactNode
  caption?: ReactNode
  right?: ReactNode
  minH?: number
  /** A control with its own 56x44 hit target (Toggle) sits closer to the edge. */
  tight?: boolean
  /** The caption is a file name or version. */
  mono?: boolean
}): ReactNode {
  // Density (Settings > Appearance): compact rows are shorter and tighter, in every section and in the Settings page.
  const compact = useLocal((s) => s.density) === 'compact'
  const flat = useContext(Flat)
  if (flat)
    return (
      <div className="flex items-center gap-[24px]" style={{ minHeight: minH ?? (compact ? 48 : 58), padding: compact ? '6px 0' : '9px 0' }}>
        <div className="flex min-w-0 flex-1 flex-col gap-[1px]">
          <span style={{ fontSize: type2.md, fontWeight: 520, color: color.text }}>{label}</span>
          {caption && <span style={{ fontSize: type2.sm, color: color.label, fontFamily: mono ? 'var(--font-mono)' : undefined, maxWidth: 330 }}>{caption}</span>}
        </div>
        {right}
      </div>
    )
  return (
    <div className="flex items-center gap-[16px]" style={{ minHeight: minH ?? ROW_HEIGHT[compact ? 'compact' : 'comfortable'], padding: tight ? '0 8px 0 16px' : '0 16px' }}>
      {I && (
        <span aria-hidden className="grid h-[32px] w-[32px] shrink-0 place-items-center" style={{ borderRadius: radius2.control, background: fill.segmentTrack, color: color.text }}>
          <I size={16} strokeWidth={1.5} />
        </span>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-[2px]" style={{ paddingBlock: compact ? 6 : 10 }}>
        {/* 14 / 13 (Michael's audit: "text is very small on settings"; it was 13 / 12). */}
        <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
          {label}
        </span>
        {caption && (
          <span style={{ fontSize: type2.sm, color: color.label, fontFamily: mono ? 'var(--font-mono)' : undefined }}>{caption}</span>
        )}
      </div>
      {right}
    </div>
  )
}

/** An outline badge ("On this Mac", "Lessons only"). */
export function Badge({ children }: { children: ReactNode }): ReactNode {
  return (
    <span
      className="flex h-[24px] shrink-0 items-center whitespace-nowrap px-[8px] font-medium"
      style={{ borderRadius: radius2.keycap, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, fontSize: type2.micro, color: fill.chipText }}
    >
      {children}
    </span>
  )
}

/** A value on the right of a row ("Lessons only", "On this Mac"): plain secondary text, never a pill that looks pressable. */
export function Plain({ children }: { children: ReactNode }): ReactNode {
  return (
    <span className="shrink-0 whitespace-nowrap" style={{ fontSize: type2.xs, color: color.label }}>
      {children}
    </span>
  )
}

/** A quiet line under a group ("Turn on opens System Settings at the right switch."). */
export function Note({ children, icon: I = Info }: { children: ReactNode; icon?: LucideIcon }): ReactNode {
  return (
    <div className="flex items-start gap-[8px] px-[4px]" style={{ fontSize: type2.xs, color: color.label }}>
      <I size={14} strokeWidth={1.5} className="mt-[1px] shrink-0" aria-hidden />
      <p className="m-0">{children}</p>
    </div>
  )
}

/** Granted / ready: a white tick and the word. Never green (green only means passed). */
export function OnWord({ children = 'On' }: { children?: ReactNode }): ReactNode {
  return (
    <span className="flex shrink-0 items-center gap-[8px] whitespace-nowrap font-medium" style={{ fontSize: type2.xs, color: color.text }}>
      <Check size={14} strokeWidth={1.6} aria-hidden />
      {children}
    </span>
  )
}

/** A text-only button (Restore defaults, Cancel, Where do I find my key?). */
export function TextButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }): ReactNode {
  return (
    <button
      type="button"
      disabled={disabled}
      className="h-[32px] shrink-0 cursor-pointer whitespace-nowrap px-[12px] font-medium hover:underline disabled:cursor-default disabled:opacity-40"
      style={{ borderRadius: radius2.control, fontSize: type2.xs, color: fill.chipText }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

/** Small numbers as words for captions ("Two of three are on."). */
export function count(n: number): string {
  return ['None', 'One', 'Two', 'Three', 'Four', 'Five'][n] ?? String(n)
}
