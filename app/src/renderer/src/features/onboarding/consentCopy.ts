/**
 * Feature: onboarding. The consent screen's copy (launch register R05 and R06), pure: no React, no reads, no sends, so
 * test/consent.test.ts checks it with node --test. Consent.tsx draws it; the store's agree() records it in main.
 *
 * What it must say, in miyagi's voice (calm, short, lowercase "miyagi", no em dash, 12 words a line at most):
 *   - during a lesson, your screen (as screenshots) and your code go to Anthropic (Claude), to build lessons and check
 *     your work. Anthropic only: D1 (Adrian, Nov 21), Claude only at launch, no Gemini (common/flags.ts
 *     GEMINI_ENABLED); with the flag on, the Google (Gemini) line for video lessons comes back;
 *   - close private apps and tabs first;
 *   - miyagi is AI and can be wrong.
 * Then the "I agree" checkbox with the terms and the privacy policy linked (common/consent.ts LEGAL_URL), and ONE
 * primary, Continue, which stays disabled until the box is ticked.
 * Push to talk (#226) and the coach's web search (#227) are off for launch: never describe either here.
 */
import { GEMINI_ENABLED } from '../../../../common/flags'

export type ConsentRowId = 'screen' | 'videos' | 'private' | 'ai'
/** One line and one line of detail under it. */
export type ConsentRow = { id: ConsentRowId; line: string; detail: string }

export const CONSENT_TITLE = 'A few things first'

const SCREEN: ConsentRow = { id: 'screen', line: 'Your screen and your code go to Anthropic (Claude).', detail: 'Screenshots during a lesson, to build lessons and check your work.' }
/** Only while Gemini is on (not at launch: D1). */
const VIDEOS: ConsentRow = { id: 'videos', line: 'Video lessons go to Google (Gemini).', detail: 'The video link and your goal, to turn it into steps.' }
const PRIVATE: ConsentRow = { id: 'private', line: 'Close private apps and tabs first.', detail: 'Anything on your screen can end up in a screenshot.' }
const AI: ConsentRow = { id: 'ai', line: 'miyagi is AI and can be wrong.', detail: 'Check its answers before you rely on them.' }

export const CONSENT_ROWS: readonly ConsentRow[] = GEMINI_ENABLED ? [SCREEN, VIDEOS, PRIVATE, AI] : [SCREEN, PRIVATE, AI]

/** The "I agree" checkbox's label, in parts so the two links sit inside it. Read as one sentence: AGREE_LINE.
 *  Michael, Nov 26: an explicit checkbox the learner ticks, not "By continuing you agree". Continue stays disabled
 *  until it is ticked. */
export const AGREE = { lead: 'I agree to the ', terms: 'terms', and: ' and ', privacy: 'privacy policy', end: '.' } as const
export const AGREE_LINE = `${AGREE.lead}${AGREE.terms}${AGREE.and}${AGREE.privacy}${AGREE.end}`
/** The one primary. Disabled until the checkbox is ticked. */
export const CONTINUE = 'Continue'
/** Shown if Continue (or Enter) is pressed before the box is ticked. */
export const AGREE_NEEDED = 'Tick the box to agree before you continue.'
/** If main didn't record it (an IPC failure): say so plainly, and the learner can press Continue again. */
export const AGREE_FAILED = "Couldn't save that. Try again."
