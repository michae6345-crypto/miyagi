/**
 * Feature: drawer (v2). Any link (ANY-LINK.md): a lesson built from a web page or a GitHub repo has no video, so the
 * panel's source is the page itself. Under "Need help": "From docs.python.org" and one row that opens the part of
 * the page this step comes from (StepSummary.pageRef: "Open “Creating Virtual Environments”"), else the page.
 *
 * Only lesson.ready's `origin` with kind web / github shows it. A step's pageRef is used only when it is a plain
 * http(s) link on the same host as the origin; otherwise the row opens the origin. It opens
 * through openSource (window.open: main hands plain https to the browser).
 */
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { SourceLink } from '../../anylink/Card'
import { pageSource, safeWebUrl } from '../../anylink/link'
import { openSource } from '../store'
import { Caption, Divider } from './ui'

const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, '')
  } catch {
    return ''
  }
}

export function PageSource(): ReactNode {
  // Select the raw origin (a stable reference) and check it here: a fresh object from a selector would re-render forever.
  const raw = useLesson((s) => s.lesson?.origin)
  const origin = pageSource(raw)
  const ref = useLesson((s) => s.steps.find((st) => st.id === s.stepId)?.pageRef)
  if (!origin) return null
  const refUrl = ref ? safeWebUrl(ref.url) : undefined
  const part = refUrl && hostOf(refUrl) === hostOf(origin.url) ? { url: refUrl, heading: ref?.heading } : undefined
  return (
    <>
      <Divider />
      <div data-part="panel-source" data-source-kind={origin.kind} className="flex flex-col gap-[10px]" style={{ padding: '16px 20px' }}>
        <Caption>{`From ${origin.site ?? hostOf(origin.url)}`}</Caption>
        <SourceLink compact kind={origin.kind} url={part?.url ?? origin.url} heading={part?.heading} site={origin.site} author={origin.author} onOpen={openSource} />
      </div>
    </>
  )
}
