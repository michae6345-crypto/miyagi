# buddy

**Status:** pass 1 done (the living bonsai mark). Pass 2 (Nov 22): the buddy is a character of its own. It comes out of the island, flies to what the coach points at, circles it, says what it is, takes the learner through several things one at a time, listens while they talk, thinks, and answers beside the part the answer is about. It uses Michael's mark rules and stands down for his `features/annotate`. Michael asked on Nov 22 (8:29 PM) to hold pass 2 until he and Adrian picked one; Adrian picked on Nov 23 (the character draws) and had it pushed that evening (PR #253, still a draft into `adrian/shell`). Typecheck green, 105 offline tests, checked in the built stage. Not run in Electron. It is the sprout (Adrian, Nov 23), and the learner picks its color when they set miyagi up, like Clicky's cursor (Adrian, Nov 23: "that is my favorite"); it comes in sand. The picker is wired in (Adrian, Nov 23: "go ahead and wire it"): setup shows "Pick your buddy's color" once, before You're ready, and Settings > General has a Buddy color row. Seven colors. The choice is kept in localStorage until Prefs has a field (Core requests 7). The character is the one that draws (Adrian, Nov 23); in a build that also has `features/annotate` it takes a 15-line change on Michael's side, written, checked and emailed to him on Nov 23; not applied on his branch yet. **Open:** its name (five candidates rendered, `name.ts`) · **Priority:** P2 · **Branch:** `adrian/buddy` · **Stage port:** 5251 (launch config `buddy-stage`)

## Goal
Adrian, Nov 22 (night): "It should definitely be a character, and it shouldn't just be the bonsai tree. The bonsai tree is a logo. We want a separate, personalized character that does this stuff for you, with a lot of back and forth. It should be really cute. It should actually guide you around: point, highlight, show. Any part you're confused about, you talk to it."

So there are two things in this feature:
- **The living bonsai** (pass 1): the logo in the notch, alive. It stays the logo and stays in the notch.
- **The buddy** (pass 2): its own character. It lives in the island beside the logo and comes out when there is something to show or when the learner talks to it.

This replaces the earlier direction ("the bonsai itself is the buddy, no face", Michael, Nov 22 morning). Michael has not seen the character yet.

## Owns
- `app/src/renderer/src/features/buddy/**`
  - The living mark: `LivingMark.tsx`, `buddy.css` (its part), `store.tsx` (`useBuddy()`, `<Buddy />`).
  - The character: `Character.tsx` (three candidates: `sprout`, `leaf`, `dot`; moods calm, happy, curious, thinking, listening, sleepy; `look`, `talking`, `flying`, `point`, `tint`, `grown`), `palette.ts` (its colors), `buddy.css` (blink, float, leaf flap, the bubble's dots and bars).
  - What it does: `Companion.tsx` (overlay layer `buddy`, z 55: the trips, the bubble, the chips), `trip.ts` (pure: flights, the perch, following the pointer, speech timing), `talk.ts` (the back and forth: summoned, listening, thinking, what it says, the replies), `wire.ts` (talk.ts wired to the engine's status, the Explain action and push to talk).
  - The loops: `Reach.tsx` (overlay layer `buddy-reach`, z 30), `marks.ts` (pure: the mark rules and the stroke's shape), `pointing.ts` (what is shown, where the buddy is, `annotate`, `fade`, `reached`, `forget`, `pointAt`).
  - Previews, browser stage only: `Stage.tsx` (`?buddy`), `PointStage.tsx` (`?buddy=point`), `CastStage.tsx` (`?buddy=cast`).
- `app/mock/scenarios/buddy.json`: `annotate` events through the mock engine.
- `app/test/buddyMarks.test.ts` (69 tests: mark rules, stroke geometry, the pointing store, trips, perch, follow, speech) and `app/test/buddyTalk.test.ts` (11 tests: the back and forth).

## The living mark (pass 1, Michael wires the notch)
```tsx
import { Buddy, usePointerLean } from '../features/buddy'
const ref = useRef<HTMLSpanElement>(null)
const lean = usePointerLean(ref, hovered)          // hovered: the notch hover state
<span ref={ref}><Buddy size={16} lean={lean} /></span>   // in place of <MiyagiMark size={16} /> (core/Island.tsx:648)
```
`LivingMark` props: `size`, `state: idle | thinking`, `lean` from -1 to 1, `bloom` counter, `tone`, `level`. Thinking sways ±2.4° about the trunk base. Lean is up to 6°. Bloom swells each pad on a real `step.passed` (a Skip is never a pass). Transform only; reduced motion turns it off. In the click-through overlay the lean needs mouse moves forwarded (`setIgnoreMouseEvents(true, { forward: true })`).

## The buddy (pass 2)
It draws the engine's `annotate` event (Michael's contract, Nov 22, branch `claude/contract-circle-ask`): `{ marks: Annotation[]; holdMs? } | { clear: true }`, marks in screen points like `spotlight.rect`.

### The character
Three candidates, all drawn here as SVG, none of them the bonsai, none taken from another product:
- **sprout** (the default): a round creature with a two-leaf sprout on its head. The leaves are its ears and its wings: they perk up when it listens, droop when it is sleepy, and flap when it flies.
- **leaf**: a leaf with a face. Its tip is its pointer.
- **dot**: a droplet of the island. Black, a rim in the buddy's color, eyes only.

Same face, moods and motion on each. `?buddy=cast` shows all three in every pose, at the size it is on the screen (54 px) over a dark and a light app. `?char=leaf` or `?char=dot` on the try-out shows another one in motion. The sheet also shows the seven colors a learner can pick, and a proposal that nothing stores yet: it grows as they learn (one leaf on day one, two after a few lessons, a bud once skills are mastered).

It has no name yet. Candidates: "bud" (short for buddy, and what a tree starts as), "pip" (a seed), "sprout".

### What it does
1. **It shows things.** When the coach points at something it pops out of the island, flies there on an arc (0.46 to 1.05 s by distance, leaning into the flight, leaves back), lands beside it with a small squash, throws a loop in its own color round it, points at it with a little arm, and says what it is in an island-black bubble, one letter at a time (30 ms each).
2. **It takes the learner through several things.** An annotate with two or three marks is a tour: one loop at a time, "2 of 3" and a Next button in the bubble, small numbers where the others wait, Done on the last.
3. **It listens.** While the learner holds push to talk it flies to their pointer, perks up and shows what it hears. It keeps the pointer company (30 px down and right, catching up a little each frame).
4. **It thinks, then answers where the answer is.** From the moment the keys are let go it shows three dots. When the answer card comes it says the card's first sentence (96 characters at most), beside the mark the answer points at if there is one.
5. **The learner answers back** from the bubble without talking: Explain (the step's Explain action, with the mark's label) or Got it.
6. **It is alive.** It blinks, floats, looks where it is going and at what it points at, turns to the learner's pointer when it comes within 150 px, and hops and beams when they get there or say Got it.
7. **It goes home.** With nothing left to show it lingers by the pointer for 7 s if the learner called it, then shrinks back into the island. Esc sends it home at once.

A new annotate while it is out: it flies straight from where it is to the new first mark, then draws.

Borrowed mechanics, in miyagi's own look and with its own character: a companion with a home that travels to the thing, the arc that grows with distance, landing beside the target and not on it, words typed out next to it, staying by the pointer while you talk (Clicky); a loop drawn on whose end overlaps its start (circle to search).

### Look
**The learner picks its color.** Adrian picked mint, then the deeper one, from the renders on Nov 22; on Nov 23, seeing it on the character, he did not like the mint, picked sand, asked for cream versions, then said his favorite is to let the learner choose, like Clicky, when they set it up, and then: "not too many and not too similar... maybe 6-8 colors. go ahead and wire it". So:
- **A color is a skin** (`palette.ts` `SKINS`): body, leaves, cheeks, the stroke it draws, the listening bars in the bubble.
- **Seven to pick from** (`PICKS`): sand, butter, peach, pink, lilac, sky, mint. One per hue, sand as the neutral it comes in. Cream is out (too close to sand: 14 apart in CIE Lab) and so is clay (the one dark color). `test/buddySkin.test.ts` holds the set to 6 to 8 colors with no two closer than `PICK_APART` (18; the closest pair kept is lilac and sky at 20). Six are kit colors; butter is not, and sky is the kit's "no blue elsewhere"; as the learner's own choice that is Adrian's call.
- **`skin.ts`** holds the one in use: `useSkin`, `pickSkin`, `confirmSkin`, `isSkinChosen`. In the app it is kept in localStorage `miyagi.buddy.skin` (only a name from `PICKS` is taken) and reaches every window through the `storage` event, the way `features/sound` kept its setting before Prefs had a field. In the browser stage a pick stays in memory, so stage loads always start in sand.
- **`ColorPicker.tsx`**: `BuddyPreview` (the buddy; it watches the pointer and beams and hops at a pick) and `BuddySwatches` (a radio group; arrow keys move the pick; the picked one's name under it).
- **Setup**: `features/onboarding/BuddyStep.tsx`, shown by `Ready.tsx` once, before You're ready, in the setup window and in the one-window first run (both mount `Ready`). A pick does not close it; Continue does (`confirmSkin`: keeping sand counts as chosen). Not shown when setup is opened again, or once a color is chosen. `?skin=<name>` in the stage counts as chosen, so stage shots of You're ready can skip it.
- **Settings**: `SettingsRows.tsx` `BuddyColor`, one row in General after push to talk, mounted the way `features/ptt` mounts its own rows.
- Pale loops (sand) sit on a firmer ink keyline or they are lost over a light app. `?skin=<name>` puts the buddy in any skin, also the ones not offered (`?buddy=colors`, `?buddy=colors&set=cream`). `?buddy=pick` is the first mock of the step, kept because its Continue shows the buddy pointing in the picked color.

A loop fits its target: one line of code gets a loop that stays in that line, a block of code or a panel gets a squarer loop that stays within 21 px of it, a mark by a screen edge is pulled in to stay on screen.

Reduced motion: no flights and nothing drawn on. It fades in where it would have landed with its words whole and the loop there, and fades out. No blink or float.

### The mark rules (the same as `features/annotate`, number for number)
Michael's engine is written against his `features/annotate/marks.ts` and `store.ts`. `marks.ts` and `pointing.ts` here follow them exactly, so a mark lives and dies the same way whichever layer draws it. Change them together.
- 3 marks at most. A mark needs `why` "point" or "answer" and a real box. Labels are cut to 4 words.
- A mark is known by its id, or (no id) by its kind and nearly the same box (12 px). A known mark re-sent keeps its stroke, and its place when it only jittered.
- A new annotate replaces the drawn set. The hold is `holdMs` kept between 1.5 and 30 s, or 6 s, counted from the newest mark's birth: a re-send does not restart it, a new mark does.
- A mark that faded stays gone for the rest of the step, however it went (reached, timed out, Esc, `{ clear: true }`), even if it is re-sent. A new `askId` starts fresh.
- "Went there": the pointer coming into the mark's box (6 px bigger) from outside and resting 280 ms fades that mark, and only that one. So does a press inside it. A pointer already resting there when the mark appears does not.
- `step.started` (not a `replay`) keeps only the marks sent with that `stepId` and forgets what was gone. `step.passed`, `lesson.ready`, `lesson.ended` and a reset clear everything.
- Draw a mark only when at least half of its box is on this display.
- Not here: his bridge that also circles today's spotlight boxes until the engine sends its first annotate.

One thing the buddy adds on top: Got it and Next fade a mark the way reaching it does.

## With features/annotate (Michael's layer)
Michael claimed "buddy draws" by email at 7:06 PM on Nov 22 and pushed `features/annotate`: a mint stroke from the island's middle to a loop with a name chip, also on `annotate`. At 8:29 PM he asked to hold this pass until the two of them pick one. **On Nov 23 Adrian picked: the character draws.** So:
- **One rule decides who draws** (`marks.ts` `standsDown`, read by `Reach.tsx` `useStandDown`): the character draws, unless the build also has a `features/annotate` that still draws. That feature yields by registering with `yieldsToBuddy: true` and drawing nothing while this feature's `buddy` layer is in the build.
  - only this feature: the character draws.
  - both, his as it is today (77874bec): his draws, this one draws nothing (no character, no bubble, no loop). Nothing is circled twice, and nothing changes for him until he takes the change.
  - both, his yielding: the character draws, his draws nothing.
- **The change on his side is 15 lines in two of his files** (`features/annotate/index.tsx` and `BuddyLayer.tsx`). It is written and checked but it is his to apply: `annotate-yields-to-buddy.patch` in Adrian's `SanD Hacks/research/buddy-compare/` (applies cleanly to 77874bec). His store keeps running under it; only the drawing stops.
- **Today's pointing is covered here too.** His store also marks every new spotlight box until the engine sends its first `annotate`. With his layer yielding that would be lost, so `pointing.ts` `spotlit` (fed by `wire.ts` from the spotlight store, read-only) does the same with his rules: the buddy goes to a spotlight box until the engine speaks `annotate`; the mark leaves with the spotlight and may come back; a Show me press marks it again. The spotlight rings that box itself and puts its caption to the right, so there the buddy draws no second ring and sits on the left (or below when there is no room).
- **Same rules** (above), so the engine sees one behavior whichever draws.
- **What he asked the buddy to expose:** `useBonsaiPoint(ref, layout, on)` (where the living mark is, for a stroke to start from) and `pointAt(box?)` (the tree leans toward a box).
- The third way that was tried on Nov 22, his stroke with this character (the stage's `?together`), is gone with the pick.

Checked merged with `origin/michael/v2-integration` at 77874bec on throwaway branches that were not pushed (Nov 23): no conflicts; typecheck passes. With his layer as it is: he draws each mark (and each spotlight box) and this feature draws nothing. With the patch applied: his layer draws nothing; the buddy goes to a spotlight box, circles one mark and says its label with Explain and Got it, and takes a tour one loop at a time; a color picked in Settings is the color of the buddy and its loop; the full suite is 851 tests with the one known failure (`linkHost.test.ts`, a drawer test, untouched here).

## How to see it
Stage port 5251 (`npm run dev:web -- --port 5251`), or build it: `npx vite build --config vite.web.config.ts --base ./ --outDir <a folder outside the worktree>`.
- `?buddy=point&clean`: the try-out. One, Tour, Far, Clear, Home; Spotlight (today's pointing: press it on a fresh load, before the others); Hold to talk (hold the button: it hears a canned question, then answers); or click anywhere to point there. The answers are canned in `PointStage.tsx`; the marks go through the bus as real `annotate` events.
- `?buddy=cast&clean`: the character sheet.
- `?onb=ready` (the setup window) and `?flow=1&step=ready` (the one-window first run): the real color step, then You're ready. `?flow=1&step=engine` walks into it from the last setup step. `?settings=general`: the Buddy color row. Add `&appearance=dark` for the dark window. `shots/buddy-setup.png`.
- `?buddy=pick&clean`: the first mock of the step. Click swatches, then Continue: the buddy comes out in that color and points at a line.
- `?buddy=colors&clean`: the color sheet (`&set=cream` for the cream versions beside sand). `&skin=cream` (or any other name on it) on the try-out shows the buddy and its loop in that color.
- `?scenario=buddy&clean`: marks arriving from the mock engine.
- Add `&char=leaf` or `&char=dot` for another character, `&notch=below` for the pill under the menu bar.
- `?buddy`: every state of the living mark (pass 1).
- `shots/buddy-cast.png` (the sheet), `shots/buddy-colors.png` (the first round of colors), `shots/buddy-setup.png` (the color step and the Settings row), `shots/buddy-moments.png` (close-ups of each moment), `shots/buddy-stage.png` (pass 1). Moving previews are outside the repo, in Adrian's `SanD Hacks/research/buddy-compare/`: `buddy-char-ask.gif`, `buddy-char-tour.gif`, `buddy-char-hop.gif`, `buddy-char-far.gif`.

## Checked
- `npm run typecheck` passes. `test/buddyMarks.test.ts` 69 of 69, `test/buddyTalk.test.ts` 11 of 11, `test/buddySkin.test.ts` 12 of 12 (the set of colors, and keeping the pick: saved, read back on the next launch, followed from another window, bad values refused, nothing written in the stage), `test/buddyDraws.test.ts` 13 of 13 (who draws, and the spotlight's boxes). The full suite is 703 tests with one failure, `linkHost.test.ts` (reads only drawer files; untouched here).
- The color, in the built stage (Nov 23): the step shows in the setup window and in the one-window first run, light and dark; a pick changes the buddy at once; Continue goes on to You're ready and Skip goes home; `?flow=1&step=done` still hands off by itself; the Settings row changes the color, and the buddy that then flies out and its loop are in it.
- Merged with `origin/michael/v2-integration` at 77874bec on a throwaway branch (Nov 23, deleted, not pushed): no conflicts (his reworked Settings keeps the row); typecheck passes; 838 tests with the same one failure; the step and the row work there too. With his layer as it is the buddy stands down there, so the color shows only in the picker; with his layer yielding (above) the buddy and its loop are in the picked color.
- Built stage in headless Chrome (1600x1000), by DOM state and recorded frames:
  - One mark: it lands, one loop draws, it says the label, Explain and Got it show and the bubble takes the mouse. Explain: it thinks, then says the explanation. Got it: it beams, the loop comes off.
  - A tour of three: one loop at a time, the numbers count down (2 and 3, then 3, then none), Next, Next, Done.
  - Hold to talk: it comes to the pointer and follows it, shows what it hears, thinks on release, flies to the answer and says the sentence with the chips. Esc sends it home.
  - A far corner, three places one after another, and a light backdrop.
  - Reduced motion (emulated): at its perch with whole words from the first frame, no blink.
- Not checked: Electron on a Mac. The buddy over real apps, the pointer rules with forwarded mouse moves, the island on a real notch, a second display, a live engine sending `annotate`, real push to talk (the wiring to `features/ptt` is written against its store and has only run with the stage's stand-in).

## Open (Adrian, then Adrian and Michael)
- Its name. Adrian, Nov 23: "we shouldn't say buddy, we need a name that will match the miyagi theme". Every word the learner reads about it now comes from `features/buddy/name.ts` (`NAME`, `words`); it has no name yet, so the copy still says buddy. Five candidates from the bonsai (not the film: the founders dropped the Karate Kid cues, launch-risk D3): bon, futaba, wakaba, moyo, hachi. `?name=<name>` in the stage shows setup's step and the Settings row with one. Code keeps saying buddy (the folder, the feature id, the layer id Michael's layer looks for). (The character is picked: the sprout. The leaf and the dot are still in the code behind `?char=` and can go.)
- Which of the seven colors, and which one it comes in (sand today). The cream versions he asked for are still there to look at (`?buddy=colors&set=cream`, `shots/buddy-cream.png`).
- Michael applying the change for his layer (emailed to him Nov 23 with the pick; no answer yet).
- Whether the growing is wanted. (The learner's color is: see above.)
- When the buddy says an answer the answer card also shows in the island. One of them should step back.

## Core requests
1. **The contract.** `annotate` and `Annotation` are on `claude/contract-circle-ask`, not on this branch. Until they land, `marks.ts` mirrors the type and `pointing.ts` casts `onMessage` to subscribe. Both go when the contract is merged.
2. **`common/wire.ts` KNOWN needs `'annotate'`**, or the app's parser drops the event in Electron (the browser stage's mock does not go through the parser). Michael has this line in b3ffd388 on `michael/app-buddy-draw`.
3. **One token for the buddy's color.** It is sand now (`brand.pastel.sand`, already in `core/theme.ts`). Michael's `features/annotate` stroke is still mint: whichever layer draws in the end, the stroke and the character should read the same token, so his needs to move to sand too, or the two will not look like one thing.
4. **A real click.** The overlay is click-through, so in Electron a click inside a mark never reaches this window. Main could broadcast a global left-mouse-down point (screen points); today the pointer resting on the mark stands in for it. Michael asks for the same thing in `agents/app-buddy-draw.md`.
5. **Longer holds for tours and answers.** The hold is counted from the newest mark's birth, so a three-mark tour sent with the default 6 s is gone before the learner reads the second one. The engine should send `holdMs` near the 30 s limit with a tour or an answer, or the rule should let an open bubble keep its mark. (The try-out sends 30 s for a tour and 12 s for an answer.)
6. **A BRAND.md section for the character.** BRAND.md does not mention a character. On Michael's integration branch it gains one exception to "no hand-drawn annotations": the buddy stroke (mint, `features/annotate`). A character with a face and pink cheeks is a brand decision; it is Adrian's to write down once he has picked one, and the stroke exception should then name whichever layer draws.
7. **A Prefs field for the learner's buddy color** (`buddyColor`, one of the names in `palette.ts` `PICKS`). The setup step and the Settings row are wired (in `features/onboarding` and `features/settings`, on Adrian's go-ahead: one new file, a wrapper in `Ready.tsx`, two lines in `General.tsx`), and the choice is kept in localStorage until Prefs has the field. If `features/annotate` keeps drawing, its stroke should read the same color (`useSkin().stroke`), or the loop and the buddy will not match. How far it has grown would need the skills count; nothing stores it.
8. **Typed questions.** The buddy comes for push to talk. A question typed in the launcher gets its answer card only; a bus event when the learner asks from anywhere would let the buddy come for those too.
