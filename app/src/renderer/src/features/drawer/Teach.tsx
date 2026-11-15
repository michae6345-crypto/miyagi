/**
 * Feature: drawer. The "Just teach me" parts of the drawer (Michael: show the big picture, then the plan, then
 * exactly what to type):
 *  - OverviewText: "What we're building", one paragraph (lesson.ready overview).
 *  - PrimerSection: "Before you start", collapsed by default; each concept with its body and a small example.
 *  - StepDetail: inside the current step, a Type / Run badge with the one-line instruction, the full code (or the
 *    exact command) in mono with Copy, "Why:" and concept chips that open the matching primer item in place.
 *
 * Glass tokens only (theme.glass); chrome stays neutral (no pastels: these aren't options), green stays for passed.
 */
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { BookOpen, Check, ChevronRight, Copy, Keyboard, Terminal, type LucideIcon } from 'lucide-react'
import { font, glass, spring } from '../../core/theme'
import { useStepSnippet } from '../overview/snippet'
import { copyText, findPrimer, usePlan, type PrimerItem, type StepKind } from './plan'

const hoverVar = { '--drawer-hover': glass.fieldHover } as CSSProperties
const thinScroll = { scrollbarWidth: 'thin', scrollbarColor: `${glass.track} transparent` } as CSSProperties

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export function OverviewText({ text }: { text: string }): ReactNode {
  return (
    <p data-part="drawer-overview" className="px-[10px] pb-[2px] text-[13.5px] leading-[19px]" style={{ color: glass.text }}>
      {text}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Before you start
// ---------------------------------------------------------------------------

export function PrimerSection(): ReactNode {
  const primer = usePlan((s) => s.primer)
  const [open, setOpen] = useState(false)
  if (primer.length === 0) return null
  return (
    <div data-part="drawer-primer" data-open={open || undefined}>
      <button
        type="button"
        className="flex w-full cursor-pointer items-center gap-[6px] px-[10px] pb-[4px] pt-[14px] text-left text-[12px] leading-[16px]"
        style={{ color: glass.label }}
        aria-expanded={open}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="font-semibold">Before you start</span>
        <span style={{ color: glass.faint }}>
          {primer.length} {primer.length === 1 ? 'idea' : 'ideas'}
        </span>
        <motion.span className="grid place-items-center" animate={{ rotate: open ? 90 : 0 }} transition={spring}>
          <ChevronRight size={13} strokeWidth={2} />
        </motion.span>
      </button>
      {open && (
        <motion.div className="flex flex-col gap-[6px] px-[2px] pb-[2px] pt-[4px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          {primer.map((p) => (
            <PrimerCard key={p.id} item={p} />
          ))}
        </motion.div>
      )}
    </div>
  )
}

function PrimerCard({ item }: { item: PrimerItem }): ReactNode {
  return (
    <div data-primer={item.id} className="rounded-[12px] px-[10px] py-[9px]" style={{ background: glass.field }}>
      <div className="text-[13px] font-semibold leading-[18px]" style={{ color: glass.text }}>
        {item.title}
      </div>
      {item.body && (
        <div className="mt-[2px] text-[13px] leading-[18px]" style={{ color: glass.label }}>
          {item.body}
        </div>
      )}
      {item.code && (
        <pre className="mt-[7px] overflow-x-auto whitespace-pre text-[12px] leading-[17px]" style={{ fontFamily: font.mono, color: glass.text, ...thinScroll }}>
          {item.code}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// The current step
// ---------------------------------------------------------------------------

const KIND: Record<StepKind, { label: string; icon: LucideIcon; caption: string }> = {
  code: { label: 'Type', icon: Keyboard, caption: 'Type this' },
  run: { label: 'Run', icon: Terminal, caption: 'Run this in the terminal' },
  read: { label: 'Read', icon: BookOpen, caption: 'Example' }
}

/**
 * The current step's body. Without any of the new fields (a video lesson, an older engine) it is the drawer's
 * old instruction line, unchanged. `bleed` lets the code block run out to the row's left edge (the text column
 * is indented under the step title; code needs the width).
 */
export function StepDetail({ stepId, instructions, planKind, indent, padX }: { stepId: string; instructions?: string; planKind?: StepKind; indent: number; padX: number }): ReactNode {
  const detail = usePlan((s) => (s.detail?.stepId === stepId ? s.detail : undefined))
  const primer = usePlan((s) => s.primer)
  const snippet = useStepSnippet()
  const [openId, setOpenId] = useState<string>()

  const kind = detail?.kind ?? planKind
  // The engine's full code first; the spotlight's snippet for this step (overview/snippet) as the fallback.
  const code = detail?.code ?? (snippet.stepId === stepId ? snippet.code : undefined)
  const why = detail?.why
  const chips = uniqueChips(detail?.concepts ?? [], primer)
  const rich = !!(kind || code || why || chips.length)

  if (!rich) {
    if (!instructions) return null
    return (
      <div
        data-part="drawer-instructions"
        className="line-clamp-3 pb-[10px] text-[13px] leading-[18px]"
        style={{ paddingLeft: indent, paddingRight: padX, marginTop: -4, color: glass.label }}
        title={instructions}
      >
        {instructions}
      </div>
    )
  }

  const open = openId ? primer.find((p) => p.id === openId) : undefined
  return (
    <div data-part="drawer-detail" className="pb-[12px]" style={{ paddingLeft: indent, paddingRight: padX, marginTop: -2 }}>
      {(kind || instructions) && (
        <div data-part="drawer-instructions" className="text-[13.5px] leading-[19px]" style={{ color: glass.text }}>
          {kind && <KindBadge kind={kind} />}
          {instructions}
        </div>
      )}
      {code && <CodeBlock code={code} caption={KIND[kind ?? 'code'].caption} bleed={indent - padX} />}
      {why && (
        <div data-part="drawer-why" className="mt-[10px] text-[13px] leading-[18px]" style={{ color: glass.label }}>
          <span className="font-semibold" style={{ color: glass.text }}>
            Why:
          </span>{' '}
          {why}
        </div>
      )}
      {chips.length > 0 && (
        <div data-part="drawer-concepts" className="mt-[10px] flex flex-wrap gap-[6px]">
          {chips.map((c) => (
            <ConceptChip key={c.key} label={c.label} item={c.item} open={!!c.item && c.item.id === openId} onToggle={(id) => setOpenId((o) => (o === id ? undefined : id))} />
          ))}
        </div>
      )}
      {open && (
        <motion.div className="mt-[8px]" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, opacity: { duration: 0.18 } }}>
          <PrimerCard item={open} />
        </motion.div>
      )}
    </div>
  )
}

/** Concepts as chips, one per primer item (a concept may name it by id or by title); unknown names stay plain. */
function uniqueChips(concepts: string[], primer: PrimerItem[]): Array<{ key: string; label: string; item?: PrimerItem }> {
  const seen = new Set<string>()
  const out: Array<{ key: string; label: string; item?: PrimerItem }> = []
  for (const c of concepts) {
    const item = findPrimer(primer, c)
    const key = item ? `p:${item.id}` : `c:${c.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ key, label: item?.title ?? c, item })
  }
  return out
}

function KindBadge({ kind }: { kind: StepKind }): ReactNode {
  const { label, icon: I } = KIND[kind]
  return (
    <span
      data-part="drawer-kind"
      data-kind={kind}
      className="mr-[7px] inline-flex h-[19px] items-center gap-[4px] rounded-[6px] px-[6px] align-[1px] text-[11.5px] font-semibold leading-none"
      style={{ background: glass.key, color: glass.keyText }}
    >
      <I size={11} strokeWidth={2} />
      {label}
    </span>
  )
}

function ConceptChip({ label, item, open, onToggle }: { label: string; item?: PrimerItem; open: boolean; onToggle: (id: string) => void }): ReactNode {
  return (
    <button
      type="button"
      data-concept={item?.id ?? label}
      className={`flex h-[24px] items-center gap-[3px] rounded-full border px-[10px] text-[12px] font-medium ${item ? 'cursor-pointer hover:bg-[var(--drawer-hover)]' : 'cursor-default'}`}
      style={{ ...hoverVar, background: open ? glass.fieldHover : glass.field, borderColor: open ? glass.track : glass.rule, color: item ? glass.text : glass.label }}
      disabled={!item}
      aria-expanded={item ? open : undefined}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => item && onToggle(item.id)}
    >
      {label}
      {item && (
        <motion.span className="grid place-items-center" style={{ color: glass.faint }} animate={{ rotate: open ? 90 : 0 }} transition={spring}>
          <ChevronRight size={12} strokeWidth={2} />
        </motion.span>
      )}
    </button>
  )
}

/** The full code (never truncated): long lines scroll sideways rather than wrap, so what you see is what you type. */
function CodeBlock({ code, caption, bleed }: { code: string; caption: string; bleed: number }): ReactNode {
  const [copied, setCopied] = useState<'yes' | 'no'>()
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  const copy = (): void => {
    void copyText(code).then((ok) => {
      setCopied(ok ? 'yes' : 'no')
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(undefined), 1600)
    })
  }
  return (
    <div data-part="drawer-code" className="mt-[10px] overflow-hidden rounded-[12px] border" style={{ marginLeft: -bleed, background: glass.field, borderColor: glass.rule }}>
      <div className="flex h-[30px] items-center justify-between gap-[8px] border-b pl-[12px] pr-[4px]" style={{ borderColor: glass.rule }}>
        <span className="truncate text-[12px]" style={{ color: glass.faint }}>
          {caption}
        </span>
        <button
          type="button"
          data-part="drawer-copy"
          className="flex h-[22px] shrink-0 cursor-pointer items-center gap-[5px] rounded-full px-[9px] text-[12px] font-medium"
          style={{ background: glass.key, color: glass.text }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={copy}
        >
          {copied === 'yes' ? <Check size={12} strokeWidth={2.2} /> : <Copy size={12} strokeWidth={1.9} />}
          {copied === 'yes' ? 'Copied' : copied === 'no' ? "Couldn't copy" : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto whitespace-pre px-[12px] py-[9px] text-[12px] leading-[18px]" style={{ fontFamily: font.mono, color: glass.text, ...thinScroll }}>
        <code>{code}</code>
      </pre>
    </div>
  )
}
