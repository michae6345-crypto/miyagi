# server/evals/links: offline eval set for lessons from any link

How well does a link (a docs page, a blog tutorial, a GitHub README) become a lesson? Each case in `cases/` is one
saved page in `pages/` (HTML, or Markdown for a README), the URL it came from, and the outline a careful tutor
expects: refuse it (and why) or teach it, in how many steps, with which code blocks landing in a step. Contract:
`shared/contracts/ANY-LINK.md`.

```
python -m server.evals.links                  # metrics + failing cases
python -m server.evals.links -v               # plus every case (brittle checks, build warnings)
python -m server.evals.links -k git           # only ids containing "git"
python -m server.evals.links --json
python -m server.evals.links --write-baseline # after link lessons got better, or cases were added
python -m pytest server/evals/links -q        # fails below baseline.json, or when a baseline-passing case fails
```

## What runs

Free and offline: no network, no model call, no key.

1. **Read the page** (`reader.py`): navigation, headers, footers, sidebars, cookie banners, newsletter boxes, share
   bars, comments and dates go; what is left (headings, paragraphs, list items, code blocks with their language) is
   the readable text. Its `events.link_content_hash` and `link_cache_key` are the contract's cache key, so the same
   page with other chrome, or through another spelling of its link, gets the same key. A 401 / 403 / 451, or a
   paywall with no content, is `blocked`; a page with almost no text and no code is `no_content`.
2. **Teachable or not** (`fake_model.verdict`): the deterministic stand-in for the contract's Haiku call on the
   outline. Code means two or more code blocks, or one of 3+ lines (output blocks don't count). Steps means a numbered
   list of 3+ items, two thirds of them imperatives ("Press Tab", "Click the face").
3. **Build the lesson** through the engine's no-video build, `server.lesson.textlesson.build_text_lesson` (the
   "Just teach me" path the contract builds link lessons on), with `fake_model.FakeModel` in place of
   `claude._generate_json` and the page in place of the research notes. The fake is faithful and dumb: one plan step
   per code block (one per command when the lesson has room), every block copied verbatim, 3-8 steps (blocks for the
   same file merged, then a long page cut at a section boundary), a check on each code step's most distinctive line,
   and the page's own output as a run step's check. So a block the lesson does not carry was lost by the engine
   (strip_injection's command allowlist, sanitize_step, order_plan, repair), not by a model.

The engine lane can score its own pieces: `runner.run_case(case, read=..., verdict=..., builder_fn=...)` takes any
`read(text, url, kind, status=, fmt=)`, `verdict(page)` and `builder_fn(page) -> lesson graph`.

## A case

```json
{"id": "python-venv", "url": "https://docs.python.org/3/tutorial/venv.html", "page": "python-venv.html",
 "status": 200,
 "expect": {"refusal": null, "steps": [3, 8], "title": "Virtual Environments and Packages", "site": "docs.python.org",
            "code": ["python3 -m venv tutorial-env", "source tutorial-env/bin/activate"],
            "never": [],
            "absent": ["Report a Bug"], "same_hash_as": null},
 "notes": "why the case is here"}
```

`refusal`: `null` (teach it), `"not_teachable"`, `"blocked"` or `"no_content"`. `code`: one fragment per code block
that must land in some step's code or run command (whitespace-insensitive; `python` reads as `python3`, the engine's
macOS rewrite). Leave out a block a lesson rightly never runs (a `>` redirect, a bare `python` REPL) and say so in
`notes`. `never`: what no step may carry. `absent`: page chrome that must not reach the readable text.
`same_hash_as`: a twin case whose readable text (and cache key) must be identical.

A case passes when the verdict is right and, for a teachable page: the lesson built and passes the lesson schema,
the step count is in range, every `code` fragment landed, no `never` fragment did, every step has code to type or a
command to run, and every code step and run step has a check; plus the reader's title / site / author / absent /
twin checks.

## Metrics

| metric | what |
|---|---|
| `verdict_accuracy` | cases refused for the right reason or accepted |
| `refusal_precision` / `refusal_recall` | refused is the positive class |
| `build_rate` | teachable pages whose lesson built and passed `schema_errors` |
| `steps_in_range` | built lessons with a step count in the case's range |
| `code_landed` | expected code fragments found in a step (a wrongly refused page counts all of its own as missed) |
| `live_steps` | steps with code to type or a command to run (an emptied step is a dead end) |
| `code_steps_checked` / `run_steps_checked` | code / run steps with at least one check |
| `portable_checks` | checks that do not ask for the page author's own screen: a `/Users/` path, a commit id, a clock time, the exact version pip printed that day (metric only) |
| `reader_ok` | the title / site / author / absent / twin checks |
| `cases_passed` | cases with every expectation met |

## Baseline (Nov 24, 21 cases, 67 code fragments)

| metric | value |
|---|---|
| verdict_accuracy | 1.000 |
| refusal_precision / recall | 1.000 / 1.000 |
| build_rate | 0.929 (13 of 14) |
| steps_in_range | 1.000 |
| code_landed | 0.940 (63 of 67) |
| live_steps | 0.861 |
| code_steps_checked / run_steps_checked | 1.000 / 1.000 |
| portable_checks | 0.973 |
| reader_ok | 1.000 |
| cases_passed | 0.762 (16 of 21) |

The five failing cases are what the engine lane should fix first; each is a real defect of the build, not of the fake:

- **python-venv, python-venv-mirror**: `source tutorial-env/bin/activate` is blanked (the allowlist only knows
  `.venv/bin/activate`), so is `python -m pip list`, and so are the REPL demo and the freeze redirect. Each blanked
  command leaves a dead step ("Run source in the terminal.", no command) with a Code check on text nobody types.
- **git-recording-changes**: `echo 'My Project' > README` (a redirect) is blanked: same dead step. The lesson should
  say it in words ("Create README with one line") or drop the step.
- **blender-python-quickstart**: `textlesson.plan_runs` adds "Run scene_tools.py" as `python3 scene_tools.py`; a bpy
  script only runs inside Blender (Text Editor, Alt-P).
- **blender-manual-extrude**: a page of app steps with no code (press Tab, E, click) cannot build: the text-lesson
  path needs code in every step. It needs app-lesson steps (`server/lesson/app_lesson.py`).

Brittle checks (`-v`): the Git book's `Initialized empty Git repository in /Users/you/...` and commit id `463dc4f`,
and pip's `Successfully installed requests-2.32.3`, copied from the page's output, would never pass on the learner's
Mac. The build keeps them today.

## Adding a case

Save the page under `pages/` (strip anything personal; keep the chrome, it is what the reader is tested on), write
`cases/<id>.json`, run `python -m server.evals.links -v -k <id>`, then `--write-baseline` once the whole set is where
it should be. A case never changes its expectations to pass.
