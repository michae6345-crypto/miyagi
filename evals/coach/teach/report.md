# "Just teach me" (lesson mode): coach copy QA

**Run:** `integration/live` at `ff8fdd1`. Zero cost: no Claude, Gemini or Bright Data calls (cost freeze). The coach runs with no API key and `DEMO=1`, so the cards below are the coach's own offline output. The orchestrator copy is deterministic and identical live.

**Lessons:** the three cached text lessons from `demo/cache/lessons/text-*.json` (snapshots in [`lessons/`](lessons/)):

| | Lesson | Goal | Folder |
|---|---|---|---|
| A | "Build a Python Calculator" | python calculator | `python-calculator-e430dc` |
| B | "Build a Python Calculator" | build a simple calculator in python | `_new` |
| C | "Build a Python Calculator" | i wanna build a calc in python in vs cods | `i-wanna-build-a-calc-…` |

## What was run

Every run uses the real `LessonSession` with real checks and the real coach module, and goes through steps 1–3 in six beginner states:
- **empty:** the starter file, no code.
- **unsaved:** the right code typed, VS Code shows `● calculator.py`, the disk still has the old file.
- **wrong_folder:** the right code typed into `Desktop/calculator.py`; window title `calculator.py — Desktop`.
- **typo:** `def(a, b):`, or `prnt(` where the step has no `def`, saved and run. The terminal shows the real `SyntaxError` / `NameError`.
- **terminal_closed:** the right code saved, VS Code's terminal panel closed.
- **right:** the right code saved and run, with the real output in the panel.

Each screen is full-screen VS Code, drawn like E6's fixtures (same geometry), then OCR'd by the engine's `observe_image`. The learner types, saves (or not), goes idle, presses **Hint** and **Show me**, then waits out the stuck timer.

Every card is graded against six rules:
- **≤ 12 words**
- **names `calculator.py`**
- **names VS Code**
- **never "Cursor"**
- **no check label glued into a template**
- **one action**

Behaviour is graded too. For example, a step must not pass on unsaved code or on code in another folder.

Harness: [`run_teach.py`](run_teach.py), [`render.py`](render.py), [`summarize.py`](summarize.py). Every event: [`results/teach.json`](results/teach.json). Full per-run table and every failing text: [`results/teach.md`](results/teach.md).

## PASS/FAIL (cards + behaviour; step action lines and spotlight captions are listed separately)

| state | step 1 (A / B / C) | step 2 (A / B / C) | step 3 (A / B / C) |
|---|---|---|---|
| empty | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| unsaved | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| wrong_folder | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| typo | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| terminal_closed | FAIL / PASS / PASS | FAIL / FAIL / FAIL | PASS / FAIL / FAIL |
| right | FAIL / PASS / PASS | PASS / FAIL / FAIL | PASS / FAIL / FAIL |

**7 of 54 pass, and only where the step rightly passed without showing any card.**

By rule, over every card shown:
- **"Cursor":** never appears ✓.
- **≤ 12 words:** most cards fail.
- **Names VS Code:** almost no card does. Only lesson C's own text says "VS Code terminal".
- **One action:** "…, then add …" and "Skip it, or ask for a hint." each carry two.
- **Check label glued into a template:** the hint ladder's question does this.

## Failures with the exact text

### E5 (coach)

1. **The not-started card is the step's raw instructions.** Seen as `Start: <title>` (auto) and `Start · <title>` (Hint). Up to 45 words, two actions, no VS Code.
   - "In calculator.py, below the comment, write def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom." (22 words, 2 actions)
   - "Replace the print line with four functions: add(a, b), subtract(a, b), multiply(a, b) and divide(a, b), each returning the result. Make divide return "Error: divide by zero" when b == 0, then add print(add(2, 3)) and print(divide(8, 0)) at the bottom to test." (45 words, 3 actions, no file)
   - "In the terminal, run: python3 calculator.py. You should see Calculator ready printed." (no VS Code)
   - **Ask:** `start_instruction()` should return ONE action of ≤ 12 words that names the file and VS Code, e.g. "In VS Code, type `def add(a, b):` in calculator.py." or "Run `python3 calculator.py` in the VS Code terminal." Build it from `step.code`'s first line and `run_command`, not from `instructions`.
2. **The hint ladder's level-0 question glues a truncated check label in.**
   - "Does your output show “add function is written in the” yet? If not, what step produces it?"
   - Also "…“The add function is still in”…", "…“subtract function is typed in the”…", "…“divide raises ValueError on zero”…".
   - The lesson's labels are cut mid-phrase (E2), but the template quotes any label.
   - **Ask:** never quote a check label. Ask about the code ("Which line of calculator.py defines add?") or fall through to level 1.
3. **The same text twice.** The auto `Start: X` card and the Hint card `Start · X` have the identical body, so pressing Hint teaches nothing new.
   - **Ask:** Hint after a not-started card goes to the next rung: the exact line plus Show me.
4. **A visible error reads as "not started" (offline route).** With `SyntaxError: invalid syntax` under `def(a, b):` in VS Code's terminal, the card is "Start: Add the add function". The route was template, after the no-key fallback.
   - **Ask:** when a self-explaining error is on screen (SyntaxError, NameError…), the offline card names it: "`def` needs a name: line 4 of calculator.py." The live Opus route is untested (freeze).
5. **"Where to work" (Show me, `pointing`) says "Create calculator.py in the lesson folder"** when lesson mode has already created it (empty).
   - **Ask:** "Open calculator.py in VS Code" when the file exists.
6. **The live Opus card contract is 30 words.** Prompt: "at most 30 words"; `clamp_body(soft=42)`. Of the 18 Opus cards recorded in this eval's earlier runs (React/pandas/git), 16 have bodies over 12 words (10–38), and 0 name VS Code.
   - **Ask:** for lesson mode, a ≤ 12-word action line on the card (file + VS Code), with the why behind Explain.

### E4 (orchestrator)

7. **Unsaved code passes the step.** A s3, B s1 and C s1 turn green while the window title is `● calculator.py — …`. The screen checks see the typed code; the file on disk doesn't have it. Lesson B then finds the file empty at step 2 and says "calculator.py is still empty / Type this step's code into calculator.py first; then we'll run it." But they did type it; they didn't save.
   - **Ask:** `dirty_files(last_obs)` contains the step's file → hold the pass and show "Save calculator.py in VS Code (⌘S)." Also use that text instead of "still empty" when the file is dirty.
8. **Code in another folder passes.** A s2, B s1 and C s1 turn green with the code in `Desktop/calculator.py` (title `calculator.py — Desktop`).
   - **Ask:** when the VS Code window's folder (after the "—") isn't the lesson folder, hold the pass and show "This is Desktop/calculator.py. Open the lesson's calculator.py in VS Code."
9. **Run steps never pass in VS Code's terminal (B, C).** With the right code run and `Calculator ready` / `Simple Calculator` printed in VS Code's terminal panel, the check stays failing with "open Terminal so I can check: Script output appears in the terminal". The checks ask for `app: Terminal`, but the panel's text belongs to the `Code` window. The lesson itself says "In the VS Code terminal…".
   - **Ask:** an `app: Terminal` check also reads VS Code's integrated terminal (E6's `region("terminal")` already finds it). Lesson A's run step does the opposite: it passes with the terminal closed, because its only screen check is about the editor.
10. **Run steps get a typing action line.**
    - A s2: "In calculator.py, type print(add(2, 3))". E2 put `code` on the run step, so `_run_command` returns "".
    - B s2 and C s2: "In (terminal), type python3 calculator.py". E2's target file is `(terminal)`.
    - **Ask:** if `run_command` is set and the title or instructions say run, it's a run step: "Run `python3 calculator.py` in the VS Code terminal." Treat a file of `(terminal)` as no file.
11. **No action line names VS Code** ("In calculator.py, type def add(a, b): …").
    - **Ask:** "In VS Code, type `def add(a, b):` in calculator.py."
12. **"Stuck on this step?" / "Skip it, or ask for a hint."** has two actions and no file. It shows on every open step after 100 s.
    - **Ask:** one action, e.g. "Ask for a hint, or skip from the menu."; or keep Skip as a button only: "Need a hand? Press Hint."

### E2 / E3 (lesson data, checks): also behind several of the above

- Check labels are cut mid-phrase: "add function is written in the", "The print line is visible in", "calculator.py has the print call for".
- Spotlight captions are copied from the lesson with two actions, up to 18 words: "Type this in the VS Code terminal (use python3 on Mac/Linux if python isn't found), then press Enter".
- OCR reads `def add(a, b):` as `def add(a, b) :` on these frames, so `def\s+add\(a,\s*b\):` fails on the right code. A s1 and C s3 never pass with the right code. Seen on rendered frames; worth checking live. E3 could drop spaces before `):,]` before matching.

## Limits

- **Model-written cards are untested** under the cost freeze. They are 30-word Opus cards live (see 6).
- **Screens are rendered,** not captured from a real Mac (E6's fixtures are rendered the same way).
- **The learner's timing is scripted:** type → save → idle → Hint → Show me → stuck.

## Re-run (no API calls)

```bash
cp -R evals/coach/teach <checkout>/evals/coach/   # plus evals/coach/__init__.py
cd <checkout> && env ANTHROPIC_API_KEY= TUT_ENV=/dev/null DEMO=1 PYTHONPATH=. python -m evals.coach.teach.run_teach
python -m evals.coach.teach.summarize > evals/coach/teach/results/teach.md
```
