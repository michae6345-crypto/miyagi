# Any link: lessons from an article, a docs page or a GitHub repo (Nov 24)

Until now a lesson came from a YouTube video (captions -> plan -> steps -> checks), a playlist, a goal ("Just teach me") or
the library. With this contract the learner can paste **any http(s) link** in the launcher: a tutorial article, a docs page
(docs.python.org, MDN, a library's guide) or a github.com repo, and get the same kind of lesson: steps, checks, the drawer.

Everything here is **additive**. `events.ts` and `events.py` carry it on both branches (`michael/app-ui-v4`,
`integration/live`); `scripts/test_contract_parity.py` checks they agree and that the mock below validates. Mock events:
`app/mock/scenarios/any-link.json`.

## Feature flag: `link.any`

The engine lists `"link.any"` (`LINK_ANY_CAPABILITY`) in `engine.hello.capabilities` once `link.get` and `learn_url` take any
http(s) link. It is a feature, not a command (the capability list was commands only until now). Without it:

- the app keeps today's launcher: only YouTube links get a preview card and Start;
- an older engine answers `link.get` for a non-YouTube link with `link.preview {kind: "unsupported"}`, as it does today.

## Messages

### `link.get` -> `link.preview` (launcher preview card)

The command is unchanged: `link.get {url, reqId?}`. `link.preview` gains two kinds and some optional fields.

| field | meaning |
|---|---|
| `kind` | `LinkKind`: `"video"`, `"playlist"`, `"unsupported"`, and now `"web"` (an article or docs page) and `"github"` (a github.com repo: its README, or a docs folder / file in it) |
| `title` | the page's title (`<title>` / `og:title` / the repo name) |
| `site` | `"docs.python.org"`; for GitHub `"github.com/<owner>/<repo>"` |
| `author` | only when the page names one (byline, `article:author`, the repo owner's display name) |
| `estMinutes` | about how long the lesson takes, whole minutes (page length and code blocks; the steps' own estimates once built) |
| `teachable` | the page can become a lesson: it has steps to follow or code to type / run |
| `teach` | `LinkTeachable {steps, code}`: the two halves of `teachable` (`teachable = steps \|\| code`) |
| `why` | one plain line on why it is or is not teachable ("It's an opinion piece, with nothing to do or type.") |
| `tools` | the `LessonTool`s the lesson would use (`["vscode", "terminal"]`) |
| `cached` | a lesson for this exact page (same normalized URL and content hash, below) is already built, on this Mac or in the shared lesson cache: Start is instant |
| `finalUrl` | where the link ended after redirects (normalized), when that differs from `url` |
| `grows`, `have`, `finishesGoal`, `catalogId` | as for a video |
| `error` | as before, plus `"blocked"`: the site needs a sign-in, a paywall, robots.txt says no, or it answered 401 / 403 / 451 |

Like a video, a fast first answer (`pending: true`: title and site from the page head, no model call) may be followed by the
full one (`pending: false`: `teachable`, `teach`, `why`, `estMinutes`, `tools`, `grows`). `thumbnail` stays `i.ytimg.com`
only: the app never loads an image from a pasted site (no tracking pixel, no surprise content).

Launcher behaviour (app lane): `teachable` -> Start sends `learn_url {url}`; not teachable -> show `why` and offer "Just
teach me" with the page title as the goal (`learn {query: title, mode: "lesson"}`); `error` -> the `LOOKUP_LINE` text.

### `learn_url` (start the lesson)

Unchanged shape: `learn_url {url, transcriptOnly?, plan?}`. With `link.any` the url may be any http(s) link.
`transcriptOnly` is ignored for a web / github link. The build reports as today:

- `lesson.building.source` is a `BuildSource` with `kind: "web"` or `"github"`, `url` always set, `site`, and `author` when
  known. The stage ids are unchanged (`watching`, `steps`, `checks`, `ready`); the engine labels the first one "Reading the
  page" (`BuildPhase.label`).
- `lesson.building.failCode` may be `"no_content"` (the page had no readable text: a script-only page, an image, a PDF the
  engine cannot read) or `"blocked"` (as for `error` above), besides the existing codes.
- `lesson.ready.lesson.mode` is `"lesson"` (no video, no player events, the editor is full screen), and
  `lesson.ready.lesson.origin` is the same `BuildSource`, so the drawer can say "From docs.python.org" with an Open link.
- `lesson.ready.lesson.sources` lists the page as a `Source` with `kind: "blog"` (web) or `"repo"` (github), `meta` = site.
- Each `StepSummary` may carry `pageRef: PageRef {url, heading?}`: the section of the page the step comes from (a
  `#fragment` when the page has an anchor for that heading). It is the web analog of `StepSummary.video`. It never carries
  the page's own words; the app may offer "Open this part" (opened through the app's safe link opener).
- `LibraryItem.source` is the same `BuildSource`, so the library shows web and GitHub lessons with their site.

### `BuildSource` kinds

`BuildSourceKind = "youtube" | "goal" | "library" | "web" | "github"`. New optional fields: `site`, `author`.

## The shared lesson cache key for a link

A video is cached by its 11-character id with `?schema=LESSON_SCHEMA_VERSION`. A page is cached by:

```
(link_cache_key(kind, url, content_hash), LESSON_SCHEMA_VERSION)
link_cache_key = ("w_" | "g_") + sha256(normalize_link_url(url) + "\n" + content_hash)[:32 hex]
content_hash   = link_content_hash(readable_text) = sha256 hex of the page's readable text, whitespace collapsed
```

All three helpers live in `events.py` (`normalize_link_url`, `link_content_hash`, `link_cache_key`, `LINK_CACHE_KEY_RE =
^[wg]_[0-9a-f]{32}$`) so the engine and miyagi-cloud agree. So:

- the same page through another spelling of its link (http, `www.`, a trailing slash, `#section`, `utm_*` / `fbclid` /
  `ref` parameters, `Pallets/Flask.git`) hits the same lesson;
- an edited page (new readable text) builds a new lesson, and an old lesson never teaches a page that changed under it;
- a new `LESSON_SCHEMA_VERSION` rebuilds every page, as for videos.

`normalize_link_url`: https; lower-case host without `www.`, a trailing dot or a default port; no user info; no fragment;
no `utm_*` or `LINK_TRACKING_PARAMS` parameters, the others sorted; repeated slashes collapsed and no trailing slash (but
`/`); on github.com the owner and repo lower case and `.git` dropped. It raises `ValueError` for a link that is not
http(s) with a host.

The content hash is of the **readable text** the lesson is built from (after removing navigation, ads, cookie banners,
dates), not the raw HTML, so a page whose sidebar changes keeps its key. For GitHub it is the README (or the docs file /
folder files, in path order) at the default branch.

## Engine notes (engine lane, `integration/live`)

- **Fetch safely.** Only http(s); never `file:`, `localhost`, `*.local`, or a private / link-local / loopback address after
  DNS resolution (and after every redirect): answer `unsupported`. No cookies or credentials, at most 5 redirects, a 10 s
  timeout, at most 2 MB read. Respect robots.txt for the user agent; a refusal is `blocked`. Pages are only ever public, so
  a lesson built from one may go to the shared cache like a video's.
- **GitHub.** `github.com/<owner>/<repo>[/tree|blob/<ref>/<path>]`: read the README (or that docs file / folder) through
  raw.githubusercontent.com or the public API without a token; `site` = `github.com/<owner>/<repo>`.
- **Models.** `link.preview`'s teachable verdict is one small Haiku call on the page outline (headings + code block
  count + first lines), through server/models.py and the guarded client; the build is Sonnet, as for a "Just teach me"
  lesson, with the page text in place of the transcript. Never Opus. A page over the build's text budget is cut at a
  section boundary (the lesson says it covers the first part), not refused.
- **Progressive first step** works as for videos: send `lesson.ready` with step 1 as soon as it is checked, then
  `lesson.updated` with the rest.
- **Cloud.** miyagi-cloud's `/lessons/{id}` route must accept `LINK_CACHE_KEY_RE` ids beside 11-character video ids; until
  it does, `lookup` / `claim` / `share` skip link lessons (local cache only) and `cached` covers this Mac only.
- Tests are offline: mock HTTP (the page, robots.txt, redirects, a private address) and the model client.

## Examples

`link.preview` for a docs page (final answer):

```json
{"type": "link.preview", "payload": {"url": "https://docs.python.org/3/tutorial/venv.html", "reqId": "r-any-1", "kind": "web",
 "pending": false, "title": "Virtual Environments and Packages", "site": "docs.python.org", "estMinutes": 10, "teachable": true,
 "teach": {"steps": true, "code": true}, "why": "Walks through commands you run, one at a time.", "tools": ["terminal"],
 "grows": [{"label": "Virtual environments"}, {"label": "Installing packages"}], "cached": true}}
```

A page that is not teachable, and one that is blocked:

```json
{"type": "link.preview", "payload": {"url": "https://example.com/blog/why-i-switched-editors", "kind": "web", "pending": false,
 "title": "Why I switched editors", "site": "example.com", "teachable": false, "teach": {"steps": false, "code": false},
 "why": "It's an opinion piece, with nothing to do or type."}}
{"type": "link.preview", "payload": {"url": "https://example.org/members/advanced-pandas", "kind": "web", "pending": false, "error": "blocked"}}
```

`lesson.building` / `lesson.ready` for a repo:

```json
{"type": "lesson.building", "payload": {"message": "Reading the page", "progress": 0.15, "stage": "watching",
 "source": {"kind": "github", "title": "Flask", "url": "https://github.com/pallets/flask", "site": "github.com/pallets/flask", "author": "Pallets"}}}
{"type": "lesson.ready", "payload": {"lesson": {"id": "web-g_9b27d311", "title": "Your first Flask app", "mode": "lesson",
 "origin": {"kind": "github", "title": "Flask", "url": "https://github.com/pallets/flask", "site": "github.com/pallets/flask"},
 "sources": [{"id": "src1", "kind": "repo", "title": "Flask", "url": "https://github.com/pallets/flask", "meta": "github.com/pallets/flask"}]},
 "steps": [{"id": "s1", "index": 0, "title": "Install Flask", "kind": "run", "estMinutes": 3,
            "pageRef": {"url": "https://github.com/pallets/flask#installing", "heading": "Installing"}}]}}
```

The mock (`npm run mock -- any-link`, or `SCENARIO=any-link`) cycles through a docs page, a repo, an essay and a blocked page on
each `link.get`, and builds the docs page or the repo on `learn_url`.
