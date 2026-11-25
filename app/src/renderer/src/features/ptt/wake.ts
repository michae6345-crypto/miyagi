/**
 * Feature: ptt. Drop a leading wake word from the spoken words: "Hey miyagi, what is this?" asks "What is this?".
 * Pure, so it is tested offline (test/pttStream.test.ts).
 *
 * Push to talk needs no wake word (the keys are the wake), but people say one anyway. Only the very start is touched:
 * an optional greeting (hey, hi, hello, ok, okay, yo), an optional "mr", then miyagi (or a near spelling the recognizer
 * gives), then any comma, period, colon, dash or "!". "miyagi's" (a possessive) is part of the question and stays.
 * When something was dropped, the first letter left is made upper case. Saying only the wake word leaves "".
 */
const WAKE = /^\s*(?:(?:hey|hi|hello|ok|okay|yo)[\s,.!-]+)?(?:mr\.?\s+|mister\s+)?(?:miyagi|myagi|mi[\s-]yagi|me[\s-]yagi|miyagui)(?![\w'’])[\s,.:;!?-]*/i

export function stripWake(text: string): string {
  const m = WAKE.exec(text)
  if (!m) return text.trim()
  const rest = text.slice(m[0].length).trim()
  return rest ? rest.charAt(0).toUpperCase() + rest.slice(1) : ''
}
