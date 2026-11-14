# sandhacks-tutor (working name)

Turn any tutorial into an auto-graded lab. Ask what you want to learn → it finds the best tutorial → breaks it into steps → the video pauses at each step until **your own code / terminal / training run passes that step's check**.

- Plan & demo script: `docs/PLAN.md`
- Frontend spec (Adrian): `docs/FRONTEND-HANDOFF.md`
- How we work (branches, worktrees, syncs): `docs/WORKFLOW.md`
- Contracts (the boundary between app and engine): `shared/contracts/`
- Mockups: `docs/mockups/`

| Folder | Owner | What |
|---|---|---|
| `app/`, `vscode-ext/` | Adrian | Electron overlay (Apple-style), VS Code spotlight extension |
| `server/lesson`, `server/checks`, `server/coach`, `server/orchestrator`, `cli/` | Michael | Gemini lesson builder, check evaluator, coach, WebSocket engine, `tut run` wrapper |
| `server/finder`, `server/diagrams`, `demo/` | Teammate 3 | Tutorial search (Bright Data + Gemini), diagram data, the PINN demo |

Built at SanD Hacks 2026 (UCSD). Commits start Sat Nov 14, 10:30 AM or later.
