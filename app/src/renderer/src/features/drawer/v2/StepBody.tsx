/**
 * Feature: drawer (v2, A1). The step itself (Les-Anatomy "Short instruction", "Fresh code to type", "Points at real
 * UI"): its title and one-line instruction, the code to type in full, and the line under it that points at the real
 * control ("Then run it with the arrow beside the cell.").
 *
 * The code is never clipped (persona QA, blocker): long lines soft-wrap with a hanging indent, so a continuation sits
 * two columns in from the line's own indent and reads as the same line. The box is keyboard-focusable (it is
 * something to read) and has a Copy chip. A code step whose code hasn't arrived yet shows a quiet skeleton of the box,
 * never an empty gap. `where` / `then` come from step.started (v2). Without `where` a code step says "Type this", a run
 * step "Run this".
 */
import { Fragment, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Check, Copy, Play } from 'lucide-react'
import type { MissingLine, StepKind } from '../../../../../../../shared/contracts/events'
import { fill, font, radius2, surface, type2 } from '../../../core/theme'
import { copyText } from '../plan'
import { Caption, Inline, tone } from './ui'

export function StepIntro({ title, instructions }: { title: string; instructions: string }): ReactNode {
  return (
    <div data-part="panel-step" className="flex flex-col gap-[8px]" style={{ padding: '20px 20px 0' }}>
      <h2 className="m-0 break-words" style={{ fontSize: type2.xl, lineHeight: '24px', fontWeight: 600, letterSpacing: '-0.01em', color: tone.text }}>
        {title}
      </h2>
      {instructions && (
        <p className="m-0 break-words" style={{ fontSize: type2.md, lineHeight: '20px', color: tone.body }}>
          <Inline text={instructions} />
        </p>
      )}
    </div>
  )
}

const DEFAULT_WHERE: Partial<Record<StepKind, string>> = { code: 'Type this', run: 'Run this' }

/** The code box: rgba white .06 on the panel, a hairline, radius 12, mono 13/20. Focusable: it is read, not clicked. */
function Box({ children, label, padLeft = 16, padRight = 16 }: { children: ReactNode; label: string; padLeft?: number; padRight?: number }): ReactNode {
  return (
    <div
      data-part="panel-code"
      role="group"
      tabIndex={0}
      aria-label={label}
      className="relative outline-none focus-visible:[box-shadow:inset_0_0_0_1px_var(--code-border),0_0_0_2px_var(--code-focus)]"
      style={{
        background: surface.row,
        boxShadow: `inset 0 0 0 1px ${surface.border}`,
        borderRadius: radius2.card,
        padding: `12px ${padRight}px 12px ${padLeft}px`,
        ['--code-border' as string]: surface.border,
        ['--code-focus' as string]: tone.text
      }}
    >
      {children}
    </div>
  )
}

/** Mono 13/20, soft-wrapped; a token too long for a row breaks only as a last resort. */
const lineStyle: CSSProperties = { fontFamily: font.mono, fontSize: type2.sm, lineHeight: '20px', whiteSpace: 'pre-wrap', overflowWrap: 'break-word', margin: 0 }

/** Where code may wrap besides spaces: after an opening bracket, a comma, a dot or an operator (never mid-name). */
const BREAK_AFTER = /([([{,.=+\-*/:])/

/**
 * One line of code with a hanging indent: the line's own indent becomes padding (so a row never breaks inside it),
 * the first row starts there and a wrapped row starts two columns further in. `ch` is the mono font's column.
 */
export function CodeLine({ text, style }: { text: string; style?: CSSProperties }): ReactNode {
  const lead = text.match(/^[ \t]*/)?.[0] ?? ''
  const cols = lead.replace(/\t/g, '    ').length
  const body = text.slice(lead.length)
  const parts = body.split(BREAK_AFTER)
  return (
    <p style={{ ...lineStyle, paddingLeft: `${cols + 2}ch`, textIndent: '-2ch', ...style }} data-code-line>
      {body
        ? parts.map((p, i) =>
            i % 2 ? (
              <Fragment key={i}>
                {p}
                <wbr />
              </Fragment>
            ) : (
              p
            )
          )
        : ' '}
    </p>
  )
}

/**
 * The Copy chip on the code box: neutral chrome (never a pastel, never the primary), then "Copied" or "Could not copy"
 * for a moment. It copies through copyText (main's drawer:copy IPC, execCommand as the last try): the overlay is
 * focusable:false and Chromium refuses navigator.clipboard in an unfocused document, so writeText alone fails silently.
 */
function CopyChip({ text }: { text: string }): ReactNode {
  const [result, setResult] = useState<'idle' | 'yes' | 'no'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  const copy = async (): Promise<void> => {
    let ok = false
    try {
      ok = await copyText(text)
    } catch {
      ok = false
    }
    setResult(ok ? 'yes' : 'no')
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setResult('idle'), ok ? 1600 : 2400)
  }
  const label = result === 'yes' ? 'Copied' : result === 'no' ? 'Could not copy' : 'Copy'
  return (
    <motion.button
      type="button"
      data-part="panel-code-copy"
      data-copy={result}
      aria-label={result === 'idle' ? 'Copy the code' : label}
      aria-live="polite"
      className="absolute right-[6px] top-[6px] flex h-[24px] cursor-pointer items-center gap-[4px] whitespace-nowrap px-[8px]"
      // "Could not copy" is wider than CHIP_ROOM: for its 2.4 s it sits on an opaque sheet so the code never shows through.
      style={{ borderRadius: radius2.control, background: result === 'no' ? surface.sheet : fill.button, color: result === 'idle' ? tone.label : tone.text, fontSize: type2.micro, fontWeight: 500 }}
      whileHover={{ backgroundColor: fill.chipHover, color: tone.text }}
      whileTap={{ scale: 0.95 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => void copy()}
    >
      {result === 'yes' ? <Check size={11} strokeWidth={2} aria-hidden /> : result === 'idle' ? <Copy size={11} strokeWidth={1.8} aria-hidden /> : null}
      <span>{label}</span>
    </motion.button>
  )
}

/** Room on the right of the first row for the Copy chip, sized for "Copied" (so it never sits on the code). */
const CHIP_ROOM = 80

export function CodeBlock({ code, where, kind, then, waiting }: { code?: string; where?: string; kind?: StepKind; then?: string; waiting?: boolean }): ReactNode {
  const label = where ?? (kind ? DEFAULT_WHERE[kind] : undefined)
  const reduced = useReducedMotion()
  const skeleton = !code && waiting && kind === 'code'
  if (!code && !then && !skeleton) return null
  const lines = code ? code.split('\n') : []
  return (
    <div className="flex flex-col gap-[8px]" style={{ padding: '16px 20px 0' }}>
      {(code || skeleton) && label && <Caption>{label}</Caption>}
      <AnimatePresence initial={false} mode="popLayout">
        {code ? (
          <motion.div key="code" initial={reduced ? { opacity: 0 } : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}>
            <Box label={label ? `${label}: code` : 'Code'} padRight={lines.length > 1 ? 16 : CHIP_ROOM}>
              <CopyChip text={code} />
              {lines.map((ln, i) => (
                <CodeLine key={i} text={ln} style={{ color: tone.text, paddingRight: i === 0 && lines.length > 1 ? CHIP_ROOM - 16 : undefined }} />
              ))}
            </Box>
          </motion.div>
        ) : skeleton ? (
          <motion.div key="skeleton" exit={{ opacity: 0, transition: { duration: 0.12 } }}>
            <CodeSkeleton />
          </motion.div>
        ) : null}
      </AnimatePresence>
      {then && <ThenLine text={then} />}
    </div>
  )
}

/** A code step whose code is still on its way: the box's shape, three soft bars that breathe (no shimmer, no hue). */
function CodeSkeleton(): ReactNode {
  const reduced = useReducedMotion()
  return (
    <div
      data-part="panel-code-skeleton"
      role="status"
      aria-label="Getting the code for this step"
      className="flex flex-col gap-[8px]"
      style={{ background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, borderRadius: radius2.card, padding: '16px' }}
    >
      {[0.72, 0.9, 0.48].map((w, i) => (
        <motion.span
          key={i}
          className="block h-[12px]"
          style={{ width: `${w * 100}%`, borderRadius: radius2.keycap, background: fill.skeleton }}
          animate={{ opacity: [1, 0.4, 1] }}
          transition={{ duration: reduced ? 2.6 : 2, repeat: Infinity, repeatDelay: 0.5, ease: 'easeInOut' }}
        />
      ))}
    </div>
  )
}

/** "Then run it with the arrow beside the cell.": the play mark, then the line (points at the real UI). */
export function ThenLine({ text }: { text: string }): ReactNode {
  return (
    <div data-part="panel-then" className="flex items-start gap-[8px]" style={{ fontSize: type2.sm, lineHeight: '18px', color: tone.body }}>
      <span className="grid h-[18px] w-[18px] shrink-0 place-items-center" style={{ borderRadius: radius2.keycap, background: fill.key, color: tone.text }} aria-hidden>
        <Play size={10} strokeWidth={2} fill="currentColor" />
      </span>
      <span className="min-w-0 break-words">
        <Inline text={text} />
      </span>
    </div>
  )
}

/**
 * Les-NotYet: the step's lines in order, the missing ones marked (a white bar at the left and "missing"), the ones
 * already there muted. Under the fix caption ("Add the first line, then run the cell"). Wrapped like CodeBlock.
 */
export function MissingBlock({ lines, caption }: { lines: MissingLine[]; caption?: string }): ReactNode {
  const missing = lines.filter((l) => l.state === 'missing').length
  const cap = caption ?? (missing === 1 ? 'Add the missing line' : 'Add the missing lines')
  return (
    <div className="flex flex-col gap-[8px]" style={{ padding: '16px 20px 0' }}>
      <Caption>{cap}</Caption>
      <Box label={cap} padLeft={14}>
        {lines.map((l, i) =>
          l.state === 'missing' ? (
            <div key={i} data-line="missing" className="flex items-start gap-[8px]" style={{ borderLeft: `2px solid ${tone.text}`, paddingLeft: 8, marginLeft: -2 }}>
              <CodeLine text={l.text} style={{ color: tone.text, flex: 1, minWidth: 0 }} />
              <span className="shrink-0" style={{ fontSize: type2.micro, lineHeight: '20px', color: tone.label }}>
                missing
              </span>
            </div>
          ) : (
            <div key={i} data-line="ok" style={{ paddingLeft: 10 }}>
              <CodeLine text={l.text} style={{ color: tone.label }} />
            </div>
          )
        )}
      </Box>
    </div>
  )
}
