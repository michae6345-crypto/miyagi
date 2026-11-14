# Hero demo rehearsal: measured timings, offline result, stage checklist

Rehearsed on 2026-11-14 on the stage Mac with `scripts/rehearse.py`, on `integration/live` **3123eb6**. That base
includes E4's fixes for the bugs this rehearsal found and S8's preflight card. An earlier batch on 9f89e04 gave the
same picture; see the end of §1. Re-checked on **bb8feb2** (the head when this PR was opened): one live take and the
offline take both PASS (58.5 s / 47.7 s). The one change: Build → `lesson.ready` now takes **1.5 s** instead of
0.02 s (the "ready hold" in 31c5f4b). On **292561d** (with E5's 96d12b8), zero-cost takes only (cost freeze): DEMO=1
offline PASS (53.4 s); LIVE offline with `COACH_OFFLINE_FALLBACK=1` gets no card. E5's PR #1 (8301c0c) fixes that:
verified offline on a throwaway merge, card 0.9 s after amber (§2). On **9f7066a** (skip_step / check_step), zero-cost
again: DEMO=1 offline PASS (44.3 s, card 0.7 s after amber, green 12.2 s); LIVE offline still no card (PR #1 not merged).

The script plays the app over the WebSocket: it reports the playhead like the player does, and it runs the learner's
code with `tut run`. It starts its own engine on **:8797** (never :8787) on a **temp copy** of `demo/pinn-lab`, spools
Tiger data into the take's own folder, and turns off the engine's real-keyboard reader (see "Typing" below).

```bash
.venv/bin/python scripts/rehearse.py --runs 3 --fix ladder --env ORCH_LADDER_MIN_S=0   # the 3 live takes
```
```bash
.venv/bin/python scripts/rehearse.py --offline --demo --fix manual                     # the offline take
```

**Cost:** one live take makes about 11 Anthropic calls (2 coach warm-up, 2 Sonnet diagrams, 1 Opus diagnosis, the rest
preflight), 3 Bright Data requests and no Gemini calls (the lesson is cached). `--offline` takes cost nothing: the keys are
bogus and every request dies at the dead proxy. During the cost freeze, run only `--offline` takes (with or without
`--demo`).

**What a take does** (the order of `docs/devpost/DEMO.md`): pre-fill sections 1–7 with `lr = 0.3` → `learn` the stage
query → pick the Toscano row → preflight card → Build → `lesson.ready` → `POST /debug/goto/7` (s8, "Train the network and
log loss") → `tut run python pinn_diffusion.py` → amber + coach card → ⌘S → "Do it for me" card → preview → Confirm →
`tut run` again → green → the video resumes.

**What it does not cover:** the app UI (launcher, pill, cards), the screen reader / OCR path (`ORCH_SCREEN=0`: the
step is graded on files plus `tut run` metrics), VS Code opening, the setup card, real YouTube playback, voice and ⌥D
diagrams. Run one full pass with the app before going on stage.

## 1. Live (network up): 3 takes on 3123eb6, all PASS

Seconds. The script picks the instant the rows land; a fourth take that waited 8 s first (stage narration) is in the
last column.

| Beat | Take 1 | Take 2 | Take 3 | 8 s pause | Notes |
|---|---|---|---|---|---|
| Search: rows | 0.00 | 0.00 | 0.00 | 0.00 | finder cache hit, 34 rows, **Toscano #1** every time |
| Pick → preflight card | 4.92 | 3.13 | 2.88 | **0.00** | S8 prefetches after the search; with narration first it's instant |
| Build → `lesson.ready` | 0.00 | 0.00 | 0.01 | 0.01 | `lesson cache hit aebc6b8fba02dac5.json`; workdir = the hero folder |
| `/debug/goto/7` → s8 starts | 0.01 | 0.01 | 0.00 | 0.00 | the lesson always starts at **s1** |
| Run 1 (`lr = 0.3`, 2500 iters) | 20.7 | 19.7 | 20.2 | 18.7 | loss flat at ~17.4; ~17 s when the Mac is idle |
| Amber (from run start) | 18.0 | 17.0 | 17.4 | 16.2 | decided at step 2000, 2.5–2.8 s **before** the run ends |
| Coach card (from amber) | 5.2 | 6.9 | 4.8 | 5.8 | lands 1.9–4.2 s after the run ends |
| ⌘S → "Do it for me" card | 0.66 | 0.79 | 0.78 | 0.76 | needs `ORCH_LADDER_MIN_S=0` (default 20 s, see §3) |
| Do it for me → preview | 0.00 | 0.00 | 0.00 | 0.00 | correct one-line diff `lr = 0.3` → `lr = 1e-3` |
| Confirm → "Fix applied" | 0.00 | 0.00 | 0.00 | 0.00 | file written, backup kept |
| Run 2 (`lr = 1e-3`) → green | 13.0 | 12.3 | 11.9 | 12.9 | loss < 1e-2 at step 1000 in every take |
| Green → video resumes | 0.40 | 0.40 | 0.40 | 0.40 | `video.seek {t: 1416, play: true}` (s9) |
| **Machine time, whole take** | **51.1** | **49.1** | **46.4** | 53.3 | stage time = this + talking |

Card texts (live Opus, all correct), e.g. take 1: "Learning rate 0.3 is too high: With lr = 0.3, Adam's steps overshoot
and saturate the tanh units, so loss stalls near 17.35 with periodic spikes. Set lr to 1e-3, as the tutorial does."

**Where the coach's time goes** (engine log, all 4 takes): run fails → ~1 s to the next tick → **two Bright Data
requests, 1.2–3.1 s** → **Opus 3.1–3.4 s** (prompt cache hit, 9658 tokens) → card. Every take logged `web=0`: none of
the Bright Data results reached the card. DEMO.md's "about 3 s" is the Opus part only. E5 made the coach skip web
lookups when there's no error text (96d12b8), but in the engine that didn't take effect. The engine passes the run's
output tail as `error_text` even for a clean run, so the coach still searched, now on `::metric::` lines. E5's PR #1
(8301c0c) treats a tail as an error only when it has an error signature (Traceback, `XxxError:`, …). On a throwaway merge,
an offline take started **no** Bright Data lookup (0 log lines, versus 2 per diagnosis before), so the card should be
Opus time only (~3.4 s). **Not merged yet, and not re-measured live** (cost freeze).

**Typing delays the card.** The engine reads the Mac's real keyboard idle time. It never speaks within 2 s of a
keystroke, and keys in the last 3 s block the idle trigger. In takes where someone was typing on this Mac, the card
came **17–18 s after the run ended** instead of 2–4 s. On stage: **hands off the keyboard after ↵.**

**The preflight card contradicts the stage for the hero:** "Building takes ~66 s" (it takes 0.02 s, cached) and "No
code editor needed … Needs: google_colab (web)", then VS Code opens. S8 fixed both in PR #42 ("Built before: ready
instantly (9 steps)", editor needed); not merged or re-checked here yet. Until then, don't read those lines out.

**Earlier batch on 9f89e04** (no preflight yet): 3/3 PASS, takes of 44–50 s; card 5.1–6.9 s after amber; green
11.6–15.9 s. Before that, 4 exploratory takes using the real keyboard reader: 4/4 PASS.

## 2. Offline (external APIs dead)

`--offline` breaks everything external: bogus API keys, `HTTPS_PROXY=http://127.0.0.1:9` for every HTTP client
(localhost exempt), and a Tiger DSN on a black-holed address. Today Tiger was unreachable even on the normal network:
every take spooled.

| Beat | LIVE engine, network dead | DEMO=1 via `scripts/miyagi-offline.sh` (this PR) |
|---|---|---|
| Cached search | ✅ 0.0 s | ✅ 2.1 s (DEMO staggers rows) |
| Preflight card | ✅ partial card in 0.19 s ("I couldn't check this video in time; you can still build it") | — (DEMO builds straight away) |
| Cached lesson | ✅ cache hit | ✅ the hero (`ORCH_LESSON`) |
| Checks (files + `tut run` metrics) | ✅ amber at step 2000 | ✅ amber at step 2000 |
| `tut run` → engine | ✅ | ✅ |
| Tiger | ✅ spooled (52 metrics/run + engine events) | ✅ spooled |
| Coach card | ❌ **no card**. One "Coach unavailable" toast, then silent retries at +15 s and +31 s (since E4's fix; before it, 43 errors in 88 s) | ✅ E5's playbook card "Learning rate is too high … for Adam, 1e-3 is a safe start" (Smith 2017), 0.6 s after amber |
| Do it for me | ❌ | ❌ no diff offline: **fix it by hand** (`lr = 1e-3`, ⌘S) |
| Run 2 → green → video event | not reached | ✅ 14.8 s / 0.4 s (48.3 s whole take) |
| The video itself | needs YouTube | needs YouTube: narrate over the card |

So with no network: the cached search, cached lesson, checks, `tut run` and the Tiger spool all work. A live coach
can't, so on 292561d **if the network dies mid-demo, the LIVE engine shows no card**: switch to
`scripts/miyagi-offline.sh`.

**`COACH_OFFLINE_FALLBACK=1` (E5): fixed on PR #1, not merged yet.** On 292561d (96d12b8) the flag gave no card. The
`lr = 0.3` loss sat **flat** at 17.32 (flags `{plateau}`), so `lr_too_high` scored 0.3 and the best match was the
convection `pinn_convection_large_beta` at 0.5, under the 0.6 bar. PR #1 (8301c0c) makes `lr_too_high` count a plateau
when the code's lr is high, and makes the β entry require a β in the code. Re-checked on a throwaway merge of PR #1 into
292561d (zero cost, LIVE engine, network dead, flag on, a flat take at 17.46): the coach logged "offline playbook card
lr_too_high (conf 0.7)" and showed **"Learning rate is too high" 0.9 s after amber**. Do it for me: no patch (the playbook
card has no diff), so fix by hand; the run then went green in 15.0 s. **Once PR #1 merges**, run the live engine with the
flag (§3 step 5), and a network death mid-demo still gets the card without switching engines. A *hanging* network (not
refused) was not tested: the fallback waits for the connection error.

Under DEMO=1 the engine now calls E5's coach (E4's fix), which would itself fall back to the playbook, but only after
Opus fails. With a dead proxy that's instant; on a half-dead network it means waiting out the timeouts (6 s web lookup,
40 s Opus; from the code, not measured). `demo/cache/coach/s8.json` is read first, so the offline card is instant and
always the same. It is exactly `coach.public(playbook_card(s8, lr_too_high))`, E5's text.

Before E4's fix (9f89e04), DEMO=1 showed the convection stub "Loss plateaued at large β … β curriculum" and loaded the
newest cached lesson. Both are fixed in 3123eb6, and `miyagi-offline.sh` pins `ORCH_LESSON` anyway.

## 3. Pre-demo checklist (T-15 min)

1. **Network:** phone hotspot. The venue Wi-Fi blocks Tiger (spooling all day today; nothing is lost).
2. **Permissions:** System Settings › Privacy & Security › **Screen & System Audio Recording** and **Accessibility** ON
   for the terminal app that runs the engine. Quit and reopen that terminal.
3. **The learner's Python, inside the lesson folder.** On this Mac `python` doesn't exist and `python3` has no torch.
   A `.venv` in `demo/pinn-lab` is git-ignored and skipped by the watcher and E2's cache key. S2's setup check looks
   there first: with it, the setup card says "You have everything this lesson needs" (measured). Use **`pyDOE==0.3.8`**
   (the lesson's version): today's pyDOE installs as `pydoe`, and S2 then reports pyDOE missing. S2's PR #41 fixes that
   (and treats slow first imports as "still checking"); after it merges the pin is optional, but it still makes the card
   faster.
   ```bash
   uv venv --python 3.12 demo/pinn-lab/.venv && uv pip install --python demo/pinn-lab/.venv/bin/python torch numpy scipy matplotlib scikit-learn "pyDOE==0.3.8" -e cli
   ```
   Warm it once, because cold first imports blow the setup check's 8 s timeout:
   ```bash
   demo/pinn-lab/.venv/bin/python -c "import torch, matplotlib, sklearn, scipy; from pyDOE import lhs"
   ```
   In the VS Code terminal: `source .venv/bin/activate` (inside `demo/pinn-lab`).
4. **Pre-fill the code** (local edit, don't commit). This writes sections 1–7 like the video, with `lr = 0.3` and
   `steps = 2500` (so the run takes ~17–21 s):
   ```bash
   .venv/bin/python scripts/rehearse.py --prefill demo/pinn-lab
   ```
   Don't add visible files to `demo/pinn-lab` (no `results.png`, no notebook). E2's cache key includes the folder's file
   names, so a miss means a live 30–80 s Gemini build, and a failure if the network is down.
5. **Engine** (live, full flow), with the hint ladder fast enough for "Do it for me" on stage:
   ```bash
   ORCH_LADDER_MIN_S=0 COACH_OFFLINE_FALLBACK=1 scripts/miyagi-engine.sh
   ```
   `COACH_OFFLINE_FALLBACK=1` matters once E5's PR #1 is merged (§2); before that it's harmless.
6. **App:** `cd app && npm run dev`.
7. **Cache warm / dry run:** the search cache for the stage query is in `demo/cache/search/` (created Nov 14 13:44;
   7-day TTL, so good until Nov 21). Do one full pass with the app and check the engine log for `cache hit for 'learn
   physics…'` and `lesson cache hit aebc6b8fba02dac5.json`. Then restore the pre-fill (`--prefill` again: the dry run's
   fix changed `lr`). A UI-free check that never touches the real folder takes about 50 s:
   ```bash
   .venv/bin/python scripts/rehearse.py --fix ladder --env ORCH_LADDER_MIN_S=0 --pick-after 8
   ```
8. **Second terminal tab** with the step jump typed in, not run (the lesson starts at s1):
   ```bash
   curl -X POST localhost:8787/debug/goto/7
   ```
9. **Third tab** with the fallback typed in, not run (stop the live engine first; both use :8787):
   ```bash
   scripts/miyagi-offline.sh
   ```
10. Focus mode on, VS Code font up, terminal visible.

## 4. Stage beats with measured timings (proposed for DEMO.md)

| Time | Do | Measured |
|---|---|---|
| 0:10 | ⌥Space, type the stage query, ↵ | rows at once (cached; the whole list in < 0.1 s) |
| 0:25 | Pick Toscano (after talking over the rows) | preflight card instant (prefetched); 3–5 s if picked right away |
| 0:30 | **Build** | `lesson.ready` in 1.5 s (cached; 0.02 s before the ready hold) |
| 0:35 | Run the `curl …/goto/7` tab | s8 starts at once; clip seeks to 20:02 |
| 0:50 | `tut run python pinn_diffusion.py` (or `python …`; the screen path wasn't rehearsed) | run ~19–21 s, loss flat at ~17.4 |
| ~1:07 | Amber | 16–18 s after ↵ (at step 2000) |
| ~1:13 | Coach card | 5–7 s after amber; **hands off the keyboard** |
| 1:15 | ⌘S → "Do it for me" → Confirm | card < 1 s, preview and apply instant (needs `ORCH_LADDER_MIN_S=0`) |
| 1:20 | Run again | green 12–13 s later |
| ~1:33 | Green, video resumes | resume 0.4 s after green |

## 5. If X fails, say this

| Beat | If it fails | Say | Do |
|---|---|---|---|
| ⌥Space | Launcher doesn't open | "Let me wake it up." | Restart the app (`npm run dev`); the engine keeps the lesson. |
| Search | Slow, empty or an error | "Live search fights the venue Wi-Fi; here's the lesson I built from it earlier." | Stop the engine, `scripts/miyagi-demo.sh` (autostarts the hero), skip to the step jump. |
| Preflight | Card slow or "couldn't check this video" | "It checks the video before spending a minute building it." | Press Build anyway: the lesson is cached. |
| Build | "Gemini is watching the video · 0:1x" (a cache miss) | "Cold, Gemini watches all 24 minutes; that's ~30 seconds, so let me use the one it built this morning." | Same as Search. A miss usually means files were added to `demo/pinn-lab`. |
| Setup card | Lists missing packages | "It checks my machine has what the lesson needs." | Skip it; checklist step 3 prevents it. |
| Step jump | Still on s1 | "Skipping ahead to training." | Run the `curl …/goto/7` tab again. |
| Run 1 | `command not found: python` / `ModuleNotFoundError` | "Wrong Python, one second." | `source .venv/bin/activate` in `demo/pinn-lab`, run again. |
| Amber | Nothing amber yet | "It only fails a check once it's decided: by step 2000 or when the run ends. It never nags mid-run." | Wait ~3 s for the end of the run. |
| Coach card | No card ~10 s after amber | "It never talks while I'm typing." | Take your hands off the keyboard; then ⌥H for a hint card. |
| Coach card | Network died ("Coach unavailable" toast, or a card marked offline) | "We just lost the network. Same checks, same lesson, offline." | With E5's PR #1 merged and `COACH_OFFLINE_FALLBACK=1`: the playbook card still comes, so fix by hand and carry on. Otherwise stop the engine and run the `miyagi-offline.sh` tab. |
| Do it for me | No button on the card | "First it explains why; the fix comes if I'm still stuck." | ⌘S once, or type `lr = 1e-3` and ⌘S yourself. |
| Preview | "Save … first" / "The file changed" | "It never overwrites unsaved work." | ⌘S, then Do it for me again. |
| Run 2 | Not green 20 s after ↵ | "Under 1e-2 by step ~1000 in every rehearsal; this one is slow." | Check `lr = 1e-3` in the file; last resort `curl -X POST localhost:8787/debug/pass`. |
| Video | Doesn't play (offline / YouTube blocked) | "The video would pick up right here; the lesson moved to step 9." | Narrate over the s9 card. |

## 6. Bugs found, and where they went

| Owner | Bug | Status |
|---|---|---|
| E4 | DEMO=1 coach used the convection β stub; DEMO=1 loaded the newest cached lesson; the offline coach error repeated every tick (43 in 88 s) | fixed in 3123eb6, re-verified here |
| E5 | No playbook fallback on a connection error in live mode; the web lookup adds 1.2–3.9 s before Opus and is never used (`web=0`); then the flag missed flat-loss takes and passing-run tails counted as errors | fixed on PR #1 (8301c0c), verified offline on a throwaway merge (card 0.9 s after amber, 0 web lookups); not merged; live timing not re-measured (cost freeze) |
| E4 | Passes the run's output tail as `error_text` even when the run exited 0 | handled on E5's side (PR #1 ignores tails with no error signature); nothing needed from E4 |
| S8 | Hero preflight card: "Building takes ~66 s" (cached: 0.02 s), "No code editor needed / google_colab" (it's a VS Code lesson) | fixed in PR #42 (not merged yet) |
| S2 | Setup check reports pyDOE missing when the current pyDOE (module `pydoe`) is installed; cold imports time out at 8 s | fixed in PR #41 (not merged yet) |
| S6 | DEMO.md timings and fixes: the first card has no Do it for me; the step jump; `python` missing on this Mac; the offline fallback | sent |
