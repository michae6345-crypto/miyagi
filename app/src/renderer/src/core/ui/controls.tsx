/**
 * Core (v2, W0-3): form controls for Settings, Onboarding and the app windows (Set-General, Set-Account, Set-Shortcuts).
 * Neutral only: chrome never gets a pastel, and On is white (never green: green means passed).
 *
 *   <Segmented options={[{value:'system',label:'System'},...]} value={v} onChange={setV} />
 *   <Toggle on={v} onChange={setV} label="Open at login" />
 *   <Field label="Anthropic key" secret value={v} onChange={setV} />   secret: password field, no autofill, no spellcheck
 *   <SidebarNav items={[{id:'general',label:'General',icon:Settings}]} active="general" onSelect={go} />
 */
import { motion } from 'motion/react'
import { useId, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { color, fill, paper, radius2, spring, type2 } from '../theme'

export type ControlSurface = 'dark' | 'paper'

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  surface = 'dark'
}: {
  options: ReadonlyArray<{ value: T; label: string }>
  value: T
  onChange: (v: T) => void
  label?: string
  surface?: ControlSurface
}): ReactNode {
  const onPaper = surface === 'paper'
  const group = useId()
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex shrink-0 items-center p-[2px]"
      style={{ background: onPaper ? paper.group : fill.segmentTrack, borderRadius: radius2.control, border: `1px solid ${onPaper ? paper.border : fill.hairline}` }}
    >
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            className="relative cursor-pointer whitespace-nowrap px-[16px]"
            style={{ height: 32, fontSize: type2.xs, fontWeight: on ? 500 : 400, color: onPaper ? paper.ink : on ? color.text : fill.chipText, borderRadius: radius2.keycap }}
            onClick={() => onChange(o.value)}
          >
            {on && (
              <motion.span
                layoutId={`seg-${group}`}
                className="absolute inset-0"
                style={{ background: onPaper ? paper.surface : fill.segmentOn, borderRadius: radius2.keycap, boxShadow: onPaper ? paper.shadowSmall : undefined }}
                transition={spring}
              />
            )}
            <span className="relative">{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export function Toggle({ on, onChange, label, disabled, surface = 'dark' }: { on: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean; surface?: ControlSurface }): ReactNode {
  const onPaper = surface === 'paper'
  const track = on ? (onPaper ? paper.ink : color.accent) : onPaper ? paper.border : fill.toggleOff
  const knob = on ? (onPaper ? paper.surface : color.onAccent) : onPaper ? paper.surface : color.text
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      className="grid shrink-0 cursor-pointer place-items-center disabled:cursor-default"
      style={{ width: 56, height: 44, opacity: disabled ? 0.4 : 1 }}
      onClick={() => onChange(!on)}
    >
      {/* Set-General: a 40x24 track with a 20 px knob (ink on white when on) inside a 56x44 hit target. */}
      <span className="relative block" style={{ width: 40, height: 24, borderRadius: radius2.round, background: track, transition: 'background 150ms ease-out' }}>
        <motion.span className="absolute top-[2px] block" style={{ width: 20, height: 20, borderRadius: radius2.round, background: knob }} initial={false} animate={{ left: on ? 18 : 2 }} transition={spring} />
      </span>
    </button>
  )
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  secret,
  hint,
  surface = 'dark',
  disabled,
  onEnter
}: {
  label?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  /** A key or token: type=password, autocomplete off, spellcheck off (Section 6). */
  secret?: boolean
  hint?: ReactNode
  surface?: ControlSurface
  disabled?: boolean
  onEnter?: () => void
}): ReactNode {
  const id = useId()
  const onPaper = surface === 'paper'
  return (
    <div className="flex flex-col gap-[6px]">
      {label && (
        <label htmlFor={id} className="font-medium" style={{ fontSize: type2.xs, color: onPaper ? paper.muted : color.label }}>
          {label}
        </label>
      )}
      <input
        id={id}
        type={secret ? 'password' : 'text'}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        disabled={disabled}
        value={value}
        placeholder={placeholder}
        className="w-full outline-none"
        style={{
          height: 34,
          padding: '0 12px',
          fontSize: type2.sm,
          borderRadius: radius2.control,
          background: onPaper ? paper.field : fill.field,
          color: onPaper ? paper.ink : color.text,
          boxShadow: `inset 0 0 0 1px ${onPaper ? paper.border : fill.fieldBorder}`
        }}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onEnter?.()}
      />
      {hint && <div style={{ fontSize: type2.xs, color: onPaper ? paper.faint : color.faint }}>{hint}</div>}
    </div>
  )
}

export type NavItem = { id: string; label: string; icon?: LucideIcon; disabled?: boolean }

export function SidebarNav({ items, active, onSelect, title }: { items: ReadonlyArray<NavItem>; active: string; onSelect: (id: string) => void; title?: string }): ReactNode {
  return (
    <nav aria-label={title} className="flex flex-col gap-[2px]">
      {items.map(({ id, label, icon: I, disabled }) => {
        const on = id === active
        return (
          <button
            key={id}
            type="button"
            data-nav={id}
            aria-current={on ? 'page' : undefined}
            disabled={disabled}
            className="flex cursor-pointer items-center gap-[9px] text-left font-medium disabled:cursor-default"
            style={{
              height: 30,
              padding: '0 10px',
              borderRadius: radius2.control,
              fontSize: type2.sm,
              background: on ? fill.navActive : 'transparent',
              color: on ? color.text : color.label,
              opacity: disabled ? 0.4 : 1
            }}
            onClick={() => onSelect(id)}
          >
            {I && <I size={15} strokeWidth={1.8} className="shrink-0" />}
            <span className="truncate">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}
