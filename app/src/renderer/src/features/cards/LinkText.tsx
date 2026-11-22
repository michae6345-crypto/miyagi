import type { ReactNode } from 'react'
import { color } from '../../core/theme'
import { linkHost } from '../drawer/links'

/**
 * A label that opens its URL outside the overlay (window.open; Electron's main hands plain https to the browser).
 * The destination host shows under it (wrap) or after it (one line), as its own element outside the clamped label and
 * never clamped itself (app-harden): the label is the engine's or a page's words and may run past two lines, the host
 * is where the click lands and must stay in view.
 */
export function LinkText({ label, url, wrap }: { label: string; url?: string; wrap?: boolean }): ReactNode {
  const fit = wrap ? 'line-clamp-2 break-words' : 'min-w-0 truncate'
  const host = linkHost(url)
  if (!url || !host) return <span className={fit}>{label}</span>
  return (
    <a
      href={url}
      data-link
      title={url}
      className={`group flex min-w-0 cursor-pointer ${wrap ? 'flex-col' : 'items-baseline'}`}
      style={{ color: 'inherit' }}
      onClick={(e) => {
        e.preventDefault()
        window.open(url, '_blank', 'noopener,noreferrer')
      }}
    >
      <span data-link-label className={`${fit} underline-offset-2 group-hover:underline`}>
        {label}
      </span>
      <span data-link-host className={wrap ? 'break-all' : 'shrink-0 whitespace-nowrap'} style={{ color: color.faint }}>
        {wrap ? host : ` · ${host}`}
      </span>
    </a>
  )
}
