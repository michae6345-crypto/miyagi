/**
 * Feature: library. The list (mockup Home-Library, 1280x820): sidebar, header with search and New lesson (the one
 * primary), Continue (lessons left mid-way), Ready to run (every cached lesson, filtered by tool), and a card to paste
 * a link. Deviations from the mockup, by rule: no Free plan box (plan A6: hidden), no "Your lessons" nav (the
 * engine's items don't say who built a lesson), and "Saved on this Mac" instead of "Built once, shared with everyone"
 * (A6: never claim cross-user sharing; the library is this Mac's cache).
 */
import { Clock, LibraryBig, Play, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge } from '../../bridge'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { SidebarNav, type NavItem } from '../../core/ui/controls'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { color, fill, radius2, scrim, surface, type2 } from '../../core/theme'
import { Chip, FILTER_TOOLS, Meter, Skeleton, TOOL_NAME, ToolTile, minutesLabel, progressLabel, soft, stepsLabel } from './parts'
import { openDetail, setQuery, setSection, setTool, start, useLibrary, visible, type Section } from './store'

const NAV: NavItem[] = [
  { id: 'library', label: 'Library', icon: LibraryBig },
  { id: 'continue', label: 'Continue', icon: Clock }
]

/** New lesson / Paste a link: the launcher takes a goal or a pasted YouTube link (it builds; the library never does). */
const openLauncher = (): void => bridge.emit('launcher:toggle')

function Sidebar(): ReactNode {
  const section = useLibrary((s) => s.section)
  const tool = useLibrary((s) => s.tool)
  return (
    <aside className="flex shrink-0 flex-col" style={{ width: 232, padding: '16px 12px', borderRight: `1px solid ${surface.border}`, background: scrim.launcher }}>
      {/* The window's own traffic lights sit here (hiddenInset). */}
      <div style={{ height: 16 }} />
      <div className="flex items-center gap-[8px]" style={{ padding: '24px 12px' }}>
        <MiyagiMark size={20} />
        <MiyagiWordmark height={16} className="h-[16px] w-auto" />
      </div>
      <SidebarNav title="Sections" items={NAV} active={section} onSelect={(id) => setSection(id as Section)} />
      <div className="font-semibold uppercase" style={{ padding: '24px 12px 8px', fontSize: type2.micro, letterSpacing: '0.04em', color: color.label }}>
        Tools
      </div>
      <div className="flex flex-col gap-[2px]">
        {FILTER_TOOLS.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={tool === t}
            className="flex cursor-pointer items-center gap-[12px] text-left"
            style={{ height: 36, padding: '0 12px', borderRadius: radius2.control, fontSize: type2.sm, color: tool === t ? color.text : soft, background: tool === t ? fill.navActive : 'transparent' }}
            onClick={() => setTool(tool === t ? 'all' : t)}
          >
            <ToolTile tool={t} size={20} />
            {TOOL_NAME[t]}
          </button>
        ))}
        <div className="flex items-center gap-[12px]" style={{ height: 36, padding: '0 12px', fontSize: type2.sm, color: color.label }}>
          <ToolTile tool="excel" size={20} muted />
          {TOOL_NAME.excel}
          <span className="ml-auto" style={{ fontSize: type2.micro }}>
            Soon
          </span>
        </div>
      </div>
    </aside>
  )
}

function Header(): ReactNode {
  const section = useLibrary((s) => s.section)
  const query = useLibrary((s) => s.query)
  return (
    <header className="flex shrink-0 items-center gap-[16px]" style={{ height: 72, padding: '0 32px', borderBottom: `1px solid ${surface.border}` }}>
      <h1 className="m-0 font-semibold" style={{ fontSize: type2.xl, letterSpacing: '-0.01em' }}>
        {section === 'continue' ? 'Continue' : 'Library'}
      </h1>
      <div className="relative ml-auto" style={{ width: 320 }}>
        <Search aria-hidden size={16} strokeWidth={1.8} className="absolute" style={{ left: 12, top: 10, color: color.label }} />
        <input
          type="search"
          aria-label="Search lessons"
          placeholder="Search lessons"
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full outline-none"
          style={{ height: 36, padding: '0 12px 0 36px', borderRadius: radius2.row, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.sm }}
        />
      </div>
      <PrimaryButton label="New lesson" keyName="launcher" onClick={openLauncher} />
    </header>
  )
}

function SectionHead({ id, title, children }: { id: string; title: string; children?: ReactNode }): ReactNode {
  return (
    <div className="flex items-center gap-[8px]" style={{ marginBottom: 16, minHeight: 32 }}>
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.body, marginRight: 8 }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

const meta = { fontSize: type2.xs, color: color.label } as const

function ContinueCard({ item }: { item: LibraryItem }): ReactNode {
  const p = item.progress!
  const starting = useLibrary((s) => s.starting)
  const canStart = useLibrary((s) => s.caps.start) && item.ready
  const busy = starting === item.id
  return (
    <div className="flex items-center gap-[16px]" style={{ padding: 16, borderRadius: radius2.group, background: fill.group, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
      <ToolTile tool={item.tools[0] ?? 'vscode'} size={48} />
      <button type="button" className="min-w-0 flex-1 cursor-pointer text-left" onClick={() => openDetail(item.id)}>
        <div className="truncate font-medium" style={{ fontSize: type2.md }}>
          {item.title}
        </div>
        <div className="truncate" style={{ ...meta, marginTop: 4 }}>
          {progressLabel(p)}
        </div>
        <div style={{ marginTop: 12 }}>
          <Meter fraction={p.stepIndex / p.total} label={`${item.title}: ${progressLabel(p)}`} />
        </div>
      </button>
      <button
        type="button"
        aria-label={`Resume ${item.title}`}
        title={canStart ? undefined : 'Open the lesson to see why it can’t start'}
        disabled={!canStart || !!starting}
        onClick={() => void start(item.id)}
        className="flex shrink-0 cursor-pointer items-center justify-center disabled:cursor-default"
        style={{ width: 44, height: 44, borderRadius: radius2.round, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, opacity: canStart || busy ? 1 : 0.4 }}
      >
        {busy ? <Spinner size={14} c={color.text} /> : <Play aria-hidden size={14} fill="currentColor" strokeWidth={0} />}
      </button>
    </div>
  )
}

function LessonCard({ item }: { item: LibraryItem }): ReactNode {
  const mins = minutesLabel(item.estMinutes)
  return (
    <button
      type="button"
      data-lesson={item.id}
      onClick={() => openDetail(item.id)}
      className="flex cursor-pointer flex-col gap-[12px] text-left"
      style={{ padding: 16, borderRadius: radius2.group, background: fill.group, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text }}
    >
      <div className="flex w-full items-center gap-[8px]">
        {item.tools.map((t) => (
          <ToolTile key={t} tool={t} />
        ))}
        <span className="ml-auto" style={{ fontSize: type2.xs, color: item.ready ? soft : color.label }}>
          {item.ready ? 'Ready instantly' : 'Not ready yet'}
        </span>
      </div>
      <div className="w-full min-w-0">
        <div className="font-medium" style={{ fontSize: type2.body }}>
          {item.title}
        </div>
        {item.by && <div style={{ ...meta, marginTop: 4 }}>by {item.by}</div>}
      </div>
      <div className="mt-auto flex w-full gap-[16px]" style={{ ...meta, paddingTop: 12, borderTop: `1px solid ${surface.border}` }}>
        <span>{stepsLabel(item.steps)}</span>
        {mins && <span>{mins}</span>}
      </div>
    </button>
  )
}

function PasteCard({ empty }: { empty?: boolean }): ReactNode {
  return (
    <article className="flex flex-col items-start justify-center gap-[12px]" style={{ padding: 16, borderRadius: radius2.group, border: `1px dashed ${surface.border}`, minHeight: 168 }}>
      <div className="font-medium" style={{ fontSize: type2.body }}>
        {empty ? 'No lessons on this Mac yet.' : 'Have a tutorial in mind?'}
      </div>
      <div style={meta}>Paste a YouTube link. miyagi turns it into a lesson.</div>
      <QuietButton label="Paste a link" onClick={openLauncher} />
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

export function Library(): ReactNode {
  const s = useLibrary()
  const { continuing, ready } = visible(s)
  const filtered = s.tool !== 'all' || s.query.trim() !== ''
  const nothing = s.loaded && s.items.length === 0
  return (
    <div className="flex h-full w-full" style={{ color: color.text }}>
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Header />
        <div className="flex min-h-0 flex-1 flex-col gap-[32px] overflow-y-auto" style={{ padding: '24px 32px 32px' }}>
          {!s.loaded ? (
            <div className="grid grid-cols-3 gap-[16px]" aria-busy>
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} h={168} />
              ))}
            </div>
          ) : (
            <>
              {(continuing.length > 0 || s.section === 'continue') && (
                <section aria-labelledby="lib-cont">
                  <SectionHead id="lib-cont" title="Continue">
                    <span className="ml-auto" style={meta}>
                      <StartError />
                      {!s.startError && 'Picks up where you left off'}
                    </span>
                  </SectionHead>
                  {continuing.length > 0 ? (
                    <div className="grid grid-cols-2 gap-[16px]">
                      {continuing.map((i) => (
                        <ContinueCard key={i.id} item={i} />
                      ))}
                    </div>
                  ) : (
                    <div style={meta}>{filtered ? 'No lesson in progress matches.' : 'Nothing in progress. Start a lesson from the library.'}</div>
                  )}
                </section>
              )}
              {s.section === 'library' && (
                <section aria-labelledby="lib-ready">
                  <SectionHead id="lib-ready" title="Ready to run">
                    <Chip label="All" on={s.tool === 'all'} onClick={() => setTool('all')} />
                    {FILTER_TOOLS.map((t) => (
                      <Chip key={t} label={TOOL_NAME[t]} on={s.tool === t} onClick={() => setTool(t)} />
                    ))}
                    <Chip label="Excel, soon" disabled />
                    <span className="ml-auto" style={meta}>
                      Saved on this Mac
                    </span>
                  </SectionHead>
                  <div className="grid grid-cols-3 gap-[16px]">
                    {ready.map((i) => (
                      <LessonCard key={i.id} item={i} />
                    ))}
                    {filtered && ready.length === 0 && !nothing ? (
                      <article className="flex flex-col items-start justify-center gap-[12px]" style={{ padding: 16, borderRadius: radius2.group, border: `1px dashed ${surface.border}`, minHeight: 168 }}>
                        <div className="font-medium" style={{ fontSize: type2.body }}>
                          No lessons match.
                        </div>
                        <QuietButton
                          label="Show all"
                          onClick={() => {
                            setTool('all')
                            setQuery('')
                          }}
                        />
                      </article>
                    ) : (
                      <PasteCard empty={nothing} />
                    )}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}
