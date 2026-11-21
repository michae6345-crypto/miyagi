/**
 * Feature: onboarding (A3). Onb-Setup-Ready: every row green, "You're all set". The "Your first lesson" card shows only
 * when the engine offers one (a cached lesson from library.list); nothing is invented when it doesn't. Start learning
 * starts that lesson (library.start: zero model calls) or, without one, opens the Library (home).
 */
import { useEffect, type ReactNode } from 'react'
import { NotebookText } from 'lucide-react'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { color, radius2, surface, type2 } from '../../core/theme'
import { Row } from './Row'
import type { Row as RowData, Summary } from './rows'
import { SheetHeader } from './Checklist'
import { Footer } from './SetupList'
import { LauncherHint } from './Welcome'
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

export function Ready({ rows, sum }: { rows: RowData[]; sum: Summary }): ReactNode {
  const suggestion = useOnboarding((s) => s.suggestion)
  useEffect(() => requestSuggestion(), [])
  return (
    <div data-onb-view="ready" role="dialog" aria-labelledby="onb-title" className="mx-auto flex h-full w-full max-w-[656px] flex-col p-[32px] pt-[40px]">
      <SheetHeader title="You're all set" rows={rows} sum={sum} brand />
      <div role="list" className="mt-[24px] grid grid-cols-2 gap-[8px]">
        {rows.map((r) => (
          <Row key={r.id} row={r} variant="compact" />
        ))}
      </div>
      {suggestion && (
        <div data-onb-lesson={suggestion.id} className="mt-[24px] flex flex-col gap-[8px]">
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
        </div>
      )}
      <div className="flex-1" />
      <Footer sum={sum} left={<LauncherHint />} />
    </div>
  )
}
