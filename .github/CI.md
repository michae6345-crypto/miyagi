# CI: what runs when

macOS runner minutes count 10x Linux ones, so the slow Mac suites run nightly, not on every push.

| Workflow | Runner | When |
| --- | --- | --- |
| `ci.yml` | Linux; `mac-build` + `replay-mac` on macOS run only nightly (09:30 UTC) or by hand | every PR, every push to `main`, nightly, manual |
| `engine-ci.yml` | Linux | PRs and `main` pushes touching `server/`, `shared/`, `cloud/` |
| `app-ci.yml` `app` | Linux | PRs and `main` pushes touching `app/`: typecheck + all unit tests (`app/test/*.test.ts`), then the report guard |
| `app-ci.yml` `mac` | macOS | same trigger: only the four test files whose tests skip off darwin (`overlayWindow`, `overlayLifecycle`, `screenLayout`, `permissionsRefresh`) |
| `app-e2e.yml` | macOS | nightly 09:00 UTC (1am Pacific) on `main`; manual; PRs labeled `run-ui-tests` that touch `app/` |
| `app-visual.yml` | macOS | nightly 09:00 UTC on `main`; manual; PRs labeled `run-ui-tests` that touch `app/` |

**Lane branches get no CI on push** (Nov 27 trim, before the repo goes private). A lane branch pushed without a PR
runs nothing; run its checks locally before merging (engine: `env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY pytest
server -q`; app: `npm run typecheck` and the unit tests), or open a PR to get CI. `trunk-guards.yml` is gone: `ci.yml`
already runs gitleaks and contract parity on every push to `main`. Don't add a macOS job that runs on every push.

Every workflow has one concurrency group per workflow and branch/PR: a newer commit cancels the older run, on `main`
too. Nightly runs get their own group, so they are never cancelled mid-way. A failed nightly run just shows red in
the Actions tab (no extra alerts).

**The unit-test report guard** (`app/scripts/check-test-report.mjs`): both app-ci jobs write a TAP report and fail
when any suite started without a result line, or when `# tests` is below a floor (1,410 on Linux, 36 on the Mac
slice). `node --test` counts only what each file's child process reports, so a report cut short used to pass green
with fewer tests (1,385 to 1,417 on the same commit). The cause was async pipe writes dropped when
`--test-force-exit` calls `process.exit()`; `app/test/setup.mjs` now makes those writes blocking. Raise the floor in
`app-ci.yml` as the suite grows; lower it only when deleting tests on purpose.

Adding a test that only runs on macOS (`{ skip: process.platform !== 'darwin' }`)? Add its file to the `mac` job in
`app-ci.yml`, or the Linux job will skip it and nothing else runs it.

## Running the UI tests (e2e + visual) before merge

- On a PR: add the label `run-ui-tests`. Both suites run once on the label, then again on each new commit while the
  label stays. Remove the label to stop.
- By hand: Actions -> app-e2e (or app-visual) -> Run workflow, pick the branch, optionally a `ref` (branch, tag or
  SHA). CLI: `gh workflow run app-e2e.yml --ref <branch>` / `gh workflow run app-visual.yml --ref <branch> -f update=true`
  (the latter uploads fresh baselines as an artifact).

## Rough Mac minutes per month

Measured over Nov 24-26: about 1,000 Mac minutes in 2 days (app-visual 538, app-ci 272, app-e2e 191), which is
about 15,000 a month.

| | Before | After |
| --- | --- | --- |
| app-visual (~15 min a run) | ~8,100 (every push to main and every PR push) | ~450 (nightly) + labeled PRs |
| app-e2e (~4 min a run) | ~2,900 | ~120 (nightly) + labeled PRs |
| app-ci (Mac) | ~4,100 (whole suite + typecheck) | ~1,500-2,000 (four files, ~2 min a run) |
| ci `replay-mac` | 0 (macos-14 retired: cancelled before it started) | 0 (unchanged here) |
| Total | ~15,000 | ~2,100-2,600 (about -85%) |

app-ci's Linux job adds roughly 3,000 Linux minutes a month (equal to ~300 Mac minutes in cost). Not counted
above and unchanged here: `ci.yml`'s `mac-build` (main pushes, a full Electron build). Reviving `replay-mac` (for example
on `macos-latest`, main pushes only, ~700 Mac min a month) is a separate decision.
