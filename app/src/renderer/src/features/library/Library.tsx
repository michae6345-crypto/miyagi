/**
 * Feature: library. The Lessons page of the home window (features/shell): Continue (lessons left mid-way), Ready to
 * run (every cached lesson, filtered by tool and search), and a card to paste a link. The shell's page header holds
 * the search field (LessonSearch) and New lesson, the one primary on this page. Deviations from the mockup, by rule:
 * no Free plan box (plan A6: hidden), no "Your lessons" split (the engine's items don't say who built a lesson), and
 * "Saved on this Mac" instead of "Built once, shared with everyone" (A6: never claim cross-user sharing).
 *
 * States: loading = three skeleton cards; offline with nothing cached = one calm line; empty = the paste card says
 * "No lessons on this Mac yet."; a filter with no match = "No lessons match." with Show all.
 */
import { CloudOff, Play, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { Spinner } from '../../core/ui/atoms'
import { QuietButton } from '../../core/ui/buttons'
import { color, copy, fill, focus, highlight, radius2, surface, type2 } from '../../core/theme'
import { Press, Ring, Rise } from './motion'
import { Chip, FILTER_TOOLS, Meter, Skeleton, TOOL_NAME, ToolTag, ToolTile, minutesLabel, stepsLabel } from './parts'
import { contLine, continueList, type Cont } from '../dashboard/continue'
import { useDash } from '../dashboard/store'
import { openDetail, setQuery, setTool, start, useLibrary, visible } from './store'

/** The Windows build says the same about its own machine: "this computer", never "this Mac" or the Keychain. */
const ON_MAC = bridge.platform.os === 'mac'
const HERE = ON_MAC ? 'this Mac' : 'this computer'

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

function SectionHead({ id, title, children }: { id: string; title: string; children?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-wrap items-center gap-[8px]" style={{ marginBottom: 16, minHeight: 32 }}>
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.body, marginRight: 8 }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

const meta = { fontSize: type2.xs, color: color.label } as const
/** Cards on the window: a lighter step, a top edge from above, a hairline (UI-POLISH-SPEC section 2, flat). */
const cardStyle = { borderRadius: radius2.group, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` } as const

function ContinueCard({ c }: { c: Cont }): ReactNode {
  const item = useLibrary((s) => s.items.find((i) => i.id === c.libraryId))
  const starting = useLibrary((s) => s.starting)
  const canStart = useLibrary((s) => s.caps.start) && (item?.ready ?? true)
  const busy = starting === c.libraryId
  return (
    <div className="flex items-center gap-[16px]" style={{ ...cardStyle, padding: 16 }}>
      <ToolTile tool={item?.tools[0] ?? 'vscode'} size={48} />
      <button type="button" className="min-w-0 flex-1 cursor-pointer text-left outline-offset-4 focus-visible:outline-2 focus-visible:outline-solid" style={{ outlineColor: focus.dark, borderRadius: radius2.control }} onClick={() => openDetail(c.libraryId)}>
        <div className="truncate font-medium" style={{ fontSize: type2.md }}>
          {c.title}
        </div>
        <div className="truncate" style={{ ...meta, marginTop: 4 }}>
          {contLine(c)}
        </div>
        <div style={{ marginTop: 12 }}>
          <Meter fraction={c.passed / c.total} label={`${c.title}: ${contLine(c)}`} />
        </div>
      </button>
      <Press
        aria-label={`Continue ${c.title}`}
        title={canStart ? undefined : 'Open the lesson to see why it can’t start'}
        disabled={!canStart || !!starting}
        onClick={() => void start(c.libraryId)}
        className="flex shrink-0 items-center justify-center"
        style={{ width: 44, height: 44, borderRadius: radius2.round, background: surface.row, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}`, color: color.text, opacity: canStart || busy ? 1 : 0.4 }}
      >
        <span className="relative flex">{busy ? <Spinner size={14} c={color.text} /> : <Play aria-hidden size={14} fill="currentColor" strokeWidth={0} />}</span>
      </Press>
    </div>
  )
}

function LessonCard({ item }: { item: LibraryItem }): ReactNode {
  const mins = minutesLabel(item.estMinutes)
  return (
    <Press large data-lesson={item.id} onClick={() => openDetail(item.id)} className="flex h-full w-full flex-col gap-[12px]" style={{ ...cardStyle, padding: 16, color: color.text }}>
      <span className="relative flex w-full items-center gap-[8px]">
        {item.tools.map((t) => (
          <ToolTag key={t} tool={t} />
        ))}
        {!item.ready && (
          <span className="ml-auto" style={{ fontSize: type2.xs, color: color.label }}>
            Not ready yet
          </span>
        )}
      </span>
      <span className="relative block w-full min-w-0">
        <span className="block font-medium" style={{ fontSize: type2.body }}>
          {item.title}
        </span>
        {item.by && <span className="block" style={{ ...meta, marginTop: 4 }}>by {item.by}</span>}
      </span>
      <span className="relative mt-auto flex w-full gap-[16px]" style={{ ...meta, paddingTop: 12, borderTop: `1px solid ${surface.border}` }}>
        <span>{stepsLabel(item.steps)}</span>
        {mins && <span>{mins}</span>}
      </span>
    </Press>
  )
}

function PasteCard({ empty }: { empty?: boolean }): ReactNode {
  return (
    <article className="flex h-full flex-col items-start justify-center gap-[12px]" style={{ padding: 16, borderRadius: radius2.group, border: `1px dashed ${surface.border}`, minHeight: 168 }}>
      <div className="font-medium" style={{ fontSize: type2.body }}>
        {empty ? `No lessons on ${HERE} yet.` : 'Have a tutorial in mind?'}
      </div>
      <div style={meta}>Paste a YouTube link. {copy.name} turns it into a lesson.</div>
      <Ring>
        <QuietButton label="Paste a link" onClick={openLauncher} />
      </Ring>
    </article>
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
    <div data-lessons className="flex flex-col gap-[32px] @container" style={{ padding: '24px 32px 32px', color: color.text }}>
      {!s.loaded ? (
        <div className="grid grid-cols-1 gap-[16px] @min-[640px]:grid-cols-2 @min-[900px]:grid-cols-3" aria-busy aria-label="Loading your lessons">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} h={168} />
          ))}
        </div>
      ) : offline ? (
        <Rise i={0}>
          <section role="status" data-lessons-offline className="flex items-center gap-[16px]" style={{ ...cardStyle, padding: '20px 24px' }}>
            <span className="flex shrink-0 items-center justify-center" style={{ width: 40, height: 40, borderRadius: radius2.card, background: fill.chip }}>
              <CloudOff aria-hidden size={18} strokeWidth={1.8} style={{ color: color.label }} />
            </span>
            <span className="flex min-w-0 flex-col gap-[2px]">
              <span className="font-medium" style={{ fontSize: type2.sm }}>
                {copy.name} is offline.
              </span>
              <span style={meta}>Your saved lessons show here when it connects.</span>
            </span>
          </section>
        </Rise>
      ) : (
        <>
          {continuing.length > 0 && (
            <Rise i={0}><section aria-labelledby="lib-cont">
              <SectionHead id="lib-cont" title="Continue">
                <span className="ml-auto" style={meta}>
                  <StartError />
                </span>
              </SectionHead>
              <div className="grid grid-cols-1 gap-[16px] @min-[760px]:grid-cols-2">
                {continuing.map((c) => (
                  <ContinueCard key={c.libraryId} c={c} />
                ))}
              </div>
            </section></Rise>
          )}
          <Rise i={1}><section aria-labelledby="lib-ready">
            <SectionHead id="lib-ready" title="Ready to run">
              <Chip label="All" on={s.tool === 'all'} onClick={() => setTool('all')} />
              {FILTER_TOOLS.map((t) => (
                <Chip key={t} label={TOOL_NAME[t]} on={s.tool === t} onClick={() => setTool(t)} />
              ))}
              <span className="ml-auto" style={meta}>
                {continuing.length === 0 && s.startError ? <StartError /> : null}
              </span>
            </SectionHead>
            <div className="grid grid-cols-1 gap-[16px] @min-[640px]:grid-cols-2 @min-[900px]:grid-cols-3">
              {ready.map((i) => (
                <LessonCard key={i.id} item={i} />
              ))}
              {filtered && ready.length === 0 && !nothing ? (
                <article className="flex flex-col items-start justify-center gap-[12px]" style={{ padding: 16, borderRadius: radius2.group, border: `1px dashed ${surface.border}`, minHeight: 168 }}>
                  <div className="font-medium" style={{ fontSize: type2.body }}>
                    No lessons match.
                  </div>
                  <Ring>
                    <QuietButton
                      label="Show all"
                      onClick={() => {
                        setTool('all')
                        setQuery('')
                      }}
                    />
                  </Ring>
                </article>
              ) : (
                <PasteCard empty={nothing} />
              )}
            </div>
          </section></Rise>
        </>
      )}
    </div>
  )
}
