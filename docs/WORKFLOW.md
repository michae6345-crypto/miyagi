# How we work together: GitHub, branches, Claude sessions

## Repo setup (Michael, first 15 minutes)
1. Create **one GitHub repo** (monorepo, private for now; make it public before submitting, since Devpost needs the link). It must be created **after Sat 10:30 AM**, and no code from before then. ✅
2. Add Adrian and the third teammate as collaborators.
3. Push this skeleton to `main`:
```
app/            Electron overlay (Adrian)
vscode-ext/     VS Code extension (Adrian)
server/         engine: lesson builder, checks, coach, finder, diagrams data (Michael + teammate)
cli/            `tut run` wrapper (Michael)
shared/contracts/  events.ts, step-graph.schema.json, check.schema.json, metric protocol (shared)
demo/           PINN repo, cached lesson + search results, scenario files (teammate)
docs/           PLAN.md, FRONTEND-HANDOFF.md, WORKFLOW.md, mockups/
.github/workflows/  ci.yml (typecheck + Mac build artifact)
.env.example    every key name, no values
```
4. Add `CODEOWNERS`: `app/ vscode-ext/ → @adrian`, `server/ cli/ → @michael`, `demo/ server/finder/ → @teammate`, `shared/contracts/ → all three`.
5. Protect `main`: PR required, CI must pass. During crunch time a lead can self-approve their own folder. **Changes in `shared/contracts/` need a second person's ✅.**
6. Share secrets **by DM, never in the repo**. Each person keeps a local `.env`.

## Branches and Claude Code sessions
- **One branch per Claude session**, named `<owner>/<area>`, e.g. `adrian/shell`, `adrian/components`, `adrian/spotlight`, `michael/lesson`, `michael/checks`.
- **Use git worktrees** so several Claude sessions run side by side without stepping on each other:
  ```
  git worktree add ../tut-shell -b adrian/shell
  git worktree add ../tut-components -b adrian/components
  ```
  Open one Claude Code session per worktree folder.
- **Each session only edits its own folder** (say so in its kickoff prompt). That alone prevents about 95% of merge conflicts.
- Commit small and often with clear messages. **Open a PR to `main` at least at every checkpoint**; merge only when the app still starts.
- **Rebase onto `main` after every sync** (`git pull --rebase origin main`) so branches don't drift.

## Changing the contract (the only thing that can break the other person)
1. Open a small PR touching only `shared/contracts/`, titled `contract: …`.
2. Ping the group chat. The other side approves, then **both update their side** (the frontend mock scenario + the server emitter).
3. Never rename or remove a field after 9 PM. Only add new ones.

## CI (`.github/workflows/ci.yml`)
- On every PR: `npm ci && npm run typecheck && npm run lint` in `app/`; `ruff` + a quick import check in `server/`.
- On push to `main`: a **`macos-latest` job builds the unsigned Mac app** (`electron-builder --mac --dir`) and uploads it as an artifact. Michael downloads it on the Mac at each sync to check the real look, even when Adrian's PR came from Windows.

## Daily rhythm
| Time | What happens |
|---|---|
| 12:30–1:30 PM | Repo + skeleton + contracts + keys. Everyone's Claude sessions start. |
| 2:30, 4:30 PM | 5-minute sync: done / contract changes / blockers + a 20s screen recording. Merge what's green. |
| **6:00 PM** | **Checkpoint 1:** merge everything; flip `ENGINE_URL` from mock to real; tag `cp1`. |
| **9:00 PM** | **Checkpoint 2:** the hero flow works on the Mac; tag `cp2`. Room closes. |
| Overnight | Polish branches; merge at 1 AM and 7 AM. |
| **9:00 AM** | **Freeze:** only bug fixes. Tag `demo`. The demo runs from the `demo` tag on Michael's Mac. |
| 10–11 AM | Backup video, Devpost, repo public, README with screenshots. |

## Who reviews what
- **Adrian's UI PRs:** Michael checks them on the Mac build and replies with a screenshot or recording + specific notes ("pill 2px too low", "morph too slow").
- **Engine PRs:** Adrian checks them by running the app against the real server.
- **Claude sessions** can open PRs themselves (`gh pr create`); a human merges.

## Rules that save the demo
- `main` must **always** start the app and the engine.
- Demo mode (`DEMO=1`) replays the final recorded run as a safety net if Wi-Fi or an API dies.
- No new features after 9 AM. No exceptions.
