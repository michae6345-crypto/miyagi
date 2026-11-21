/**
 * Build-time feature flags, shared by main and the renderer.
 *
 * VOICE_ENABLED (Michael, Nov 20): voice is off for now (the computer's own voice read as obnoxious; ElevenLabs may
 * come later). While false: no Voice button or keycap anywhere (lesson panel, shortcut bar, settings, spotlight), the
 * voice shortcut is never registered, nothing is ever spoken, and the app never grants the microphone. The voice code
 * stays in place: flip this to true to bring it all back.
 */
export const VOICE_ENABLED = false
