# Friends (MIC-85)

Nov 24, 2026. Adrian picked every decision below on Nov 24. Mockups: `shots/social/`. Background and sources: `RESEARCH.md` (finding numbers in brackets).

**In one line:** friends are people you already know. You add them with a code or a link, both sides agree, and a friend sees your name, your bon and your weekly steps.

## Decisions

| | Decision | Why | The other option, not taken |
|---|---|---|---|
| Finding each other | **A friend code** (`K7M2-Q9XD`) **and the same code as a link.** No username search, no contacts, no suggestions. | Nintendo chose codes to keep strangers apart [B1]. Instagram, Snapchat and Strava all default teens to private and limit who can reach them [B5, B6, A6]. The app has no username today, so search would mean building a public namespace. | Username search for adults, later. |
| Agreement | **Both sides.** Entering a code sends a request; the other person accepts. | Codes get passed around [B1]. | A code alone makes you friends. Faster, but a forwarded link lets anyone in. |
| Who you are to a friend | **A first name or nickname** (starts as the first word of the Google name) **and your bon.** Never email, last name or a photo. | Michael's rule for 13 to 17, applied to everyone. | A unique username. |
| What a friend sees | **Name, bon color and level, steps passed per week and today, skills mastered** (a number, switchable) **and your plan's name** (switchable; a lesson you made yourself is never named). | Enough for a board and a reason to say something to each other. | Name, bon and weekly steps only. |
| Off until turned on | **Friends starts off.** Turning it on shows exactly what a friend sees. | Progress never leaves the Mac today. This is the moment that changes. | |
| Not in it | Messages, reactions, photos, bios, public profiles, an activity feed. | Each one needs moderation, and chat is where the FTC expects teen defaults to be off [C2]. | Preset nudges, later. |
| During the private beta | **Invites work only between people already in the beta.** A link does not let a new person download the app. | The beta stays closed, as the founders decided on Nov 22. | A link also lets a friend in. |

## The flow

| Action | What happens | What the other person learns |
|---|---|---|
| Send | Type a code or open a link, see the name and bon, send. Up to 10 waiting. | A request with your name and bon |
| Accept | You are on each other's board from this week on. | That you accepted |
| Decline | The request goes away. | Nothing. It lapses for them after 30 days |
| Cancel | Your request is withdrawn. | It disappears |
| Remove | You leave each other's lists and boards. Either can ask again. | Nothing |
| Block | Removes them. Their requests and code lookups fail as "No one has that code". Listed in Settings, where you can unblock. An option reports the name. | Nothing |
| New code | The old code and link stop working. Friends are kept. | Nothing |

Limits: 50 friends, 10 requests waiting, 10 code tries an hour.

## 13 to 17: what is different

The rules above are already the careful ones, for everyone. The app knows age only as a band the learner gave, kept on the Mac, so a rule that protects only people who told the truth is weak. Three things differ:

1. **Turning Friends on asks again** for "My parent or guardian agrees", the same line as setup.
2. **Invites are single links**, one friend each, good for 7 days. There is no standing code to pass around.
3. **The plan name is not shared.**

Not designed yet: a parent's view of the friends list, as consoles and Snapchat have [B6, B8]. The app holds no contact for a parent today, only the checkbox. That needs new data and a lawyer's read.

## States

| State | What the learner sees |
|---|---|
| Not signed in | Friends needs an account |
| Code not found, their own code, or already friends | One line under the field. No request is sent |
| Request waiting | In Sent, with Cancel request |
| A friend turned Friends off | They leave your list and board, and return when they turn it on |
| Name refused by the filter | Asked for another before Friends turns on |
| Offline | The list as last seen. Accept, send and block wait for a connection |
| Account deleted | Friendships, requests and blocks go with it |

## Never shown to anyone

Email and last name. Age and birthday. Minutes, times of day and when you were last here. Lessons, code, screen and questions. Steps skipped or not passed.

## What the backend would need

1. **An account record.** None exists beyond Google's name and email (`account:get` returns null). It would hold the display name, bon color, Friends on or off, the two sharing switches and the age band. The band is only in `userData/age.json` on the Mac today; the server needs the band, never the birthday.
2. **Codes.** One per learner, replaceable. A lookup returns a name and a bon, nothing else, and is rate limited. Single-use links for 13 to 17.
3. **Requests, friendships and blocks**, with every rule above held on the server.
4. **A page at `miyagi.study/add/<code>`** that opens the app. Sign-in uses a loopback redirect today, so the app may have no link scheme yet.
5. **A name filter and a place for reports** (support@ is enough in the beta).
6. **Policy text.** `web/privacy.md` says lesson progress is kept on this Mac. Friends changes that for learners who turn it on.
