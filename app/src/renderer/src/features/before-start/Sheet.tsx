/**
 * Feature: before-start. Mockup 03, "Before you start": a sheet that drops out of the notch before step 1 of a
 * "Just teach me" lesson (and again from the drawer's "Needs: ..." chip). Every part is optional and hides when
 * the engine didn't send it (lesson.ready build / flow / prerequisites / learnFirst):
 *   - What you'll build: build.summary, then the outcome ("what it does when it's done") in a quieter line.
 *   - How it works: the flow boxes, left to right (./Flow.tsx).
 *   - You'll need: each prerequisite with its status. Passed = the green tick + evidence ("Passed in Python
 *     Calculator"); unknown = a gray ring + "Not seen yet" (never a failure, never red or amber).
 *   - Learn first: the mini-lessons for prerequisites not passed yet; clicking one starts it.
 *   - Buttons: "Learn <first mini-lesson> first" (neutral) and "Start the lesson" (the one white primary).
 *
 * Learn first sends learn {query: title, mode: "lesson"} ("video" kind: mode "video"), per the contract's
 * LearnFirstItem note; the engine ends the current lesson itself. Start only closes the sheet: the engine already
 * runs step 1 (Michael's call pending; see the PR).
 * Island tokens (color / fill): the sheet is born from the black notch island like every card.
 */
import type { CSSProperties, ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, MousePointerClick, NotebookText, Play, type LucideIcon } from 'lucide-react'
import type { LearnFirstItem, Prerequisite } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson, noteLearnMode } from '../../core/lesson'
import { color, fill } from '../../core/theme'
import { CloseButton, PrimaryButton } from '../../core/ui/atoms'
import { FlowDiagram } from './Flow'
import { closeBeforeStart, lessonDone, startLesson } from './store'

export const SHEET_W = 520
const PAD = 22

const LEARN_KIND: Record<LearnFirstItem['kind'], { icon: LucideIcon; label: string }> = {
  notebook: { icon: NotebookText, label: 'Notebook' },
  interactive: { icon: MousePointerClick, label: 'Interactive' },
  video: { icon: Play, label: 'Video' },
  read: { icon: BookOpen, label: 'Read' }
}

/** Start a mini-lesson for a prerequisite (contract LearnFirstItem: learn {query: title, mode}). */
function learn(item: LearnFirstItem): void {
  noteLearnMode(undefined)
  bridge.send(cmd('learn', { query: item.title, mode: item.kind === 'video' ? 'video' : 'lesson' }))
  closeBeforeStart()
}

export function Sheet(): ReactNode {
  const l = useLesson(
    useShallow((s) => ({
      title: s.lesson?.title ?? '',
      build: s.lesson?.build,
      flow: s.lesson?.flow,
      prerequisites: s.lesson?.prerequisites,
      learnFirst: s.lesson?.learnFirst,
      stepIndex: s.steps.find((x) => x.id === s.stepId)?.index,
      done: lessonDone(s)
    }))
  )
  const needs = l.prerequisites ?? []
  const learnFirst = l.learnFirst ?? []
  const first = learnFirst[0]
  return (
    <div data-sheet="before-start" style={{ padding: `18px ${PAD}px 18px` }}>
      <div className="flex items-start gap-[10px]">
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-semibold leading-[16px]" style={{ color: color.label }}>
            Your lesson
          </div>
          <div className="mt-[2px] line-clamp-2 text-[19px] font-semibold leading-[24px] tracking-[-0.01em]">{l.title}</div>
        </div>
        <CloseButton />
      </div>

      {l.build && (
        <Section title="What you'll build">
          <div className="text-[14px] leading-[20px]" style={{ color: color.text }}>
            {l.build.summary}
          </div>
          {l.build.outcome && (
            <div className="mt-[4px] text-[13px] leading-[18px]" style={{ color: color.label }}>
              {l.build.outcome}
            </div>
          )}
        </Section>
      )}

      {!!l.flow?.length && (
        <Section title="How it works">
          <FlowDiagram flow={l.flow} currentIndex={l.stepIndex} tone={{ text: color.text, faint: color.faint, box: fill.field, border: fill.rule, current: color.text }} />
        </Section>
      )}

      {needs.length > 0 && (
        <Section title="You'll need">
          <div className="flex flex-col gap-[8px]">
            {needs.map((p) => (
              <NeedRow key={p.id} need={p} done={l.done} />
            ))}
          </div>
        </Section>
      )}

      {learnFirst.length > 0 && (
        <Section title="Learn first">
          <div className="flex flex-col gap-[4px]">
            {learnFirst.map((m) => (
              <LearnRow key={`${m.covers}:${m.title}`} item={m} />
            ))}
          </div>
        </Section>
      )}

      <div className="mt-[18px] flex items-center justify-end gap-[8px]">
        {first && (
          <button
            type="button"
            data-part="learn-first"
            className="flex h-[30px] max-w-[260px] cursor-pointer items-center truncate rounded-full px-[13px] text-[13px] font-medium"
            style={{ background: fill.button, color: color.text }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => learn(first)}
          >
            <span className="truncate">Learn {first.title} first</span>
          </button>
        )}
        <PrimaryButton label="Start the lesson" onClick={startLesson} />
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }): ReactNode {
  return (
    <div className="mt-[16px]">
      <div className="mb-[7px] text-[12px] font-semibold leading-[16px]" style={{ color: color.label }}>
        {title}
      </div>
      {children}
    </div>
  )
}

/** done: the lesson's steps have all passed, so an unseen prerequisite reads "Used in this lesson", not "Not seen yet". */
function NeedRow({ need, done }: { need: Prerequisite; done?: boolean }): ReactNode {
  const passed = need.status === 'passed'
  return (
    <div data-need={need.id} data-status={need.status} className="flex items-start gap-[10px]">
      {passed ? (
        <span className="mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full" style={{ background: color.green }}>
          <Check size={11} strokeWidth={2.6} style={{ color: color.onAccent }} />
        </span>
      ) : (
        <span className="mt-[1px] h-[18px] w-[18px] shrink-0 rounded-full border-[1.5px]" style={{ borderColor: fill.ring }} />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-[10px]">
          <span className="truncate text-[13.5px] font-semibold leading-[18px]">{need.title}</span>
          <span className="shrink-0 text-[12px] leading-[16px]" style={{ color: passed ? color.label : color.faint }}>
            {passed ? need.evidence || 'Passed' : done ? 'Used in this lesson' : 'Not seen yet'}
          </span>
        </div>
        {need.why && (
          <div className="text-[12.5px] leading-[17px]" style={{ color: color.faint }}>
            {need.why}
          </div>
        )}
      </div>
    </div>
  )
}

function LearnRow({ item }: { item: LearnFirstItem }): ReactNode {
  const k = LEARN_KIND[item.kind] ?? LEARN_KIND.read
  const I = k.icon
  return (
    <button
      type="button"
      data-learn={item.covers}
      className="flex h-[36px] w-full cursor-pointer items-center gap-[10px] rounded-[10px] px-[8px] text-left hover:bg-[var(--sheet-hover)]"
      style={{ '--sheet-hover': fill.chipHover } as CSSProperties}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => learn(item)}
    >
      <span className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-[7px]" style={{ background: fill.field, color: color.label }}>
        <I size={13} strokeWidth={1.8} />
      </span>
      <span className="min-w-0 flex-1 truncate text-[13.5px] leading-[18px]">{item.title}</span>
      <span className="shrink-0 text-[12px]" style={{ color: color.faint }}>
        {k.label} · {item.minutes} min
      </span>
    </button>
  )
}
