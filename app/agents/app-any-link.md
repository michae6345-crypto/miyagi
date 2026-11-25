# app-any-link: lessons from any link (app side)

Contract: `shared/contracts/ANY-LINK.md` (link.preview kinds web / github, BuildSource web / github, lesson.origin,
StepSummary.pageRef, the `link.any` capability). Branch `michael/app-any-link` from `michael/app-ui-v4`.

## What it does

- **Launcher** (`features/launcher/Launcher.tsx`, small hooks only): with `link.any` + `link.get` in engine.hello, a pasted
  page (an article, a docs page, a github.com repo; not YouTube, which keeps its own preview) shows the **link card**
  (`features/anylink/Card.tsx` LinkCard): kind and site, title, about how long and the tools, "Ready instantly" when
  `cached`, or one calm line on why miyagi can't teach it (`why`, or the LOOKUP line for an error). The footer's one
  primary says what Enter does: Build lesson / Start lesson (`learn_url {url}`), Just teach me on the page's title (not
  teachable), disabled "Reading the page…" until the full answer, nothing for an error. Footer hint: "Paste any link or
  type a goal". Without `link.any` nothing changes.
- **Notch** (`features/notch-home`): the drop zone reads "Drop a link to learn it". A YouTube drop builds at once, as
  before; a page drop asks link.get and shows NotchLinkCard in place of Continue (its own Build lesson, ✕ to dismiss).
- **Library** (`features/library`): `sanitize.ts` keeps web / github sources (a safe http(s) url, site, author). Rows draw
  the kind's tile (theme.kindTone, never an image from the site) and a site badge after the title; the lesson detail has
  an "Open source" row (The original page / The repo on GitHub) that opens in the browser.
- **Lesson panel** (`features/drawer/v2/Source.tsx`): a page lesson (lesson.origin web / github) shows "From <site>" under
  Need help, with this step's part of the page (pageRef heading, same host only) or the page itself.

Pure helpers in `features/anylink/link.ts` (parseWebLink, siteOf, linkKey / sameLink, safeWebUrl, pageAction,
lookupLine), the link.get round trip in `features/anylink/store.ts`. Tests: `test/anyLink.test.ts`.

## See it

`npm run dev:web -- --port 5231` then `/?scenario=any-link&size=1440x900&clean&appearance=dark`: Ctrl+K and paste, in
order, docs.python.org/3/tutorial/venv.html, github.com/pallets/flask, example.com/blog/why-i-switched-editors,
example.org/members/advanced-pandas (the mock cycles through those answers). A fresh page + the docs link + Enter builds
the lesson (panel source section). `&window=library` → Library for the rows and the detail. Hover the notch and drop a
docs.python.org link for the notch card. Shots: `agents/shots/anylink-*.png` (light and dark).

## Status

Done for the mock, merged up to michael/app-ui-v4 a12a7873 (ambient help in the launcher: a pasted page skips the
ambient rows like a YouTube link). Shots re-taken after the merge (light and dark). Not checked in Electron. The mock answers by order, not by URL (`link.get` cycles), so a card for a
link pasted out of order stays on "Reading the page…" in the stage.

## Core requests

None. Home's "Up next" rows and the launcher's Ready rows still draw the tool art for a page lesson (left as is to keep
launcher edits small).
