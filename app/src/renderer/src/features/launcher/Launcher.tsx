/**
 * Spotlight-style launcher (⌥Space · Ctrl+Shift+Space on Windows).
 * Open: backdrop dims 0 → .35 over 160ms; panel scale .96 → 1, y -8 → 0 on the spring; caret focuses.
 * Results stream in (y 6 → 0, 40ms stagger); the highlight glides between rows (shared layoutId).
 * Build lesson: THE signature transition. The panel itself morphs onto the pill's exact rect
 * (top-center, 300×34, radius 17, black) while its content fades; then the overlay pill takes over.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { CornerDownLeft, FileCode2, FileText, Mic, Newspaper, Sparkles } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { Spinner, Thumb } from '../../core/ui/atoms'
import { color, launcher as L, pill, spring } from '../../core/theme'
import { startSearch, useSearch, type SearchResult } from './store'

type Phase = 'closed' | 'open' | 'closing' | 'building'

const ROW_H = 64
const MAX_ROWS = 4

export function Launcher({ layout, openOnMount = false }: { layout: Layout; openOnMount?: boolean }): ReactNode {
  const [phase, setPhase] = useState<Phase>(openOnMount ? 'open' : 'closed')
  const [gen, setGen] = useState(0)
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState(0)
  const search = useSearch(useShallow((s) => s))
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => bridge.on('launcher:open', () => (setPhase('open'), setGen((g) => g + 1), setSel(0))), [])
  useEffect(() => bridge.on('launcher:close', () => setPhase((p) => (p === 'open' ? 'closing' : p))), [])
  useEffect(() => {
    if (phase !== 'open') return
    const id = requestAnimationFrame(() => {
      input.current?.focus()
      input.current?.select()
    })
    return () => cancelAnimationFrame(id)
  }, [phase, gen])

  const results = search.results
  const hasSearch = search.pending || results.length > 0
  const rows = Math.min(MAX_ROWS, Math.max(results.length, search.pending ? 1 : 0))

  const close = (): void => setPhase((p) => (p === 'open' ? 'closing' : p))

  const build = (): void => {
    if (!results.length) return
    const first = results[Math.min(sel, results.length - 1)].id
    bridge.send(cmd('build_lesson', { resultIds: [first, ...results.map((r) => r.id).filter((id) => id !== first)] }))
    setPhase('building')
  }

  const submit = (): void => {
    const q = query.trim()
    if (!q) return
    if (q !== search.query || (!results.length && !search.pending)) {
      startSearch(q)
      bridge.send(/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\//.test(q) ? cmd('learn_url', { url: q }) : cmd('learn', { query: q }))
      setSel(0)
    } else build()
  }

  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') return close()
    if (e.key === 'Enter') return (e.preventDefault(), submit())
    if (e.key === 'ArrowDown') return (e.preventDefault(), setSel((i) => Math.min(results.length - 1, i + 1)))
    if (e.key === 'ArrowUp') return (e.preventDefault(), setSel((i) => Math.max(0, i - 1)))
  }

  const done = (): void => {
    if (phase === 'closing') {
      setPhase('closed')
      bridge.emit('launcher:hidden')
    } else if (phase === 'building') {
      setPhase('closed')
      bridge.emit('launcher:built')
    }
  }

  const top = Math.round(layout.height * L.topRatio)
  const minutes = estimateMinutes(results)

  if (phase === 'closed') return null

  return (
    <div key={gen} className="absolute inset-0" style={{ width: layout.width, height: layout.height }}>
      {/* Backdrop: dims (and blurs, where the platform can) the desktop. Click to dismiss. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,.35)', backdropFilter: 'blur(14px) saturate(1.1)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: phase === 'open' ? 1 : 0 }}
        transition={{ duration: phase === 'open' ? 0.16 : phase === 'building' ? 0.42 : 0.14 }}
        onClick={close}
      />

      <motion.div
        className="absolute left-1/2 overflow-hidden border"
        style={{ x: '-50%', borderColor: phase === 'building' ? 'rgba(255,255,255,0)' : color.hairline, boxShadow: '0 30px 80px rgba(0,0,0,.5)' }}
        initial={{ opacity: 0, scale: 0.96, y: -8, top, width: L.width, borderRadius: 28, backgroundColor: 'rgba(32,33,38,.9)' }}
        animate={
          phase === 'open'
            ? { opacity: 1, scale: 1, y: 0, top, width: L.width, borderRadius: 28, backgroundColor: 'rgba(32,33,38,.9)' }
            : phase === 'closing'
              ? { opacity: 0, scale: 0.96, y: -8 }
              : { opacity: 1, scale: 1, y: 0, top: bridge.platform.pillTop, width: pill.landingWidth, height: pill.height, borderRadius: pill.height / 2, backgroundColor: 'rgba(0,0,0,1)' }
        }
        transition={phase === 'closing' ? { duration: 0.14, ease: 'easeIn' } : spring}
        onAnimationComplete={done}
      >
        <motion.div style={{ width: L.width }} animate={{ opacity: phase === 'building' ? 0 : 1 }} transition={{ duration: 0.12 }}>
          <div className="pt-[30px] text-center text-[28px] font-semibold tracking-[-0.02em] text-white">What do you want to learn?</div>

          <div className="mx-[26px] mt-[22px] flex h-[62px] items-center gap-[14px] rounded-[16px] border px-[20px]" style={{ background: 'rgba(255,255,255,.06)', borderColor: 'rgba(255,255,255,.14)' }}>
            <Sparkles size={20} strokeWidth={1.6} className="shrink-0 text-white/85" />
            <input
              ref={input}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKey}
              placeholder="Train a PINN, fine-tune Llama, build a ray tracer…"
              spellCheck={false}
              className="h-full flex-1 bg-transparent text-[20px] text-white caret-[#0A84FF] outline-none placeholder:text-white/30"
            />
            <Mic size={18} strokeWidth={1.6} className="shrink-0 text-white/45" />
          </div>

          <motion.div className="overflow-hidden" initial={false} animate={{ height: hasSearch ? 34 + rows * ROW_H : 0 }} transition={spring}>
            <div className="px-[26px] pt-[16px] text-[13px] font-medium text-white/50">{results.length ? 'Top results' : 'Searching'}</div>
            <div className="px-[26px] pt-[6px]">
              {results.length === 0 && search.pending && (
                <div className="flex items-center gap-[12px] px-[12px] text-[14px] text-white/55" style={{ height: ROW_H }}>
                  <Spinner size={16} /> Looking across videos, notebooks and papers…
                </div>
              )}
              <AnimatePresence initial={false}>
                {results.slice(0, MAX_ROWS).map((r, i) => (
                  <Row key={r.id} r={r} i={i} selected={i === sel} onHover={() => setSel(i)} onPick={() => (setSel(i), build())} />
                ))}
              </AnimatePresence>
            </div>
          </motion.div>

          <div className="flex items-center gap-[12px] px-[38px] pb-[22px] pt-[18px]">
            <span className="flex-1 text-[13px] text-white/45">
              {results.length ? `${minutes ? `about ${minutes} min · ` : ''}each step auto-checked` : 'Press ↵ to find the best tutorial and turn it into a lab'}
            </span>
            <motion.button
              className="flex h-[40px] cursor-pointer items-center gap-[10px] rounded-[14px] pl-[18px] pr-[8px] text-[16px] font-semibold text-white disabled:cursor-default"
              style={{ background: color.accent, boxShadow: '0 6px 20px rgba(10,132,255,.35)' }}
              animate={{ opacity: results.length ? 1 : 0.35 }}
              whileTap={{ scale: 0.96 }}
              disabled={!results.length}
              onClick={build}
            >
              Build lesson
              <span className="grid h-[24px] w-[28px] place-items-center rounded-[7px]" style={{ background: 'rgba(255,255,255,.22)' }}>
                <CornerDownLeft size={13} strokeWidth={2.2} />
              </span>
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  )
}

function Row({ r, i, selected, onHover, onPick }: { r: SearchResult; i: number; selected: boolean; onHover: () => void; onPick: () => void }): ReactNode {
  const best = /best/i.test(r.reason) || i === 0
  return (
    <motion.button
      className="relative flex w-full cursor-pointer items-center gap-[14px] px-[12px] text-left"
      style={{ height: ROW_H }}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ ...spring, delay: i * 0.04 }}
      onMouseEnter={onHover}
      onClick={onPick}
    >
      {selected && (
        <motion.div
          layoutId="launcher-highlight"
          className="absolute inset-0 rounded-[14px] border"
          style={{ background: 'rgba(255,255,255,.08)', borderColor: 'rgba(255,255,255,.1)' }}
          transition={spring}
        />
      )}
      <span className="relative">
        {r.kind === 'video' ? (
          <Thumb w={62} h={40} src={r.thumbnail} />
        ) : (
          <span className="grid h-[40px] w-[62px] place-items-center rounded-[8px] text-white/70" style={{ background: 'rgba(255,255,255,.08)' }}>
            {r.kind === 'notebook' ? <FileCode2 size={17} strokeWidth={1.6} /> : r.kind === 'paper' ? <FileText size={17} strokeWidth={1.6} /> : <Newspaper size={17} strokeWidth={1.6} />}
          </span>
        )}
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="block truncate text-[15px] font-medium text-white">{r.title}</span>
        <span className="mt-[1px] block truncate text-[13px] text-white/50">{r.meta}</span>
      </span>
      <span className="relative shrink-0 text-[13px]" style={{ color: best ? '#4aa3ff' : 'rgba(255,255,255,.5)' }}>
        {r.reason}
      </span>
    </motion.button>
  )
}

/** "about 45 min": ~2.4× the best video's length, rounded to 5. */
function estimateMinutes(results: SearchResult[]): number | undefined {
  const v = results.find((r) => r.kind === 'video')
  const m = v?.meta.match(/(\d+):(\d{2})(?!.*\d+:\d{2})/)
  if (!m) return
  const mins = Number(m[1]) + Number(m[2]) / 60
  return Math.max(5, Math.round((mins * 2.4) / 5) * 5)
}
