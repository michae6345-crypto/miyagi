# buddy

**Status:** pass 1 done (the living bonsai mark). Pass 2 (Nov 22): the buddy is a character of its own. It comes out of the island, flies to what the coach points at, circles it, says what it is, takes the learner through several things one at a time, listens while they talk, thinks, and answers beside the part the answer is about. It uses Michael's mark rules and stands down for his `features/annotate`. Everything after 95712e94 is committed locally and NOT pushed: Michael asked on Nov 22 (8:29 PM) to hold pass 2 until he and Adrian pick one. Typecheck green, 80 offline tests, checked in the built stage. Not run in Electron. It is the sprout (Adrian, Nov 23), and the learner picks its color when they set miyagi up, like Clicky's cursor (Adrian, Nov 23: "that is my favorite"); it comes in sand. The picker is built and mocked as a setup step; setup and Settings do not mount it yet (Core requests 7). **Open:** which layer draws in the end, its name · **Priority:** P2 · **Branch:** `adrian/buddy` · **Stage port:** 5251 (launch config `buddy-stage`)

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

Same face, moods and motion on each. `?buddy=cast` shows all three in every pose, at the size it is on the screen (54 px) over a dark and a light app. `?char=leaf` or `?char=dot` on the try-out shows another one in motion. The sheet also shows the nine colors a learner can pick, and a proposal that nothing stores yet: it grows as they learn (one leaf on day one, two after a few lessons, a bud once skills are mastered).

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
**The learner picks its color.** Adrian picked mint, then the deeper one, from the renders on Nov 22; on Nov 23, seeing it on the character, he did not like the mint, picked sand, asked for cream versions, and then said his favorite is to let the learner choose, like Clicky, when they set it up. So: a color is a skin (`palette.ts` `SKINS`: body, leaves, cheeks, the stroke it draws, the listening bars in the bubble), `skin.ts` holds the one in use (`useSkin`, `pickSkin`), and `ColorPicker.tsx` is the picker: the buddy, big, watching the pointer, over nine swatches (`PICKS`: sand, cream, butter, peach, clay, pink, lilac, sky, mint). A pick shows at once (it beams and hops) and everything it does from then on is in that color. It comes in sand until they pick. Seven of the nine are kit colors; butter is not, and sky is the kit's "no blue elsewhere"; as the learner's own choice that is Adrian's call and he made it by asking for all of them. Pale loops (sand, cream) sit on a firmer ink keyline or they are lost over a light app. `?buddy=pick` is a mock of the setup step; `?skin=<name>` puts the buddy in any skin, also the cream versions that are not offered (`?buddy=colors&set=cream`). In Electron the pick is kept in localStorage `miyagi.buddy.skin` and reaches the overlay through the `storage` event, the way `features/sound` did before Prefs had its field; in the browser stage a pick stays in memory.

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
Michael claimed "buddy draws" by email at 7:06 PM on Nov 22 and pushed `features/annotate`: a mint stroke from the island's middle to a loop with a name chip, also on `annotate`. At 8:29 PM he asked to hold this pass until the two of them pick one. So:
- **By default this feature draws nothing while `features/annotate` is mounted** (`STAND_DOWN_FOR` in `Reach.tsx`): no character, no bubble, no loop. The branches can merge in either order and a mark is never circled twice.
- **Same rules** (above), so the engine sees one behavior whichever draws.
- **What he asked the buddy to expose:** `useBonsaiPoint(ref, layout, on)` (where the living mark is, for a stroke to start from) and `pointAt(box?)` (the tree leans toward a box).
- **Three ways it can end.** (a) His layer alone: a stroke and a chip, no character. (b) This one draws: the character, its bubble and its loop; his layer stands down. (c) Both: his stroke circles, the character does everything else. The stage's `?together` shows (c) on a merged build, and as it is it is rough: his name chip sits where the buddy lands and says the same words, a tour shows all three strokes at once, and Got it cannot take his loop off. To be good, (c) needs his layer to hide its chip while the buddy is at that mark and to let a reply fade his mark.

Checked merged with `origin/michael/v2-integration` at 77874bec (Nov 22, 10 PM; it has `features/annotate` and circle to ask), on a throwaway branch that was not pushed: no conflicts; typecheck passes; the full suite is 826 tests with the one known failure (`linkHost.test.ts`, a drawer test, untouched here); in the built stage his layer draws each mark (three for a tour, one for an answer) and this feature draws nothing; with `?together` the character and its bubble also show and this feature's loops still do not.

## How to see it
Stage port 5251 (`npm run dev:web -- --port 5251`), or build it: `npx vite build --config vite.web.config.ts --base ./ --outDir <a folder outside the worktree>`.
- `?buddy=point&clean`: the try-out. One, Tour, Far, Clear, Home; Hold to talk (hold the button: it hears a canned question, then answers); or click anywhere to point there. The answers are canned in `PointStage.tsx`; the marks go through the bus as real `annotate` events.
- `?buddy=cast&clean`: the character sheet.
- `?buddy=pick&clean`: the setup step where the learner picks its color. Click swatches, then Continue: the buddy comes out in that color and points at a line. `shots/buddy-pick.png`.
- `?buddy=colors&clean`: the color sheet (`&set=cream` for the cream versions beside sand). `&skin=cream` (or any other name on it) on the try-out shows the buddy and its loop in that color.
- `?scenario=buddy&clean`: marks arriving from the mock engine.
- Add `&char=leaf` or `&char=dot` for another character, `&notch=below` for the pill under the menu bar.
- `?buddy`: every state of the living mark (pass 1).
- `shots/buddy-cast.png` (the sheet), `shots/buddy-colors.png` (the colors), `shots/buddy-moments.png` (close-ups of each moment), `shots/buddy-stage.png` (pass 1). Moving previews are outside the repo, in Adrian's `SanD Hacks/research/buddy-compare/`: `buddy-char-ask.gif`, `buddy-char-tour.gif`, `buddy-char-hop.gif`, `buddy-char-far.gif`.

## Checked
- `npm run typecheck` passes. `test/buddyMarks.test.ts` 69 of 69, `test/buddyTalk.test.ts` 11 of 11. The full suite has one failure, `linkHost.test.ts` (reads only drawer files; untouched here).
- Built stage in headless Chrome (1600x1000), by DOM state and recorded frames:
  - One mark: it lands, one loop draws, it says the label, Explain and Got it show and the bubble takes the mouse. Explain: it thinks, then says the explanation. Got it: it beams, the loop comes off.
  - A tour of three: one loop at a time, the numbers count down (2 and 3, then 3, then none), Next, Next, Done.
  - Hold to talk: it comes to the pointer and follows it, shows what it hears, thinks on release, flies to the answer and says the sentence with the chips. Esc sends it home.
  - A far corner, three places one after another, and a light backdrop.
  - Reduced motion (emulated): at its perch with whole words from the first frame, no blink.
- Not checked: Electron on a Mac. The buddy over real apps, the pointer rules with forwarded mouse moves, the island on a real notch, a second display, a live engine sending `annotate`, real push to talk (the wiring to `features/ptt` is written against its store and has only run with the stage's stand-in).

## Open (Adrian, then Adrian and Michael)
- Its name. (The character is picked: the sprout. The leaf and the dot are still in the code behind `?char=` and can go.)
- Which nine colors, and which one it comes in (sand today). The cream versions he asked for are still there to look at (`?buddy=colors&set=cream`, `shots/buddy-cream.png`).
- Which of the three ways above.
- Whether the growing is wanted. (The learner's color is: see above.)
- When the buddy says an answer the answer card also shows in the island. One of them should step back.

## Core requests
1. **The contract.** `annotate` and `Annotation` are on `claude/contract-circle-ask`, not on this branch. Until they land, `marks.ts` mirrors the type and `pointing.ts` casts `onMessage` to subscribe. Both go when the contract is merged.
2. **`common/wire.ts` KNOWN needs `'annotate'`**, or the app's parser drops the event in Electron (the browser stage's mock does not go through the parser). Michael has this line in b3ffd388 on `michael/app-buddy-draw`.
3. **One token for the buddy's color.** It is sand now (`brand.pastel.sand`, already in `core/theme.ts`). Michael's `features/annotate` stroke is still mint: whichever layer draws in the end, the stroke and the character should read the same token, so his needs to move to sand too, or the two will not look like one thing.
4. **A real click.** The overlay is click-through, so in Electron a click inside a mark never reaches this window. Main could broadcast a global left-mouse-down point (screen points); today the pointer resting on the mark stands in for it. Michael asks for the same thing in `agents/app-buddy-draw.md`.
5. **Longer holds for tours and answers.** The hold is counted from the newest mark's birth, so a three-mark tour sent with the default 6 s is gone before the learner reads the second one. The engine should send `holdMs` near the 30 s limit with a tour or an answer, or the rule should let an open bubble keep its mark. (The try-out sends 30 s for a tour and 12 s for an answer.)
6. **A BRAND.md section for the character.** BRAND.md does not mention a character. On Michael's integration branch it gains one exception to "no hand-drawn annotations": the buddy stroke (mint, `features/annotate`). A character with a face and pink cheeks is a brand decision; it is Adrian's to write down once he has picked one, and the stroke exception should then name whichever layer draws.
7. **The learner's buddy color needs a home in three places.** (a) Core Prefs: a `buddyColor` field (one of the names in `palette.ts` `PICKS`); until then `skin.ts` keeps it in localStorage. (b) Setup: a step that mounts `BuddyColorPicker` (exported from `features/buddy`); `?buddy=pick` is the mock. (c) Settings: a row that mounts the same picker. And if `features/annotate` keeps drawing, its stroke should read the same color (`useSkin().stroke`), or the loop and the buddy will not match. How far it has grown would need the skills count; nothing stores it.
8. **Typed questions.** The buddy comes for push to talk. A question typed in the launcher gets its answer card only; a bus event when the learner asks from anywhere would let the buddy come for those too.
