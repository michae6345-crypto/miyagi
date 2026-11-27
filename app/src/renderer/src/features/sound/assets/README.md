# Sound assets

## lesson-complete.wav

The chime miyagi plays once when a learner finishes a lesson (Linear MIC-90).

- **What it is:** two soft bell notes a fifth apart (D5, then A5 140 ms later), ringing out. 900 ms, peak -26 dBFS, 44.1 kHz, 16-bit mono PCM, 79,424 bytes.
- **Source:** made by us, in this repo. `make-chime.ts` renders it from the `chime` spec in `../synth.ts` with plain math (sines with exponential decay). No recording, sample, sound library or third-party audio was used, and no AI audio model.
- **License:** our own work, so no third-party license or attribution applies. miyagi holds every right to it. It goes in the app bundle like the rest of our code.
- **Remake it:** change `CUES.chime` in `../synth.ts`, then run this from `app/` and commit both files:

  ```
  npx tsx src/renderer/src/features/sound/assets/make-chime.ts
  ```

  `test/lessonChime.test.ts` fails if the committed file no longer matches what the script writes.
- **Loaded:** `../player.ts` imports it as a Vite asset (`?url`), served from the app's own files, never the network. If it can't be read, the same sound is rendered in code from the same spec.
