/**
 * Feature: settings. The computer in Settings copy: "this Mac" on macOS, "this computer" on Windows (the same words as
 * onboarding/device.ts). privacy/facts.ts keeps the Mac wording because web/privacy.md quotes it and facts.test.ts
 * checks it; the rows pass their text through here() so Windows reads its own words. Keys are encrypted by the
 * Keychain on a Mac and by Windows' own protected storage (DPAPI, through Electron safeStorage) on a PC.
 */
import { bridge } from '../../bridge'

export const isMac = (): boolean => bridge.platform.os === 'mac'

/** Mac wording in, this computer's wording out. A Mac gets the text unchanged. */
export function here(text: string): string {
  if (isMac()) return text
  return text
    .replace(/Locked by your Keychain/g, 'Encrypted by Windows')
    .replace(/your Mac’s Keychain/g, 'Windows’ protected storage')
    .replace(/\bthis Mac\b/g, 'this computer')
    .replace(/\bThis Mac\b/g, 'This computer')
}

/** The note under Your own key. */
export const keysNote = (): string => (isMac() ? 'Kept in your Mac’s Keychain, never on our servers.' : 'Encrypted on this computer, never on our servers.')

/** The flash after a Save that reached secure storage. */
export const savedSecure = (): string => (isMac() ? 'Saved to Keychain' : 'Saved and encrypted')
