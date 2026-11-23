/** Web links shown in the overlay (citations, sources, the Watch tile): pure, so tests import it without the stores. */

/** http(s) only: what openSource and a citation will open. */
export function isWebLink(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:'
  } catch {
    return false
  }
}

/** The longest host shown as is next to a link; a longer one keeps its end (see shownHost). */
export const HOST_MAX = 32
/** The same, for a narrow spot (the Help panel's Watch tile). */
export const HOST_MAX_NARROW = 20

/**
 * A host as shown next to a link: never clamped, so never longer than max + 1. A long host keeps its END behind a
 * leading "…", because the end is the part that decides where the click lands: `docs.python.org.aaaa…aaaa.evil.example`
 * shows as "…evil.example"-ish, never as its harmless-looking start. Whole labels when at least three fit (enough for
 * "example.co.uk"), else the last max characters (a cut label is still the real end).
 */
export function shownHost(host: string, max = HOST_MAX): string {
  if (host.length <= max) return host
  const labels = host.split('.')
  let tail = labels[labels.length - 1]
  let n = 1
  for (let i = labels.length - 2; i >= 0 && tail.length + 1 + labels[i].length <= max; i--, n++) tail = `${labels[i]}.${tail}`
  return `…${n >= 3 ? tail : host.slice(-max)}`
}

/**
 * Where a link goes, to show next to it (citations, sources): "python.org" for https://www.python.org/x. The label
 * comes from the engine or a page; the host can't lie about where the click lands. A long host is shortened from the
 * start, to at most max characters (shownHost). undefined = not a web link.
 */
export function linkHost(url: string | undefined, max = HOST_MAX): string | undefined {
  if (!url || !isWebLink(url)) return undefined
  try {
    const host = new URL(url).hostname.replace(/^www\./, '')
    return host ? shownHost(host, max) : undefined
  } catch {
    return undefined
  }
}
