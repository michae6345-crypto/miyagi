/**
 * Two layouts for Adrian to pick from (pass 3, "make them simpler"):
 *   'all'   every command is a tile: Back · Explain · Diagram · Show me · Hint · Voice | Check · Skip step · End lesson
 *   'more'  Back / Skip step / End lesson move into a "More" tile with a small menu above the bar
 * Default 'all' (nothing removed). The stage previews the other with ?bar=more. Once Adrian picks, delete the other.
 */
export type BarLayout = 'all' | 'more'

export const barLayout: BarLayout = (() => {
  try {
    const q = new URLSearchParams(window.location.search).get('bar')
    if (q === 'all' || q === 'more') return q
  } catch {
    /* no window (tests) */
  }
  return 'all'
})()
