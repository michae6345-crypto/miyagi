/**
 * Feature: library. The Lessons page of the home window (features/shell): Continue (lessons left mid-way), Ready to
 * run (every cached lesson, filtered by tool and search), and a last row to paste a link. Redraft (Adrian, Nov 21):
 * plain rows on the content panel (title, then the tool in words, steps and minutes), no cards, tiles or pills. The page
 * header (LessonsHeader, rendered by the shell above the scroller) holds the title and the search field, on the same
 * column as the list. Deviations from the mockup, by rule:
 * no Free plan box (plan A6: hidden), no "Your lessons" split (the engine's items don't say who built a lesson), and
 * "Saved on this Mac" instead of "Built once, shared with everyone" (A6: never claim cross-user sharing).
 *
 * States: loading = three skeleton cards; offline with nothing cached = one calm line; empty = the paste card says
 * "No lessons on this Mac yet."; a filter with no match = "No lessons match." with Show all.
 */
import { CloudOff, Play, Plus, Search } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { Empty, Row, RowChevron } from '../shell/ui'
import { color, copy, fill, focus, highlight, radius2, surface, type2 } from '../../core/theme'
import { Column, Pane, rhythm } from './layout'
import { Ring, Rise } from './motion'
import { FILTER_TOOLS, Skeleton, TOOL_NAME, minutesLabel, stepsLabel } from './parts'
import { contLine, continueList, type Cont } from '../dashboard/continue'
import { useDash } from '../dashboard/store'
import { openDetail, setQuery, setTool, start, useLibrary, visible } from './store'

/** New lesson / Paste a link: the launcher takes a goal or a pasted YouTube link (it builds; the library never does). */
export const openLauncher = (): void => bridge.emit('launcher:toggle')

/** The Lessons page's search field (the shell puts it in the page header). A well: pressed into the header. */
export function LessonSearch(): ReactNode {
  const query = useLibrary((s) => s.query)
  return (
    <div data-no-drag className="relative min-w-0" style={{ width: 280 }}>
      <Search aria-hidden size={16} strokeWidth={1.8} className="pointer-events-none absolute" style={{ left: 12, top: 10, color: color.label }} />
      <input
        type="search"
        aria-label="Search lessons"
        placeholder="Search lessons"
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          // Esc clears the search first (never the window).
          if (e.key === 'Escape' && query) {
            e.preventDefault()
            e.stopPropagation()
            setQuery('')
          }
        }}
        className="w-full outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
        style={{ height: 36, padding: '0 12px 0 36px', borderRadius: radius2.row, background: surface.well, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.well}`, color: color.text, fontSize: type2.sm, outlineColor: focus.dark }}
      />
    </div>
  )
}

/**
 * The Lessons page header: the title and the search field on the page's own column (layout.tsx), so the title's left
 * edge is the list's left edge and the search field's right edge is the list's right edge at every window size (the
 * shell's generic header pads 40 from the pane and drifted 344 px off the list in full screen). The whole 76 px strip
 * drags the window; the search field opts out. The shell renders this above the page's scroller in place of its own
 * header for the Lessons page (Shell.tsx Header: `if (page === 'lessons') return <LessonsHeader title={label} />`).
 */
export function LessonsHeader({ title = 'Lessons' }: { title?: string }): ReactNode {
  return (
    <Pane data-drag data-lessons-header className="shrink-0">
      <header>
        {/* 76 tall, the row's bottom 8 above the scroller: with the list's 24 top padding, title to first section is 32. */}
        <Column className="flex items-end" style={{ height: 76, paddingBottom: 8 }}>
          <div className="flex min-h-[36px] w-full min-w-0 items-center gap-[16px]">
            <h1 className="m-0 min-w-0 truncate font-semibold" style={{ fontSize: 22, lineHeight: '28px', letterSpacing: '-0.015em', color: color.text }}>
              {title}
            </h1>
            <div data-no-drag className="ml-auto flex min-w-0 items-center">
              <LessonSearch />
            </div>
          </div>
        </Column>
      </header>
    </Pane>
  )
}

const meta = { fontSize: type2.xs, color: color.label } as const

/** A section header: the label (spec section 6: 13/18, semibold, secondary), then what the section puts beside it. */
function Head({ id, title, children }: { id: string; title: string; children?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-wrap items-center gap-[8px]" style={{ marginBottom: 8, minHeight: 32 }}>
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.sm, lineHeight: '18px', marginRight: 8, color: color.label }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

const titleText = { fontSize: type2.md, color: color.text } as const

/**
 * Where a lesson stands, as Home's Continue card shows it: one continuous hairline, a fixed width so every row's line
 * starts and ends at the same x (round 3: the segmented bars were as wide as their step counts and never lined up).
 */
function ProgressLine({ done, total }: { done: number; total: number }): ReactNode {
  const f = total ? Math.max(0, Math.min(1, done / total)) : 0
  return (
    <span role="img" aria-label={`${done} of ${total} steps done`} className="relative block shrink-0 overflow-hidden" style={{ width: 88, height: 3, borderRadius: radius2.round, background: fill.hairline }}>
      <span className="absolute inset-y-0 left-0 block" style={{ width: `${f * 100}%`, background: color.text, borderRadius: radius2.round }} />
    </span>
  )
}

/** A lesson left mid-way: title, where it stands, its progress, and Continue (the first one is the page's primary). */
function ContinueRow({ c, first }: { c: Cont; first: boolean }): ReactNode {
  const item = useLibrary((s) => s.items.find((i) => i.id === c.libraryId))
  const starting = useLibrary((s) => s.starting)
  const canStart = useLibrary((s) => s.caps.start) && (item?.ready ?? true)
  const busy = starting === c.libraryId
  const Btn = first ? PrimaryButton : QuietButton
  return (
    <div data-continue={c.libraryId} className="flex items-center gap-[12px]" style={{ paddingRight: 10 }}>
      <Row onClick={() => openDetail(c.libraryId)} label={`${c.title}. ${contLine(c)}. Open its preview.`} style={{ flex: 1, minWidth: 0, padding: '12px 10px' }}>
        <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
          <span className="truncate" style={titleText}>
            {c.title}
          </span>
          <span className="truncate" style={meta}>
            {contLine(c)}
          </span>
        </span>
        <span className="relative hidden items-center @min-[640px]/pane:flex" style={{ marginRight: 8 }}>
          <ProgressLine done={c.passed} total={c.total} />
        </span>
      </Row>
      <Ring>
        <Btn label="Continue" icon={Play} busy={busy} disabled={!canStart || (!!starting && !busy)} title={canStart ? undefined : 'Open the lesson to see why it can\u2019t start'} onClick={() => void start(c.libraryId)} />
      </Ring>
    </div>
  )
}

/** One saved lesson: its title, then the tool in words, steps and minutes. Opens the preview. */
function LessonRow({ item }: { item: LibraryItem }): ReactNode {
  const mins = minutesLabel(item.estMinutes)?.replace('About ', '')
  const line = [item.tools.map((t) => TOOL_NAME[t]).join(', '), stepsLabel(item.steps), mins, item.by ? `by ${item.by}` : '', !item.ready ? 'Not ready yet' : ''].filter(Boolean).join(' \u00b7 ')
  return (
    <Row onClick={() => openDetail(item.id)} label={`${item.title}. ${line}. Open its preview.`} data={{ 'data-lesson': item.id }} style={{ padding: '12px 10px' }}>
      <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="truncate" style={titleText}>
          {item.title}
        </span>
        <span className="truncate" style={meta}>
          {line}
        </span>
      </span>
      <RowChevron />
    </Row>
  )
}

/** The last row of the list: paste a YouTube link (the launcher builds it). */
function PasteRow(): ReactNode {
  return (
    <Row onClick={openLauncher} label="Paste a YouTube link to build a lesson" data={{ 'data-lessons-paste': '' }} style={{ padding: '16px 10px' }}>
      <Plus aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.label, marginLeft: -2 }} />
      <span className="relative flex min-w-0 flex-1 items-baseline gap-[8px]">
        <span style={{ fontSize: type2.md, color: color.text }}>Paste a YouTube link</span>
        <span className="truncate" style={meta}>
          {copy.name} turns it into a lesson
        </span>
      </span>
    </Row>
  )
}

function StartError(): ReactNode {
  const err = useLibrary((s) => s.startError)
  if (!err) return null
  return (
    <span role="status" style={meta}>
      {err.text}
    </span>
  )
}

const list = { margin: 0, padding: 0, listStyle: 'none', marginInline: -10 } as const

/**
 * A list item whose hairline runs exactly under the text column (the list sits 10px outside it so a row's hover fill
 * can bleed past the text; the item steps back in, and its row steps out again with marginInline -10).
 */
const divided = (rule: boolean): CSSProperties => ({ marginInline: 10, borderTop: rule ? `1px solid ${fill.hairline}` : undefined })

/** The tool filter: a small segmented control (chrome: neutral, the selected segment lifts). */
function ToolFilter(): ReactNode {
  const tool = useLibrary((s) => s.tool)
  return (
    <div role="group" aria-label="Filter by tool" className="ml-auto flex items-center" style={{ padding: 2, gap: 2, borderRadius: radius2.row, background: fill.segmentTrack }}>
      {(['all', ...FILTER_TOOLS] as const).map((t) => {
        const on = tool === t
        return (
          <button
            key={t}
            type="button"
            aria-pressed={on}
            onClick={() => setTool(t)}
            className="cursor-pointer outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
            style={{ height: 26, padding: '0 10px', borderRadius: radius2.control, fontSize: type2.xs, fontWeight: 500, color: on ? color.text : color.label, background: on ? fill.segmentOn : 'transparent', boxShadow: on ? `${highlight.topSoft}, var(--e-raised)` : undefined, outlineColor: focus.dark }}
          >
            {t === 'all' ? 'All' : TOOL_NAME[t]}
          </button>
        )
      })}
    </div>
  )
}

/** The Lessons page body (the shell scrolls it and keeps its scroll). */
export function Lessons(): ReactNode {
  const s = useLibrary()
  const connected = useLesson((st) => st.connected)
  // The page always shows the whole list: Continue and Ready to run together.
  const data = useDash((st) => st.data)
  const shown = visible({ ...s, section: 'library' })
  const q = s.query.trim().toLowerCase()
  const continuing = continueList(data, s.items).filter((c) => !q || c.title.toLowerCase().includes(q)).filter((c) => s.tool === 'all' || (s.items.find((i) => i.id === c.libraryId)?.tools.includes(s.tool) ?? false))
  const going = new Set(continuing.map((c) => c.libraryId))
  const ready = shown.ready.filter((i) => !going.has(i.id))
  const filtered = s.tool !== 'all' || s.query.trim() !== ''
  const nothing = s.loaded && s.items.length === 0
  const offline = nothing && !connected
  return (
    // The shared 720 column (layout.tsx), centered in the pane like Home and the preview: at full screen the rows no
    // longer run 1400 px from the title to its chevron. Sections sit 40 apart, the page ends 64 under the last row.
    <Pane data-lessons style={{ color: color.text }}>
      <Column className="flex flex-col" style={{ gap: rhythm.section, paddingTop: 24, paddingBottom: rhythm.bottom }}>
        {!s.loaded ? (
          <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading your lessons">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} h={48} />
            ))}
          </div>
        ) : offline ? (
          <Empty mark={<CloudOff aria-hidden size={28} strokeWidth={1.6} style={{ color: color.label }} />} title={`${copy.name} is offline.`} line="Your saved lessons show here when it connects." />
        ) : nothing ? (
          <Empty
            mark={<MiyagiMark size={44} />}
            title="No lessons yet"
            line="Ask for a goal or paste a YouTube link."
            action={
              <Ring>
                <PrimaryButton label="New lesson" keyName="launcher" onClick={openLauncher} />
              </Ring>
            }
          />
        ) : (
          <>
            {continuing.length > 0 && (
              <Rise i={0}>
                <section aria-labelledby="lib-cont">
                  <Head id="lib-cont" title="In progress">
                    <span className="ml-auto">
                      <StartError />
                    </span>
                  </Head>
                  <ul style={list}>
                    {continuing.map((c, i) => (
                      <li key={c.libraryId}>
                        <ContinueRow c={c} first={i === 0} />
                      </li>
                    ))}
                  </ul>
                </section>
              </Rise>
            )}
            <Rise i={1}>
              <section aria-labelledby="lib-ready">
                <Head id="lib-ready" title="Ready to run">
                  <ToolFilter />
                  {continuing.length === 0 && s.startError ? <StartError /> : null}
                </Head>
                <ul style={list}>
                  {ready.map((i, n) => (
                    <Rise key={i.id} as="li" i={n} style={divided(n > 0)}>
                      <div style={{ marginInline: -10 }}>
                        <LessonRow item={i} />
                      </div>
                    </Rise>
                  ))}
                  {filtered && ready.length === 0 ? (
                    <li className="flex items-center gap-[12px]" style={{ padding: '12px 10px' }}>
                      <span style={{ ...meta, fontSize: type2.sm }}>No lessons match.</span>
                      <Ring>
                        <QuietButton
                          label="Show all"
                          onClick={() => {
                            setTool('all')
                            setQuery('')
                          }}
                        />
                      </Ring>
                    </li>
                  ) : (
                    <li style={divided(ready.length > 0)}>
                      <div style={{ marginInline: -10 }}>
                        <PasteRow />
                      </div>
                    </li>
                  )}
                </ul>
              </section>
            </Rise>
          </>
        )}
      </Column>
    </Pane>
  )
}
