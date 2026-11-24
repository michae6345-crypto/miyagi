/**
 * Feature: plans. The lesson-plan catalog (Adrian's docs/ui-next/catalog, Nov 24: 40 plans, 382 lessons, 372 skills)
 * and the 50 YouTube playlists matched to 25 of them. Data only: copied in as catalog.json / playlists.json (both
 * as Adrian ships them). It replaces library/presets/packs.ts for the Library and Plans pages.
 *
 * A lesson's `goal` is the text the engine builds it from (`learn {query: goal, mode: "lesson"}`); `passes` is one
 * sentence a machine could verify. Skill ids are stable (`bl.modifiers`).
 */
import type { Catalog, CatalogLesson, CatalogPlan, CatalogPlaylist, CatalogSkill, PlanCheckKind, PlanProposal, PlanState, PlanTopic, PlaylistInfo } from '../../../../../../shared/contracts/events'
import raw from './catalog.json'
import rawPlaylists from './playlists.json'

// The catalog's shape is the ui-v4 contract's (shared/contracts/events.ts, UI-V4.md "Plans"): no local copies.
export type { Catalog, CatalogLesson, CatalogPlan, CatalogPlaylist, CatalogProject, CatalogSkill, PlanCheckKind, PlanLessonRef, PlanTopic } from '../../../../../../shared/contracts/events'

export const PLANS: readonly CatalogPlan[] = (raw as Catalog).plans
export const PLAYLISTS: readonly CatalogPlaylist[] = rawPlaylists as CatalogPlaylist[]

const byId = new Map(PLANS.map((p) => [p.id, p]))
export const planById = (id: string | undefined): CatalogPlan | undefined => (id ? byId.get(id) : undefined)

export const TOPIC_TABS: ReadonlyArray<{ id: PlanTopic | 'all'; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'code', label: 'Code' },
  { id: 'data', label: 'Data' },
  { id: 'ai', label: 'AI' },
  { id: '3d', label: '3D' },
  { id: 'cad', label: 'CAD' },
  { id: 'design', label: 'Design' },
  { id: 'tools', label: 'Tools' }
]

/** The Plans page's three tables (the mock's groups, by the plan's `group`), each sorted by title. */
export const PLAN_GROUPS: ReadonlyArray<{ id: string; label: string; match: (p: CatalogPlan) => boolean; after: boolean }> = [
  { id: 'languages', label: 'Coding languages', match: (p) => p.group === 'language', after: true },
  { id: 'apps', label: 'Apps and tools', match: (p) => p.group === 'environment', after: false },
  { id: 'further', label: 'Going further', match: (p) => p.group === 'topic', after: true }
]

/** The four plans the mock puts first ("Start here", and Library's "Start a plan"). */
export const START_HERE = ['intro-python', 'intro-blender', 'intro-cad', 'intro-javascript']
/** The first-run Library's eight (Library -27). */
export const FIRST_RUN = [...START_HERE, 'pandas', 'plotting', 'neural-networks', 'intro-terminal']
/** Library's "Start a plan" once the learner has a plan going (the mock: pandas, plotting, CAD, JavaScript). */
export const NEXT_UP = ['pandas', 'plotting', 'intro-cad', 'intro-javascript', 'intro-python']

export const planMinutes = (p: CatalogPlan): number => p.lessons.reduce((n, l) => n + l.minutes, 0)

/** "about 2.5 hr", rounded to the half hour; under an hour, "about 45 min". */
export function aboutHours(min: number): string {
  if (min < 60) return `about ${Math.max(5, Math.round(min / 5) * 5)} min`
  const h = Math.round(min / 30) / 2
  return `about ${h} hr`
}
/** "2.5 hr" (the tables' Time column). */
export const hoursShort = (min: number): string => `${Math.max(0.5, Math.round(min / 30) / 2)} hr`

/** "A desk lamp, modeled and rendered" → "a desk lamp, modeled and rendered" after "Ends with". */
export const endsWith = (p: CatalogPlan): string => `Ends with ${p.project.title.charAt(0).toLowerCase()}${p.project.title.slice(1)}`

/** Where a plan's work is read from, in words (the plan page's "Checked by"). */
export function checkedBy(p: CatalogPlan): string {
  const kinds = new Set(p.lessons.map((l) => l.check))
  if (kinds.has('scene')) return p.tool.id === 'blender' ? 'Reading your scene through the miyagi add-on' : `Reading your model through ${p.tool.label}`
  if (kinds.has('run')) return 'Running your code and reading what it prints'
  if (kinds.has('code')) return 'Reading the file you typed'
  if (kinds.has('file')) return 'Reading the files you save'
  return `Looking at the ${p.tool.label} window`
}

/** A skill's label, from any plan (skill ids are global). */
const skillLabels = new Map(PLANS.flatMap((p) => p.skills.map((s) => [s.id, s.label] as const)))
export const skillLabel = (id: string): string | undefined => skillLabels.get(id)

/**
 * The catalog skill a video title names ("Blender Basic UV Unwrapping Tutorial" -> UV unwrapping), or undefined. Every
 * catalog skill is a candidate: the playlist's own plan first, then plans in the same tool, then the rest. Words are
 * compared by stem ("Texturing" ~ "textures", "Modelling" ~ "model"), whole words only, so "Edit mode" never matches
 * "Modelling". A skill of another tool needs every word of its label in the title; a skill of the playlist's own tool
 * may match on its last word alone when no other skill uses that word ("Image textures" for "Basic Texturing"). No match means no chip, never a
 * guess from the video's position.
 */
const TITLE_NOISE = new Set(['and', 'the', 'for', 'with', 'from', 'your', 'into', 'basic', 'basics', 'first', 'part', 'tutorial', 'beginner', 'beginners', 'course', 'lesson', 'intro', 'introduction', 'guide', 'building', 'making', 'using', 'getting', 'started', 'learn', 'learning', 'explained'])
const stem = (w: string): string => w.replace(/(ings|ing|es|ed|s)$/, '').replace(/(.)\1$/, '$1')
const stems = (t: string, tool = ''): string[] =>
  t
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length > 2 && !TITLE_NOISE.has(w) && w !== tool)
    .map(stem)
const STEM_USES = new Map<string, number>()
for (const p of PLANS) for (const k of p.skills) for (const w of new Set(stems(k.label))) STEM_USES.set(w, (STEM_USES.get(w) ?? 0) + 1)
export function skillForTitle(title: string, plan: CatalogPlan | undefined): CatalogSkill | undefined {
  const tool = plan?.tool.label.toLowerCase() ?? ''
  const words = new Set(stems(title, tool))
  const own = plan ? PLANS.filter((p) => p.tool.id === plan.tool.id).sort((a, b) => (a === plan ? -1 : b === plan ? 1 : 0)) : []
  const rest = PLANS.filter((p) => !own.includes(p))
  const every = (label: string): boolean => {
    const need = stems(label, tool)
    return need.length > 0 && need.every((w) => words.has(w))
  }
  // The last word alone counts only when no other skill in the catalog uses that word ("textures" yes, "model" no).
  const head = (label: string): boolean => {
    const need = stems(label, tool)
    const last = need[need.length - 1]
    return !!last && words.has(last) && (STEM_USES.get(last) ?? 0) === 1
  }
  for (const test of [every, head]) {
    for (const p of own) {
      const s = p.skills.find((k) => test(k.label))
      if (s) return s
    }
  }
  for (const p of rest) {
    const s = p.skills.find((k) => every(k.label))
    if (s) return s
  }
  return undefined
}

/** The plan a lesson title belongs to (catalog titles are unique enough for this). */
const lessonPlan = new Map(PLANS.flatMap((p) => p.lessons.map((l) => [l.title.toLowerCase(), p] as const)))
export const planForLesson = (title: string): CatalogPlan | undefined => lessonPlan.get(title.toLowerCase())

/** The plan's short name for a table cell: "Neural networks from scratch" → "Neural networks". */
export const planShort = (p: CatalogPlan): string => p.title.replace(/ from scratch$/i, '').replace(/^Working with /i, '')

export const playlistsFor = (planId: string): CatalogPlaylist[] => PLAYLISTS.filter((l) => l.planId === planId)

/** The playlist id in a pasted link (`list=`), or a bare id. */
export function playlistIdOf(text: string): string | undefined {
  const t = text.trim()
  const m = /[?&]list=([A-Za-z0-9_-]{10,64})/.exec(t)
  if (m) return m[1]
  return /^PL[A-Za-z0-9_-]{10,62}$/.test(t) ? t : undefined
}
export const playlistById = (id: string | undefined): CatalogPlaylist | undefined => (id ? PLAYLISTS.find((l) => l.playlistId === id) : undefined)

/** "4 h 20 min". */
export function lengthLabel(seconds: number): string {
  const m = Math.round(seconds / 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`
}

/** The plans named as `needs`, as titles ("Intro to JavaScript"). */
export const afterTitles = (p: CatalogPlan): string => p.needs.map((id) => planById(id)?.title ?? '').filter(Boolean).join(', ')

/** Plans that list this one in `needs` (the plan page's "After this plan"). */
export const nextPlans = (p: CatalogPlan): CatalogPlan[] => PLANS.filter((q) => q.needs.includes(p.id))

/**
 * A plan from a goal, offline (until the contract's plan message lands): the plans whose words match the goal, the
 * chosen tool's plan first, then the plan that builds on it. Lessons stop at eight, then the first plan's project.
 */
export type GoalLesson = CatalogLesson & { from: CatalogPlan }
export function planFromGoal(goal: string, toolId?: string): { tools: CatalogPlan[]; lessons: GoalLesson[]; project?: { title: string; check: string; minutes: number }; from: CatalogPlan[] } {
  const words = goal
    .toLowerCase()
    .split(/[^a-z0-9+#]+/)
    .filter((w) => w.length > 2 && !STOP.has(w))
  const score = (p: CatalogPlan): number => {
    const hay = `${p.title} ${p.line} ${p.project.title} ${p.project.brief} ${p.tool.label} ${p.track}`.toLowerCase()
    return words.reduce((n, w) => n + (hay.includes(w) ? 1 : 0), 0) + (words.some((w) => SYNONYM[w] && SYNONYM[w].includes(p.topic)) ? 2 : 0)
  }
  const ranked = PLANS.map((p) => [p, score(p)] as const)
    .filter(([, s]) => s > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([p]) => p)
  if (!ranked.length) return { tools: [], lessons: [], from: [] }
  const top = ranked[0]
  // The tools: start plans of the same topic that the goal's words also match (FreeCAD, Fusion, Onshape for a CAD
  // goal; Google Sheets and Excel for a budget, not every app in the topic), each app once (QA R2-06).
  const matched = PLANS.filter((p) => p.topic === top.topic && p.level === 'start' && ranked.includes(p))
  const fallback = top.level === 'start' ? top : planById(top.needs[0]) ?? top
  const tools = uniqueTools(matched.length ? matched : [fallback])
  const base = (toolId && tools.find((p) => p.tool.id === toolId)) || (top.level === 'start' ? top : planById(top.needs[0]) ?? top)
  if (!tools.some((p) => p.tool.id === base.tool.id)) tools.unshift(base)
  const further = PLANS.find((p) => p.needs.includes(base.id) && p.topic === base.topic && ranked.includes(p))
  const lessons: GoalLesson[] = [...base.lessons.slice(0, further ? 6 : 8).map((l) => ({ ...l, from: base })), ...(further ? further.lessons.slice(0, 2).map((l) => ({ ...l, from: further })) : [])]
  const proj = base.project
  return { tools, lessons, from: further ? [base, further] : [base], project: { title: proj.title, check: proj.checks[0], minutes: 45 } }
}
/** One plan per app (two start plans can share a tool, as two Terminal plans do). */
function uniqueTools(plans: CatalogPlan[]): CatalogPlan[] {
  const seen = new Set<string>()
  return plans.filter((p) => !seen.has(p.tool.id) && !!seen.add(p.tool.id))
}
const STOP = new Set(['want', 'the', 'and', 'for', 'my', 'how', 'make', 'learn', 'with', 'own', 'build', 'some', 'that', 'this', 'from'])
const SYNONYM: Record<string, PlanTopic[]> = { print: ['cad'], stand: ['cad'], bracket: ['cad'], model: ['3d', 'cad'], render: ['3d'], game: ['code'], website: ['code'], data: ['data'], chart: ['data'], app: ['code'] }

// ---- offline fallbacks in the contract's shapes ------------------------------------------------------------------
// When no engine answers playlist.get / plan.propose (the browser stage, an engine without the ui-v4 plan messages),
// the dialogs draw the same PlaylistInfo / PlanProposal from the catalog, so there is one way to draw each.

/** A catalog playlist as playlist.get's answer: every video a lesson growing the skill its title names. */
export function playlistInfoFromCatalog(list: CatalogPlaylist): PlaylistInfo {
  const plan = planById(list.planId)
  return {
    url: list.url,
    playlistId: list.playlistId,
    title: list.title,
    channel: list.channel,
    videoCount: list.videoCount,
    totalSeconds: list.totalSeconds,
    videos: list.videos,
    proposing: false,
    proposal: {
      title: list.title,
      source: 'playlist',
      tool: plan?.tool,
      lessons: list.videos.map((v) => {
        const k = skillForTitle(v.title, plan)
        return { title: v.title, videoId: v.id, seconds: v.seconds, minutes: Math.round((v.seconds ?? 0) / 60), grows: k ? [k.id] : [], skills: k ? [k.label] : [] }
      }),
      project: plan?.project ?? null,
      fromPlans: plan ? [plan.id] : []
    }
  }
}

/** planFromGoal as plan.proposal's answer (lessons carry `from`, the plan's project at the end). Null: nothing fits. */
export function proposalFromGoal(goal: string, toolId?: string): PlanProposal | null {
  const built = planFromGoal(goal, toolId)
  const base = built.from[0]
  if (!base) return null
  const minutes = built.lessons.reduce((n, l) => n + l.minutes, 0) + (built.project?.minutes ?? 0)
  return {
    title: goal.trim().replace(/^i want to /i, '').replace(/^./, (c) => c.toUpperCase()),
    source: 'goal',
    tool: base.tool,
    tools: built.tools.map((p) => p.tool),
    lessons: built.lessons.map((l) => ({ title: l.title, goal: l.goal, minutes: l.minutes, grows: l.grows, skills: l.grows.map((g) => skillLabel(g) ?? g), from: { planId: l.from.id, index: l.from.lessons.findIndex((x) => x.title === l.title) } })),
    project: base.project,
    minutes,
    fromPlans: built.from.map((p) => p.id),
    note: built.from.length > 1 ? 'Built from two plans. Lessons you would not need are left out.' : `Built from ${base.title}.`
  }
}

/** A catalog plan as the engine's PlanState before it answers (plan.start's optimistic row; ?plans=demo). */
export function planStateFromCatalog(p: CatalogPlan, done = 0): PlanState {
  return {
    id: p.id,
    title: p.title,
    source: 'preset',
    catalogId: p.id,
    track: p.track,
    tool: p.tool,
    lessons: p.lessons.map((l, index) => ({ index, title: l.title, goal: l.goal, minutes: l.minutes, stepCount: l.steps, check: l.check, passes: l.passes, skillIds: l.grows, state: index < done ? 'done' : index === done ? 'next' : 'todo' })),
    project: { ...p.project, state: 'locked' },
    done,
    total: p.lessons.length,
    nextIndex: done < p.lessons.length ? done : null,
    minutesLeft: p.lessons.slice(done).reduce((n, l) => n + l.minutes, 0)
  }
}

/** A proposal (playlist or goal) as the PlanState it becomes, for the offline path. Skipped lessons are left out. */
export function planStateFromProposal(id: string, pr: PlanProposal, extra: Partial<PlanState> = {}): PlanState {
  const kept = pr.lessons.filter((l) => !l.skip)
  return {
    id,
    title: pr.title,
    source: pr.source,
    tool: pr.tool,
    lessons: kept.map((l, index) => ({ index, title: l.title, goal: l.goal, videoId: l.videoId, seconds: l.seconds, minutes: l.minutes, skillIds: l.grows, state: index === 0 ? 'next' : 'todo' })),
    project: pr.project ? { ...pr.project, state: 'locked' } : null,
    done: 0,
    total: kept.length,
    nextIndex: kept.length ? 0 : null,
    minutesLeft: kept.reduce((n, l) => n + (l.minutes ?? 0), 0),
    ...extra
  }
}
