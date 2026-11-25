/**
 * Feature: buddy. bon's levels, only in the browser stage with ?buddy=grow (index.tsx). Not an app window.
 * Every level big on the island's black and at the size it is on the screen, the growth card as Settings shows it,
 * and two buttons that pass steps the way the engine does (a `step.passed` through the bus), so the level-up moment
 * can be seen: bon comes out, grows in front of the learner and says its new level. ?steps=<n> or ?level=<n> sets
 * where it starts.
 */
import { useRef, type CSSProperties, type ReactNode } from 'react'
import { dispatch } from '../../core/bus'
import { brand, color, fill, radius, radius2, text, type2 } from '../../core/theme'
import { Character } from './Character'
import { BonBar, BonLadder, useLevelWords } from './GrowthCard'
import { LEVELS, useGrowth } from './growth'
import { BODY } from './trip'

const LABEL = { font: '500 12px -apple-system, "Segoe UI", sans-serif', color: '#8F8F88' } as const
const chip: CSSProperties = { background: fill.chip, border: `1px solid ${fill.chipBorder}`, borderRadius: radius.chip, color: fill.chipText, cursor: 'pointer', padding: '5px 12px', fontWeight: 500, fontSize: text.xs, whiteSpace: 'nowrap' }

export function GrowStage(): ReactNode {
  const n = useRef(0)
  const steps = useGrowth((g) => g.steps)
  const pass = (times: number): void => {
    for (let i = 0; i < times; i++) dispatch({ type: 'step.passed', payload: { stepId: `grow-${++n.current}` } } as never)
  }
  const { title, caption } = useLevelWords()
  return (
    <div data-hit data-theme="dark" data-grow style={{ position: 'absolute', inset: 0, background: '#161615', padding: '22px 26px', overflow: 'hidden', color: '#F4F4F5' }}>
      <div style={{ font: '600 20px -apple-system, "Segoe UI", sans-serif', marginBottom: 2 }}>bon grows as you pass steps: eight levels</div>
      <div style={{ ...LABEL, fontSize: 13, marginBottom: 14 }}>Each level big, then at real size ({BODY.size} px) over a dark and a light app. Under them: the card Settings shows.</div>
      <div data-grow-levels style={{ display: 'grid', gridTemplateColumns: `repeat(${LEVELS.length}, 1fr)`, gap: 10 }}>
        {LEVELS.map((l, i) => (
          <div key={l.name} style={{ background: '#000', borderRadius: 16, padding: '34px 0 12px', display: 'grid', justifyItems: 'center', gap: 6 }}>
            <Character size={104} level={i + 1} mood={i + 1 >= 6 ? 'happy' : 'calm'} />
            <span style={{ ...LABEL, fontSize: 15, fontWeight: 600, color: '#F4F4F5', marginTop: 6 }}>
              {i + 1} · {l.name}
            </span>
            <span style={LABEL}>{l.at === 0 ? 'where it starts' : `${l.at} steps passed`}</span>
            <span style={LABEL}>{l.has}</span>
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
              {(['dark', 'light'] as const).map((tone) => (
                <span key={tone} style={{ background: tone === 'dark' ? '#1E1E1E' : brand.paper, borderRadius: 10, padding: '16px 8px 6px', lineHeight: 0 }}>
                  <Character size={BODY.size} level={i + 1} />
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16, marginTop: 16, alignItems: 'start' }}>
        {/* The card, as Settings draws it (SettingsRows.tsx). */}
        <section data-grow-card style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
          <div className="flex items-center gap-[16px]" style={{ minHeight: 56, padding: '0 16px' }}>
            <div className="flex min-w-0 flex-1 flex-col gap-[2px] py-[10px]">
              <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
                {title}
              </span>
              <span style={{ fontSize: type2.sm, color: color.label }}>{caption}</span>
            </div>
            <BonBar />
          </div>
          <div className="h-px" style={{ marginLeft: 16, background: fill.hairline }} />
          <BonLadder />
        </section>
        <div data-grow-controls style={{ display: 'grid', gap: 8, justifyItems: 'start' }}>
          <span style={{ ...LABEL, fontSize: 13, color: '#F4F4F5' }}>Try it: {steps} steps passed</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button data-grow-pass="1" style={chip} onClick={() => pass(1)}>
              Pass a step
            </button>
            <button data-grow-pass="5" style={chip} onClick={() => pass(5)}>
              Pass 5
            </button>
          </div>
          <span style={LABEL}>On a level-up bon comes out by your pointer, grows, and says its new level.</span>
        </div>
      </div>
    </div>
  )
}
