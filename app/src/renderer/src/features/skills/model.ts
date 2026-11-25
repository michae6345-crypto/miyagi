/**
 * Feature: skills. The Skills page's one view model, pure (no store, no React, no layout).
 *
 * `buildSkillGraph(raw, now)` reads the engine's `progress` payload in either shape and returns one `SkillGraph`:
 *
 *   graph      `progress.graph` (shared/contracts SkillGraphInfo, Nov 22): skills, edges, capstones, goal, next,
 *              alsoReady, keepFresh, events + ackedUntil, week, portfolio. Used whenever it carries skills.
 *   tracks     today's `progress.skills[]` tracks, read by features/dashboard/types.ts (both wire shapes). Each track's
 *              own edges become `requires` links; a track with no edges is drawn as a short chain (links marked
 *              `inferred`); a cross link that names a skill on another track becomes a `helps` link.
 *
 * Whatever is missing is derived, never invented as progress:
 *   state      mastered / practicing as given (or masteredAt / evidence); otherwise ready when every `requires`
 *              prerequisite is mastered, else locked. Review is a modifier on mastered (its dueAt has come).
 *   goal       the chosen capstone; with none chosen, the capstone furthest along; with no capstones, the
 *              furthest-along track's last skill, drawn as the capstone (`goal.inferred`). `graph.goal: null` = the
 *              learner hasn't picked one yet: goal stays null and the page shows the goal picker.
 *   next       one skill: practicing on the goal's path first, then ready on it, then anywhere.
 *   alsoReady  <= 3 other startable skills (ready or practicing), the goal's path first.
 *   keepFresh  <= 3 mastered skills whose review is due, soonest first.
 *   events     unseen unlock events (newer than ackedUntil), oldest first; `ack` is what skills.ack {until} sends.
 */
import type { SkillGraphInfo, SkillWeek } from '../../../../../../shared/contracts/events'
import { lessonIndex, dueItems, reviewFor, reviewIndex } from '../dashboard/model'
import { readDashboard, skillKey, toMs, type DashData } from '../dashboard/types'

// ---- view model types -------------------------------------------------------------------------------------------

export type SkillNodeState = 'locked' | 'ready' | 'practicing' | 'mastered'
export type SkillNodeKind = 'skill' | 'capstone'
export type SkillLinkKind = 'requires' | 'helps'

export type SkillGraphLesson = {
  lessonId: string
  libraryId?: string
  title?: string
  /** The steps of that lesson that build this skill. */
  stepIds: string[]
  role?: 'teaches' | 'uses' | 'practices'
  inProgress: boolean
}

export type SkillGraphStep = { key?: string; lessonId: string; lessonTitle?: string; stepId: string; title: string; passed: boolean; at?: number; assisted?: boolean }

export type SkillGraphNode = {
  id: string
  label: string
  /** SkillGraphTrack.id of its group. */
  track: string
  kind: SkillNodeKind
  state: SkillNodeState
  /** Mastered and its review is due now (a hollow green ring). Never a demotion. */
  review: boolean
  /** ms. Set when the engine schedules a review, due or not. */
  dueAt?: number
  /** Steps passed of the steps behind it ("2 of 4 steps"). */
  evidence?: { done: number; total: number }
  summary?: string
  example?: { code?: string; caption?: string }
  lessons: SkillGraphLesson[]
  masteredAt?: number
  lastPracticedAt?: number
  /** ui-v4 (UI-V4.md section 4): every step behind it, passed or not, in lesson order. Undefined: the engine sent none. */
  steps?: SkillGraphStep[]
  /** ui-v4: the two-day mastery rule's progress. */
  mastery?: { need: number; days: string[]; assisted?: number }
  /** ui-v4: the spaced-review schedule (dueAt in ms). */
  schedule?: { dueAt: number; round: number; interval: number }
  /** ui-v4: proofs kept for its passes, newest first (proof.get). */
  proofIds: string[]
  /** Ids this node `requires` (helps links are not prerequisites). */
  requires: string[]
  /** The `requires` ids not mastered yet: "needs 3 skills" / "needs A single neuron". */
  needs: string[]
  /** Longest chain of `requires` links into it (0 = a root). layout.ts may use it as the first layering. */
  depth: number
  /** On the way to the goal (the goal itself included). */
  onGoalPath: boolean
  isGoal: boolean
  isNext: boolean
}

export type SkillGraphLink = {
  from: string
  to: string
  kind: SkillLinkKind
  /** 0..1, helps links only. */
  weight?: number
  /** Drawn from track order because the engine sent no edges for that track. */
  inferred: boolean
  /** Both ends are on the goal's path (the Map draws these in ink). */
  onGoalPath: boolean
}

export type SkillGraphTrack = {
  /** Stable key (lowercased label). */
  id: string
  /** As the engine wrote it ("numpy"): the group header. */
  label: string
  /** In the engine's order. */
  nodeIds: string[]
  /** Skills only (capstones are not counted). */
  mastered: number
  total: number
}

export type SkillGraphCapstone = {
  id: string
  label: string
  track: string
  brief?: string
  requires: string[]
  checks: string[]
  starterFile?: string
  estMinutes?: number
  completedAt?: number
  artifact?: { kind: 'image' | 'file'; path?: string; caption?: string }
}

export type SkillGraphGoal = {
  /** The capstone node's id. */
  id: string
  label: string
  /** The skills the goal counts, its own id excluded ("6 of 11 skills"). */
  pathIds: string[]
  mastered: number
  practicing: number
  total: number
  /** Not chosen by the learner: the furthest-along capstone or track end. */
  inferred: boolean
}

export type SkillGraphPick = {
  skillId: string
  label: string
  practicing: boolean
  lessonId?: string
  libraryId?: string
  lessonTitle?: string
  /** 0-based step of the lesson to continue at (as LibraryItem.progress.stepIndex; "Step 3 of 4" = 2). */
  stepIndex?: number
  stepCount?: number
  estMinutes?: number
  /** Launcher text for learn {query: goal, mode: "lesson"} when no saved lesson teaches it. */
  goal?: string
  /** <= 12 words: "gets you closer to Layers". */
  why?: string
}

export type SkillGraphEvent = {
  id: string
  kind: 'mastered' | 'unlocked' | 'review_due' | 'capstone_done'
  skillId: string
  /** ms. */
  at: number
  from?: string
  lessonId?: string
}

export type SkillGraphWeek = {
  mastered?: number
  keptFresh?: number
  minutes?: number
  /** Monday first. */
  days: boolean[]
  weeklyGoal?: number
  goalAway?: number
}

export type SkillGraphPortfolioItem = {
  capstoneId: string
  title: string
  at?: number
  track?: string
  skillIds: string[]
  artifact?: SkillGraphCapstone['artifact']
}

export type SkillGraph = {
  /** Where it came from: the new `progress.graph`, or today's tracks. */
  source: 'graph' | 'tracks'
  /** Skills and capstones, in the engine's order (tracks in first-seen order). */
  nodes: SkillGraphNode[]
  byId: Record<string, SkillGraphNode>
  links: SkillGraphLink[]
  tracks: SkillGraphTrack[]
  capstones: SkillGraphCapstone[]
  /** null: no goal yet (the goal picker shows), or no skills at all. */
  goal: SkillGraphGoal | null
  next: SkillGraphPick | null
  alsoReady: string[]
  keepFresh: string[]
  /** Unseen, oldest first. Each plays once. */
  events: SkillGraphEvent[]
  /** skills.ack {until: ack} once `events` have played. undefined: nothing to ack. */
  ack?: string | number
  week: SkillGraphWeek | null
  portfolio: SkillGraphPortfolioItem[]
}

// ---- small readers ----------------------------------------------------------------------------------------------

type Rec = Record<string, unknown>
const rec = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : {})
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const str = (v: unknown, max = 200): string => (typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, max) : '')
const opt = (v: unknown, max = 200): string | undefined => str(v, max) || undefined
const count = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 1e7 ? Math.floor(v) : undefined)
const ids = (v: unknown): string[] => [...new Set(list(v).map((x) => str(x, 80)).filter(Boolean))]
const LIB_RE = /^[A-Za-z0-9_-]{1,64}$/
const libId = (v: unknown): string | undefined => (typeof v === 'string' && LIB_RE.test(v) ? v : undefined)
const STATES = new Set<SkillNodeState>(['locked', 'ready', 'practicing', 'mastered'])
const EVENT_KINDS = new Set<SkillGraphEvent['kind']>(['mastered', 'unlocked', 'review_due', 'capstone_done'])
const MAX_SIDE = 3

/** A node before states, goal and next are known. */
type Draft = Omit<SkillGraphNode, 'state' | 'review' | 'needs' | 'depth' | 'onGoalPath' | 'isGoal' | 'isNext' | 'requires'> & {
  given?: SkillNodeState
  reviewDue: boolean
}
type DraftLink = Omit<SkillGraphLink, 'onGoalPath'>

function pushLink(links: DraftLink[], l: DraftLink, known: Set<string>): void {
  if (!known.has(l.from) || !known.has(l.to) || l.from === l.to) return
  if (links.some((x) => x.from === l.from && x.to === l.to)) return
  links.push(l)
}

/** A label as the UI shows it: inline code marks (`groupby`) dropped, the words kept. */
export function plain(s: string): string {
  return s.replace(/`([^`]*)`/g, '$1').replace(/`/g, '').replace(/\s+/g, ' ').trim()
}

// ---- input: progress.graph --------------------------------------------------------------------------------------

function draftsFromGraph(g: Rec, dash: DashData | undefined, now: number): { drafts: Draft[]; links: DraftLink[]; capstones: SkillGraphCapstone[] } {
  const lessons = lessonIndex(dash)
  const drafts: Draft[] = []
  const seen = new Set<string>()
  for (const x of list(g.skills)) {
    const s = rec(x)
    const id = str(s.id, 80)
    const label = plain(str(s.label, 80))
    if (!id || !label || seen.has(id)) continue
    seen.add(id)
    const ev = rec(s.evidence)
    const total = count(ev.total)
    const done = count(ev.done)
    const evidence = total ? { done: Math.min(done ?? 0, total), total } : undefined
    const sched = rec(s.schedule)
    const schedDue = toMs(sched.dueAt)
    const dueAt = toMs(rec(s.review).dueAt) ?? schedDue
    const mastery = rec(s.mastery)
    const need = count(mastery.need)
    const given = STATES.has(s.state as SkillNodeState) ? (s.state as SkillNodeState) : undefined
    const example = rec(s.example)
    const ex = { code: opt(example.code, 200), caption: opt(example.caption, 120) }
    drafts.push({
      id,
      label,
      track: str(s.track, 80),
      kind: s.kind === 'capstone' ? 'capstone' : 'skill',
      given,
      reviewDue: dueAt !== undefined && dueAt <= now,
      dueAt,
      evidence,
      summary: opt(s.summary, 160),
      example: ex.code || ex.caption ? ex : undefined,
      lessons: list(s.lessons)
        .map((l): SkillGraphLesson | undefined => {
          const r = rec(l)
          const lessonId = str(r.lessonId, 120)
          if (!lessonId) return undefined
          const known = lessons.get(lessonId)
          const role = r.role === 'teaches' || r.role === 'uses' || r.role === 'practices' ? r.role : undefined
          return {
            lessonId,
            libraryId: libId(r.libraryId) ?? known?.libraryId,
            title: opt(r.title, 120) ?? known?.title,
            stepIds: ids(r.stepIds),
            role,
            inProgress: !!known?.inProgress
          }
        })
        .filter((l): l is SkillGraphLesson => !!l),
      masteredAt: toMs(s.masteredAt),
      lastPracticedAt: toMs(s.lastPracticedAt),
      steps: Array.isArray(s.steps) ? readSteps(s.steps) : undefined,
      mastery: need ? { need, days: list(mastery.days).map((d) => str(d, 20)).filter(Boolean).slice(0, 12), assisted: count(mastery.assisted) } : undefined,
      schedule: schedDue !== undefined ? { dueAt: schedDue, round: count(sched.round) ?? 0, interval: count(sched.interval) ?? 0 } : undefined,
      proofIds: ids(s.proofIds).slice(0, 12)
    })
  }
  const capstones: SkillGraphCapstone[] = []
  const byId = new Map(drafts.map((d) => [d.id, d]))
  for (const x of list(g.capstones)) {
    const c = rec(x)
    const node = byId.get(str(c.id, 80))
    if (!node || capstones.some((k) => k.id === node.id)) continue
    node.kind = 'capstone'
    const art = rec(c.artifact)
    const completedAt = toMs(c.completedAt)
    if (completedAt && !node.given) node.given = 'mastered'
    capstones.push({
      id: node.id,
      label: node.label,
      track: node.track,
      brief: opt(c.brief, 300),
      requires: ids(c.requires).filter((r) => byId.has(r) && r !== node.id),
      checks: list(c.checks).map((k) => str(k, 160)).filter(Boolean),
      starterFile: opt(c.starterFile, 200),
      estMinutes: count(c.estMinutes),
      completedAt,
      artifact: art.kind === 'image' || art.kind === 'file' ? { kind: art.kind, path: opt(art.path, 400), caption: opt(art.caption, 120) } : undefined
    })
  }
  // A node marked capstone with no details still gets an entry, so the hero card always has one.
  for (const d of drafts) if (d.kind === 'capstone' && !capstones.some((c) => c.id === d.id)) capstones.push({ id: d.id, label: d.label, track: d.track, requires: [], checks: [] })
  const known = new Set(byId.keys())
  const links: DraftLink[] = []
  for (const x of list(g.edges)) {
    const e = rec(x)
    const kind: SkillLinkKind = e.kind === 'helps' ? 'helps' : 'requires'
    const w = typeof e.weight === 'number' && e.weight >= 0 && e.weight <= 1 ? e.weight : undefined
    pushLink(links, { from: str(e.from, 80), to: str(e.to, 80), kind, weight: kind === 'helps' ? w : undefined, inferred: false }, known)
  }
  return { drafts, links, capstones }
}

function readSteps(v: unknown[]): SkillGraphStep[] {
  const out: SkillGraphStep[] = []
  for (const x of v.slice(0, 40)) {
    const r = rec(x)
    const title = plain(str(r.title, 120))
    const stepId = str(r.stepId, 80)
    if (!title) continue
    out.push({ key: opt(r.key, 200), lessonId: str(r.lessonId, 120), lessonTitle: opt(r.lessonTitle, 120), stepId, title, passed: r.passed === true, at: toMs(r.at), assisted: r.assisted === true || undefined })
  }
  return out
}

// ---- input: today's tracks (fallback) ---------------------------------------------------------------------------

function draftsFromTracks(dash: DashData, now: number): { drafts: Draft[]; links: DraftLink[] } {
  const lessons = lessonIndex(dash)
  const due = reviewIndex(dueItems(dash.review, now))
  const all = reviewIndex(dash.review?.items ?? [])
  const drafts: Draft[] = []
  const links: DraftLink[] = []
  const used = new Set<string>()
  /** Per track: the track's own id -> the graph id (ids are made unique across tracks). */
  const local = new Map<string, Map<string, string>>()
  for (const t of dash.tracks) {
    const map = new Map<string, string>()
    local.set(t.track, map)
    for (const s of t.skills) {
      const id = used.has(s.id) ? `${skillKey(t.track)}:${s.id}` : s.id
      if (used.has(id)) continue
      used.add(id)
      map.set(s.id, id)
      const r = reviewFor(all, s)
      drafts.push({
        id,
        label: plain(s.label),
        track: t.track,
        kind: 'skill',
        given: s.state === 'mastered' ? 'mastered' : s.state === 'practicing' ? 'practicing' : undefined,
        reviewDue: s.state === 'mastered' && !!reviewFor(due, s),
        dueAt: r?.dueAt,
        summary: s.detail,
        lessons: s.lessons.map((lessonId) => {
          const k = lessons.get(lessonId)
          return { lessonId, libraryId: k?.libraryId, title: k?.title, stepIds: [], inProgress: !!k?.inProgress }
        }),
        masteredAt: s.masteredAt,
        lastPracticedAt: s.lastPracticedAt,
        proofIds: []
      })
    }
  }
  const known = new Set(used)
  for (const t of dash.tracks) {
    const map = local.get(t.track)!
    if (t.edges.length) {
      for (const e of t.edges) pushLink(links, { from: map.get(e.from) ?? '', to: map.get(e.to) ?? '', kind: 'requires', inferred: false }, known)
    } else {
      // No edges from the engine: the track is a short chain in its own order.
      const chain = t.skills.map((s) => map.get(s.id)).filter((x): x is string => !!x)
      for (let i = 1; i < chain.length; i++) pushLink(links, { from: chain[i - 1], to: chain[i], kind: 'requires', inferred: true }, known)
    }
    // A cross link names another track's idea by label: a `helps` link when that skill is on the map, else dropped.
    for (const c of t.cross) {
      const from = drafts.find((d) => d.track !== t.track && skillKey(d.label) === skillKey(c.label) && (!c.track || skillKey(d.track) === skillKey(c.track)))
      const to = map.get(c.to)
      if (from && to) pushLink(links, { from: from.id, to, kind: 'helps', inferred: false }, known)
    }
  }
  return { drafts, links }
}

// ---- derivations ------------------------------------------------------------------------------------------------

function requiresOf(links: DraftLink[]): Map<string, string[]> {
  const m = new Map<string, string[]>()
  for (const l of links) if (l.kind === 'requires') m.set(l.to, [...(m.get(l.to) ?? []), l.from])
  return m
}

/** Longest chain of requires links into each node; capped at n passes so a cycle can't spin. */
export function depths(nodeIds: string[], links: Array<{ from: string; to: string; kind: SkillLinkKind }>): Record<string, number> {
  const d: Record<string, number> = Object.fromEntries(nodeIds.map((id) => [id, 0]))
  const req = links.filter((l) => l.kind === 'requires' && l.from in d && l.to in d)
  for (let pass = 0; pass < nodeIds.length; pass++) {
    let moved = false
    for (const l of req) {
      if (d[l.to] < d[l.from] + 1 && d[l.from] + 1 < nodeIds.length) {
        d[l.to] = d[l.from] + 1
        moved = true
      }
    }
    if (!moved) break
  }
  return d
}

/** Every node upstream of `id` through requires links (not `id` itself), nearest first. */
export function ancestors(id: string, requires: Map<string, string[]>): string[] {
  const out: string[] = []
  const seen = new Set([id])
  const queue = [id]
  while (queue.length) {
    for (const p of requires.get(queue.shift()!) ?? []) {
      if (seen.has(p)) continue
      seen.add(p)
      out.push(p)
      queue.push(p)
    }
  }
  return out
}

/** Given by the engine, else known from its evidence; undefined = derive from the prerequisites. */
function knownState(d: Draft): SkillNodeState | undefined {
  if (d.given) return d.given
  if (d.masteredAt !== undefined) return 'mastered'
  if (d.evidence && d.evidence.done > 0) return 'practicing'
  return undefined
}

/** The furthest-along track (most of it mastered, still unfinished first) and its last skill. */
function trackEnd(drafts: Draft[], links: DraftLink[], states: Map<string, SkillNodeState>): string | undefined {
  const tracks = new Map<string, Draft[]>()
  for (const d of drafts) if (d.kind === 'skill') tracks.set(d.track, [...(tracks.get(d.track) ?? []), d])
  let best: { ds: Draft[]; ratio: number; done: number; open: boolean } | undefined
  for (const ds of tracks.values()) {
    const done = ds.filter((d) => states.get(d.id) === 'mastered').length
    const ratio = done / ds.length
    const open = done < ds.length
    const better = !best || (open && !best.open) || (open === best.open && (ratio > best.ratio || (ratio === best.ratio && done > best.done)))
    if (better) best = { ds, ratio, done, open }
  }
  if (!best) return undefined
  const inTrack = new Set(best.ds.map((d) => d.id))
  const sinks = best.ds.filter((d) => !links.some((l) => l.kind === 'requires' && l.from === d.id && inTrack.has(l.to)))
  return (sinks.length ? sinks : best.ds)[(sinks.length ? sinks : best.ds).length - 1].id
}

function pickGoal(
  g: Rec | undefined,
  drafts: Draft[],
  links: DraftLink[],
  capstones: SkillGraphCapstone[],
  states: Map<string, SkillNodeState>
): { id: string; inferred: boolean } | null {
  if (!drafts.length) return null
  // No goal picked: the picker shows when there are projects to pick from. With none, the goal is inferred (below):
  // the furthest skill the engine's next one leads to, else the furthest-along track's end.
  if (g && 'goal' in g && g.goal === null && capstones.length) return null
  const chosen = g ? str(g.goal, 80) : ''
  if (chosen && drafts.some((d) => d.id === chosen)) return { id: chosen, inferred: false }
  const requires = requiresOf(links)
  const open = capstones.filter((c) => states.get(c.id) !== 'mastered')
  if (open.length) {
    const share = (c: SkillGraphCapstone): number => {
      const path = c.requires.length ? c.requires : ancestors(c.id, requires)
      return path.length ? path.filter((p) => states.get(p) === 'mastered').length / path.length : 0
    }
    const best = [...open].sort((a, b) => share(b) - share(a))[0]
    return { id: best.id, inferred: true }
  }
  const ahead = g ? downstreamEnd(str(rec(g.next).skillId, 80), drafts, links) : undefined
  if (ahead) return { id: ahead, inferred: true }
  const end = trackEnd(drafts, links, states)
  return end ? { id: end, inferred: true } : null
}

/** The furthest skill `from` leads to through requires links (the longest chain; the engine's order breaks ties). */
function downstreamEnd(from: string, drafts: Draft[], links: DraftLink[]): string | undefined {
  if (!from || !drafts.some((d) => d.id === from)) return undefined
  const dist = new Map<string, number>([[from, 0]])
  let frontier = [from]
  for (let step = 1; frontier.length && step <= drafts.length; step++) {
    const nextFrontier: string[] = []
    for (const id of frontier)
      for (const l of links)
        if (l.kind === 'requires' && l.from === id && (dist.get(l.to) ?? -1) < step) {
          dist.set(l.to, step)
          nextFrontier.push(l.to)
        }
    frontier = nextFrontier
  }
  const order = new Map(drafts.map((d, i) => [d.id, i]))
  let best: string | undefined
  for (const [id, d] of dist) if (id !== from && (!best || d > dist.get(best)! || (d === dist.get(best)! && order.get(id)! > order.get(best)!))) best = id
  return best
}

function readWeek(v: unknown): SkillGraphWeek | null {
  if (!v || typeof v !== 'object') return null
  const w = rec(v)
  const days = list(w.days).slice(0, 7).map((d) => d === true)
  return {
    mastered: count(w.mastered),
    keptFresh: count(w.keptFresh),
    minutes: count(w.minutes),
    days,
    weeklyGoal: count(w.weeklyGoal),
    goalAway: count(w.goalAway)
  }
}

// ---- the view model ---------------------------------------------------------------------------------------------

/**
 * The Skills page's view model from a raw `progress` payload (either shape), or undefined when it isn't one.
 * An empty `nodes` means no skills yet (the page's empty state / goal picker).
 */
export function buildSkillGraph(raw: unknown, now: number = Date.now()): SkillGraph | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const m = rec(raw)
  const dash = readDashboard(raw)
  const g = m.graph && typeof m.graph === 'object' && !Array.isArray(m.graph) ? rec(m.graph as SkillGraphInfo) : undefined
  const useGraph = !!g && list(g.skills).length > 0
  const { drafts, links, capstones } = useGraph
    ? draftsFromGraph(g!, dash, now)
    : { ...(dash ? draftsFromTracks(dash, now) : { drafts: [], links: [] }), capstones: [] as SkillGraphCapstone[] }

  // States: given ones first, then ready / locked from the prerequisites' final state.
  const requires = requiresOf(links)
  const states = new Map<string, SkillNodeState>()
  for (const d of drafts) {
    const k = knownState(d)
    if (k) states.set(d.id, k)
  }
  const isMastered = (id: string): boolean => states.get(id) === 'mastered'
  for (const d of drafts) if (!states.has(d.id)) states.set(d.id, (requires.get(d.id) ?? []).every(isMastered) ? 'ready' : 'locked')

  // Goal and its path.
  const goalRef = pickGoal(useGraph ? g : undefined, drafts, links, capstones, states)
  if (goalRef?.inferred && !capstones.length) {
    // No capstones on the wire: the furthest-along track's last skill is drawn as the project.
    const d = drafts.find((x) => x.id === goalRef.id)!
    d.kind = 'capstone'
    capstones.push({ id: d.id, label: d.label, track: d.track, requires: [], checks: [] })
  }
  const cap = goalRef ? capstones.find((c) => c.id === goalRef.id) : undefined
  const pathIds = goalRef ? (cap?.requires.length ? cap.requires : ancestors(goalRef.id, requires).filter((id) => drafts.find((d) => d.id === id)?.kind !== 'capstone')) : []
  const onPath = new Set(goalRef ? [goalRef.id, ...pathIds] : [])

  const depth = depths(
    drafts.map((d) => d.id),
    links
  )
  const order = new Map(drafts.map((d, i) => [d.id, i]))
  const nodes: SkillGraphNode[] = drafts.map((d) => {
    const reqs = requires.get(d.id) ?? []
    const state = states.get(d.id)!
    const { given: _given, reviewDue, ...rest } = d
    return {
      ...rest,
      state,
      review: state === 'mastered' && reviewDue,
      requires: reqs,
      needs: reqs.filter((r) => !isMastered(r)),
      depth: depth[d.id] ?? 0,
      onGoalPath: onPath.has(d.id),
      isGoal: d.id === goalRef?.id,
      isNext: false
    }
  })
  const byId: Record<string, SkillGraphNode> = Object.fromEntries(nodes.map((n) => [n.id, n]))

  const goal: SkillGraphGoal | null = goalRef
    ? {
        id: goalRef.id,
        label: byId[goalRef.id].label,
        pathIds,
        mastered: pathIds.filter((id) => byId[id]?.state === 'mastered').length,
        practicing: pathIds.filter((id) => byId[id]?.state === 'practicing').length,
        total: pathIds.length,
        inferred: goalRef.inferred
      }
    : null

  // Ordering for the dock: the goal's path first, then the shallowest, then the engine's order.
  const rank = (a: SkillGraphNode, b: SkillGraphNode): number =>
    Number(b.onGoalPath) - Number(a.onGoalPath) || a.depth - b.depth || (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)
  const skills = nodes.filter((n) => n.kind === 'skill')

  // Next.
  const given = useGraph ? rec(g!.next) : {}
  let nextId = str(given.skillId, 80)
  if (!byId[nextId]) {
    const practicing = skills
      .filter((n) => n.state === 'practicing')
      .sort((a, b) => Number(b.onGoalPath) - Number(a.onGoalPath) || (b.lastPracticedAt ?? 0) - (a.lastPracticedAt ?? 0) || rank(a, b))
    const ready = skills.filter((n) => n.state === 'ready').sort(rank)
    const onPathFirst = [...practicing.filter((n) => n.onGoalPath), ...ready.filter((n) => n.onGoalPath), ...practicing, ...ready]
    nextId = onPathFirst[0]?.id ?? (goal && byId[goal.id].state === 'ready' ? goal.id : '')
  }
  const next = nextId ? pickFor(byId[nextId], given, dash, byId, goal) : null
  if (next) byId[next.skillId].isNext = true

  // Also ready, keep fresh.
  const valid = (xs: string[], ok: (n: SkillGraphNode) => boolean): string[] => xs.filter((id) => byId[id] && id !== nextId && ok(byId[id])).slice(0, MAX_SIDE)
  const startable = (n: SkillGraphNode): boolean => n.kind === 'skill' && (n.state === 'ready' || n.state === 'practicing')
  const alsoReady =
    useGraph && Array.isArray(g!.alsoReady)
      ? valid(ids(g!.alsoReady), startable)
      : skills
          .filter((n) => startable(n) && n.id !== nextId)
          .sort(rank)
          .slice(0, MAX_SIDE)
          .map((n) => n.id)
  const keepFresh =
    useGraph && Array.isArray(g!.keepFresh)
      ? valid(ids(g!.keepFresh), (n) => n.state === 'mastered')
      : skills
          .filter((n) => n.review)
          .sort((a, b) => (a.dueAt ?? 0) - (b.dueAt ?? 0))
          .slice(0, MAX_SIDE)
          .map((n) => n.id)

  // Events not acked yet, oldest first.
  const ackedUntil = useGraph ? toMs(g!.ackedUntil) : undefined
  const events: SkillGraphEvent[] = []
  let ack: string | number | undefined
  let newest = -Infinity
  for (const x of useGraph ? list(g!.events) : []) {
    const e = rec(x)
    const id = str(e.id, 80)
    const at = toMs(e.at)
    const kind = e.kind as SkillGraphEvent['kind']
    if (!id || at === undefined || !EVENT_KINDS.has(kind) || !byId[str(e.skillId, 80)] || events.some((v) => v.id === id)) continue
    if (ackedUntil !== undefined && at <= ackedUntil) continue
    events.push({ id, kind, skillId: str(e.skillId, 80), at, from: byId[str(e.from, 80)] ? str(e.from, 80) : undefined, lessonId: opt(e.lessonId, 120) })
    if (at > newest) {
      newest = at
      ack = e.at as string | number
    }
  }
  events.sort((a, b) => a.at - b.at)

  // Tracks, in first-seen order.
  const tracks: SkillGraphTrack[] = []
  for (const n of nodes) {
    const key = skillKey(n.track) || '_'
    let t = tracks.find((x) => x.id === key)
    if (!t) tracks.push((t = { id: key, label: n.track, nodeIds: [], mastered: 0, total: 0 }))
    t.nodeIds.push(n.id)
    if (n.kind === 'skill') {
      t.total++
      if (n.state === 'mastered') t.mastered++
    }
  }
  for (const n of nodes) n.track = skillKey(n.track) || '_'
  for (const c of capstones) c.track = skillKey(c.track) || '_'

  const fallbackWeek = rec(m.week)
  const week = useGraph && g!.week ? readWeek(g!.week as SkillWeek) : m.week ? readWeek({ minutes: fallbackWeek.minutes, days: fallbackWeek.days }) : null
  const portfolio: SkillGraphPortfolioItem[] = []
  for (const x of useGraph ? list(g!.portfolio) : []) {
    const p = rec(x)
    const capstoneId = str(p.capstoneId, 80)
    const title = str(p.title, 120)
    if (!capstoneId || !title) continue
    const art = rec(p.artifact)
    portfolio.push({
      capstoneId,
      title,
      at: toMs(p.at),
      track: opt(p.track, 80),
      skillIds: ids(p.skillIds),
      artifact: art.kind === 'image' || art.kind === 'file' ? { kind: art.kind, path: opt(art.path, 400), caption: opt(art.caption, 120) } : undefined
    })
  }

  return {
    source: useGraph ? 'graph' : 'tracks',
    nodes,
    byId,
    links: links.map((l) => ({ ...l, onGoalPath: onPath.has(l.from) && onPath.has(l.to) })),
    tracks,
    capstones,
    goal,
    next,
    alsoReady,
    keepFresh,
    events,
    ack,
    week,
    portfolio
  }
}

/** The dock's NEXT for one skill: the engine's pick when given, else the lesson that teaches it (in progress first). */
function pickFor(n: SkillGraphNode, given: Rec, dash: DashData | undefined, byId: Record<string, SkillGraphNode>, goal: SkillGraphGoal | null): SkillGraphPick {
  const lesson = n.lessons.find((l) => l.inProgress) ?? n.lessons.find((l) => l.role !== 'uses') ?? n.lessons[0]
  const active = lesson ? dash?.inProgress.find((a) => a.lessonId === lesson.lessonId) : undefined
  const keys = new Set([n.id, skillKey(n.label)])
  const upNext = dash?.next.find((x) => x.unlocks.some((u) => keys.has(u) || keys.has(skillKey(u))))
  // "gets you closer to X": the first locked skill on the goal's path that needs this one.
  const opens = goal ? Object.values(byId).find((m) => m.onGoalPath && m.state === 'locked' && m.requires.includes(n.id)) : undefined
  const mine = str(given.skillId, 80) === n.id
  return {
    skillId: n.id,
    label: n.label,
    practicing: n.state === 'practicing',
    lessonId: (mine ? opt(given.lessonId, 120) : undefined) ?? lesson?.lessonId,
    libraryId: (mine ? libId(given.libraryId) : undefined) ?? lesson?.libraryId ?? active?.libraryId ?? upNext?.id,
    lessonTitle: (mine ? opt(given.lessonTitle, 120) : undefined) ?? lesson?.title ?? active?.title ?? upNext?.title,
    stepIndex: (mine ? count(given.stepIndex) : undefined) ?? active?.stepIndex,
    stepCount: (mine ? count(given.stepCount) : undefined) ?? active?.stepCount,
    estMinutes: (mine ? count(given.estMinutes) : undefined) ?? upNext?.estMinutes,
    goal: (mine ? opt(given.goal, 300) : undefined) ?? upNext?.goal,
    why: (mine ? opt(given.why, 120) : undefined) ?? (opens ? `gets you closer to ${opens.label}` : undefined)
  }
}

/** A Library item's skill chips (LibraryItem teaches / uses / unlocks), resolved against the graph by id or label. */
export function libraryItemSkills(item: unknown, g: SkillGraph | undefined): { teaches: SkillGraphNode[]; uses: SkillGraphNode[]; unlocks: SkillGraphNode[] } {
  const i = rec(item)
  const find = (v: string): SkillGraphNode | undefined => g?.byId[v] ?? g?.nodes.find((n) => skillKey(n.label) === skillKey(v))
  const resolve = (v: unknown): SkillGraphNode[] => ids(v).map(find).filter((n): n is SkillGraphNode => !!n)
  return { teaches: resolve(i.teaches), uses: resolve(i.uses), unlocks: resolve(i.unlocks) }
}

/** "needs 3 skills" / "needs A single neuron" for a locked node; undefined when nothing is missing. */
export function needsLine(n: SkillGraphNode, g: SkillGraph): string | undefined {
  if (n.state !== 'locked' || !n.needs.length) return undefined
  return n.needs.length === 1 ? `needs ${g.byId[n.needs[0]]?.label ?? '1 skill'}` : `needs ${n.needs.length} skills`
}
