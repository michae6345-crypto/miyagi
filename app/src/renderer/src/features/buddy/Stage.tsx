/**
 * Feature: buddy. A preview of every state, only in the browser stage with ?buddy (index.tsx). Not an app window.
 * Rows: idle, thinking, lean left, lean right, bloom (replays every 1.6 s), and one that follows the pointer.
 * Columns: the notch ear size (16), 30, 64 and 120, on the notch black and on paper.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { LivingMark, usePointerLean, type LivingMarkProps } from './LivingMark'

const SIZES = [16, 30, 64, 120]

function Row({ label, ...props }: { label: string } & LivingMarkProps): ReactNode {
  return (
    <div style={{ display: 'contents' }}>
      <div style={{ font: '500 12px -apple-system, "Segoe UI", sans-serif', color: '#8F8F88', alignSelf: 'center' }}>{label}</div>
      {(['dark', 'light'] as const).map((tone) => (
        <div key={tone} data-buddy-cell={`${label}-${tone}`} style={{ display: 'flex', alignItems: 'flex-end', gap: 22, padding: '14px 18px', borderRadius: 12, background: tone === 'dark' ? '#000' : '#F6F6F3' }}>
          {SIZES.map((s) => <LivingMark key={s} size={s} tone={tone} {...props} />)}
        </div>
      ))}
    </div>
  )
}

export function BuddyStage(): ReactNode {
  const [bloom, setBloom] = useState(1)
  useEffect(() => {
    const t = setInterval(() => setBloom((b) => b + 1), 1600)
    return () => clearInterval(t)
  }, [])
  const follow = useRef<HTMLDivElement>(null)
  const lean = usePointerLean(follow, true, 300)
  return (
    <div ref={follow} data-hit style={{ position: 'absolute', inset: 0, background: '#1C1C1E', padding: 22, overflow: 'auto', display: 'grid', gridTemplateColumns: '110px 1fr 1fr', gap: 10 }}>
      <Row label="idle" />
      <Row label="thinking" state="thinking" />
      <Row label="lean left" lean={-1} />
      <Row label="lean right" lean={1} />
      <Row label="bloom" bloom={bloom} />
      <Row label={`pointer ${lean.toFixed(2)}`} lean={lean} />
    </div>
  )
}
