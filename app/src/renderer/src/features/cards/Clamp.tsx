/**
 * Text clamped to a few lines that opens in place: when it doesn't fit, a faint "More" under it (and a click on
 * the text itself) shows all of it; "Less" folds it back. Nothing to click when it fits. A new text starts folded.
 */
import { ChevronDown } from 'lucide-react'
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { color } from '../../core/theme'

export function Clamp({ text, lines, className = '', style }: { text: string; lines: number; className?: string; style?: CSSProperties }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [over, setOver] = useState(false)
  const [seen, setSeen] = useState(text)
  // A new text (the next card) starts folded.
  if (seen !== text) {
    setSeen(text)
    setOpen(false)
  }
  useLayoutEffect(() => {
    const el = ref.current
    if (el && !open) setOver(el.scrollHeight > el.clientHeight + 1)
  }, [text, lines, open])
  const can = over || open
  const toggle = can ? () => setOpen((x) => !x) : undefined
  const clamp: CSSProperties = open ? {} : { display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: lines, overflow: 'hidden' }
  return (
    <>
      <div ref={ref} data-clamp={open ? 'open' : over ? 'folded' : undefined} className={`${className} ${can ? 'cursor-pointer' : ''}`} style={{ ...style, ...clamp }} onClick={toggle}>
        {text}
      </div>
      {can && (
        <button
          type="button"
          data-more
          className="mt-[2px] flex cursor-pointer items-center gap-[3px] text-[12px] font-medium"
          style={{ color: color.faint }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={toggle}
        >
          {open ? 'Less' : 'More'}
          <ChevronDown size={12} strokeWidth={2} style={{ transform: open ? 'rotate(180deg)' : undefined }} />
        </button>
      )}
    </>
  )
}

/** Lines a card body shows before "More" (Explain / Hint / Answer). */
export const BODY_LINES = 6
/** Lines a body-as-headline (the title only repeated the kind) shows before "More". */
export const HEADLINE_LINES = 3
