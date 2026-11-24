/**
 * Feature: drawer. The "Just teach me" parts of the drawer (Michael: show the big picture, then the plan, then
 * exactly what to type):
 *  - OverviewText: "What you're building", one paragraph (lesson.ready overview).
 *  - PrimerSection: "Before you start", collapsed by default; each concept with its body and a small example.
 *  - StepDetail: inside the current step, a Type / Run badge with the one-line instruction, the full code (or the
 *    exact command) in mono with Copy, "Why:" and concept chips that open the matching primer item in place.
 *  - StepActions: "Check my work" under the current step's checks, the drawer's one primary (the options are in
 *    the shortcut bar, A11).
 *
 * Glass tokens only (theme.glass); chrome stays neutral, green stays for passed.
 */
import { motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { BookOpen, Check, ChevronDown, ChevronRight, ChevronUp, Copy, Keyboard, Terminal, type LucideIcon } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import type { Prerequisite, PrimerItem, StepKind, StepSummary } from '../../../../../../shared/contracts/events'
import { useLesson, useThinking } from '../../core/lesson'
import { sendAction, usePressed } from '../../core/shortcuts'
import { font, glass, spring } from '../../core/theme'
import { GlassPrimary, GlassSpinner } from '../../core/ui/glass'
import { FlowDiagram } from '../before-start/Flow'
import { openBeforeStart } from '../before-start/store'
import { useStepSnippet } from '../overview/snippet'
import { copyText, findPrimer, useStepDetail, type OutlineRow } from './plan'
import { openConcept, useDrawer } from './store'
import { fade, prefersReduced } from '../../core/ui/motion'

const hoverVar = { '--drawer-hover': glass.fieldHover } as CSSProperties
const thinScroll = { scrollbarWidth: 'thin', scrollbarColor: `${glass.track} transparent` } as CSSProperties

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

/**
 * Mockup 01's "What you're building" strip (lesson.ready build + flow): the summary, the outcome in a quieter
 * line, and the small "how it works" diagram with the current step's box outlined. Used instead of the overview
 * paragraph when the engine sends `build`.
 */
export function BuildStrip(): ReactNode {
  const b = useLesson(
    useShallow((s) => ({ build: s.lesson?.build, flow: s.lesson?.flow, stepIndex: s.steps.find((x) => x.id === s.stepId)?.index }))
  )
  if (!b.build) return null
  return (
    <div data-part="drawer-build" className="px-[10px] pb-[2px]">
      <p className="text-[13.5px] leading-[19px]" style={{ color: glass.text }}>
        {b.build.summary}
      </p>
      {b.build.outcome && (
        <p className="mt-[3px] text-[12.5px] leading-[17px]" style={{ color: glass.label }}>
          {b.build.outcome}
        </p>
      )}
      {!!b.flow?.length && (
        <div className="mt-[9px]">
          <FlowDiagram flow={b.flow} currentIndex={b.stepIndex} tone={{ text: glass.text, faint: glass.faint, box: glass.field, border: glass.rule, current: glass.text }} />
        </div>
      )}
    </div>
  )
}

const NO_NEEDS: Prerequisite[] = []

/**
 * Mockup 01's "Needs: ..." chip (lesson.ready prerequisites): what the lesson leans on, with a tick when every one
 * has passed in an earlier lesson. It opens the "Before you start" sheet (features/before-start) for the details.
 */
export function NeedsChip(): ReactNode {
  const needs = useLesson((s) => s.lesson?.prerequisites) ?? NO_NEEDS
  if (needs.length === 0) return null
  const allPassed = needs.every((n) => n.status === 'passed')
  const names = needs.slice(0, 2).map((n) => n.title).join(', ')
  const more = needs.length > 2 ? ` +${needs.length - 2}` : ''
  return (
    <div className="px-[10px] pt-[10px]">
      <button
        type="button"
        data-part="drawer-needs"
        className="flex h-[26px] max-w-full cursor-pointer items-center gap-[6px] rounded-full border px-[10px] text-[12px] hover:bg-[var(--drawer-hover)]"
        style={{ ...hoverVar, background: glass.field, borderColor: glass.rule, color: glass.label }}
        title="Your lesson"
        onMouseDown={(e) => e.preventDefault()}
        onClick={openBeforeStart}
      >
        {allPassed && <Check size={12} strokeWidth={2.4} style={{ color: glass.pass }} className="shrink-0" />}
        <span className="shrink-0 font-semibold" style={{ color: glass.text }}>
          Needs:
        </span>
        <span className="truncate">
          {names}
          {more}
        </span>
        <ChevronRight size={12} strokeWidth={2} className="shrink-0" style={{ color: glass.faint }} />
      </button>
    </div>
  )
}

/**
 * The eyebrow's short topic ("Just teach me · calculator"): the title without a leading "how to" / verb / article, cut
 * before its first qualifier (" in ", " with ", ": " ...), at most 4 words. From the data, never a fixed word.
 */
export function lessonTopic(title: string): string {
  const full = title.trim()
  let t = full
    .replace(/^(?:how\s+to\s+|let's\s+)?(?:learn|build|make|create|write|code|train|solve|implement)\s+/i, '')
    .replace(/^(?:a|an|the|your)\s+/i, '')
  const cut = t.search(/\s*[:—–]\s*|\s+-\s+|\s+(?:in|with|using|for|from|on|via|by|to|that)\s+/i)
  if (cut > 0) t = t.slice(0, cut)
  t = t.split(/\s+/).slice(0, 4).join(' ').replace(/[.,;]+$/, '')
  return t || full
}

/**
 * "about N min left": the steps' estMinutes summed over the steps not passed or skipped yet (undefined without estimates).
 * rows: the outline's (E23) while the rest of the lesson is still streaming in. A row counts until its step arrives; an
 * arrived step without its own estimate keeps its row's, so the sum doesn't jump as steps land (review A14).
 */
export function minutesLeft(steps: StepSummary[], done: string[], rows: OutlineRow[] = []): number | undefined {
  const byIndex = new Map(rows.map((r) => [r.index, r.estMinutes]))
  const arrived = new Set(steps.map((s) => s.index))
  const est = [
    ...steps.filter((s) => !done.includes(s.id)).map((s) => s.estMinutes ?? byIndex.get(s.index)),
    ...rows.filter((r) => !arrived.has(r.index)).map((r) => r.estMinutes)
  ]
  const known = [...steps.map((s) => s.estMinutes ?? byIndex.get(s.index)), ...rows.map((r) => r.estMinutes)]
  if (!known.some((m) => typeof m === 'number')) return undefined
  return Math.max(0, Math.round(est.reduce<number>((sum, m) => sum + (m ?? 0), 0)))
}

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

const NO_PRIMER: PrimerItem[] = []

export function PrimerSection(): ReactNode {
  const primer = useLesson((s) => s.lesson?.primer) ?? NO_PRIMER
  const [open, setOpen] = useState(false)
  if (primer.length === 0) return null
  return (
    <div data-part="drawer-primer" data-open={open || undefined}>
      <button
        type="button"
        className="flex w-full cursor-pointer items-center gap-[6px] px-[10px] pb-[4px] pt-[14px] text-left text-[12px] leading-[16px]"
        style={{ color: glass.faint }}
        aria-expanded={open}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen((o) => !o)}
      >
        {/* The drawer's section labels (mockup 01's small caps). */}
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em]">Key ideas</span>
        <span>
          {primer.length} {primer.length === 1 ? 'idea' : 'ideas'}
        </span>
        <motion.span className="grid place-items-center" animate={{ rotate: open ? 90 : 0 }} transition={spring}>
          <ChevronRight size={13} strokeWidth={2} />
        </motion.span>
      </button>
      {open && (
        <motion.div className="flex flex-col gap-[6px] px-[2px] pb-[2px] pt-[4px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={fade.in}>
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
        <pre data-code-pre className="mt-[7px] overflow-x-auto whitespace-pre leading-[17px]" style={{ fontFamily: font.mono, fontSize: 'var(--mg-code-size, 12px)', color: glass.text, ...thinScroll }}>
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
  const detail = useStepDetail((s) => (s.detail?.stepId === stepId ? s.detail : undefined))
  const primer = useLesson((s) => s.lesson?.primer) ?? NO_PRIMER
  const snippet = useStepSnippet()
  // Mockup 02: a concept chip opens the concept panel (Concept.tsx); the drawer collapses to a step rail.
  const openId = useDrawer((s) => s.concept)

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
            <ConceptChip key={c.key} label={c.label} item={c.item} open={!!c.item && c.item.id === openId} onToggle={openConcept} />
          ))}
        </div>
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

/** Code longer than CLAMP_OVER lines shows its first CLAMP lines and "Show all N lines" (Copy always copies all of it). */
const CLAMP = 10
const CLAMP_OVER = 12

/**
 * The full code: long lines scroll sideways rather than wrap, so what you see is what you type. A line cut off at the
 * right edge gets a cue there (a chevron strip that scrolls on), so a missing ")" never looks like a typo. Long code
 * starts clamped to CLAMP lines with "Show all".
 */
export function CodeBlock({ code, caption, bleed }: { code: string; caption: string; bleed: number }): ReactNode {
  const lines = code.split('\n')
  const long = lines.length > CLAMP_OVER
  const [all, setAll] = useState(false)
  const shown = long && !all ? lines.slice(0, CLAMP).join('\n') : code
  const pre = useRef<HTMLPreElement>(null)
  const more = useMoreToTheRight(pre, shown)
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
          className="flex h-[24px] shrink-0 cursor-pointer items-center gap-[5px] rounded-full px-[9px] text-[12px] font-medium"
          style={{ background: glass.key, color: glass.text }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={copy}
        >
          {copied === 'yes' ? <Check size={12} strokeWidth={2.2} /> : <Copy size={12} strokeWidth={1.9} />}
          {copied === 'yes' ? 'Copied' : copied === 'no' ? "Couldn't copy" : 'Copy'}
        </button>
      </div>
      <div className="relative">
        {/* Lines never wrap (Michael, test 10: "sparse_categoric / al_crossentropy" broke inside a name, and typing it as
            shown fails); long lines scroll sideways. */}
        <pre ref={pre} data-code-pre className="overflow-x-auto whitespace-pre px-[12px] py-[9px] leading-[18px]" style={{ fontFamily: font.mono, fontSize: 'var(--mg-code-size, 12px)', color: glass.text, ...thinScroll }}>
          <code>
            {shown.split(/\r?\n/).map((line, i) => (
              <span key={i} data-code-line className="block">
                {line || ' '}
              </span>
            ))}
          </code>
        </pre>
        {more && (
          <button
            type="button"
            data-part="drawer-code-more"
            className="absolute inset-y-0 right-0 w-[22px] cursor-pointer border-l"
            // Opaque (the panel's glass twice, like the panel itself) so the cut-off characters don't show through.
            style={{ background: glass.bg, boxShadow: `inset 0 0 0 22px ${glass.bg}`, borderColor: glass.rule, color: glass.label }}
            title="More to the right"
            aria-label="Scroll the code right"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => pre.current?.scrollBy({ left: Math.round(pre.current.clientWidth * 0.6), behavior: prefersReduced() ? 'auto' : 'smooth' })}
          >
            <span className="absolute inset-0 grid place-items-center" style={{ background: glass.field }}>
              <ChevronRight size={13} strokeWidth={2} />
            </span>
          </button>
        )}
      </div>
      {long && (
        <button
          type="button"
          data-part="drawer-code-all"
          className="flex h-[28px] w-full cursor-pointer items-center justify-center gap-[4px] border-t text-[12px] font-medium hover:bg-[var(--drawer-hover)]"
          style={{ ...hoverVar, borderColor: glass.rule, color: glass.label }}
          aria-expanded={all}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setAll((a) => !a)}
        >
          {all ? 'Show less' : `Show all ${lines.length} lines`}
          {all ? <ChevronUp size={12} strokeWidth={2} /> : <ChevronDown size={12} strokeWidth={2} />}
        </button>
      )}
    </div>
  )
}

/** True while the <pre>'s lines run past its right edge and it isn't scrolled to the end. */
function useMoreToTheRight(ref: RefObject<HTMLPreElement | null>, content: string): boolean {
  const [more, setMore] = useState(false)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const check = (): void => setMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
    check()
    el.addEventListener('scroll', check, { passive: true })
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', check)
      ro.disconnect()
    }
  }, [ref, content])
  return more
}

// ---------------------------------------------------------------------------
// The step's action
// ---------------------------------------------------------------------------

/** The spinner in the primary's icon slot: the glass button's text color (white on dark, ink on light). */
const SpinPrimary = ((p: { size?: number }) => <GlassSpinner size={p.size ?? 13} c={glass.buttonText} track={glass.rule} />) as unknown as LucideIcon

/**
 * The current step's one action: "Check my work" (action check_step). Explain / Diagram / Show me / Hint live only
 * in the shortcut bar, which is always up during a step, so the drawer doesn't repeat them (tests 2-3, A11).
 * Never looks dead: the icon spins while the engine thinks about it.
 */
export function StepActions({ padX }: { padX: number }): ReactNode {
  const thinking = useThinking()
  const pressed = usePressed((p) => p.kind)
  const checking = thinking && pressed === 'check_step'
  return (
    // Sticky at the scroller's bottom while its step is on screen (Michael's test 8: on a tall step 6 the button was
    // cut off at the drawer's bottom edge). Opaque glass under the current row's tint, so rows scrolling behind don't show through.
    <div
      data-part="drawer-actions"
      className="sticky bottom-0 z-[1] flex items-center justify-end pb-[12px] pt-[6px]"
      style={{ paddingLeft: padX, paddingRight: padX, borderRadius: '0 0 12px 12px', background: glass.bg, boxShadow: `inset 0 0 0 999px ${glass.bg}, inset 0 0 0 999px ${glass.fieldHover}` }}
    >
      <GlassPrimary label={checking ? 'Checking…' : 'Check my work'} icon={checking ? SpinPrimary : Check} onClick={() => !checking && sendAction('check_step')} />
    </div>
  )
}
