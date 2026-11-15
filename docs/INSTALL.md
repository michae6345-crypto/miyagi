# Install Miyagi

Miyagi has two parts, and you need both:

- **The Miyagi app**: the pill under your MacBook's notch, the ⌥Space launcher, the cards and the video player.
- **The engine**: a Python program on your Mac that finds the tutorial, builds the lesson, reads your screen and runs the
  coach. The app talks to it at `ws://localhost:8787`. When the engine isn't running, the pill says **Offline**.

One command installs both. You don't need git, Node or Python first. (How we plan to turn this into a single download:
[DISTRIBUTION.md](DISTRIBUTION.md).)

## What you need

- A Mac with **macOS 12 or newer**. The app build we publish is **Apple Silicon only** for now; on an Intel Mac, build
  the app from source (see [From source](#from-source-developers)).
- An **Anthropic API key** (https://console.anthropic.com). Every call Miyagi makes is billed to your own key.
- About 1 GB of disk space and an internet connection.
- Optional: **VS Code**. Miyagi offers to install it when a lesson needs it. A **Bright Data** key gives better search and
  lets the coach cite documentation.

## 1. Install

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/michae6345-crypto/sandhacks-tutor/integration/live/scripts/install.sh | bash
```

It takes 1–3 minutes and:

1. installs [uv](https://docs.astral.sh/uv/), a small Python manager, if you don't have it (into `~/miyagi/engine/bin`; it
   doesn't change your shell settings);
2. downloads the engine into `~/miyagi/engine/src` and sets up Python 3.12 with its packages in `~/miyagi/engine/venv`;
3. writes `~/miyagi/engine/bin/miyagi-engine`, the one command that starts the engine;
4. downloads **Miyagi.app** into `/Applications` (or `~/Applications`). It never replaces a different app with the same name;
5. asks before it adds the **Miyagi Companion** to VS Code, a small extension that lets Miyagi see your editor and terminal
   exactly. It only listens on your own Mac (127.0.0.1);
6. offers to start Miyagi.

It makes no paid API calls. To see every step without changing anything, add `-s -- --dry-run` after `bash`.

> **During the hackathon (Nov 14–15, 2026), two pieces aren't public yet:**
> - **The repo is private.** Ask Michael for access, run `gh auth login`, then run the command above (the installer uses
>   your GitHub login). Or clone the repo and run `scripts/install.sh` from the clone.
> - **The Mac app download isn't published yet.** The installer says so and installs the engine anyway. Get
>   `Miyagi-Mac.zip` from the team, then run `scripts/install.sh --app-zip ~/Downloads/Miyagi-Mac.zip` (from a clone),
>   or `curl … | bash -s -- --app-zip ~/Downloads/Miyagi-Mac.zip`.

## 2. First run

1. **Start the engine.** In Terminal:

   ```bash
   ~/miyagi/engine/bin/miyagi-engine
   ```

   Keep that window open; closing it stops Miyagi.
2. **Allow screen recording.** The first time, macOS asks to let **Terminal** record your screen. Miyagi needs this to
   check your work. Turn Terminal on in **System Settings › Privacy & Security › Screen & System Audio Recording**, quit
   Terminal (⌘Q), open it again and run the command again. If you skip this, Miyagi still grades steps from your saved
   files and from `tut run`, but checks that need to see the screen wait.
3. **Open Miyagi** from Applications. It has no Dock icon: look for the pill under the notch (top center).
4. **Add your key.** Settings opens by itself. Paste your Anthropic key and press Save; Test should show a white dot.
   - Leave **Gemini** empty. This build doesn't use it, even though the sheet may still mark it as needed.
   - **Bright Data** is optional. **Tiger** is optional (learning stats).
   - The keys are stored encrypted in your macOS Keychain, never in a file. If macOS asks whether Miyagi may use
     "Miyagi Safe Storage", choose **Always Allow**.
5. **Accessibility (optional).** If macOS asks to let Terminal control your computer, allow it in **Privacy & Security ›
   Accessibility**. Miyagi then reads the text on screen exactly and can place VS Code next to the video.
6. Press **⌥Space** and type what you want to learn, for example `learn physics informed machine learning with PINNs in PyTorch`.

### Every day after that

Start the engine in Terminal (`~/miyagi/engine/bin/miyagi-engine`), then open Miyagi. Quit Miyagi with ⌥Q and the engine
with Ctrl+C. (Once the app starts the engine itself, opening Miyagi will be enough.)

## Update

Run the install command again. It replaces the engine and the app (quit Miyagi first) and keeps your keys, your lessons
and the lessons already built.

## Uninstall

```bash
rm -rf ~/miyagi/engine /Applications/Miyagi.app
```

Then, if you want:

- Remove the VS Code extension: `code --uninstall-extension miyagi.companion`, or in VS Code under Extensions.
- Delete your keys: `rm ~/Library/Application\ Support/Miyagi/keys.bin`. In **Keychain Access**, also delete "Miyagi Safe Storage".
- Turn Terminal (or Miyagi) off under **System Settings › Privacy & Security › Screen & System Audio Recording** and **Accessibility**.
- Your lesson folders are in `~/miyagi/lessons` and the session history is in `~/miyagi/state`. They're yours: delete them
  or keep them.

## If you downloaded Miyagi-Mac.zip in a browser

The app isn't signed with an Apple Developer ID yet, so the first time you open it macOS says it can't verify it.

- **macOS 15 (Sequoia) and newer:** click **Done**, open **System Settings › Privacy & Security**, scroll down and click
  **Open Anyway**, then confirm.
- **macOS 14 and older:** right-click Miyagi.app, choose **Open**, then **Open**.

The install command avoids this: files that `curl` downloads aren't flagged, so the app opens normally.

## Troubleshooting

| What you see | What to do |
|---|---|
| The pill says **Offline** | The engine isn't running. Start `~/miyagi/engine/bin/miyagi-engine` in Terminal. |
| `port 8787 is already in use` | An engine is already running (another Terminal window, or `scripts/miyagi-engine.sh` from a clone). Use that one, or stop it. |
| Checks never pass, "can't see your screen" | Screen recording isn't allowed for the app that started the engine (Terminal). See step 2, and quit and reopen Terminal afterwards. |
| `Couldn't download michae6345-crypto/sandhacks-tutor` | The repo is still private: `gh auth login` with an account that has access, then run it again. |
| `This Miyagi build is for 'arm64'` | Intel Mac: build the app from source (below) and run the installer with `--no-app`. |
| `the engine's packages didn't import` | Run the installer again. If it still fails, delete `~/miyagi/engine/venv` and run it again. |
| Miyagi asks for a key again | Open Settings (press ⌥Space and type `settings`) and press Test. Keys are per Mac user. |

The engine prints what it does in its Terminal window. When the app starts it (coming soon), the log is
`~/miyagi/engine/logs/engine.log`.

## From source (developers)

```bash
git clone https://github.com/michae6345-crypto/sandhacks-tutor.git && cd sandhacks-tutor
git switch integration/live        # the engine's live branch
scripts/miyagi-engine.sh           # first run creates .venv with uv; listens on ws://localhost:8787 and your LAN
```

The app's source is `app/` on `main` (Adrian's `adrian/shell` is merged there):

```bash
git worktree add ../miyagi-app origin/main && cd ../miyagi-app/app
npm ci && npm run dev              # or: npm run dist:mac -> dist/mac-arm64/Miyagi.app
```

- Keys: the app's Settings, or a `.env` at the repo root for engine-only work (copy `.env.example`; never commit it).
- `scripts/install.sh` from a clone uses that checkout in place: it makes `~/miyagi/engine/venv` and
  `~/miyagi/engine/bin/miyagi-engine` but doesn't download or copy the source.
- `scripts/miyagi-engine.sh` listens on all interfaces so a second laptop on the same network can use the engine.
  `~/miyagi/engine/bin/miyagi-engine` listens on this Mac only.
- VS Code companion by hand: `scripts/package-vscode-ext.sh` builds a `.vsix`, then
  `code --install-extension vscode-ext/dist/miyagi-companion-0.0.1.vsix`.

## Windows

- **The app:** [Miyagi-Windows-Setup.exe](https://github.com/adrian-erlikhman/miyagi/releases/download/windows/Miyagi-Windows-Setup.exe)
  installs it for your user, without an admin prompt. It isn't signed yet: if SmartScreen appears, click **More info ›
  Run anyway**. Ctrl+Shift+Space opens the launcher.
- **The engine:** there's no Windows installer yet, and the screen reader is macOS-only. To try it (untested), install
  [uv](https://docs.astral.sh/uv/) and, in PowerShell in a clone:

  ```powershell
  uv venv --python 3.12 .venv
  uv pip install --python .venv\Scripts\python.exe -e server -e cli
  $env:ORCH_SCREEN = "0"; $env:LESSON_ENGINE = "claude"
  .venv\Scripts\python.exe -m server.orchestrator.main --host 127.0.0.1 --port 8787
  ```

  Without screen reading, steps are graded from your saved files, from `tut run`, and from the VS Code companion.
