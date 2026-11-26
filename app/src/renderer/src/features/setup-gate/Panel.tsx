/**
 * Feature: setup-gate. The calm loading panel while the lesson's environment installs (user test Nov 25).
 *
 *   header   the bonsai (core MiyagiMark, in color, breathing on the core mg-pulse keyframes: opacity only), the
 *            headline ("Installing tensorflow… 2/4") and the time it has taken
 *   rows     one per item: label, its status words (Downloading 41% · 92 of 224 MB / Waiting / Installed / the failure in
 *            plain words), a thin white bar while it downloads, Skip on optional rows
 *   failed   Retry (the one primary), Show details (the installer's last lines), Continue anyway
 *
 * Neutral only: white on the island's black, no hue (green means passed; nothing has passed here).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { MiyagiMark } from '../../core/ui/Mark'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { color, fill, font, radius2, spring, type2 } from '../../core/theme'
import { actions, clock, elapsedS, headline, rowFraction, rowText, subline } from './machine'
import { press, useSetupGate } from './store'
import type { SetupGateItem } from '../../../../../../shared/contracts/events'

export const PANEL_W = 440
const PAD = 24

/** Re-render once a second for the elapsed time. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  return now
}

export function SetupGatePanel(): ReactNode {
  const s = useSetupGate()
  const now = useNow()
  const g = s.gate
  if (!g) return null
  const btns = actions(g)
  const failed = g.phase === 'failed'
  const log = s.logFor ? g.items.find((x) => x.tool === s.logFor)?.log : undefined
  return (
    <div data-setup-gate data-hit style={{ padding: `18px ${PAD}px ${PAD - 4}px` }} aria-live="polite">
      <div className="flex items-center gap-[12px]">
        <span aria-hidden className="shrink-0" style={failed ? undefined : { animation: 'mg-pulse 2.4s ease-in-out infinite both' }}>
          <MiyagiMark size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate" style={{ fontSize: type2.lg, fontWeight: 600, color: color.text }}>
            {headline(g)}
          </div>
          <div style={{ fontSize: type2.xs, color: color.label }}>{subline(g)}</div>
        </div>
        <span className="shrink-0 tabular-nums" style={{ fontSize: type2.xs, color: color.label }} title="Time so far">
          {clock(elapsedS(s, now))}
        </span>
      </div>

      <ul className="mt-[16px] flex flex-col gap-[10px]" aria-label="What's being set up">
        {g.items.map((x) => (
          <Row key={x.tool} x={x} skipping={s.pressed === `skip:${x.tool}`} canSkip={btns.some((b) => b.kind === 'skip' && b.tool === x.tool)} />
        ))}
      </ul>

      {log && (
        <pre
          className="mt-[12px] max-h-[160px] overflow-auto whitespace-pre-wrap"
          style={{ fontFamily: font.mono, fontSize: type2.micro, color: color.label, background: fill.field, borderRadius: radius2.control, padding: 10 }}
        >
          {log}
        </pre>
      )}

      {failed && (
        <div className="mt-[18px] flex items-center justify-end gap-[8px]">
          {btns.some((b) => b.kind === 'details') && (
            <QuietButton label={s.logFor ? 'Hide details' : 'Show details'} onClick={() => press({ kind: 'details' })} />
          )}
          <QuietButton label="Continue anyway" busy={s.pressed === 'continue'} onClick={() => press({ kind: 'continue' })} />
          <PrimaryButton label="Retry" busy={s.pressed === 'retry'} onClick={() => press({ kind: 'retry' })} />
        </div>
      )}
    </div>
  )
}

function Row({ x, canSkip, skipping }: { x: SetupGateItem; canSkip: boolean; skipping: boolean }): ReactNode {
  const frac = rowFraction(x)
  const dim = x.status === 'queued' || x.status === 'skipped'
  return (
    <li className="flex flex-col gap-[6px]">
      <div className="flex items-baseline gap-[10px]">
        <span className="shrink-0" style={{ fontSize: type2.sm, fontWeight: 500, color: dim ? color.label : color.text }}>
          {x.label}
          {x.optional && <span style={{ color: color.faint }}> · optional</span>}
        </span>
        <span className="min-w-0 flex-1 truncate text-right tabular-nums" style={{ fontSize: type2.xs, color: color.label }} title={rowText(x)}>
          {rowText(x)}
        </span>
        {canSkip && <QuietButton label="Skip" busy={skipping} onClick={() => press({ kind: 'skip', tool: x.tool })} />}
      </div>
      {x.status === 'installing' && (
        <div className="h-[3px] overflow-hidden rounded-full" style={{ background: fill.track }} role="progressbar" aria-label={`${x.label} progress`}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={frac === undefined ? undefined : Math.round(frac * 100)}>
          {frac === undefined ? (
            // No size known yet (resolving, unpacking): a calm pulse, never a fake number.
            <div className="mg-skeleton h-full w-full rounded-full" style={{ background: color.label }} />
          ) : (
            <motion.div className="h-full w-full rounded-full" style={{ background: color.text, transformOrigin: '0% 50%' }} initial={false} animate={{ scaleX: frac }} transition={spring} />
          )}
        </div>
      )}
      {x.status === 'failed' && x.error && <span style={{ fontSize: type2.xs, color: color.label }}>{x.error}</span>}
    </li>
  )
}
