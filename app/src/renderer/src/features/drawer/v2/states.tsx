/**
 * Feature: drawer (v2, A1). What changes between the panel's states, besides the primary button (LessonPanel.tsx):
 *   NotYetBox       Les-NotYet: a hollow white ring and "Not yet" (no hue, no shake), the finding, a muted detail.
 *                   The ring fades in from 0.85 once (UI-POLISH-SPEC 7).
 *   HintBox         Les-Hint: the pink "Hint" chip (an option's pastel: the learner asked for it), "1 of 2", its ✕, and
 *                   while there is a next rung, a quiet "Another hint" with the Hint keycap. A new hint rises in.
 *   PassedBody      Les-Passed: the green circle springs up from 0.6 and its tick draws in after it (the only green),
 *                   core copy.passed (today "Step done."; CLAUDE.md says "Good. Now the next one.", Core request 9),
 *                   what the learner did, Up next.
 *   CheckingCaption Les-Checking: what the engine is looking at right now (status.detail), in plain words, with the
 *                   calm thinking dots.
 */
import type { ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import { actionTone, color, copy, highlight, radius2, status, surface, type2 } from '../../../core/theme'
import { Spinner } from '../../../core/ui/atoms'
import { Keycap } from '../../../core/ui/Keycap'
import { beat, draw, pop, pressMotion, rise } from '../../../core/ui/motion'
import { ThinkingDots } from '../../../core/ui/Thinking'
import { Caption, Inline, Tip, tone } from './ui'

export function NotYetBox({ lines }: { lines: string[] }): ReactNode {
  const [first, ...rest] = lines
  const reduced = useReducedMotion()
  return (
    <div style={{ padding: '16px 20px 0' }}>
      <div
        role="status"
        data-part="panel-notyet"
        className="flex flex-col gap-[4px]"
        style={{ boxShadow: `inset 0 0 0 1px ${surface.border}`, borderRadius: radius2.card, padding: '12px 16px' }}
      >
        <div className="flex items-center gap-[8px]">
          <motion.span
            aria-hidden
            className="block h-[12px] w-[12px] shrink-0 rounded-full"
            style={{ border: `2px solid ${status.notYet}` }}
            {...pop(reduced, 0.85)}
          />
          <span style={{ fontSize: type2.md, fontWeight: 600, color: tone.text }}>Not yet</span>
        </div>
        {first && (
          <p className="m-0 break-words [text-wrap:pretty]" style={{ paddingLeft: 20, fontSize: type2.sm, lineHeight: '20px', color: tone.text }}>
            <Inline text={first} />
          </p>
        )}
        {rest.map((t, i) => (
          <p key={i} className="m-0 break-words [text-wrap:pretty]" style={{ paddingLeft: 20, fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
            <Inline text={t} />
          </p>
        ))}
      </div>
    </div>
  )
}

export function HintBox({
  lines,
  n,
  of,
  onClose,
  onMore,
  moreBusy
}: {
  lines: string[]
  n?: number
  of?: number
  onClose: () => void
  /** Ask for the next rung (Hint again). Shown only while n < of. */
  onMore?: () => void
  moreBusy?: boolean
}): ReactNode {
  const [first, ...rest] = lines
  const reduced = useReducedMotion()
  const r = rise(reduced)
  const more = !!onMore && !!n && !!of && n < of
  return (
    <div style={{ padding: '16px 20px 0' }}>
      <section
        aria-label="Hint"
        data-part="panel-hint"
        className="flex flex-col gap-[8px]"
        style={{ background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.topSoft}`, borderRadius: radius2.card, padding: '12px 12px 12px 16px' }}
      >
        <div className="flex items-center gap-[8px]">
          <span className="inline-flex h-[20px] items-center" style={{ padding: '0 8px', borderRadius: radius2.round, background: actionTone.hint, color: color.onPastel, fontSize: type2.micro, fontWeight: 600 }}>
            Hint
          </span>
          {n && of && of > 1 ? (
            <span data-part="panel-hint-count" style={{ fontSize: type2.xs, color: tone.label }}>
              {n} of {of}
            </span>
          ) : null}
          <span className="flex-1" />
          <Tip label="Close hint" k="dismiss">
            <motion.button
              type="button"
              aria-label="Close hint"
              className="mg-press grid h-[28px] w-[28px] cursor-pointer place-items-center"
              style={{ borderRadius: radius2.control, color: tone.label }}
              {...pressMotion()}
              onMouseDown={(e) => e.preventDefault()}
              onClick={onClose}
            >
              <X size={12} strokeWidth={1.8} aria-hidden />
            </motion.button>
          </Tip>
        </div>
        {/* A new rung replaces the old one in place: it rises in, keyed on its number. */}
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div key={n ?? 0} className="flex flex-col gap-[8px]" style={{ paddingRight: 4 }} initial={r.initial} animate={r.animate} exit={r.exit} transition={r.transition}>
            {first && (
              <p className="m-0 break-words [text-wrap:pretty]" style={{ fontSize: type2.body, lineHeight: '22px', color: tone.text }}>
                <Inline text={first} />
              </p>
            )}
            {rest.map((t, i) => (
              <p key={i} className="m-0 break-words [text-wrap:pretty]" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
                <Inline text={t} />
              </p>
            ))}
          </motion.div>
        </AnimatePresence>
        {more && (
          <div className="flex">
            <motion.button
              type="button"
              data-part="panel-hint-more"
              aria-busy={moreBusy || undefined}
              className="mg-press -ml-[8px] flex h-[28px] cursor-pointer items-center gap-[8px] px-[8px]"
              style={{ borderRadius: radius2.control, color: tone.text, fontSize: type2.sm, fontWeight: 500 }}
              {...pressMotion(moreBusy)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={onMore}
            >
              <span>Another hint</span>
              {moreBusy ? <Spinner size={12} c={tone.text} /> : <Keycap k="hint" size="sm" />}
            </motion.button>
          </div>
        )}
      </section>
    </div>
  )
}

/**
 * The passed circle (UI-POLISH-SPEC 7): green springs up from 0.6 (never from 0), the ink tick draws in a beat after
 * it, over 240 ms (core/ui/motion pop and draw). Reduced motion: both fade in.
 */
export function PassedCheck({ size = 48 }: { size?: number }): ReactNode {
  const reduced = useReducedMotion()
  return (
    <motion.svg
      data-status-glyph="passed"
      width={size}
      height={size}
      viewBox="0 0 18 18"
      className="shrink-0"
      {...pop(reduced)}
      aria-hidden
    >
      <circle cx="9" cy="9" r="9" fill={status.passed} />
      <motion.path
        d="M5.2 9.3 L7.8 11.8 L12.9 6.4"
        fill="none"
        stroke={color.onGreen}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        {...draw(reduced)}
      />
    </motion.svg>
  )
}

export function PassedBody({ summary, upNext, total }: { summary?: string; upNext?: { index: number; title: string; what?: string }; total: number }): ReactNode {
  const reduced = useReducedMotion()
  // The circle, then the words a beat after its tick starts, then Up next a beat after that.
  const words = rise(reduced, { delay: 2 * beat })
  const next = rise(reduced, { delay: 3 * beat })
  return (
    <>
      <div role="status" data-part="panel-passed" className="flex flex-col items-center gap-[16px] text-center" style={{ padding: '32px 20px 0' }}>
        <PassedCheck size={48} />
        <motion.div className="flex flex-col gap-[8px]" initial={words.initial} animate={words.animate} transition={words.transition}>
          <h2 className="m-0" style={{ fontSize: type2.xl, lineHeight: '24px', fontWeight: 600, letterSpacing: '-0.01em', color: tone.text }}>
            {copy.passed}
          </h2>
          {summary && (
            <p className="m-0 break-words [text-wrap:pretty]" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
              <Inline text={summary} codeColor={tone.text} />
            </p>
          )}
        </motion.div>
      </div>
      {upNext && (
        <motion.div style={{ padding: '24px 20px 0' }} initial={next.initial} animate={next.animate} transition={next.transition}>
          <div
            data-part="panel-upnext"
            className="flex flex-col gap-[4px]"
            style={{ background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.topSoft}`, borderRadius: radius2.card, padding: '12px 16px' }}
          >
            <Caption>
              Up next, step {upNext.index + 1} of {total}
            </Caption>
            <span className="break-words" style={{ fontSize: type2.body, fontWeight: 600, color: tone.text }}>
              {upNext.title}
            </span>
            {upNext.what && upNext.what !== upNext.title && (
              <span className="break-words [text-wrap:pretty]" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.body }}>
                <Inline text={upNext.what} />
              </span>
            )}
          </div>
        </motion.div>
      )}
    </>
  )
}

/**
 * The engine's status.detail in a first-timer's words: "Reading `x` in your kernel" becomes "Looking at `x`" (persona
 * QA: kernel is jargon). Anything else passes through.
 */
export function plainDetail(text: string | undefined): string | undefined {
  const t = text?.trim()
  if (!t) return undefined
  return t
    .replace(/^Reading\s+(.+?)\s+in your kernel\.?$/i, 'Looking at $1')
    .replace(/\s+in your kernel\b/i, '')
    .replace(/\bthe engine\b/gi, 'miyagi')
}

export function CheckingCaption({ text }: { text?: string }): ReactNode {
  return (
    <span role="status" data-part="panel-checking" className="flex items-center justify-center gap-[6px] text-center" style={{ fontSize: type2.xs, lineHeight: '16px', color: tone.label }}>
      <span className="min-w-0 truncate">
        <Inline text={plainDetail(text) || 'Running the checks for this step'} />
      </span>
      <span className="shrink-0">
        <ThinkingDots size={3} gap={2} label={null} />
      </span>
    </span>
  )
}
