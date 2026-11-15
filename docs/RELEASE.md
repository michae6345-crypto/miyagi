# Release: integration/live + adrian/shell -> main

Run after the 9 AM PST feature freeze, before the noon Devpost deadline. A person runs this; agents never push to `main`,
never force-push and never merge PRs. Same route as the last release (PR #93): a release branch, a PR, a merge commit.

Dry run (2026-11-15 06:43 PST, branch `claude/release-dryrun`): `origin/main` dbf341d + `integration/live` cf10b26 +
`adrian/shell` d7e6de9 merged with **no conflicts**. On the merged tree: `server/`, `shared/`, `docs/`, `cli/`,
`vscode-ext/` are byte-identical to integration/live, `app/` is byte-identical to adrian/shell. Only two files differ from
integration/live outside `app/`: `.github/workflows/ci.yml` (adrian/shell's Mac zip step) and
`scripts/contract_check_allow.txt` (main's three `offtrack.action` lines). Both are correct as merged.

## Ownership (how to resolve any conflict)

| Path | Owner | Resolution |
|---|---|---|
| `server/`, `shared/`, `docs/` | integration/live | take integration/live's version |
| `app/` | adrian/shell | take adrian/shell's version |
| `.github/workflows/ci.yml` | both | adrian/shell's version (integration/live's plus the Mac zip step) |
| `scripts/contract_check_allow.txt` | both | keep every line from both sides |
| anything else (`cli/`, `vscode-ext/`, `scripts/`, `README.md`, ...) | integration/live | take integration/live's version unless the app side clearly adds to it |

adrian/shell's own edits to `shared/contracts/events.ts` / `events.py` are syncs copied from integration/live, so taking
integration/live's contract loses nothing (`git` auto-merged them to integration/live's exact text in the dry run).

## Commands

```bash
set -euo pipefail
cd "/Users/tripi/sand hacks/sandhacks-tutor"
git fetch origin
ENGINE=$(git rev-parse origin/integration/live)   # pin the frozen tips once; other sessions keep fetching
APP=$(git rev-parse origin/adrian/shell)
echo "engine $ENGINE  app $APP"

git worktree add -b claude/release-final .claude/worktrees/release-final origin/main
cd .claude/worktrees/release-final

# 1. engine
git merge --no-ff -m "Merge integration/live ${ENGINE:0:7} (engine) into release" "$ENGINE" || {
  git restore --source="$ENGINE" --staged --worktree -- server shared docs
  git restore --source="$APP"    --staged --worktree -- app
  git diff --name-only --diff-filter=U        # if this lists files, the commit below stops: resolve them by the table above, `git add`, `git commit --no-edit`, carry on
  git commit --no-edit
}

# 2. app
git merge --no-ff -m "Merge adrian/shell ${APP:0:7} (app) into release" "$APP" || {
  git restore --source="$APP"    --staged --worktree -- app
  git restore --source="$ENGINE" --staged --worktree -- server shared docs
  git diff --name-only --diff-filter=U        # if this lists files, the commit below stops: resolve them by the table above, `git add`, `git commit --no-edit`, carry on
  git commit --no-edit
}

# 3. ownership holds (both must print nothing)
git diff --stat "$ENGINE" HEAD -- server shared docs
git diff --stat "$APP" HEAD -- app
```

`git restore --source=X -- dir` makes `dir` match X exactly, deleting files X doesn't have, so it is safe to run on a
merge that had no conflicts in that directory.

## Fixes to commit on the release branch

1. **Contract check (CI job `contract`) fails on the merged tree**: `card.shown` and `card.closed` are in
   `AppCommands` (E14, optional) but the app never sends them. Unless the app sends them by the freeze, allow-list them:

   ```bash
   python3 scripts/check_contract.py || cat >> scripts/contract_check_allow.txt <<'EOF'
   command:card.shown   # optional (E14, events.ts AppCommands): the app doesn't report card visibility yet; the engine keeps its old behaviour without it
   command:card.closed  # same: optional E14 report, not sent by the app yet
   EOF
   python3 scripts/check_contract.py && python3 scripts/test_check_contract.py
   git commit -am "ci: allow-list the optional card.shown / card.closed commands"
   ```

2. **README**: delete the note under "2. Overlay app" that says the newest overlay is on `adrian/shell` "until it's
   merged here". After this merge it is wrong.

## Verify on the merged tree

```bash
PY="/Users/tripi/sand hacks/sandhacks-tutor/.claude/worktrees/run-live/.venv/bin/python"
env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u BRIGHTDATA_API_KEY "$PY" -m pytest server -q -k "not screencapture_backend_live"
"$PY" -c "import sys; sys.path.insert(0,'.'); import server.orchestrator.main"
python3 scripts/check_contract.py
(cd app && npm ci && npm run typecheck && npm run build)
```

Dry-run results (cf10b26 + d7e6de9): pytest 1004 passed, 1 skipped, 1 deselected; import OK; typecheck OK;
`electron-vite build` OK; contract check OK after fix 1.

## Ship

```bash
git push -u origin claude/release-final
gh pr create --base main --head claude/release-final \
  --title "Release: integration/live ${ENGINE:0:7} + adrian/shell ${APP:0:7}" \
  --body "Final release merge. server/shared/docs = integration/live, app = adrian/shell. See docs/RELEASE.md."
```

Merge the PR on GitHub with **Create a merge commit** (not squash or rebase, so both branches' history stays an ancestor
of `main`). `origin/main` is an ancestor of the release branch, so no force-push is ever needed. Pushing to `main` runs
CI's `mac-build` (the downloadable `.app` zip).

After the merge: the repo is already public. It has no LICENSE file, so it is "all rights reserved" by default; add one
if the Devpost entry needs an open-source license.
