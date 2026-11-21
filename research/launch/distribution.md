# C. Distribution and deploy

Area C of Michael's launch-risk brief (Nov 21, 2026): signing, install, updates, the cloud, sign-in, limits.
Status: **early version**. The code reading is done; the source research (8 agents) is still running, and rows marked "researching" get their links and dates in the next push.

Code read for this: app `origin/michael/v2-integration` (d959e0e9, Nov 21), engine and cloud `origin/integration/live` (ddecb79c, Nov 20).

## What the code does today

| Piece | What it does | Where |
|---|---|---|
| Mac signing | Ad hoc only. `mac.identity: null`; `ship-mac.sh` builds `--dir`, then `codesign --force --deep -s -`. No hardened runtime, no entitlements, no notarization. | `app/electron-builder.yml`, `app/scripts/ship-mac.sh` |
| Mac install | 126 MB DMG (457 MB installed). First open needs System Settings > Privacy & Security > Open Anyway. | `app/SHIP.md`, `app/SIZE.md` |
| Permissions | Screen Recording (the app starts the engine, so the prompt names miyagi). Every new ad hoc build counts as a new app, so grants break after each update. | `app/SHIP.md` "Permissions after a reinstall" |
| Releases | `gh release upload mac ... --clobber` to a rolling `mac` tag on the public repo `adrian-erlikhman/miyagi` (Adrian's personal account, which also hosts miyagi.study). No version tag, no history. | `app/scripts/ship-mac.sh` |
| Updates (#189) | Checks the GitHub Releases API 45 s after launch, every 6 h and on wake. Reads a version from the tag, title or body. Opens the DMG in the browser. Nothing installs by itself. | `app/src/main/features/updates.ts`, `app/agents/updates.md` |
| Version | `app/package.json` is `0.1.0`. Nothing bumps it. | `app/package.json` |
| Engine in the release | Built from whatever `origin/integration/live` is at build time (`MIYAGI_ENGINE_REF`). | `app/scripts/ship-mac.sh` |
| Windows | Unsigned one-click NSIS installer, app only (the engine needs macOS). | `app/electron-builder.yml` `win`, `nsis` |
| miyagi-cloud | Render Blueprint: `plan: starter`, one 1 GB persistent disk (SQLite), one uvicorn process, health check `/healthz`. A disk means a single instance. | `cloud/render.yaml`, `cloud/README.md` |
| Install token | `POST /v1/install` with a 10 s timeout, retried at most every 5 min on engine connect. | `app/src/main/features/cloud.ts` |
| Sign-in | Supabase Google sign-in, PKCE in the system browser, loopback `127.0.0.1:47217`. Google's redirect goes to Supabase's own `*.supabase.co` callback. | `app/src/main/features/auth.ts`, `app/src/main/publicConfig.ts` |

## Register (early)

| id | area | risk | evidence (link) | applies to miyagi? (where) | severity | fix | owner | status |
|---|---|---|---|---|---|---|---|---|
| C01 | Apple | The app isn't signed with a Developer ID or notarized, so every install goes through Open Anyway | researching | applies: `electron-builder.yml` `identity: null`, `ship-mac.sh` ad hoc sign | P0 | Developer ID + hardened runtime + notarization (blocked on who can enroll: area B) | Adrian, Michael | open |
| C02 | Apple | Ad hoc builds lose Screen Recording on every update, so updated users see a broken app until they remove and re-add miyagi in System Settings | `app/SHIP.md` "Known gaps" | applies: every release | P1 | Developer ID signing keeps the grant (same team ID) | Adrian | open |
| C03 | Updates | Rolling `mac` tag with `--clobber`: no version history, no rollback | `app/scripts/ship-mac.sh` publish step | applies | P1 | Versioned tags, keep old releases | Adrian | open |
| C04 | Updates | The update card can't offer an update unless the release carries a version it can parse | `app/agents/updates.md` "Core requests" 2 | applies: release title/body today unknown | P1 | Title `miyagi X.Y.Z`, bump `package.json` per release | Adrian | researching |
| C05 | Render | A single instance with a disk: no scaling, and every deploy is downtime | `cloud/render.yaml`, `cloud/README.md` | applies | P1 | researching | Michael | researching |
| C06 | Google | Testing mode: only listed test users can sign in | brief section 3 | applies | P0 | Publish the OAuth app | Michael | researching |
| C07 | Windows | Unsigned installer: SmartScreen and Smart App Control | `electron-builder.yml` `nsis` | applies | P1 | researching | Adrian | researching |

More rows (Supabase pausing, AI provider limits and spend, cost per lesson, DNS and email, repo and domain transfer) come with the research.
