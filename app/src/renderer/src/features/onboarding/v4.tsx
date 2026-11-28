/**
 * Feature: onboarding. The v4 setup look (Adrian's ui-next mock, `onboard-1` / `onboard-2`, Nov 24), shared by every
 * first-run screen: Sign in (features/auth), consent, guided setup, the buddy's color, You're ready, Review setup.
 *
 *   SetupPage   the page: cream (v4 page), centered in the window both ways (onboarding redesign, Nov 28: the step
 *               sits on the same center line as the progress dots, and a little above the middle). With a rail: the
 *               step on the left and a quiet rail on the right, one hairline between them, the pair centered as one
 *               block; one column, no rail, under 860. Without a rail: one narrow centered column, centered text,
 *               like the birthday screen (sign in, consent, the engine step). onb-v4.css
 *   SetupTitle  the v4 page title (32 / 600) and its one-line lede
 *   SetupGroup  a hairline box of SetupRows (mock .group / .srow): a name, one line under it, the state on the right
 *   LiveState   the live check: the status glyph and its word (green only once passed)
 *   RailSection / RailRow  the rail's label and its 48 px rows; `n` puts a numbered ring in front (a how-to)
 *   Actions     the one primary and anything quiet beside it, under the step (centered in a centered page)
 *   BackButton  the one Back of the first run (features/onboarding/back.ts): a chevron and "Back" in the window's top
 *               bar, right of the traffic lights, never inside a step
 *
 * Tokens only (v4c, v4type, color): no new colors. Neutral chrome; green only for passed; no pastel here.
 */
import { AnimatePresence, motion } from 'motion/react'
import { ChevronLeft } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { color, v4c, v4type } from '../../core/theme'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { rise, stagger } from './parts'
import type { RowState } from './rows'
import { wordColor } from './Row'
import { useBackAction } from './back'
import './onb-v4.css'

/**
 * The page's least top room in a flow under its strip. The page centers itself vertically; in a flow it adds the
 * strip's 64 below as well, so the step sits on the window's middle, not the body's.
 */
export const FLOW_TOP = '24px'
/** The strip above a flow's body (styles.css .mg-flow-head). */
const STRIP_H = 64

export function SetupPage({
  children,
  rail,
  view,
  top,
  enterDelay = 0,
  animate = true,
  labelledBy = 'onb-title',
  data,
  style,
  align
}: {
  children: ReactNode
  rail?: ReactNode
  /** 'center': one narrow centered column (the default without a rail); 'split': step and rail (the default with one). */
  align?: 'center' | 'split'
  /** data-onb-view on the page (consent, setup, ready, buddy, checklist; sign-in passes its own data). */
  view?: string
  /** The room above the step (CSS length). Default: clamp(24px, 8vh, 96px). */
  top?: string
  enterDelay?: number
  /** false: the children carry their own motion (a step that slides). */
  animate?: boolean
  labelledBy?: string
  data?: Record<string, string | boolean | undefined>
  style?: CSSProperties
}): ReactNode {
  const inFlow = top === FLOW_TOP
  const vars = {
    ...(top ? { ['--onb4-top' as string]: top } : {}),
    ...(inFlow ? { ['--onb4-bottom' as string]: `calc(${FLOW_TOP} + ${STRIP_H}px + 4vh)` } : {}),
    ...style
  } as CSSProperties
  const layout = align ?? (rail ? 'split' : 'center')
  return (
    <div data-onb-view={view} data-onb-v4 data-onb-align={layout} role="dialog" aria-labelledby={labelledBy} className="mg-onb4" style={{ ...vars, background: v4c.page, color: color.text }} {...data}>
      <div className="mg-onb4-col">
        <div className="mg-onb4-grid" data-rail={rail ? 'side' : 'none'}>
          {animate ? (
            <motion.div className="mg-onb4-main" variants={stagger(enterDelay)} initial="hidden" animate="shown">
              {children}
            </motion.div>
          ) : (
            <div className="mg-onb4-main">{children}</div>
          )}
          {rail && (
            <motion.aside data-onb-rail className="mg-onb4-rail" variants={stagger(enterDelay + 0.08)} initial={animate ? 'hidden' : false} animate="shown">
              {rail}
            </motion.aside>
          )}
        </div>
      </div>
    </div>
  )
}

/** One piece of the step that rises in with the page's stagger. */
export function Rise({ children, className, style, data }: { children: ReactNode; className?: string; style?: CSSProperties; data?: Record<string, string | boolean | undefined> }): ReactNode {
  return (
    <motion.div variants={rise} className={className} style={{ width: '100%', ...style }} {...data}>
      {children}
    </motion.div>
  )
}

export function SetupTitle({ title, lede, id = 'onb-title' }: { title: ReactNode; lede?: ReactNode; id?: string }): ReactNode {
  return (
    <>
      <Rise>
        <h1 id={id} className="m-0" style={{ ...v4type.title, color: color.text }}>
          {title}
        </h1>
      </Rise>
      {lede && (
        <Rise>
          <p className="m-0" style={{ ...v4type.lede, color: color.label, marginTop: 6 }}>
            {lede}
          </p>
        </Rise>
      )}
    </>
  )
}

export function SetupGroup({ children, label, style }: { children: ReactNode; label?: string; style?: CSSProperties }): ReactNode {
  return (
    <div role="list" aria-label={label} className="mg-onb4-group" style={style}>
      {children}
    </div>
  )
}

/**
 * One row of a setup group: the name (14 / 550) and one line under it (12.5 muted), then `right`. `current` washes it
 * (the step on screen). `onClick` makes it a button (the sample lesson). `lead` sits in front (a glyph, an avatar).
 */
export function SetupRow({
  name,
  line,
  right,
  lead,
  current,
  onClick,
  children,
  data
}: {
  name: ReactNode
  line?: ReactNode
  right?: ReactNode
  lead?: ReactNode
  current?: boolean
  onClick?: () => void
  /** Drawn over the row (the soft progress line at its foot). */
  children?: ReactNode
  data?: Record<string, string | boolean | undefined>
}): ReactNode {
  const body = (
    <>
      {lead}
      <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 1 }}>
        <span className="min-w-0 break-words" style={{ ...v4type.row, color: color.text }}>
          {name}
        </span>
        {line && <span style={{ fontSize: 12.5, lineHeight: '17px', color: color.label }}>{line}</span>}
      </span>
      {right && <span className="flex shrink-0 items-center gap-[10px]">{right}</span>}
      {children}
    </>
  )
  if (onClick)
    return (
      <button type="button" role="listitem" className="mg-onb4-srow outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ outlineColor: color.text }} onMouseDown={(e) => e.preventDefault()} onClick={onClick} {...data}>
        {body}
      </button>
    )
  return (
    <div role="listitem" className="mg-onb4-srow" data-current={current || undefined} aria-current={current ? 'step' : undefined} {...data}>
      {body}
    </div>
  )
}

/** The live check: glyph and word. Passed is the one green (wordColor); everything else stays neutral. */
export function LiveState({ state, word, still }: { state: RowState | StatusState; word: string; still?: boolean }): ReactNode {
  return (
    <span data-onb-live={state} className="flex items-center gap-[7px] whitespace-nowrap" style={{ ...v4type.body, color: state === 'passed' ? color.greenText : wordColor(state as RowState) }}>
      <StatusGlyph state={state} size={16} still={still} />
      {word}
    </span>
  )
}

export function RailSection({ title, children, first, right }: { title: ReactNode; children: ReactNode; first?: boolean; right?: ReactNode }): ReactNode {
  return (
    <motion.section variants={rise} className="flex flex-col">
      <div className="flex items-center" style={{ marginTop: first ? 0 : 30, marginBottom: 6, minHeight: 18 }}>
        <h2 className="m-0" style={{ ...v4type.sec, color: color.label }}>
          {title}
        </h2>
        {right && <span className="ml-auto" style={{ ...v4type.sec, fontWeight: 450, color: color.label }}>{right}</span>}
      </div>
      <div className="flex flex-col">{children}</div>
    </motion.section>
  )
}

export function RailRow({ title, detail, n, right, lead }: { title: ReactNode; detail?: ReactNode; n?: number; right?: ReactNode; lead?: ReactNode }): ReactNode {
  return (
    <div className="mg-onb4-rrow" style={{ minHeight: detail ? 48 : 36 }}>
      {n != null && (
        <span aria-hidden className="mg-onb4-num" style={{ color: color.label }}>
          {n}
        </span>
      )}
      {lead}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate" style={{ fontSize: 13.5, lineHeight: '18px', fontWeight: 520, color: color.text }}>
          {title}
        </span>
        {detail && <span style={{ fontSize: 12.5, lineHeight: '17px', color: color.label }}>{detail}</span>}
      </span>
      {right && <span className="shrink-0" style={{ ...v4type.meta, color: color.label }}>{right}</span>}
    </div>
  )
}

/** The actions under a step: the one primary first, quiet ones beside it (centered in a centered page). */
export function Actions({ children, style }: { children: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <Rise style={{ marginTop: 24, ...style }}>
      <div className="mg-onb4-actions flex w-full flex-wrap items-center gap-[8px]">{children}</div>
    </Rise>
  )
}

/**
 * The one Back of the first run: a chevron and "Back" in the window's top bar, just right of the traffic lights (where
 * a Mac window keeps its back button), the same place on every step that has one. Quiet (the label gray, ink on hover,
 * a soft wash under it), never a boxed button and never inside the step. Renders whatever step registered a Back
 * (back.ts useBack); nothing when none did. Fades in and out with the step.
 */
export function BackButton({ className = '', style }: { className?: string; style?: CSSProperties }): ReactNode {
  const back = useBackAction()
  return (
    <AnimatePresence initial={false}>
      {back && (
        <motion.button
          key="back"
          type="button"
          data-no-drag
          data-onb-back
          aria-label="Back"
          onClick={back}
          onMouseDown={(e) => e.preventDefault()}
          className={`mg-onb4-back inline-flex h-[28px] cursor-pointer items-center gap-[2px] rounded-[7px] pl-[4px] pr-[9px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid ${className}`}
          style={{ ...v4type.body, fontSize: 13, fontWeight: 500, color: color.label, outlineColor: color.text, border: 0, ...style }}
          initial={{ opacity: 0, x: 4 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 4 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        >
          <ChevronLeft aria-hidden size={16} strokeWidth={1.9} />
          Back
        </motion.button>
      )}
    </AnimatePresence>
  )
}

/** Fine print under a step (12.5, faint). */
export function Fine({ children, style }: { children: ReactNode; style?: CSSProperties }): ReactNode {
  return <span style={{ fontSize: 12.5, lineHeight: '18px', color: color.faint, ...style }}>{children}</span>
}
