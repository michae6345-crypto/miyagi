# app-ready-copy (Lane D, Nov 25): wording note for Adrian

Branch `michael/app-ready-copy`. Every line below is live in the app. Please check the wording and reply with changes.
The app does not sync. Lesson history and skills are kept on this Mac, so the copy no longer promises sync.

## Sign in
| Where | Was | Now |
| --- | --- | --- |
| Login lede (auth/Login.tsx) | Your lessons and progress follow you to any computer. | Your lesson history and skills stay on this Mac. |
| Account sheet title, signed out | Sign in to sync | Sign in to miyagi |
| Account sheet sub, signed out | Your lessons and progress, across Macs. | Your lesson history and skills stay on this Mac. |
| Account sheet, New user lead | Make an account. Your lessons and progress follow you. | Make an account. Lessons work with or without one. |
| Account sheet, just signed in | Your lessons and progress now sync across Macs. | Your lesson history and skills stay on this Mac. |
| Account page, signed out row | Sign in to sync your progress across Macs (group "Sync") | Sign in to miyagi (group "Account"), with the caption "Your lesson history and skills stay on this Mac." |
| Sidebar account chip, screen reader line | Sign in to sync | Sign in |
| Pro plan features (planFeatures.ts) | Progress synced across your computers | (removed) |

## Settings > Apps
- There are no Connect buttons now. The app has no way to set up an add-on yet, so Connect could only say "Not ready yet."
- Blender, FreeCAD, Fusion and Onshape show "Screen only" and "Used by N plans." Their "Reads your scene..." lines are gone until an add-on really connects. Then the engine's health makes the row say Connected.
- A health item that is off now says "Not open". "Not found" is kept for missing.

## Lesson build cap (signincard/notice.ts)
- Was: "You've used this month's new lessons. More on Nov 30."
- Now: "This lesson builds right here. It may take a minute."
- Why: when the cloud refuses a shared build claim, the lesson still builds on this Mac. It just isn't shared, so the learner hasn't run out of anything.

## Skills, empty state
- If you click a skill chip before you have any skills, the page now uses that skill's name as the title. The line under it is "Not started yet. A lesson that teaches it adds it here."
- With no clicked skill it still says "No skills yet".

## Not copy, for the record
- The packaged renderer now carries no mock data. The mock engine, the scenarios, the Stage and the auth, account and circle stand-ins load only in a dev build (dev/stageMocks.ts). `grep "Sam Rivera" out/renderer` finds nothing after `npm run build`.
- test/appReadyCopy.test.ts fails if "sync" or "follow you" appears in any renderer string.
