/**
 * Feature: library. The Lessons page of the home window (features/shell): Continue (lessons left mid-way), Ready to
 * run (every cached lesson, filtered by tool and search), and a last row to paste a link. Redraft (Adrian, Nov 21):
 * lists of rows on the content panel, no grid of bordered cards; each lesson keeps its tool's pastel tile. The shell's page header holds
 * the search field (LessonSearch) and New lesson, the one primary on this page. Deviations from the mockup, by rule:
 * no Free plan box (plan A6: hidden), no "Your lessons" split (the engine's items don't say who built a lesson), and
 * "Saved on this Mac" instead of "Built once, shared with everyone" (A6: never claim cross-user sharing).
 *
 * States: loading = three skeleton cards; offline with nothing cached = one calm line; empty = the paste card says
 * "No lessons on this Mac yet."; a filter with no match = "No lessons match." with Show all.
 */
import { ChevronRight, CloudOff, Play, Plus, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { Empty, LessonTile, Row, StepBar } from '../shell/ui'
import { color, copy, fill, focus, highlight, radius2, surface, type2 } from '../../core/theme'
import { Ring, Rise } from './motion'
import { FILTER_TOOLS, Skeleton, TOOL_NAME, ToolTag, minutesLabel, stepsLabel } from './parts'
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

const meta = { fontSize: type2.xs, color: color.label } as const

/** A section header: the title, then whatever the section puts beside it (filters, a note). */
function Head({ id, title, children }: { id: string; title: string; children?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-wrap items-center gap-[6px]" style={{ marginBottom: 6, minHeight: 32 }}>
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.sm, marginRight: 10, color: color.text }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

/** A lesson left mid-way: one row with its tile, where it stands, its steps as a bar and a Continue. */
function ContinueRow({ c, first }: { c: Cont; first: boolean }): ReactNode {
  const item = useLibrary((s) => s.items.find((i) => i.id === c.libraryId))
  const starting = useLibrary((s) => s.starting)
  const canStart = useLibrary((s) => s.caps.start) && (item?.ready ?? true)
  const busy = starting === c.libraryId
  const Btn = first ? PrimaryButton : QuietButton
  return (
    <div data-continue={c.libraryId} className="flex items-center gap-[12px]" style={{ padding: '4px 10px 4px 0' }}>
      <Row onClick={() => openDetail(c.libraryId)} label={`${c.title}. ${contLine(c)}. Open its preview.`} style={{ flex: 1, minWidth: 0, padding: '10px 10px' }}>
        <span className="relative flex">
          <LessonTile tools={item?.tools} id={c.libraryId} size={36} />
        </span>
        <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
          <span className="truncate font-medium" style={{ fontSize: type2.body, color: color.text }}>
            {c.title}
          </span>
          <span className="truncate" style={meta}>
            {contLine(c)}
          </span>
        </span>
        <span className="relative hidden @[620px]:flex">
          <StepBar done={c.passed} total={c.total} width={128} />
        </span>
      </Row>
      <Ring>
        <Btn label="Continue" icon={Play} busy={busy} disabled={!canStart || (!!starting && !busy)} title={canStart ? undefined : 'Open the lesson to see why it can\u2019t start'} onClick={() => void start(c.libraryId)} />
      </Ring>
    </div>
  )
}

/** One saved lesson: tile, title (and who made it), its tools, its length. Opens the preview. */
function LessonRow({ item }: { item: LibraryItem }): ReactNode {
  const mins = minutesLabel(item.estMinutes)?.replace('About ', '')
  const length = [stepsLabel(item.steps), mins].filter(Boolean).join(' \u00b7 ')
  const sub = [item.by ? `by ${item.by}` : '', !item.ready ? 'Not ready yet' : ''].filter(Boolean).join(' \u00b7 ')
  return (
    <Row onClick={() => openDetail(item.id)} label={`${item.title}. ${stepsLabel(item.steps)}. Open its preview.`} data={{ 'data-lesson': item.id }} style={{ padding: '10px 10px' }}>
      <span className="relative flex">
        <LessonTile tools={item.tools} id={item.id} size={36} />
      </span>
      <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="truncate font-medium" style={{ fontSize: type2.body, color: color.text }}>
          {item.title}
        </span>
        <span className="truncate" style={meta}>
          {sub || length}
        </span>
      </span>
      <span className="relative hidden shrink-0 gap-[6px] @[560px]:flex">
        {item.tools.map((t) => (
          <ToolTag key={t} tool={t} />
        ))}
      </span>
      <span className="relative hidden shrink-0 text-right tabular-nums @[720px]:block" style={{ ...meta, width: 120 }}>
        {length}
      </span>
      <ChevronRight aria-hidden size={14} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.faint }} />
    </Row>
  )
}

/** The last row of the list: paste a YouTube link (the launcher builds it). */
function PasteRow(): ReactNode {
  return (
    <Row onClick={openLauncher} label="Paste a YouTube link" data={{ 'data-lessons-paste': '' }} style={{ padding: '10px 10px' }}>
      <span aria-hidden className="relative inline-flex shrink-0 items-center justify-center" style={{ width: 36, height: 36, borderRadius: radius2.control, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.label }}>
        <Plus size={16} strokeWidth={1.8} />
      </span>
      <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="font-medium" style={{ fontSize: type2.body, color: color.text }}>
          Paste a YouTube link
        </span>
        <span style={meta}>{copy.name} turns it into a lesson.</span>
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
    <div data-lessons className="flex flex-col gap-[30px] @container" style={{ padding: '8px 40px 48px', color: color.text }}>
      {!s.loaded ? (
        <div className="flex flex-col gap-[10px]" aria-busy aria-label="Loading your lessons">
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
                  <Rise key={i.id} as="li" i={n}>
                    <LessonRow item={i} />
                  </Rise>
                ))}
                {filtered && ready.length === 0 ? (
                  <li className="flex items-center gap-[12px]" style={{ padding: '14px 10px' }}>
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
                  <li>
                    <PasteRow />
                  </li>
                )}
              </ul>
            </section>
          </Rise>
        </>
      )}
    </div>
  )
}
