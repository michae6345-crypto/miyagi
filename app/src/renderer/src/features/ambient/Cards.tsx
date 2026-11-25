/**
 * Feature: ambient. The two cards that grow out of the notch island (black in both appearances, like the notch):
 *
 *   ExplainCard  the error in calm words: what went wrong (why), the likely fix, the command to copy, and Show me (bon
 *                points at where to look). One white primary: Install <tool> when the fix is an install, else Copy fix.
 *                "Not in <app>" mutes that app. Close (✕ / Esc) tells the engine to forget the error.
 *   SetupCard    "Set up this project": what the project's own files ask for, missing first, each with Fix (setup.fix)
 *                or Get it (a licensed app's page; never installed); "Fix all" is the one primary.
 * No hue for anything missing: a hollow gray ring, never red. Green stays for passed only, so a ready row is a quiet tick.
 */
import { motion, useReducedMotion } from 'motion/react'
import { Check, Copy } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { SetupItem } from '../../../../../../shared/contracts/events'
import { color, fill, font, spring, type2 } from '../../core/theme'
import { OptionButton, Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { fade } from '../../core/ui/motion'
import { copyText } from '../drawer/plan'
import { linkRowAct } from '../drawer/store'
import { baseName, canRetry, clip, failLine, fixable, readyLine, rowDetail, rowFix, scanError, sortRows, stopLine } from './model'
import { muteApp } from './prefs'
import { closeExplain, closeSetup, fixAll, fixRow, retryExplain, showError, useAmbient, type Install } from './store'

export const EXPLAIN_W = 400
export const SETUP_W = 428
/** Rows the setup card shows before it scrolls. */
const ROWS_SHOWN = 6
const ROW_H = 46
/** Lines of a diff the card shows (the rest is "+N more lines"). */
const DIFF_LINES = 10

/** Parts settle in one after another (40 ms apart); reduced motion keeps only the fade. */
function usePart(): (i: number) => Record<string, unknown> {
  const reduce = useReducedMotion()
  return (i) => {
    const delay = reduce ? 0 : 0.05 + i * 0.04
    return {
      initial: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
      animate: { opacity: 1, y: 0 },
      transition: { ...spring, delay, opacity: { ...fade.in, delay } }
    }
  }
}

/** "Copied" for a moment after a copy. */
function useCopied(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1600)
    return () => clearTimeout(t)
  }, [copied])
  return [copied, (text) => void copyText(text).then((ok) => ok && setCopied(true))]
}

function Header({ title, meta }: { title: string; meta?: string }): ReactNode {
  return (
    <div className="flex min-h-[22px] items-center gap-[10px]">
      <MiyagiMark size={18} />
      <div className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.label, fontWeight: 500 }}>
        {title}
        {meta && <span>&nbsp;· {meta}</span>}
      </div>
      <Keycap k="dismiss" />
    </div>
  )
}

function Waiting({ text }: { text: string }): ReactNode {
  return (
    <div className="flex items-center gap-[10px]" style={{ fontSize: type2.sm, color: color.label }} role="status" aria-live="polite">
      <Spinner size={14} />
      <span>{text}</span>
    </div>
  )
}

/** A command or a diff, in the code face on a quiet tile. */
function CodeBlock({ children, data }: { children: ReactNode; data?: string }): ReactNode {
  return (
    <div
      data-ambient-code={data}
      className="overflow-hidden rounded-[8px]"
      style={{ background: fill.chip, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, fontFamily: font.mono, fontSize: 12.5, lineHeight: '18px', padding: '8px 10px', color: color.text }}
    >
      {children}
    </div>
  )
}

function Diff({ diff }: { diff: string }): ReactNode {
  const lines = diff.split('\n').filter((l) => !/^(---|\+\+\+|@@|diff |index )/.test(l))
  const shown = lines.slice(0, DIFF_LINES)
  return (
    <CodeBlock data="diff">
      {shown.map((l, i) => (
        // No red, no green: the sign says it. Removed lines are the quieter label color.
        <div key={i} className="truncate whitespace-pre" style={{ color: l.startsWith('-') ? color.label : color.text }}>
          {l || ' '}
        </div>
      ))}
      {lines.length > shown.length && <div style={{ color: color.label }}>+{lines.length - shown.length} more lines</div>}
    </CodeBlock>
  )
}

/** One install's state, in a few calm words. */
function installWords(i: Install | undefined, label: string): string | undefined {
  if (!i) return undefined
  if (i.running) return i.line ? clip(i.line, 60) : `Installing ${label}…`
  if (i.ok) return `${label} is installed.`
  return `${label} didn't install. ${i.error && i.error !== 'failed' ? clip(i.error, 60) : 'Try again in a minute.'}`
}

export function ExplainCard(): ReactNode {
  const part = usePart()
  const e = useAmbient((s) => s.error)
  const x = useAmbient((s) => s.explanation)
  const cleared = useAmbient((s) => s.cleared)
  const install = useAmbient((s) => (x?.install ? s.installs[x.install.tool] : undefined))
  const [copied, copy] = useCopied()
  const [pointed, setPointed] = useState<boolean | undefined>(undefined)
  if (!e) return null
  const pending = !x || x.pending
  const where = stopLine(e)
  const target = x?.target ?? e.rect
  const app = e.app.trim()
  const fixTool = x?.install && rowFix(x.install) === 'install' ? x.install : undefined
  const done = install && !install.running && install.ok
  return (
    <div data-hit data-ambient="explain" role="dialog" aria-labelledby="ambient-explain-title" className="flex flex-col" style={{ padding: 18, gap: 12, color: color.text }}>
      <motion.div {...part(0)}>
        <Header title={where} meta={app ? `${clip(app, 20)}` : undefined} />
      </motion.div>
      {pending ? (
        <motion.div {...part(1)} className="flex flex-col" style={{ gap: 10 }}>
          <h2 id="ambient-explain-title" className="m-0 truncate" style={{ fontSize: type2.md, lineHeight: '20px', fontWeight: 600 }}>
            {clip(e.title, 70)}
          </h2>
          <Waiting text="Reading the error…" />
        </motion.div>
      ) : x?.error ? (
        <motion.div {...part(1)} className="flex flex-col" style={{ gap: 12 }}>
          <h2 id="ambient-explain-title" className="m-0" style={{ fontSize: type2.md, lineHeight: '20px', fontWeight: 600 }}>
            {failLine(x.error, x.retryInS)}
          </h2>
          {canRetry(x.error) && (
            <div className="flex">
              <QuietButton label="Try again" onClick={retryExplain} />
            </div>
          )}
        </motion.div>
      ) : (
        <>
          <motion.div {...part(1)} className="flex flex-col" style={{ gap: 6 }}>
            <h2 id="ambient-explain-title" className="m-0" style={{ fontSize: type2.lg, lineHeight: '22px', fontWeight: 600, letterSpacing: '-0.01em' }}>
              {x?.title ?? clip(e.title, 60)}
            </h2>
            {x?.why && (
              <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }} data-ambient-why>
                {x.why}
              </p>
            )}
          </motion.div>
          {(x?.fix || x?.command || x?.diff) && (
            <motion.div {...part(2)} className="flex flex-col" style={{ gap: 8 }}>
              {x?.fix && (
                <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px' }} data-ambient-fix>
                  {x.fix}
                </p>
              )}
              {x?.command && (
                <CodeBlock data="command">
                  <span style={{ color: color.label }}>$ </span>
                  {x.command}
                </CodeBlock>
              )}
              {x?.diff && <Diff diff={x.diff} />}
            </motion.div>
          )}
          {(install || cleared) && (
            <div role="status" aria-live="polite" className="flex items-center gap-[8px]" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
              {install?.running && <Spinner size={12} />}
              <span className="truncate">{cleared ? 'That error is gone.' : installWords(install, x?.install?.label ?? 'It')}</span>
            </div>
          )}
          <motion.div {...part(3)} className="flex flex-wrap items-center" style={{ gap: 8 }}>
            {fixTool && !done ? (
              <PrimaryButton label={`Install ${clip(fixTool.label, 22)}`} busy={install?.running} onClick={() => fixRow(fixTool.tool)} />
            ) : x?.command ? (
              <PrimaryButton label={copied ? 'Copied' : 'Copy fix'} icon={copied ? Check : Copy} onClick={() => copy(x.command!)} />
            ) : null}
            {target && <OptionButton action="show_me" label="Show me" onClick={() => setPointed(showError())} />}
            {fixTool && !done && x?.command && <QuietButton label={copied ? 'Copied' : 'Copy fix'} icon={copied ? Check : Copy} onClick={() => copy(x.command!)} />}
          </motion.div>
          {pointed === false && (
            <div style={{ fontSize: type2.xs, color: color.label }} role="status">
              Can't see it on screen right now.
            </div>
          )}
        </>
      )}
      {app && (
        <div className="flex items-center justify-between" style={{ fontSize: type2.xs, color: color.label }}>
          <span className="truncate">{e.file ? `${baseName(e.file)}${e.line ? `:${e.line}` : ''}` : ''}</span>
          <button
            type="button"
            data-hit
            data-ambient-mute
            className="shrink-0 cursor-pointer rounded-[6px] px-[6px] py-[2px] hover:underline"
            style={{ color: color.label }}
            onMouseDown={(ev) => ev.preventDefault()}
            onClick={() => {
              muteApp(app)
              closeExplain()
            }}
          >
            Not in {clip(app, 20)}
          </button>
        </div>
      )}
    </div>
  )
}

/** A row's left glyph: a quiet tick when it's there, a hollow gray ring when it's missing. No hue either way. */
function RowGlyph({ ok }: { ok: boolean }): ReactNode {
  return ok ? (
    <Check size={14} strokeWidth={2} style={{ color: color.label }} aria-label="Ready" />
  ) : (
    <span aria-label="Missing" className="block h-[12px] w-[12px] rounded-full" style={{ boxShadow: `inset 0 0 0 1.5px ${color.gray}` }} />
  )
}

/** The small neutral button at a row's end (Fix, Get it): chrome, not the card's primary. */
function RowButton({ label, onClick, data }: { label: string; onClick: () => void; data?: string }): ReactNode {
  return (
    <motion.button
      type="button"
      data-hit
      data-ambient-row-button={data}
      className="h-[26px] shrink-0 cursor-pointer rounded-full px-[12px] text-[12px] font-medium"
      style={{ backgroundColor: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: 0.97 }}
      transition={{ ...spring, backgroundColor: fade.tint }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}

function SetupRow({ x, install }: { x: SetupItem; install?: Install }): ReactNode {
  const fix = rowFix(x)
  const missing = x.needed && !x.ok
  const detail = install?.running || (install && !install.ok) ? installWords(install, x.label) : rowDetail(x)
  let right: ReactNode
  if (install?.running) right = <Spinner size={14} />
  else if (install?.ok && missing) right = <span style={{ fontSize: type2.xs, color: color.label }}>Checking…</span>
  else if (fix === 'install') right = <RowButton label={install && !install.ok ? 'Try again' : 'Fix'} onClick={() => fixRow(x.tool)} data={`fix-${x.tool}`} />
  else if (fix === 'link') right = <RowButton label="Get it" onClick={() => linkRowAct(x.tool, x.install.url)} data={`link-${x.tool}`} />
  else if (!missing) right = x.version ? <span className="tabular-nums" style={{ fontSize: type2.xs, color: color.label }}>{clip(x.version, 14)}</span> : null
  else right = <span style={{ fontSize: type2.xs, color: color.label }}>By hand</span>
  return (
    <div data-ambient-row={x.tool} data-missing={missing || undefined} className="flex items-center gap-[10px]" style={{ minHeight: ROW_H, borderTop: `1px solid ${fill.rule}` }}>
      <span className="grid w-[16px] shrink-0 place-items-center">
        <RowGlyph ok={!missing} />
      </span>
      <div className="min-w-0 flex-1 py-[6px]">
        <div className="truncate" style={{ fontSize: type2.sm, lineHeight: '17px', fontWeight: 500, color: missing ? color.text : color.label }}>
          {x.label}
        </div>
        {detail && (
          <div className="truncate" title={detail} style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label, fontFamily: install?.running ? font.mono : undefined }}>
            {detail}
          </div>
        )}
      </div>
      {right}
    </div>
  )
}

export function SetupCard(): ReactNode {
  const part = usePart()
  const r = useAmbient((s) => s.report)
  const installs = useAmbient((s) => s.installs)
  const queue = useAmbient((s) => s.queue)
  if (!r) return null
  const rows = sortRows(r.items)
  const err = scanError(r.error)
  const scanning = !!r.scanning && !r.items.length
  const tools = fixable(r.items)
  const running = Object.values(installs).some((i) => i.running)
  const env = [r.env?.python && `Python ${r.env.python.replace(/^.*\((?:Python )?([^)]+)\)$/, '$1')}`, r.env?.node].filter(Boolean).join(' · ')
  return (
    <div data-hit data-ambient="setup" role="dialog" aria-labelledby="ambient-setup-title" className="flex flex-col" style={{ padding: 18, gap: 12, color: color.text }}>
      <motion.div {...part(0)}>
        <Header title="Set up this project" />
      </motion.div>
      <motion.div {...part(1)} className="flex items-baseline justify-between gap-[12px]">
        <h2 id="ambient-setup-title" className="m-0 min-w-0 truncate" style={{ fontSize: type2.lg, lineHeight: '22px', fontWeight: 600, letterSpacing: '-0.01em' }}>
          {r.name ?? 'This project'}
        </h2>
        {!scanning && !err && (
          <span className="shrink-0 tabular-nums" style={{ fontSize: type2.sm, color: color.label }} data-ambient-ready>
            {readyLine(r.ready, r.total)}
          </span>
        )}
      </motion.div>
      {err ? (
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
          {err}
        </p>
      ) : scanning ? (
        <Waiting text="Reading the project's files…" />
      ) : (
        <motion.div {...part(2)} className="flex flex-col">
          <div className="flex flex-col overflow-y-auto" style={{ maxHeight: ROWS_SHOWN * ROW_H }}>
            {rows.map((x) => (
              <SetupRow key={x.tool} x={x} install={installs[x.tool]} />
            ))}
          </div>
          {!!r.more && (
            <div style={{ fontSize: type2.xs, color: color.label, paddingTop: 6, borderTop: `1px solid ${fill.rule}` }}>
              +{r.more} more ready
            </div>
          )}
        </motion.div>
      )}
      {(env || r.files.length > 0) && !err && !scanning && (
        <div className="truncate" style={{ fontSize: type2.xs, color: color.label }} title={[r.root, ...r.files].filter(Boolean).join(' · ')}>
          {env || `Read ${r.files.slice(0, 3).join(', ')}`}
        </div>
      )}
      <motion.div {...part(3)} className="flex items-center justify-end" style={{ gap: 8 }}>
        {tools.length > 1 && !err && !scanning ? (
          <>
            <QuietButton label="Close" onClick={closeSetup} />
            <PrimaryButton label={running || queue.length ? 'Fixing…' : `Fix all ${tools.length}`} busy={running} onClick={fixAll} />
          </>
        ) : (
          <PrimaryButton label="Done" onClick={closeSetup} />
        )}
      </motion.div>
    </div>
  )
}
