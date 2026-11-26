# CI: what runs when

macOS runner minutes count 10x Linux ones, so the slow Mac suites run nightly, not on every push.

| Workflow | Runner | When |
| --- | --- | --- |
| `ci.yml` | Linux (+ `replay-mac` and `mac-build` on macOS, main pushes only) | every PR, every push to `main` |
| `engine-ci.yml` | Linux | PRs and pushes touching `server/`, `shared/`, `cloud/` |
| `app-ci.yml` `app` | Linux | PRs and pushes touching `app/`: typecheck + all unit tests (`app/test/*.test.ts`) |
| `app-ci.yml` `mac` | macOS | same trigger: only the four test files whose tests skip off darwin (`overlayWindow`, `overlayLifecycle`, `screenLayout`, `permissionsRefresh`) |
| `app-e2e.yml` | macOS | nightly 09:00 UTC (1am Pacific) on `main`; manual; PRs labeled `run-ui-tests` |
| `app-visual.yml` | macOS | nightly 09:00 UTC on `main`; manual; PRs labeled `run-ui-tests` |
| `trunk-guards.yml` | Linux | pushes to the legacy trunks `integration/live`, `michael/app-ui-v4`; manual |

Every workflow has one concurrency group per workflow and branch/PR: a newer commit cancels the older run, on `main`
too. Nightly runs get their own group, so they are never cancelled mid-way. A failed nightly run just shows red in
the Actions tab (no extra alerts).

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
| ci `replay-mac` | 0 (macos-14 retired: cancelled before it started) | ~700 (main pushes, ~3 min a run) |
| Total | ~15,000 | ~2,800-3,300 (about -80%) |

app-ci's Linux job adds roughly 3,000 Linux minutes a month (equal to ~300 Mac minutes in cost). Not counted
above and unchanged here: `ci.yml`'s `mac-build` (main pushes, a full Electron build).
