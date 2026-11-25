/**
 * The Library's lesson tables: which columns show and how wide each one is (Adrian's v4 mock, `libraryFull` in
 * docs/ui-next/mock/v4.js: Lesson · Plan · Works in · Grows · Time · Progress · Opened).
 *
 * Rules (Michael, Nov 24 "library-cols"):
 *   - A column shows unless every row lacks it (the caller passes need 0 for an empty one). Never by width alone.
 *   - The Lesson column comes first: it gets the room its longest title needs (capped at half the table, so one long
 *     title can't push every other column out). The other columns are sized to their content, like the mock's fixed
 *     colgroup; on a wide pane they ease out toward the mock's widths (EASY), and the Lesson column takes the rest.
 *   - When the titles don't fit, Plan and Grows give way first: they shrink (and truncate) down to their floor.
 *   - Only then does a column drop, in DROP order (Plan, Grows, Opened, Works in). Time and Progress always stay.
 *   - If the titles still don't fit with everything dropped, the titles truncate.
 *
 * Pure (no DOM): Library.tsx measures the text and passes the widths in. Tested by test/libraryCols.test.ts.
 */

export type ColKey = 'plan' | 'tool' | 'grows' | 'time' | 'progress' | 'opened'

/** The mock's column order after Lesson. */
export const ORDER: readonly ColKey[] = ['plan', 'tool', 'grows', 'time', 'progress', 'opened']
/** Who leaves first when the titles need the room. */
export const DROP: readonly ColKey[] = ['plan', 'grows', 'opened', 'tool']
/** The columns that shrink (and truncate) before anything drops, and how far. */
export const FLOOR: Partial<Record<ColKey, number>> = { plan: 72, grows: 84 }
/** The most a content-sized column takes (the mock's colgroup widths less the cell padding, a little looser). */
export const CAP: Record<ColKey, number> = { plan: 160, tool: 96, grows: 200, time: 72, progress: 160, opened: 96 }
/**
 * The mock's colgroup (156 / 96 / 186 / 70 / 136 / 96, cell padding included) less our 16 px gap: room a column gets
 * on a wide pane once every title fits, so the columns breathe like the mock's instead of the Lesson column taking it all.
 */
export const EASY: Record<ColKey, number> = { plan: 140, tool: 80, grows: 170, time: 54, progress: 120, opened: 80 }
/** The Lesson column never asks for less than this, so a table of short titles keeps a readable first column. */
export const LESSON_MIN = 200

export type ColsInput = {
  /** The table's width (px). */
  width: number
  /** The grid's column gap (px). */
  gap: number
  /** What the Lesson column needs for its longest title, thumb included (px). */
  title: number
  /** Each column's content width (px, header included); 0 or missing = every row lacks it, so it's left out. */
  need: Partial<Record<ColKey, number>>
}

export type ColsLayout = {
  /** The columns that show, in order, with their widths (px). */
  cols: { key: ColKey; width: number }[]
  /** The grid template: Lesson first (`minmax(0,1fr)`, it takes the rest), then each column's px. */
  template: string
  /** What's left for the Lesson column (px). */
  lesson: number
  /** True when the longest title fits whole. */
  titleFits: boolean
}

const sum = (xs: number[]): number => xs.reduce((a, b) => a + b, 0)

export function layoutCols({ width, gap, title, need }: ColsInput): ColsLayout {
  const present = ORDER.filter((k) => (need[k] ?? 0) > 0)
  const want = (k: ColKey): number => Math.min(CAP[k], Math.ceil(need[k] ?? 0))
  const floor = (k: ColKey): number => Math.min(want(k), FLOOR[k] ?? want(k))
  // Whole titles first, but never more than half the table (a very long title truncates rather than empty the row).
  const lessonNeed = Math.max(Math.min(title, width / 2), Math.min(title, LESSON_MIN))
  const shown = [...present]
  const make = (widths: Map<ColKey, number>): ColsLayout => {
    // Floor, not round: the px columns never add up to more than the room, so the Lesson column keeps its share.
    const cols = shown.map((key) => ({ key, width: Math.floor(widths.get(key) ?? want(key)) }))
    const lesson = width - gap * cols.length - sum(cols.map((c) => c.width))
    return { cols, template: ['minmax(0,1fr)', ...cols.map((c) => `${c.width}px`)].join(' '), lesson, titleFits: lesson >= title }
  }
  for (;;) {
    const room = width - gap * shown.length
    const full = sum(shown.map(want))
    // Everything at its content width, and the titles fit: done (Lesson takes the rest).
    if (room - full >= lessonNeed) {
      // Room to spare: each column eases toward the mock's width, evenly, never past what's spare.
      const ease = shown.map((k) => Math.max(0, EASY[k] - want(k)))
      const f = Math.min(1, (room - full - lessonNeed) / Math.max(1, sum(ease)))
      return make(new Map(shown.map((k, i) => [k, want(k) + ease[i] * f])))
    }
    // Plan and Grows give way first: shrink them evenly toward their floor.
    const short = lessonNeed - (room - full)
    const give = shown.map((k) => want(k) - floor(k))
    const slack = sum(give)
    if (slack >= short) {
      const f = short / slack
      return make(new Map(shown.map((k, i) => [k, want(k) - give[i] * f])))
    }
    // Then a column drops.
    const next = DROP.find((k) => shown.includes(k))
    if (!next) return make(new Map(shown.map((k) => [k, floor(k)])))
    shown.splice(shown.indexOf(next), 1)
  }
}
