/**
 * Feature: plans. The lesson-plan catalog (Adrian's docs/ui-next/catalog, Nov 24: 40 plans, 382 lessons, 372 skills)
 * and the 50 YouTube playlists matched to 25 of them. Data only: copied in as catalog.json / playlists.json (the
 * playlists keep only what the UI shows). It replaces library/presets/packs.ts for the Library and Plans pages.
 *
 * A lesson's `goal` is the text the engine builds it from (`learn {query: goal, mode: "lesson"}`); `passes` is one
 * sentence a machine could verify. Skill ids are stable (`bl.modifiers`).
 */
import raw from './catalog.json'
import rawPlaylists from './playlists.json'

export type PlanTopic = 'code' | 'data' | 'ai' | '3d' | 'cad' | 'design' | 'tools'
export type PlanGroup = 'language' | 'environment' | 'topic'
export type CheckKind = 'run' | 'code' | 'scene' | 'file' | 'screen'

export type PlanSkill = { id: string; label: string; needs: string[] }
export type PlanLesson = { title: string; goal: string; grows: string[]; minutes: number; steps: number; check: CheckKind; passes: string }
export type Plan = {
  id: string
  title: string
  group: PlanGroup
  topic: PlanTopic
  track: string
  tool: { id: string; label: string }
  also: string[]
  level: 'start' | 'next'
  needs: string[]
  line: string
  project: { title: string; brief: string; checks: string[] }
  skills: PlanSkill[]
  lessons: PlanLesson[]
}
export type Playlist = { planId: string; title: string; channel: string; playlistId: string; videoCount: number; totalSeconds: number; videos: { title: string; seconds: number }[] }

export const PLANS: readonly Plan[] = (raw as { plans: Plan[] }).plans
export const PLAYLISTS: readonly Playlist[] = rawPlaylists as Playlist[]

const byId = new Map(PLANS.map((p) => [p.id, p]))
export const planById = (id: string | undefined): Plan | undefined => (id ? byId.get(id) : undefined)

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
export const PLAN_GROUPS: ReadonlyArray<{ id: string; label: string; match: (p: Plan) => boolean; after: boolean }> = [
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

export const planMinutes = (p: Plan): number => p.lessons.reduce((n, l) => n + l.minutes, 0)

/** "about 2.5 hr", rounded to the half hour; under an hour, "about 45 min". */
export function aboutHours(min: number): string {
  if (min < 60) return `about ${Math.max(5, Math.round(min / 5) * 5)} min`
  const h = Math.round(min / 30) / 2
  return `about ${h} hr`
}
/** "2.5 hr" (the tables' Time column). */
export const hoursShort = (min: number): string => `${Math.max(0.5, Math.round(min / 30) / 2)} hr`

/** "A desk lamp, modeled and rendered" → "a desk lamp, modeled and rendered" after "Ends with". */
export const endsWith = (p: Plan): string => `Ends with ${p.project.title.charAt(0).toLowerCase()}${p.project.title.slice(1)}`

/** Where a plan's work is read from, in words (the plan page's "Checked by"). */
export function checkedBy(p: Plan): string {
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

/** The plan a lesson title belongs to (catalog titles are unique enough for this). */
const lessonPlan = new Map(PLANS.flatMap((p) => p.lessons.map((l) => [l.title.toLowerCase(), p] as const)))
export const planForLesson = (title: string): Plan | undefined => lessonPlan.get(title.toLowerCase())

/** The plan's short name for a table cell: "Neural networks from scratch" → "Neural networks". */
export const planShort = (p: Plan): string => p.title.replace(/ from scratch$/i, '').replace(/^Working with /i, '')

export const playlistsFor = (planId: string): Playlist[] => PLAYLISTS.filter((l) => l.planId === planId)

/** The playlist id in a pasted link (`list=`), or a bare id. */
export function playlistIdOf(text: string): string | undefined {
  const t = text.trim()
  const m = /[?&]list=([A-Za-z0-9_-]{10,64})/.exec(t)
  if (m) return m[1]
  return /^PL[A-Za-z0-9_-]{10,62}$/.test(t) ? t : undefined
}
export const playlistById = (id: string | undefined): Playlist | undefined => (id ? PLAYLISTS.find((l) => l.playlistId === id) : undefined)

/** "4 h 20 min". */
export function lengthLabel(seconds: number): string {
  const m = Math.round(seconds / 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`
}

/** The plans named as `needs`, as titles ("Intro to JavaScript"). */
export const afterTitles = (p: Plan): string => p.needs.map((id) => planById(id)?.title ?? '').filter(Boolean).join(', ')

/** Plans that list this one in `needs` (the plan page's "After this plan"). */
export const nextPlans = (p: Plan): Plan[] => PLANS.filter((q) => q.needs.includes(p.id))

/**
 * A plan from a goal, offline (until the contract's plan message lands): the plans whose words match the goal, the
 * chosen tool's plan first, then the plan that builds on it. Lessons stop at eight, then the first plan's project.
 */
export type GoalLesson = PlanLesson & { from: Plan }
export function planFromGoal(goal: string, toolId?: string): { tools: Plan[]; lessons: GoalLesson[]; project?: { title: string; check: string; minutes: number }; from: Plan[] } {
  const words = goal
    .toLowerCase()
    .split(/[^a-z0-9+#]+/)
    .filter((w) => w.length > 2 && !STOP.has(w))
  const score = (p: Plan): number => {
    const hay = `${p.title} ${p.line} ${p.project.title} ${p.project.brief} ${p.tool.label} ${p.track}`.toLowerCase()
    return words.reduce((n, w) => n + (hay.includes(w) ? 1 : 0), 0) + (words.some((w) => SYNONYM[w] && SYNONYM[w].includes(p.topic)) ? 2 : 0)
  }
  const ranked = PLANS.map((p) => [p, score(p)] as const)
    .filter(([, s]) => s > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([p]) => p)
  if (!ranked.length) return { tools: [], lessons: [], from: [] }
  const top = ranked[0]
  // The tools: start plans of the same topic (FreeCAD, Fusion, Onshape for CAD).
  const tools = PLANS.filter((p) => p.topic === top.topic && p.level === 'start')
  const base = (toolId && tools.find((p) => p.tool.id === toolId)) || (top.level === 'start' ? top : planById(top.needs[0]) ?? top)
  const further = PLANS.find((p) => p.needs.includes(base.id) && p.topic === base.topic && ranked.includes(p))
  const lessons: GoalLesson[] = [...base.lessons.slice(0, further ? 6 : 8).map((l) => ({ ...l, from: base })), ...(further ? further.lessons.slice(0, 2).map((l) => ({ ...l, from: further })) : [])]
  const proj = base.project
  return { tools, lessons, from: further ? [base, further] : [base], project: { title: proj.title, check: proj.checks[0], minutes: 45 } }
}
const STOP = new Set(['want', 'the', 'and', 'for', 'my', 'how', 'make', 'learn', 'with', 'own', 'build', 'some', 'that', 'this', 'from'])
const SYNONYM: Record<string, PlanTopic[]> = { print: ['cad'], stand: ['cad'], bracket: ['cad'], model: ['3d', 'cad'], render: ['3d'], game: ['code'], website: ['code'], data: ['data'], chart: ['data'], app: ['code'] }
