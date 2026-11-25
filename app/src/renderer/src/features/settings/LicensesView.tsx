/**
 * Feature: settings. About > Open-source licenses (app-font-licenses lane, Nov 24): the fonts miyagi carries, their
 * copyright and license, a way to each project's page, and the OFL 1.1 in full in a quiet scrolling block. It opens in
 * place of About's rows, with "‹ About" to go back; leaving the panel closes it (licenses.ts useLicenses).
 *
 * The text comes from the font's own license file, bundled with ?raw: the same file electron-builder copies to
 * Resources/licenses/fonts, so the view and the shipped file can't drift.
 */
import { ArrowUpRight, ChevronLeft } from 'lucide-react'
import { useContext, useEffect, useRef, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { color, fill, radius2, type2 } from '../../core/theme'
import { QuietButton } from '../../core/ui/atoms'
import bricolageOfl from '../../assets/fonts/BricolageGrotesque-OFL.txt?raw'
import { closeLicenses, FONT_LICENSES, LICENSE_WORDS, licenseText, useLicenses } from './licenses'
import { PanelRows } from './rows'
import { Flat, Group, Note, Row } from './ui'

const TEXT = licenseText(bricolageOfl)

/** A font's project page in the default browser, through main's one way out (open:external → main/safeOpen.ts). */
const openPage = (href: string): void => void bridge.invoke('open:external', href).catch(() => undefined)

/** "‹ About": the way back to About's rows. */
export function LicensesBack(): ReactNode {
  return (
    <button
      type="button"
      data-licenses-back
      className="mg-press flex w-fit cursor-pointer items-center gap-[4px] whitespace-nowrap"
      style={{ fontSize: type2.sm, color: color.label, background: 'none', border: 0, padding: 0, minHeight: 24, marginBottom: 6 }}
      onClick={closeLicenses}
    >
      <ChevronLeft size={14} strokeWidth={1.8} aria-hidden />
      {LICENSE_WORDS.back}
    </button>
  )
}

/** In the v4 page the big header carries the title and the way back (Content.tsx BigHeader); the sheet draws its own. */
export function Licenses(): ReactNode {
  const flat = useContext(Flat)
  const h = useRef<HTMLHeadingElement>(null)
  useEffect(() => h.current?.focus({ preventScroll: true }), [])
  return (
    <div data-licenses className="flex flex-col gap-[24px]">
      {!flat && (
        <div className="flex flex-col">
          <LicensesBack />
          <h2 ref={h} tabIndex={-1} className="m-0 font-semibold outline-none" style={{ fontSize: 20, color: color.text }}>
            {LICENSE_WORDS.title}
          </h2>
        </div>
      )}
      <Group label={LICENSE_WORDS.fonts}>
        {FONT_LICENSES.map((f) => (
          <div key={f.name} data-license={f.name}>
            <Row
              label={f.name}
              caption={`${f.copyright}. ${f.license}.`}
              right={<QuietButton label={LICENSE_WORDS.open} icon={ArrowUpRight} title={f.href.replace(/^https:\/\//, '')} onClick={() => openPage(f.href)} />}
            />
          </div>
        ))}
      </Group>
      <Note>{LICENSE_WORDS.others}</Note>
      <Group label={LICENSE_WORDS.text}>
        <pre
          data-license-text
          tabIndex={0}
          aria-label={`${LICENSE_WORDS.text}, SIL Open Font License 1.1`}
          className="m-0 overflow-auto outline-none"
          style={{
            maxHeight: 320,
            margin: '12px 0',
            padding: '14px 16px',
            borderRadius: radius2.card,
            background: fill.segmentTrack,
            boxShadow: `inset 0 0 0 1px ${fill.hairline}`,
            color: color.label,
            fontFamily: 'inherit',
            fontSize: type2.xs,
            lineHeight: 1.55,
            whiteSpace: 'pre-wrap',
            overflowWrap: 'anywhere'
          }}
        >
          {TEXT}
        </pre>
      </Group>
    </div>
  )
}

/** The About panel: its rows, or the licenses in their place while open. */
export function About(): ReactNode {
  const open = useLicenses((s) => s.open)
  useEffect(() => closeLicenses, [])
  return open ? <Licenses /> : <PanelRows panel="about" />
}
