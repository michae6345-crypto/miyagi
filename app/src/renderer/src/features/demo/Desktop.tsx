/**
 * Feature: demo. The learner's screen for the offline demo: a macOS menu bar and VS Code (Dark Modern) with nn.py
 * and the terminal docked right. It is the "other app" under miyagi, so it uses VS Code's own colors, not the brand's.
 *
 * Drawn at the stage's 1600×1000 points from lesson.ts's geometry, so the engine's spotlight rects land on the
 * exact lines. Sits under every overlay layer (z -100) and takes no pointer events.
 */
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { Blocks, ChevronDown, ChevronRight, Files, GitBranch, Play, Search, Wifi, BatteryFull } from 'lucide-react'
import { FILE_NAME, FOLDER, G, codeX, lineTop, termLineTop } from './lesson'
import { highlight } from './syntax'
import { PROMPT, useDesk } from './store'

/** VS Code Dark Modern. */
const vs = {
  bg: '#1F1F1F',
  side: '#181818',
  border: '#2B2B2B',
  text: '#CCCCCC',
  muted: '#9D9D9D',
  faint: '#6E7681',
  lineNo: '#6E7681',
  lineNoActive: '#CCCCCC',
  caret: '#AEAFAD',
  current: '#282828',
  selection: '#3A3D41',
  menu: '#232325'
} as const

const mono: CSSProperties = { fontFamily: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace', fontSize: 13, lineHeight: `${G.lineH}px` }
const ui: CSSProperties = { fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif' }

export function Desktop(): ReactNode {
  return (
    <div className="pointer-events-none absolute left-0 top-0 select-none overflow-hidden" style={{ width: 1600, height: 1000, background: vs.bg, ...ui }}>
      <MenuBar />
      <TitleBar />
      <ActivityBar />
      <Explorer />
      <Editor />
      <Terminal />
      <StatusBar />
    </div>
  )
}

function useClock(): string {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(id)
  }, [])
  const day = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).replace(',', '')
  const time = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${day} ${time}`
}

function MenuBar(): ReactNode {
  const clock = useClock()
  return (
    <div className="absolute left-0 top-0 flex w-full items-center px-[18px] text-[13px]" style={{ height: G.menuH, background: vs.menu, color: '#E6E6E6' }}>
      <span className="mr-[20px] font-semibold">Code</span>
      {['File', 'Edit', 'Selection', 'View', 'Go', 'Run', 'Terminal', 'Window', 'Help'].map((m) => (
        <span key={m} className="mr-[18px] opacity-90">
          {m}
        </span>
      ))}
      <span className="ml-auto flex items-center gap-[16px] opacity-90">
        <BatteryFull size={17} />
        <Wifi size={15} />
        <Search size={14} />
        <span>{clock}</span>
      </span>
    </div>
  )
}

function TitleBar(): ReactNode {
  const open = useDesk((d) => d.open)
  return (
    <div
      className="absolute left-0 flex w-full items-center text-[12px]"
      style={{ top: G.menuH, height: G.titleH, background: vs.side, borderBottom: `1px solid ${vs.border}`, color: vs.muted }}
    >
      <span className="ml-[12px] flex gap-[8px]">
        {['#FF5F57', '#FEBC2E', '#28C840'].map((c) => (
          <span key={c} className="h-[12px] w-[12px] rounded-full" style={{ background: c }} />
        ))}
      </span>
      <span className="absolute left-1/2 -translate-x-1/2">{open ? `${FILE_NAME} — ${FOLDER}` : FOLDER}</span>
    </div>
  )
}

const top = G.menuH + G.titleH
const bottom = 1000 - G.statusH

function ActivityBar(): ReactNode {
  const icons = [Files, Search, GitBranch, Play, Blocks]
  return (
    <div className="absolute left-0 flex flex-col items-center gap-[22px] pt-[14px]" style={{ top, width: G.activityW, height: bottom - top, background: vs.side, borderRight: `1px solid ${vs.border}` }}>
      {icons.map((Icon, i) => (
        <Icon key={i} size={22} strokeWidth={1.5} color={i === 0 ? '#D7D7D7' : '#868686'} />
      ))}
    </div>
  )
}

function Explorer(): ReactNode {
  const open = useDesk((d) => d.open)
  return (
    <div className="absolute text-[13px]" style={{ left: G.activityW, top, width: G.explorerW, height: bottom - top, background: vs.side, borderRight: `1px solid ${vs.border}`, color: vs.text }}>
      <div className="px-[20px] pt-[10px] text-[11px] tracking-[.04em]" style={{ color: vs.muted }}>
        EXPLORER
      </div>
      <div className="mt-[10px] flex items-center gap-[2px] px-[6px] text-[11px] font-bold tracking-[.03em]">
        <ChevronDown size={15} />
        {FOLDER.toUpperCase()}
      </div>
      <div className="mt-[4px] flex items-center gap-[4px] pl-[20px] leading-[22px]" style={{ color: vs.muted }}>
        <ChevronRight size={14} /> .venv
      </div>
      {open && (
        <div className="flex items-center gap-[6px] pl-[38px] leading-[22px]" style={{ background: '#37373D' }}>
          <span className="text-[11px] font-bold" style={{ color: '#E5C07B' }}>
            py
          </span>
          {FILE_NAME}
        </div>
      )}
    </div>
  )
}

function Editor(): ReactNode {
  const { open, lines, caret, selected } = useDesk()
  const [blink, setBlink] = useState(true)
  useEffect(() => {
    const id = setInterval(() => setBlink((b) => !b), 530)
    return () => clearInterval(id)
  }, [])
  const left = G.editorX
  const tabsTop = top
  const crumbsTop = tabsTop + G.tabsH
  return (
    <div className="absolute" style={{ left, top, width: G.editorW, height: bottom - top, background: vs.bg }}>
      <div className="absolute left-0 flex w-full" style={{ top: 0, height: G.tabsH, background: vs.side, borderBottom: `1px solid ${vs.border}` }}>
        {open && (
          <div className="flex items-center gap-[6px] px-[14px] text-[13px]" style={{ background: vs.bg, color: '#FFFFFF', borderTop: '1px solid #9D9D9D', borderRight: `1px solid ${vs.border}` }}>
            <span className="text-[11px] font-bold" style={{ color: '#E5C07B' }}>
              py
            </span>
            {FILE_NAME}
          </div>
        )}
      </div>
      {open ? (
        <>
          <div className="absolute flex items-center gap-[4px] pl-[18px] text-[12.5px]" style={{ top: G.tabsH, height: G.crumbsH, color: vs.muted }}>
            {FOLDER} <ChevronRight size={13} /> {FILE_NAME}
          </div>
          {caret && (
            <div className="absolute" style={{ left: 0, top: lineTop(caret.line) - top, width: G.editorW, height: G.lineH, border: `1px solid ${vs.current}` }} />
          )}
          {selected && (
            <div
              className="absolute"
              style={{ left: codeX - left, top: lineTop(selected[0]) - top, width: 300, height: (selected[1] - selected[0] + 1) * G.lineH, background: vs.selection }}
            />
          )}
          {lines.map((text, i) => {
            const n = i + 1
            return (
              <div key={n} className="absolute whitespace-pre" style={{ top: lineTop(n) - top, left: 0, height: G.lineH, ...mono }}>
                <span className="absolute text-right" style={{ width: G.gutterW - 10, color: caret?.line === n ? vs.lineNoActive : vs.lineNo }}>
                  {n}
                </span>
                <span className="absolute" style={{ left: codeX - left }}>
                  {highlight(text)}
                </span>
              </div>
            )
          })}
          {caret && blink && (
            <div className="absolute" style={{ left: codeX - left + caret.col * charW, top: lineTop(caret.line) - top + 1, width: 2, height: G.lineH - 2, background: vs.caret }} />
          )}
        </>
      ) : (
        <EmptyEditor crumbsTop={crumbsTop} />
      )}
    </div>
  )
}

/** Monospace advance at 13px (SF Mono / Menlo / Consolas are all close to 0.6em). */
const charW = 7.8

function EmptyEditor({ crumbsTop }: { crumbsTop: number }): ReactNode {
  void crumbsTop
  const rows = [
    ['Show All Commands', '⇧ ⌘ P'],
    ['Go to File', '⌘ P'],
    ['New Untitled Text File', '⌘ N'],
    ['Toggle Terminal', '⌃ `']
  ]
  return (
    <div className="absolute left-1/2 top-[300px] -translate-x-1/2 text-[13px]" style={{ color: vs.faint }}>
      {rows.map(([a, b]) => (
        <div key={a} className="flex justify-between gap-[28px] leading-[26px]">
          <span>{a}</span>
          <span style={{ color: '#8B8B8B' }}>{b}</span>
        </div>
      ))}
    </div>
  )
}

function Terminal(): ReactNode {
  const term = useDesk((d) => d.term)
  const [blink, setBlink] = useState(true)
  useEffect(() => {
    const id = setInterval(() => setBlink((b) => !b), 530)
    return () => clearInterval(id)
  }, [])
  const tabs = ['PROBLEMS', 'OUTPUT', 'DEBUG CONSOLE', 'TERMINAL', 'PORTS']
  return (
    <div className="absolute" style={{ left: G.termX, top, width: 1600 - G.termX, height: bottom - top, background: vs.side, borderLeft: `1px solid ${vs.border}` }}>
      <div className="flex h-[35px] items-end gap-[22px] px-[16px] text-[11px] tracking-[.03em]" style={{ color: vs.muted }}>
        {tabs.map((t) => (
          <span key={t} className="pb-[8px]" style={t === 'TERMINAL' ? { color: '#E7E7E7', borderBottom: '1px solid #E7E7E7' } : undefined}>
            {t}
          </span>
        ))}
      </div>
      {term.map((line, i) => {
        const last = i === term.length - 1
        const prompt = line.startsWith(PROMPT)
        return (
          <div key={i} className="absolute whitespace-pre" style={{ left: 14, top: termLineTop(i + 1) - top, ...mono, color: vs.text }}>
            {prompt ? (
              <>
                <span style={{ color: '#6A9955' }}>{PROMPT.trimEnd()}</span> {line.slice(PROMPT.length)}
              </>
            ) : (
              line
            )}
            {last && prompt && blink && <span className="inline-block align-[-2px]" style={{ width: 8, height: 15, background: vs.caret }} />}
          </div>
        )
      })}
    </div>
  )
}

function StatusBar(): ReactNode {
  const caret = useDesk((d) => d.caret)
  const open = useDesk((d) => d.open)
  return (
    <div className="absolute left-0 flex w-full items-center gap-[16px] px-[12px] text-[12px]" style={{ top: bottom, height: G.statusH, background: vs.side, borderTop: `1px solid ${vs.border}`, color: vs.muted }}>
      <span className="flex items-center gap-[4px]">
        <GitBranch size={13} /> main
      </span>
      <span className="ml-auto">{open && caret ? `Ln ${caret.line}, Col ${caret.col + 1}` : ''}</span>
      <span>Spaces: 4</span>
      <span>UTF-8</span>
      <span>Python 3.12.10 (.venv)</span>
    </div>
  )
}
