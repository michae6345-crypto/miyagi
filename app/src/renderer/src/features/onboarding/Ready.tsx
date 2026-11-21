/**
 * Feature: onboarding. Onb-Setup-Ready, the end of setup: "You're ready", every row green, Start. The "Your first
 * lesson" card shows only when the engine offers one (a cached lesson from library.list); nothing is invented when it
 * doesn't. Start starts that lesson (library.start: zero model calls) or, without one, opens home (the Library). The
 * rows rise in one after another; the launcher hint says how to open miyagi from now on.
 */
import { motion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { NotebookText } from 'lucide-react'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { color, radius2, surface, type2 } from '../../core/theme'
import { staggerList } from '../../core/ui/motion'
import { Row } from './Row'
import type { Row as RowData, Summary } from './rows'
import { SheetHeader } from './Checklist'
import { Footer, LauncherHint, rise, stagger } from './parts'
import { requestSuggestion, useOnboarding } from './store'

const TOOL: Record<LessonTool, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'Terminal', excel: 'Excel' }

/** "6 steps · Jupyter in VS Code · 25 min": only what the item says. */
export function lessonMeta(item: LibraryItem): string {
  const tools = item.tools.filter((t) => TOOL[t])
  const where = tools.includes('jupyter') && tools.includes('vscode') ? 'Jupyter in VS Code' : tools.map((t) => TOOL[t]).join(', ')
  return [`${item.steps} ${item.steps === 1 ? 'step' : 'steps'}`, where, item.estMinutes ? `${item.estMinutes} min` : '']
    .filter(Boolean)
    .join('  ·  ')
}

/**
 * `onStart` / `mark`: the one-window flow (features/shell/flow) hands over to home and shows the bonsai in its strip.
 * `again`: setup opened again over home; the primary is Done (back to home, no lesson), so no first lesson is offered.
 */
export function Ready({ rows, sum, onStart, mark, again }: { rows: RowData[]; sum: Summary; onStart?: () => void; mark?: boolean; again?: boolean }): ReactNode {
  const suggestion = useOnboarding((s) => s.suggestion)
  useEffect(() => requestSuggestion(), [])
  return (
    <div data-onb-view="ready" role="dialog" aria-labelledby="onb-title" className="mx-auto flex h-full w-full max-w-[656px] flex-col p-[32px] pt-[40px]">
      <SheetHeader title="You're ready" rows={rows} sum={sum} brand mark={mark} />
      <motion.p className="m-0 mt-[8px]" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
        miyagi is set up on this Mac.
      </motion.p>
      <motion.div role="list" className="mt-[24px] grid grid-cols-2 gap-[8px]" variants={stagger(0.06)} initial="hidden" animate="shown">
        {rows.map((r) => (
          <motion.div key={r.id} role="none" variants={rise}>
            <Row row={r} variant="compact" />
          </motion.div>
        ))}
      </motion.div>
      {suggestion && !again && (
        <motion.div data-onb-lesson={suggestion.id} className="mt-[24px] flex flex-col gap-[8px]" variants={rise} initial="hidden" animate="shown">
          <span style={{ fontSize: type2.xs, letterSpacing: '0.2px', color: color.label }}>Your first lesson</span>
          <div className="flex items-center gap-[16px] p-[16px]" style={{ borderRadius: radius2.chip, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
            <div className="grid h-[48px] w-[48px] shrink-0 place-items-center" style={{ borderRadius: radius2.card, background: surface.row }}>
              <NotebookText size={22} strokeWidth={1.5} color={color.text} />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-[4px]">
              <span className="truncate" style={{ fontSize: type2.body, fontWeight: 600, color: color.text }}>
                {suggestion.title}
              </span>
              <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
                {lessonMeta(suggestion)}
              </span>
            </div>
          </div>
        </motion.div>
      )}
      <div className="flex-1" />
      <Footer sum={sum} label={again ? 'Done' : 'Start'} onStart={onStart} left={<LauncherHint lead="Open miyagi anytime" />} />
    </div>
  )
}
