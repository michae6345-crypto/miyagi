# core-v2 (wave 0)

**Status:** W0-1 to W0-7 implemented, typecheck green, Python contract compiles and validates. Draft PR #163 into `adrian/shell` · **Priority:** P0 (every wave 1 lane waits on it) · **Port:** 5173 (stage checks ran on 5197) · **Branch:** `michael/app-core-v2`

## Goal
The shared base for miyagi v2 (`miyagi-v2/BUILD-PLAN.md` section 2): the contract, tokens, atoms, windows, shell services and security that wave 1 builds on. Additive only: every existing export, signature and behaviour stays (nothing reserved, no hello, no prefs set = exactly today).

## What landed
| Item | Files | Notes |
|---|---|---|
| W0-1 contract | `shared/contracts/events.ts`, `events.py`, `app/src/common/wire.ts` | run-live copy first, then optional v2 fields/events/commands (see the commit). `card.kind "complete"` is typed as `CardKindV2` (not in the union) so the cards feature's exhaustive table keeps compiling. `check.schema.json` needed nothing. v2 commands go out only when `engine.hello.capabilities` lists them (main enforces it in `EngineLink.send`; renderer `canSend`). |
| W0-2 tokens | `core/theme.ts`, `styles.css` | `status`, `surface`, `paper`, `dock` (360/16/10/380, top 52), `windowSize`, `type2`, `radius2`; new keys on `fill`, `color.onGreen/window`, `copy.editorName()` (unsupported editor names → "your editor"). BRAND pastels kept; mockup sky `#BFE3F5` not used. |
| W0-3 atoms | `core/ui/status.tsx`, `Keycap.tsx`, `GlassCard.tsx`, `buttons.tsx`, `controls.tsx`, `StepDots.tsx`, `HelpRow.tsx`, `KeysFooter.tsx`; re-exports in `atoms.tsx`, `glass.tsx` | v2 PrimaryButton is exported from atoms as `PrimaryButtonV2` (the island's `PrimaryButton` keeps its signature). Keycaps take a key NAME, labels only from `bridge.platform.keys`. Toggle on = white (never green). Watch has no keycap. |
| W0-4 windows | `core/registry.ts`, `main/appWindows.ts`, `main/context.ts`, `main/platform.ts`, `core/surfaces.ts`, `dev/Stage.tsx`, `main.tsx` | `FeatureWindow.kind/size`, `Feature.enabled`; allowlisted routes onboarding/library/progress/account; `ctx.openWindow/appWindow`; `platform.keys.settings/dismiss`, `showInDock`, `appWindowOptions`; stage `?size=WxH`, `?window=<route>&id=&view=`. |
| W0-5 services | `core/geometry.ts`, `core/dock.ts`, `core/Island.tsx` (`useIslandBox`), `core/lesson.ts`, `core/bus.ts`, `common/prefs.ts`, `main/prefs.ts`, `main/permissions.ts`, `main/localEngine.ts`, `main/engine.ts`, `main/features/cloud.ts`, `mock/engine.ts`, `bridge.ts`; re-export shims `features/spotlight/place.ts`, `features/player/dock.ts` | lesson: hello/canSend/useCapability, notice queue (`notify` returns an id, `dismissNotice`, `useNextNotice`), `useCurrentStep`, `useStepPhase`, `useUpNext`, paused/blockers/busy/statusDetail, build phases and `buildFailed.silent`. Engine token: 32 random bytes per launch, env `MIYAGI_ENGINE_TOKEN` to the engine we start, header `X-Miyagi-Token`. `engine-local:restart`. Cloud token: off unless `MIYAGI_CLOUD_URL` is set (no network otherwise), safeStorage `install.bin`, rides inside the settings feature's full `config.keys`. |
| W0-6 security | `renderer/index.html`, `main/serve.ts`, `main/index.ts`, `main/safeOpen.ts`, `main/context.ts` | CSP header (built app) + dev-safe meta; nosniff; navigation/redirect/webview blocked; deny-all permissions except mic audio for our origin; sender-frame checks on `engine:cmd`, `ui:ready`, `ui:emit`, every `ctx.handle`, and every core handler (app windows, permissions, `open:external`, `prefs:*`, `engine-local:*` including restart, which neither kills nor spawns for an untrusted sender); outgoing allowlist; renderer `config.keys` dropped; `open:external` via the allowlist. |
| W0-7 bookkeeping | `agents/ports.json` (5186-5196), `agents/README.md` (v2 lanes + island priority table), `mock/scenarios/core-v2.json` | Named `core-v2` (the plan said `v2-core`) so it sorts before `library`, `onboarding`, `progress` in `?scenario=full`: its unscoped triggers (`health.get`, `library.*`, `progress.get`) lose to the wave 1 lanes' own files (build.ts: A to Z, later file wins). |

## Deviations from the plan (and why)
- CSP adds `https://www.youtube.com https://s.ytimg.com` to script-src (the player loads the IFrame API), `'unsafe-inline'` to style-src, and the engine's http origin to media-src/connect-src (speak audio, `/stats`). Dev keeps a meta subset because Vite's HMR socket and React refresh preamble need inline script and ws to the dev port.
- `islandPlace.ts` takes geometry from core and avoids `useReserved()` rects, but still reads `useCards` and `useSpotlight` (see Core requests): removing them needs edits in those features' stores, outside this package.
- `UiSignal` (preload/api.ts) is unchanged; the new bus members are `UiEvent` `panel` and `surface`.
- Mini pill priority 9 in the README table is a proposal for A2.
- Scenario file is `mock/scenarios/core-v2.json`, not the plan's `v2-core.json` (see W0-7 above).
- The engine token goes into the `EngineLink` constructor (`main/engine.ts`, third argument): the first WebSocket attempt starts inside the constructor, before `setupLocalEngine` runs, so a later `setToken` alone would leave that attempt without `X-Miyagi-Token`.
- Two link rules in `main/safeOpen.ts`. `open:external` (IPC, `safeOpenExternal`) stays on the strict `ALLOWED_HOSTS` allowlist plus plain mailto. The window-open handler (`window.open` / `target=_blank`, `openLinkInBrowser`) accepts any https URL with no username, no password and no port other than 443 (plus a plain mailto); every other scheme is refused. Reason: setup download rows (`server/workspace/setup.py` TOOLS: python.org, nodejs.org, git-scm.com, rustup.rs, go.dev, ...), card and off-track citations and drawer sources link to arbitrary docs sites, and the pre-v2 handler sent every http(s) link to the browser; an allowlist there broke them. Plain http is no longer opened.

## Fix round 1 (review)
- Buttons: rounded rectangles per the mockups. `lg` 44 high, radius 12, 15 px / 600, padding 0 24; `md` 36 high, radius 10, 13 px / 600, padding 0 16. QuietButton: same geometry on `surface.row` with an inset `surface.border` hairline, 13 px / 500.
- HelpRow: five flex-1 OptionTiles, 56 high, radius 12, solid pastel (`actionTone`), ink label 12 px / 600, keycap inside (`on="accent"`), optional small ink `glyph`; row gap 8, title gap 12. Watch keeps no keycap.
- StepDots: `variant: 'dots' | 'bars'`. dots (panel header): 8x8, current a 20x8 pill (white, green once passed), gap 6, next `fill.trackNext`. bars (Les-Mini): 16x4, gap 3, next `fill.trackNextMini` (new token, white .24). More than `cap` steps keeps the proportional track.
- Toggle: 40x24 track, 20 px knob, 56x44 hit target. Segmented: options 32 high, padding 0 16, 12 px, track with a 1 px hairline border.
- KeysFooter: `divider` defaults to false; padded 0 20 16, gap 16.
- `safeOpen.isAllowedUrl`: a malformed `%` in a mailto returns false instead of throwing.
- `prefs:*` and `engine-local:*` handlers take main's `trusted` predicate.

## Fix round 2 (review)
- Window-open handler: any plain https link opens in the default browser again (see Deviations); `open:external` stays allowlisted.
- `feat:window:args` checks `deps.trusted(e)` like every other core handler.

## Fix round 3 (review)
- Mock engine (`mock/engine.ts`) says `engine.hello` with every `V2_COMMANDS` capability on `start()`, on `dev.reset` and when a `_link` item comes back open, before the scenario's own items. Every scenario (`?scenario=full` included) now passes `canSend()` / `useCapability()` and `setDock` sends `panel.state`. A scenario's own later hello replaces it (core-v2 still sends its `restored` hello after the fake reconnect).
- `main/engine.ts`: the `X-Miyagi-Token` header and the cloud install token in `config.keys` go only to a loopback ENGINE_URL (the localEngine.ts test) or a `wss:` one (`secureEngineUrl`). Any other URL gets neither, and main warns once without printing a value.

## Test
`npm run typecheck` (green). Python: `python -m py_compile shared/contracts/events.py` and an import + validate script with empty keys (green; library ids with a path are rejected).
Stage: `npm run dev:web -- --port 5197` → `http://localhost:5197/?scenario=core-v2&size=1440x900&clean`: hello with 7 capabilities, build phases, a lesson step with where/then, a kernel blocker and clear, a fake reconnect (`_link` 1 and 2 failures, then open and a restored hello), busy with retryInS. Checked in the page: `canSend('panel.state')` true after hello; `openLibrary('mnist_intro')` opens the stage window with args `{id}`; `openWindow('evil')` false; `permissions:get` honours `?perm=`; `panelRect` at 1440x900 = x 1064, y 52, w 360. No console errors. Atoms rendered on a panel card for a look (status rows, help row, buttons, controls, dots, keys footer).
Not verified: Electron (`npm run dev`), real TCC probes, the cloud mint against a live proxy (none exists; cost freeze), CSP in a packaged build.

## Core requests (for other lanes / the integrator)
1. **spotlight/store.ts** (integrator) and **cards/store.ts** (A2): publish target rects with `reserveRect('spotlight', ...)` / `reserveRect('card-targets', ...)` so `core/islandPlace.ts` can drop its last two feature imports (its keepOff would then read `useReserved`). Until then the W0-5 criterion "islandPlace imports only core" is NOT met (`core/islandPlace.ts` still imports `features/cards/store` and `features/spotlight/store`); keep this on the integrator's list.
2. **cards** (A2): handle `CardKindV2` `"complete"` (or route it to A8); add `complete` to the per-kind tile table before E3 sends it.
3. **overview** (`main/features/overview.ts`) and **player** (`main/features/player.ts`): move their `shell.openExternal` calls to `safeOpenExternal` from `main/safeOpen.ts`.
4. **settings** (A4): `settings:open` should read `{section}` (core/surfaces `openSettings(section)` sends it); BYOK under Advanced and `REQUIRED = []` once the cloud token is live (DISTRIBUTION-PLAN `michael/app-cloud-token`).
5. **errors** (A7): register the main handler for `diagnostics:copy` (the stage stand-in exists in bridge.ts); Restart calls `engine-local:restart` and shows "Restart it in Terminal" on `{ok:false, state:'external'}`.
6. **engine** (E2): accept `X-Miyagi-Token` when `MIYAGI_ENGINE_TOKEN` is set (absent = allow, for engines started in Terminal), reject browser Origins, send `engine.hello` first on every connect with `contract: "2026-11-20"` and the v2 commands it supports (`V2_CAPABILITIES` in events.py). Also add `MIYAGI_ENGINE_TOKEN` to the variables `safe_env()` strips from learner subprocesses: the engine inherits it from the app (`main/localEngine.ts` `env`), and a learner's notebook or script must never see it.
7. **preload/api.ts** (integrator): if wave 1 needs cross-window signals for the panel, add `UiSignal` members there; nothing in wave 0 needed one.

## Notes
- `common/prefs.ts` `shortcuts` replaces the whole map on `prefs:set`; send all of it.
- `notify()` now returns the notice id; existing callers ignore it.
- App windows show a Dock icon while open and keep their own Space (no `followSpaces`), unlike overlay windows.
