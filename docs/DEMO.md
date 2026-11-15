# miyagi at judging: run of show

For Michael, on your Mac, judging at about 12:30 PM. The talk is about 2.5 minutes. Sections 1 to 3 are for the
day. Section 4 explains what happens underneath. Keep it to yourself.

## 1. Before you go on (10 minutes)

- [ ] **Builds.** Engine from `adrian/stage-mode`, app from `adrian/stage-app`, or the branch they were merged into.
      To check: open the launcher (⌥Space), type anything, and a third chip, **Demo**, appears next to Watch a video
      and Just teach me.
- [ ] **Engine.** Start one, from the repo root. Only one process can hold :8787, so quit any other engine or
      `npm run mock` first.

      | | Command | Use it when |
      |---|---|---|
      | LIVE | `scripts/miyagi-engine.sh`, with `ANTHROPIC_API_KEY` in `.env` or in the app's Settings | Wi-Fi works. Typed questions get real answers. Watch a video and Just teach me work for any topic. |
      | Offline | `scripts/miyagi-nn-demo.sh` | Wi-Fi is bad. Nothing goes over the network. Questions are answered from the lesson's own cards. |

      The neural-net lesson looks and behaves the same on both.
- [ ] **App.** `cd app && npm run dev`. The pill sits under the notch.
- [ ] **VS Code companion.** `curl -s 127.0.0.1:8791/health` should answer. If it doesn't, run
      `rm -rf ~/.vscode/extensions/miyagi.companion-0.0.* && cp -R vscode-ext ~/.vscode/extensions/miyagi.companion-0.0.3`,
      then ⌘⇧P → Developer: Reload Window.
- [ ] **Screen Recording.** System Settings › Privacy & Security › Screen & System Audio Recording: turn it on for
      Terminal (or whatever app runs the engine). The engine script warns at startup when it's off.
- [ ] **Wi-Fi and the screen.** LIVE: keep Wi-Fi on and try one typed question. Offline engine: turn Wi-Fi off. In
      both cases: Do Not Disturb on, other apps closed, VS Code zoomed in once or twice (⌘=).
- [ ] **Free the keys.** Quit Rectangle, Magnet or any other window manager, because they use ⌃⌥⌘← and ⌃⌥⌘→.
- [ ] **Dry run.** Do one full take (section 2). Along the way, try each presenter key once: ⌃⌥⌘→ passes the
      step, ⌃⌥⌘← goes back a step, ⌃⌥⌘R starts again at step 1 with a clean `nn.py`. Nobody has tried these keys in
      Electron yet, so don't skip this check.
- [ ] **Reset for the real take.** Press ⌃⌥⌘R (`nn.py` goes back to just the four section comments), then end the
      lesson (End in the bar, tapped twice). The launcher then opens fresh on stage.

## 2. The run (about 2.5 minutes)

| # | You do | On screen | You say |
|---|---|---|---|
| 0 | Nothing yet. VS Code is in front. | | "Most coding tutorials leave you copying along and hoping it works. miyagi turns 'teach me X' into a lesson in your own editor. It watches what you write and checks each step." |
| 1 | ⌥Space, type `teach me to build a neural network from scratch`, Tab to the third chip (or click it), Enter. | The launcher folds into the pill, then the **Before you start** sheet: how it works (input → hidden layer 1 → hidden layer 2 → output → backprop → gradient step) and what to know first (NumPy arrays, matrix multiply, derivatives). | "I'll ask it to teach me a neural network from scratch, in plain NumPy. Before step one, it shows me the plan and what I should know first." |
| 2 | Click **Start the lesson**. | VS Code opens `nn.py`. The drawer on the right shows step 1 of 6, its code, and the network, marked as a preview (no epoch or loss until a run). | "Six steps. It opened the file for me." |
| 3 | Step 1, Build the network: **Copy** in the drawer, paste under `# The network`. Change the three weight lines to `W1 = np.zeros((1, 4))`, `W2 = np.zeros((4, 4))` and `W3 = np.zeros((4, 1))`. ⌘S. | The panel shows a preview of the network you're building, firing. The rows go green one by one, then step 2 starts. | "This is what we're building: x goes in, two layers of four neurons, y comes out. It will learn to draw a sine curve. I'll take a shortcut and start the weights at zero. The shapes are right, so it passes." |
| 4 | Step 2, Backprop: Copy, paste under `# Backprop`, ⌘S. | The panel previews the error flowing back. Green, next step. | "Backprop. The error goes back along the same weights, and every weight gets its share of the blame." |
| 5 | Step 3, Write the training loop: Copy, paste under `# Training`, ⌘S. | The panel previews the network the loop starts from, standing still: nothing trains before the run. Green, next step. | "The training loop: forward, backward, then move every weight a little downhill, twenty thousand times." |
| 6 | Step 4, Train it: press **Run it for me** once and wait. The button is on the step's Run it card, which comes up next to the ▷ box. | The run card shows `loss 0.4900` on every line. The panel switches to your run and reads **loss stuck**: all eight hidden neurons identical and dark, loss 0.4900, a flat loss line. Then the **Not yet · Loss is stuck at 0.49** card takes the run card's place. | "Every check passed, but the loss never moved. All eight hidden neurons are the same neuron, so it answers zero for every x." |
| 7 | Press **Hint** on the card (or ⌃⌥H). | **Hint 1 of 2:** "Look at how W1, W2 and W3 start…" The box marks the W1 to W3 lines in `nn.py`; VS Code scrolls there if they were off screen. | "I'll ask for a hint, not the answer. Look at how the weights start. They're all zero, so every neuron outputs zero and gets the same update." |
| 8 | Change the three lines back to `np.random.randn(1, 4)`, `np.random.randn(4, 4)` and `np.random.randn(4, 1) * 0.1`. ⌘S. Press **Check my work** (in the bar or the drawer). The Run it for me button is gone at this point, which is expected. | After ⌘S the box moves back to VS Code's ▷. The loss goes from 0.8187 to 0.0009 by epoch 18000. The row goes green. The panel shows your run training, its weights moving as the loss falls from 0.8187, and the prediction climbing to its target 1.000. | "Random starts break the tie. Now it learns." |
| 9 | Step 5, Test it: Copy, paste under `# Test it`, ⌘S. | Green, next step. | "Last piece: print its answers and the weights it learned." |
| 10 | Step 6, See what it learned: press **Run it for me**. | "Ran nn.py · It ran without errors", with `[-1.0, 0.0, 1.0]` (its answers for x = -π/2, 0, π/2) and then W1 to b3. The drawer says **All 6 steps done**, then the completion panel reads **Neural networks · 8 skills mastered**. The panel shows the network answering x = π/2 (prediction about 1.0, target 1.000), drawn from the weights it printed. | "Minus one, zero, one. That's sine at minus pi over two, zero and pi over two. From nothing to a network that draws a sine wave, every step checked." |
| 11 | Close. | | "Type any topic and it builds the lesson the same way. It can also play a YouTube tutorial and pause it until your code catches up. That's miyagi." |

The launcher chip reads "Demo" and its button reads "Start demo". Don't read them aloud. Get past the launcher
quickly while you talk.

## 3. If something goes wrong

| Symptom | Fix |
|---|---|
| ⌘S and the rows don't go green | Press **Check my work**. If nothing happens, press ⌃⌥⌘→. A second ⌘S right after a pass never skips a step. |
| The paste landed in the wrong place, or the indentation is off | Keep going. The step still passes. |
| Train it learned on the first run (no "Not yet") | All three weight lines (W1, W2, W3) were random when you pressed Run it for me. Skip the stuck beat and say "Random starts, so it learns right away." If you forgot the zeros at step 1, change the lines at step 4, before the first Run it for me. |
| Short on time at step 4 | ⌃⌥⌘→ passes Train it on the run that learns, with no "Not yet". |
| No Run it for me button after "Not yet" | That's expected. **Check my work** runs it again, and the second run always learns. |
| You went one step too far | ⌃⌥⌘← goes back one step. |
| Anything else is off mid-lesson | ⌃⌥⌘R: step 1, clean `nn.py`. Click **Start the lesson** if the sheet comes back. Say "Let me take that from the top." |
| VS Code still shows the old code after ⌃⌥⌘R | The editor had unsaved edits. ⌘⇧P → File: Revert File. |
| The presenter keys do nothing | They work only in a lesson started from the Demo chip, on the real engine. Another app may be holding them (Rectangle, Magnet). From a terminal: `curl -X POST localhost:8787/stage/next` (or `back`, `restart`). On screen, Check my work and Run it for me do the same job. |
| VS Code didn't open `nn.py` | Open it yourself. LIVE: `~/miyagi/lessons/a-neural-net-from-scratch-*/nn.py`. Offline engine: `demo/nn-lab/nn.py`. |
| The wrong lesson started | Watch a video or Just teach me was lit instead of the third chip. ⌥Space, ⇥ New lesson, type the goal, Tab to the third chip, Enter. |
| A typed question takes a while, then answers about the step | Wi-Fi is bad on the LIVE engine: after about 7 s the step's own explanation answers instead. On bad Wi-Fi, run the offline engine; its answers are instant. |
| A judge asks for another topic | ⌥Space, ⇥ New lesson, type it, pick **Just teach me**, Enter. That builds a real lesson. It needs the LIVE engine and Wi-Fi, and it takes longer, so talk over the building pill. |
| The engine says `port 8787 is already in use` | Another engine or `npm run mock` is still running. The script prints its PID: `kill <pid>`, then start again. |
| The engine or Python is broken on the Mac (last resort) | Quit the engine. In `app/`, run `DEMO=1 SCENARIO=nndemo npm run dev`, or `npm run mock -- nndemo` in one terminal and `npm run dev` in another. Launcher → anything → third chip → Enter. You get the same lesson, cards, runs and network panel. It can't see saves, so press Check my work after each paste. Use Run it for me on steps 4 and 6, and Check my work again after "Not yet". There are no presenter keys, VS Code won't open by itself, and Video and Just teach me don't work. |

### No network at the venue (offline fallback)

Checked on Nov 15 on a private engine with the network blocked (sandbox, a proxy and a Tiger port that never answer,
no keys). The Demo chip run of show passed every row on the LIVE engine and on the offline one.

1. **Wi-Fi fully off is better than flaky.** With Wi-Fi off, every call fails at once and the lesson's own cards
   answer. With flaky Wi-Fi, a typed question waits up to 12 s (`MIYAGI_ASK_DEADLINE_S`) and then the step's own
   explanation answers.
2. **Engine.** Quit the LIVE engine (Ctrl-C in its terminal; :8787 must be free), then from the repo root run
   `scripts/miyagi-nn-demo.sh`. It puts a clean `demo/nn-lab/nn.py` in place and wipes `demo/.nn-state`, so every
   start is step 1. Hint, Explain and typed questions come from `demo/cache/cards`, with no wait. If you are already
   mid-take on the LIVE engine when Wi-Fi drops, keep going: the Demo needs no network.
3. **App.** `cd app && npm run dev`, then ⌥Space, type the goal, the **Demo** chip, Enter. Same run of show as section 2.
   VS Code opens `demo/nn-lab/nn.py`. NumPy is not needed (Demo runs are recorded).
4. **Between takes.** Press ⌃⌥⌘R (step 1, clean `nn.py`), or End and start the Demo again from the launcher. Both gave a
   fresh take on this engine.
5. **Tiger Data.** Nothing to do. Its port is blocked at the venue, so every event and loss value goes to
   `~/.miyagi/tiger-spool` at once and the lesson never waits. Don't delete that folder. Once you are back online the
   engine uploads it by itself (it retries every 30 s), or run
   `.venv/bin/python -m server.checks.tiger --flush-spool`. `/stats` reads "offline" until then.
6. **What doesn't work offline.** Watch a video, and Just teach me for any other topic. That one sits on "Setting up
   your project folder" for minutes. Say "that one needs the internet" and stay on the neural net. On the offline
   engine use only the Demo chip: its Just teach me keeps the old `demo/nn-lab/nn.py` and doesn't grade it the same
   way. On the LIVE engine with Wi-Fi off, Just teach me for the neural net works, but its setup card asks to install
   NumPy, which needs the network: press Skip. Its runs use `python3`, which needs NumPy.
7. **Last resort** (no Python engine at all): the app's mock, `DEMO=1 SCENARIO=nndemo npm run dev` in `app/` (see the
   table above).

## 4. For you, not for the judges

**How it works.** The Demo chip sends `learn` with `mode: "demo"`. Whatever was typed, the engine
(`server/orchestrator/stage.py`) loads the curated neural-net lesson (the same folder, cards, hints, Explain and
live network panel) and stages it. A typing step passes on cue: a save in the lesson folder (ignored in the step's
first 2.5 s), Check my work, or ⌃⌥⌘→. It doesn't matter what the file holds. The rows go green one by one, then the
step passes the normal way. A run step never runs anything. Run it for me, Check my work, Do it for me, or a
`python3 nn.py` typed in VS Code's terminal all show a recorded run of the lesson's own code
(`demo/cache/stage/nn-runs.json`, real NumPy output from `scripts/make_stage_runs.py`). Its loss lines feed the
live curve and the panel. There is one planned "Not yet". On Train it, the first run is the stuck one (loss 0.4900 on
every line) if `W1`, `W2` or `W3` in `nn.py` isn't started with something random. The engine reads the editor's text through the companion,
unsaved edits included, and falls back to the saved file. The card comes from `demo/cache/coach/nn4.json` and the
hints from `demo/cache/cards/nn4-stuck-hint*.json`. Any later run learns. A Demo lesson does no grading, screen
reading, setup card, idle nudges or coach calls, so NumPy doesn't need to be installed. Watch a video and Just
teach me are untouched and real.

**Watch out for:**

- Don't type `python3 nn.py` in VS Code's terminal. miyagi still shows the recorded run, but the terminal runs real
  Python, and without NumPy it prints an error on screen. Use Run it for me.
- A second press of Run it for me (or Check my work) while a run is going, or within a second after it, is ignored: one press, one run. ⌃⌥⌘→ during a run makes that run the one that learns.
- `curl -s localhost:8787/stage` shows whether a Demo lesson is running, which step it's on, and how many runs it
  has done. The app binds the presenter keys only when this says `on`, and lets them go when the lesson ends.
- With the offline engine, the folder (`demo/nn-lab`) is pinned, so starting again from the launcher keeps the old
  `nn.py`. ⌃⌥⌘R always puts the clean file back. The LIVE engine puts it back on every Demo start.

**Engine knobs.** Set them when you start the engine, for example
`MIYAGI_STAGE_STUCK=always scripts/miyagi-engine.sh`.

| Variable | Default | What it does |
|---|---|---|
| `MIYAGI_STAGE_STUCK` | `zeros` | `zeros`: the first Train it run is stuck only if W1, W2 or W3 isn't random. `always`: the first run is stuck whatever the file says. `never`: no stuck run. |
| `MIYAGI_STAGE` | off | `1`: every lesson is a Demo lesson (Just teach me, a video search, a pasted link). With this you can pick Just teach me so the button reads "Teach me" and the word Demo never shows, but real Video and Just teach me lessons are gone until you restart the engine without it. |
| `MIYAGI_STAGE_DWELL_S` | `2.5` | A save in a step's first N seconds doesn't count. |
| `MIYAGI_STAGE_GRADE_S` | `1.0` | Time spent "checking" before the first row goes green. |
| `MIYAGI_STAGE_ROW_S` | `0.35` | Time between rows going green. |
| `MIYAGI_STAGE_RUN_S` | `1.4` | How long Run it for me takes. |
| `MIYAGI_STAGE_STUCK_S` | `2.0` | How long the stuck run's output stays on screen before "Not yet". |
