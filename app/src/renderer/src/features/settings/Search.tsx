/**
 * Feature: settings. Search across settings: the field (sidebar top) and the results that replace the panel while a
 * query is typed. A result opens its panel and flashes the row (nav.ts flashRow). Neutral chrome, no hue.
 */
import { Search, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { riseIn } from '../../core/ui/motion'
import { FINDABLE } from './rows'
import { searchSettings } from './local'
import { flashRow, setQuery, useNav } from './nav'
import { panelOf, type PanelId } from './panels'

export function SearchField(): ReactNode {
  const query = useNav((s) => s.query)
  return (
    <label
      className="flex items-center gap-[8px] px-[10px]"
      style={{ height: 32, borderRadius: radius2.control, background: fill.segmentTrack, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, color: color.label }}
    >
      <Search size={14} strokeWidth={1.8} aria-hidden className="shrink-0" />
      <input
        type="search"
        aria-label="Search settings"
        placeholder="Search settings"
        autoComplete="off"
        spellCheck={false}
        value={query}
        className="min-w-0 flex-1 bg-transparent outline-none placeholder:opacity-70 [&::-webkit-search-cancel-button]:hidden"
        style={{ fontSize: type2.sm, color: color.text }}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          // Esc clears the search first; only an empty field lets Esc through to the sheet.
          if (e.key === 'Escape' && query) {
            e.preventDefault()
            e.stopPropagation()
            setQuery('')
          }
        }}
      />
      {query && (
        <button type="button" aria-label="Clear search" className="grid h-[18px] w-[18px] cursor-pointer place-items-center outline-none" style={{ color: color.label }} onClick={() => setQuery('')}>
          <X size={13} strokeWidth={2} aria-hidden />
        </button>
      )}
    </label>
  )
}

export function SearchResults({ query, onPick }: { query: string; onPick: (panel: PanelId) => void }): ReactNode {
  const hits = useMemo(() => searchSettings(FINDABLE, query), [query])
  return (
    <motion.div data-settings-results className="flex flex-col gap-[16px]" {...riseIn}>
      <header className="flex flex-col gap-[4px]">
        <h2 className="m-0 font-semibold" style={{ fontSize: 22, letterSpacing: -0.2, color: color.text }}>
          Search
        </h2>
        <p className="m-0" style={{ fontSize: type2.sm, color: color.label }}>
          {hits.length ? `${hits.length} ${hits.length === 1 ? 'setting' : 'settings'} for “${query.trim()}”.` : `Nothing matches “${query.trim()}”. Try another word.`}
        </p>
      </header>
      {hits.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-[2px] p-0" role="list">
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className="mg-press flex w-full cursor-pointer items-center gap-[16px] text-left outline-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:[outline-color:var(--focus-ring,currentColor)]"
                style={{ minHeight: 52, padding: '8px 12px', borderRadius: radius2.row }}
                onClick={() => {
                  onPick(h.panel as PanelId)
                  setQuery('')
                  flashRow(h.id)
                }}
              >
                <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
                    {h.label}
                  </span>
                  {h.caption && (
                    <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
                      {h.caption}
                    </span>
                  )}
                </span>
                <span className="shrink-0" style={{ fontSize: type2.xs, color: color.label }}>
                  {panelOf(h.panel as PanelId).label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  )
}
