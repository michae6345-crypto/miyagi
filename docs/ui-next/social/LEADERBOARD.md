# Leaderboard (MIC-84)

Nov 24, 2026. Adrian picked every decision below on Nov 24. Mockups: `shots/social/`. Background and sources: `RESEARCH.md` (finding numbers in brackets).

**In one line:** a weekly board of steps passed, among friends, on a new Friends page and in a small block on Home.

## Decisions

| | Decision | Why | The other option, not taken |
|---|---|---|---|
| What is ranked | **Steps passed**, counted the way bon counts them: a step you did and the check passed, once per step. Skipped steps and steps already done do not count. | It is the one number the engine grades, and it already exists per day. | Skills mastered: honest, but 0 to 2 in a week. Minutes exist too, but reward leaving a lesson open; Duolingo had to rework XP when grinding made boards unfair [A4]. |
| Period | **One week, Monday to Sunday**, each learner's own local days. Last week stays on the page as final. | A week forgives a missed day and everyone starts level on Monday. | Daily punishes a day off. All-time can never be caught, and bon's level already shows it. |
| Against whom | **Friends only.** No board of everyone. | Steps are graded on the learner's own Mac, so the server cannot prove a count. Among friends that is fine; among strangers it is not. The beta is small, low rank is what drives people away [A10], and Strava defaults under-18s off its open boards [A6]. | Both: friends, plus groups of about 30 strangers for adults who opt in. Later, once counts can be checked. |
| Where it sits | **A Friends item in the sidebar** under Progress, opening on the Leaderboard tab, and four rows in the Home rail. | Home is seen every day, which is the daily pull the issue asks for, without a notification. | A tab inside Progress. |
| How a learner appears | **First name or nickname, and their bon** in its color at its level. No photo, no email. | bon is already theirs and already shows all-time progress. | |
| Streaks | **None.** | The app rules them out (`dashboard/Summary.tsx`: "never a streak"). | |

## Rules

- **Places.** The same number of steps is the same place, and the next place skips: 1, 2, 3, 3, 5.
- **No last place.** A learner with no steps this week is listed under the others without a number.
- **A day counts at most 30 steps** (number to tune). It blunts grinding and a faked count.
- **Today.** Each row shows the steps passed today (+3). That is the only detail finer than a week.
- **Together.** One line gives the whole board's total for the week, so there is something to share as well as a place [A5, A9].
- **Nothing pushes.** No notifications, no demotion, no "you lost your place" at launch.
- **Sit out.** A switch in Settings keeps your friends and leaves you off every board. Turning Friends off shares nothing at all.

## States

| State | What the learner sees |
|---|---|
| Friends never turned on | Their own last eight weeks and a Turn on Friends button |
| On, no friends yet | Their own weeks, their code, a field for a friend's code |
| Offline | The last board, dimmed, with its time. Their own steps still count and are sent later |
| Removed or blocked | Gone from each other's boards at once, last week's table included |
| Joined mid-week | The whole current week counts. Earlier weeks are not sent |
| Not signed in | Their own weeks and Continue with Google |

## 13 to 17

The same board. It is already friends only and opt-in. Turning it on asks again for "My parent or guardian agrees", and the plan name is not shown. Before a public launch a lawyer should read Connecticut's rule on features that extend a minor's use and New York's consent rule [C6, C7]. The cautious fallback is friends without places for under 18.

## Never on the board

Minutes, time of day, when someone was last here, which lessons, skipped or failed steps, email, age.

## What the backend would need

1. Today all progress stays in `~/miyagi/state` on the Mac and the cloud keeps no per-user progress. The board needs one thing kept per learner who turned Friends on: **steps passed per local day**.
2. One read for "me and my accepted friends": this week, last week and today, plus each friend's name, bon color, steps in all (for the level) and skills mastered.
3. The rules held on the server, not in the app: only accepted friends can read a learner's numbers; Sit out and Friends off stop serving them; a block hides both ways.
4. A limit on what the app may write (30 a day, only for today and yesterday), because the count comes from the learner's own Mac.
5. A fetch when the page opens and every few minutes. No live connection.
6. One learner on two Macs: a step counts once.
7. Deleting the account or clearing history removes their rows.

Questions for Michael: can the opt-in `step_passed` count already sent per install be reused, or should it stay apart because the consent is different? Does bon's count survive a new Mac today (`growth.ts` says yes, `UI-V4.md` says no)?
