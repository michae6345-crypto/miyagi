/**
 * Feature: drawer (v2, A1). What changes between the panel's states, besides the primary button (LessonPanel.tsx):
 *   NotYetBox       Les-NotYet: a hollow white ring and "Not yet" (no hue, no shake), the finding, a muted detail.
 *   HintBox         Les-Hint: the pink "Hint" chip (an option's pastel: the learner asked for it), "1 of 2", its ✕.
 *   PassedBody      Les-Passed: the green circle (the only green), the passed line, what the learner did, Up next.
 *   CheckingCaption Les-Checking: what the engine is reading right now (status.detail).
 */
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { actionTone, color, copy, fill, radius2, status, surface, type2 } from '../../../core/theme'
import { StatusGlyph } from '../../../core/ui/status'
import { Caption, Inline, tone } from './ui'

export function NotYetBox({ lines }: { lines: string[] }): ReactNode {
  const [first, ...rest] = lines
  return (
    <div style={{ padding: '16px 20px 0' }}>
      <div
        role="status"
        data-part="panel-notyet"
        className="flex flex-col gap-[4px]"
        style={{ boxShadow: `inset 0 0 0 1px ${surface.border}`, borderRadius: radius2.card, padding: '12px 16px' }}
      >
        <div className="flex items-center gap-[8px]">
          <span aria-hidden className="block h-[12px] w-[12px] shrink-0 rounded-full" style={{ border: `2px solid ${status.notYet}` }} />
          <span style={{ fontSize: type2.md, fontWeight: 600, color: tone.text }}>Not yet</span>
        </div>
        {first && (
          <p className="m-0 break-words" style={{ paddingLeft: 20, fontSize: type2.sm, lineHeight: '20px', color: tone.text }}>
            <Inline text={first} />
          </p>
        )}
        {rest.map((t, i) => (
          <p key={i} className="m-0 break-words" style={{ paddingLeft: 20, fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
            <Inline text={t} />
          </p>
        ))}
      </div>
    </div>
  )
}

export function HintBox({ lines, n, of, onClose }: { lines: string[]; n?: number; of?: number; onClose: () => void }): ReactNode {
  const [first, ...rest] = lines
  return (
    <div style={{ padding: '16px 20px 0' }}>
      <section
        aria-label="Hint"
        data-part="panel-hint"
        className="flex flex-col gap-[8px]"
        style={{ background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, borderRadius: radius2.card, padding: '12px 16px 16px' }}
      >
        <div className="flex items-center gap-[8px]">
          <span className="inline-flex h-[20px] items-center" style={{ padding: '0 8px', borderRadius: radius2.round, background: actionTone.hint, color: color.onAccent, fontSize: type2.micro, fontWeight: 600 }}>
            Hint
          </span>
          {n && of && of > 1 ? (
            <span style={{ fontSize: type2.xs, color: tone.label }}>
              {n} of {of}
            </span>
          ) : null}
          <span className="flex-1" />
          <button
            type="button"
            aria-label="Close hint"
            className="grid h-[28px] w-[28px] cursor-pointer place-items-center hover:bg-[var(--panel-hover)]"
            style={{ borderRadius: radius2.control, color: tone.label, ['--panel-hover' as string]: fill.chipHover }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={onClose}
          >
            <X size={12} strokeWidth={1.8} aria-hidden />
          </button>
        </div>
        {first && (
          <p className="m-0 break-words" style={{ fontSize: type2.body, lineHeight: '22px', color: tone.text }}>
            <Inline text={first} />
          </p>
        )}
        {rest.map((t, i) => (
          <p key={i} className="m-0 break-words" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
            <Inline text={t} />
          </p>
        ))}
      </section>
    </div>
  )
}

export function PassedBody({ summary, upNext, total }: { summary?: string; upNext?: { index: number; title: string; what?: string }; total: number }): ReactNode {
  return (
    <>
      <div role="status" data-part="panel-passed" className="flex flex-col items-center gap-[16px] text-center" style={{ padding: '32px 20px 0' }}>
        <StatusGlyph state="passed" size={48} />
        <div className="flex flex-col gap-[8px]">
          <h2 className="m-0" style={{ fontSize: type2.xl, lineHeight: '24px', fontWeight: 600, letterSpacing: '-0.01em', color: tone.text }}>
            {copy.passed}
          </h2>
          {summary && (
            <p className="m-0 break-words" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.label }}>
              <Inline text={summary} codeColor={tone.text} />
            </p>
          )}
        </div>
      </div>
      {upNext && (
        <div style={{ padding: '24px 20px 0' }}>
          <div
            data-part="panel-upnext"
            className="flex flex-col gap-[4px]"
            style={{ background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, borderRadius: radius2.card, padding: '12px 16px' }}
          >
            <Caption>
              Up next, step {upNext.index + 1} of {total}
            </Caption>
            <span className="break-words" style={{ fontSize: type2.body, fontWeight: 600, color: tone.text }}>
              {upNext.title}
            </span>
            {upNext.what && upNext.what !== upNext.title && (
              <span className="break-words" style={{ fontSize: type2.sm, lineHeight: '20px', color: tone.body }}>
                <Inline text={upNext.what} />
              </span>
            )}
          </div>
        </div>
      )}
    </>
  )
}

export function CheckingCaption({ text }: { text?: string }): ReactNode {
  return (
    <span role="status" data-part="panel-checking" className="block text-center" style={{ fontSize: type2.xs, lineHeight: '16px', color: tone.label }}>
      <Inline text={text || 'Running the checks for this step'} />
    </span>
  )
}
