/**
 * Feature: skills. The learner's own work behind a pass (contract ui-v4, UI-V4.md section 4, "Proof"): the peek asks
 * `proof.get {skillId}` for a passed or mastered skill and shows the newest one (the code, its output, the check it
 * passed, the file). Kept per skill for this window; the engine keeps proofs on this Mac only.
 */
import { useEffect } from 'react'
import { create } from 'zustand'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import { toMs } from '../dashboard/types'

export type ProofItem = {
  id: string
  kind: string
  stepTitle: string
  lessonTitle?: string
  at?: number
  check: string
  text?: string
  output?: string
  file?: string
  truncated?: boolean
}

type State = { bySkill: Record<string, ProofItem[]>; asked: Record<string, boolean> }
export const useProof = create<State>(() => ({ bySkill: {}, asked: {} }))

type Rec = Record<string, unknown>
const rec = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : {})
const str = (v: unknown, max: number): string => (typeof v === 'string' ? v.slice(0, max) : '')
const line = (v: unknown, max: number): string => str(v, max).replace(/\s+/g, ' ').trim()

/** One proof as the peek shows it, or undefined when it has no check to name. */
export function readProof(v: unknown): ProofItem | undefined {
  const p = rec(v)
  const id = line(p.id, 120)
  const check = line(rec(p.check).label, 200)
  if (!id || !check) return undefined
  return {
    id,
    kind: line(p.kind, 20),
    stepTitle: line(p.stepTitle, 120),
    lessonTitle: line(p.lessonTitle, 120) || undefined,
    at: toMs(p.at),
    check,
    text: str(p.text, 2000).replace(/\s+$/, '') || undefined,
    output: str(p.output, 1000).replace(/\s+$/, '') || undefined,
    file: line(p.file, 200) || undefined,
    truncated: p.truncated === true || undefined
  }
}

onMessage('proof', (raw) => {
  const m = rec(raw)
  const items = (Array.isArray(m.items) ? m.items : []).map(readProof).filter((x): x is ProofItem => !!x)
  const skillId = line(m.skillId, 80)
  if (!skillId) return
  useProof.setState((s) => ({ bySkill: { ...s.bySkill, [skillId]: items } }))
})

/** The newest proof for a skill; asks the engine once per skill when it lists proof.get. */
export function useSkillProof(skillId: string | undefined, want: boolean): ProofItem | undefined {
  const items = useProof((s) => (skillId ? s.bySkill[skillId] : undefined))
  useEffect(() => {
    if (!skillId || !want || useProof.getState().asked[skillId] || !canSend('proof.get')) return
    useProof.setState((s) => ({ asked: { ...s.asked, [skillId]: true } }))
    bridge.send(cmd('proof.get', { skillId, reqId: `skills-proof-${skillId}` }))
  }, [skillId, want])
  return items?.[0]
}
