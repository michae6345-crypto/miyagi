/**
 * Feature: drawer (v2, A1). The step itself (Les-Anatomy "Short instruction", "Fresh code to type", "Points at real
 * UI"): its title and one-line instruction, the code to type in full (never truncated: long lines scroll sideways),
 * and the line under it that points at the real control ("Then run it with the arrow beside the cell.").
 *
 * `where` / `then` come from step.started (v2). Without `where` a code step says "Type this", a run step "Run this".
 */
import type { ReactNode } from 'react'
import { Play } from 'lucide-react'
import type { MissingLine, StepKind } from '../../../../../../../shared/contracts/events'
import { font, highlight, radius2, surface, type2 } from '../../../core/theme'
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

/** The code box: a hairline, radius 12, mono 13/20. Polish: a well, darker than the panel and shaded from the top edge, so it reads pressed IN while the buttons stand out. */
function Box({ children, padLeft = 16 }: { children: ReactNode; padLeft?: number }): ReactNode {
  return (
    <div
      data-part="panel-code"
      className="overflow-x-auto"
      style={{ background: surface.well, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.well}`, borderRadius: radius2.card, padding: `12px 16px 12px ${padLeft}px`, scrollbarWidth: 'thin' }}
    >
      {children}
    </div>
  )
}

const lineStyle = { fontFamily: font.mono, fontSize: type2.sm, lineHeight: '20px', whiteSpace: 'pre' as const, margin: 0 }

export function CodeBlock({ code, where, kind, then }: { code?: string; where?: string; kind?: StepKind; then?: string }): ReactNode {
  const label = where ?? (kind ? DEFAULT_WHERE[kind] : undefined)
  if (!code && !then) return null
  return (
    <div className="flex flex-col gap-[8px]" style={{ padding: '16px 20px 0' }}>
      {code && label && <Caption>{label}</Caption>}
      {code && (
        <Box>
          {code.split('\n').map((ln, i) => (
            <p key={i} style={{ ...lineStyle, color: tone.text }}>
              {ln || ' '}
            </p>
          ))}
        </Box>
      )}
      {then && <ThenLine text={then} />}
    </div>
  )
}

/** "Then run it with the arrow beside the cell.": the play mark, then the line (points at the real UI). */
export function ThenLine({ text }: { text: string }): ReactNode {
  return (
    <div data-part="panel-then" className="flex items-center gap-[8px]" style={{ fontSize: type2.sm, lineHeight: '18px', color: tone.body }}>
      <Play size={12} strokeWidth={1.8} className="shrink-0" style={{ color: tone.text }} aria-hidden />
      <span className="min-w-0 break-words">
        <Inline text={text} />
      </span>
    </div>
  )
}

/**
 * Les-NotYet: the step's lines in order, the missing ones marked (a white bar at the left and "missing"), the ones
 * already there muted. Under the fix caption ("Add the first line, then run the cell").
 */
export function MissingBlock({ lines, caption }: { lines: MissingLine[]; caption?: string }): ReactNode {
  const missing = lines.filter((l) => l.state === 'missing').length
  return (
    <div className="flex flex-col gap-[8px]" style={{ padding: '16px 20px 0' }}>
      <Caption>{caption ?? (missing === 1 ? 'Add the missing line' : 'Add the missing lines')}</Caption>
      <Box padLeft={14}>
        {lines.map((l, i) =>
          l.state === 'missing' ? (
            <div key={i} data-line="missing" className="flex items-center gap-[8px]" style={{ borderLeft: `2px solid ${tone.text}`, paddingLeft: 8, marginLeft: -2 }}>
              <p className="flex-1" style={{ ...lineStyle, color: tone.text }}>
                {l.text || ' '}
              </p>
              <span className="shrink-0" style={{ fontSize: type2.micro, color: tone.label }}>
                missing
              </span>
            </div>
          ) : (
            <p key={i} data-line="ok" style={{ ...lineStyle, color: tone.label, paddingLeft: 10 }}>
              {l.text || ' '}
            </p>
          )
        )}
      </Box>
    </div>
  )
}
