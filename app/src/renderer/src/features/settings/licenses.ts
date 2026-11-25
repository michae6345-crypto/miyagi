/**
 * Feature: settings. Settings > About > Open-source licenses (app-font-licenses lane, Nov 24): what the view lists, and
 * whether it is open. Plain data, so test/fontLicenses.test.ts can hold it to the files the app ships.
 *
 * Both bundled fonts are SIL OFL 1.1 and load from the app itself, never from Google's servers. Their license texts
 * also ship in the packaged app (Contents/Resources/licenses/fonts, electron-builder.yml extraResources), with the npm
 * packages' notices beside them (licenses/THIRD-PARTY-NOTICES.txt).
 */
import { create } from 'zustand'

export type FontLicense = {
  name: string
  copyright: string
  license: string
  /** The font project's page; github.com is on main's open allowlist (main/safeOpen.ts ALLOWED_HOSTS). */
  href: string
  /** Where its license text sits in the repo, and where electron-builder puts it in the app (Resources/...). */
  source: string
  shipped: string
}

export const OFL = 'SIL Open Font License 1.1'

export const FONT_LICENSES: readonly FontLicense[] = [
  {
    name: 'Bricolage Grotesque',
    copyright: 'Copyright 2022 The Bricolage Grotesque Project Authors',
    license: OFL,
    href: 'https://github.com/ateliertriay/bricolage',
    source: 'src/renderer/src/assets/fonts/BricolageGrotesque-OFL.txt',
    shipped: 'licenses/fonts/BricolageGrotesque-OFL.txt'
  },
  {
    name: 'Google Sans Flex',
    copyright: 'Copyright 2025 The Google Sans Project Authors',
    license: OFL,
    href: 'https://github.com/googlefonts/google-sans-flex',
    source: 'brand/fonts/OFL.txt',
    shipped: 'licenses/fonts/GoogleSansFlex-OFL.txt'
  }
]

export const LICENSE_WORDS = {
  title: 'Open-source licenses',
  back: 'About',
  fonts: 'Fonts',
  others: 'Other open-source parts are listed in the app’s licenses folder.',
  text: 'License text',
  open: 'Source'
} as const

/** Whether the About panel shows the licenses in place of its rows. Leaving the panel closes it. */
export const useLicenses = create<{ open: boolean }>(() => ({ open: false }))
export const openLicenses = (): void => useLicenses.setState({ open: true })
export const closeLicenses = (): void => useLicenses.setState({ open: false })

/**
 * The text the view shows: each font's copyright line, then the OFL 1.1 itself, cut from a font's license file at its
 * "SIL OPEN FONT LICENSE" banner (the dashed rule above it included). Both fonts carry the same license word for word.
 */
export function licenseText(raw: string, fonts: readonly FontLicense[] = FONT_LICENSES): string {
  const lines = raw.replace(/\r\n/g, '\n').split('\n')
  let at = lines.findIndex((l) => /^SIL OPEN FONT LICENSE/.test(l))
  if (at < 0) return raw.trim()
  if (at > 0 && /^-{10,}\s*$/.test(lines[at - 1])) at -= 1
  const body = lines
    .slice(at)
    .map((l) => l.trimEnd())
    .join('\n')
    .trim()
  const head = fonts.map((f) => `${f.name}: ${f.copyright} (${f.href}).`).join('\n')
  return `${head}\n\nThis Font Software is licensed under the SIL Open Font License, Version 1.1.\n\n${body}\n`
}
