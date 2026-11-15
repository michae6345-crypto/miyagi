/**
 * Select any text in the drawer (step text, why, concepts, code, check labels) and a small "Explain more"
 * pop-up appears next to the selection. It sends the existing action {kind: 'explain', text}, so the engine
 * answers with a normal Explain card about that selection. No contract change.
 *
 * Text inside the drawer is made selectable by wrapping its layer in <Selectable> (the overlay root sets
 * user-select: none everywhere else).
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { MessageSquareText } from 'lucide-react'
import { sendAction } from '../../core/shortcuts'
import { glass, spring } from '../../core/theme'

/** The engine gets at most this much selected text. */
export const MAX_SELECTION = 2000
const ATTR = 'data-drawer-select'

/** Wraps the drawer's layer: its text becomes selectable; layout is untouched (display: contents). */
export function Selectable({ children }: { children: ReactNode }): ReactNode {
  return (
    <div {...{ [ATTR]: '' }} style={{ display: 'contents', userSelect: 'text', cursor: 'auto' }}>
      {children}
    </div>
  )
}

type Picked = { text: string; x: number; y: number }

/** The current selection, if it is non-empty and sits inside the drawer. */
function readSelection(): Picked | undefined {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return undefined
  const text = sel.toString().replace(/\s+/g, ' ').trim()
  if (!text) return undefined
  const range = sel.getRangeAt(0)
  const node = range.commonAncestorContainer
  const el = node instanceof Element ? node : node.parentElement
  if (!el?.closest(`[${ATTR}]`)) return undefined
  const r = range.getBoundingClientRect()
  if (!r.width && !r.height) return undefined
  return { text, x: r.left + r.width / 2, y: r.top }
}

export function SelectionExplain(): ReactNode {
  const [picked, setPicked] = useState<Picked>()

  useEffect(() => {
    // Read on mouse/key up so the pop-up doesn't chase the cursor mid-drag; clear as soon as the selection goes.
    const update = (): void => setPicked(readSelection())
    const onChange = (): void => {
      if (!readSelection()) setPicked(undefined)
    }
    document.addEventListener('mouseup', update)
    document.addEventListener('keyup', update)
    document.addEventListener('selectionchange', onChange)
    return () => {
      document.removeEventListener('mouseup', update)
      document.removeEventListener('keyup', update)
      document.removeEventListener('selectionchange', onChange)
    }
  }, [])

  const explain = (): void => {
    if (!picked) return
    sendAction('explain', picked.text.slice(0, MAX_SELECTION))
    window.getSelection()?.removeAllRanges()
    setPicked(undefined)
  }

  // Above the selection; below it when there's no room at the top of the screen.
  const above = (picked?.y ?? 0) > 52
  return (
    <AnimatePresence>
      {picked && (
        <div
          key="explain-selection"
          style={{
            position: 'fixed',
            left: Math.max(70, Math.min(picked.x, window.innerWidth - 70)),
            top: above ? picked.y - 8 : picked.y + 28,
            transform: above ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
            zIndex: 60
          }}
        >
          <motion.button
            data-hit
            type="button"
            // Keep the selection: a mousedown on a button would otherwise clear it before the click lands.
            onMouseDown={(e) => e.preventDefault()}
            onClick={explain}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={spring}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 12px',
              borderRadius: 999,
              border: `1px solid ${glass.hairline}`,
              background: glass.bg,
              color: glass.text,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              userSelect: 'none',
              whiteSpace: 'nowrap'
            }}
          >
            <MessageSquareText size={14} strokeWidth={2} />
            Explain more
          </motion.button>
        </div>
      )}
    </AnimatePresence>
  )
}
