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

/**
 * Where a link goes, to show next to it (citations, sources): "python.org" for https://www.python.org/x. The label
 * comes from the engine or a page; the host can't lie about where the click lands. undefined = not a web link.
 */
export function linkHost(url: string | undefined): string | undefined {
  if (!url || !isWebLink(url)) return undefined
  try {
    return new URL(url).hostname.replace(/^www\./, '') || undefined
  } catch {
    return undefined
  }
}
