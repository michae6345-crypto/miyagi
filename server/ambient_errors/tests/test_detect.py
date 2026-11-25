"""The parser on recorded Vision OCR of each error kind (fixtures/*.ocr.json) and on the exact text (Accessibility)."""

from __future__ import annotations

import pytest

from server.ambient_errors.detect import Row, find_errors
from server.ambient_errors.tests.helpers import ocr_rows, text_rows

# name -> (kind, title as read exactly, file, line, module, command)
WANT = {
    "python_traceback": ("python_traceback", "ModuleNotFoundError: No module named 'pandas'",
                         "/Users/sam/code/weather-app/app.py", 3, "pandas", "python3 app.py"),
    "node_stack": ("js_error", "TypeError: Cannot read properties of undefined (reading 'port')",
                   "/Users/sam/code/api/server.js", 12, None, "node server.js"),
    "tsc_error": ("compiler", "error TS2322: Type 'string' is not assignable to type 'number'.", "src/index.ts", 14,
                  None, "npx tsc --noEmit"),
    "pip_failure": ("shell_exit", "ERROR: No matching distribution found for tensorflow==2.3", None, None, None,
                    "pip install tensorflow==2.3"),
    "npm_failure": ("shell_exit", "npm error E404: 'reactt@*' is not in this registry.", None, None, "reactt",
                    "npm install reactt"),
    "git_error": ("shell_exit", "error: failed to push some refs to 'github.com:sam/api.git'", None, None, None,
                  "git push"),
    "jupyter_cell": ("notebook_cell", "NameError: name 'df' is not defined", None, 1, None, None),
}
NOTEBOOK = {"jupyter_cell"}


@pytest.mark.parametrize("name", sorted(WANT))
def test_exact_text_each_kind(name):
    kind, title, file, line, module, command = WANT[name]
    got = find_errors(text_rows(name), notebook=name in NOTEBOOK)
    assert len(got) == 1, [g.title for g in got]
    f = got[0]
    assert (f.kind, f.title, f.file, f.line, f.module, f.command) == (kind, title, file, line, module, command)
    assert 1 <= len(f.lines) <= 8 and f.rect() is None  # Accessibility rows have no rect


@pytest.mark.parametrize("name", sorted(WANT))
def test_recorded_ocr_each_kind(name):
    """Vision drops indentation and quotes and misreads a letter now and then: the kind, file:line and a rect hold."""
    kind, title, file, line, module, _command = WANT[name]
    got = find_errors(ocr_rows(name), notebook=name in NOTEBOOK)
    assert len(got) == 1, [g.title for g in got]
    f = got[0]
    assert f.kind == kind
    assert (f.file, f.line) == (file, line)
    assert f.rect() is not None and f.rect().w > 100
    words = [w for w in title.split() if len(w) > 5 and w.isalpha()]
    assert sum(w in f.title for w in words) >= len(words) // 2, f.title  # OCR noise, mostly the same words


def test_ids_survive_ocr_noise_where_the_text_is_clean():
    for name in ("python_traceback", "node_stack", "tsc_error", "pip_failure", "npm_failure"):
        exact = find_errors(text_rows(name))[0]
        seen = find_errors(ocr_rows(name))[0]
        assert exact.key("Terminal") == seen.key("Terminal"), name
        assert exact.key("Terminal").startswith("err-") and len(exact.key("Terminal")) == 10


def test_clean_output_has_no_error():
    assert find_errors(text_rows("clean_run")) == []
    assert find_errors(ocr_rows("clean_run")) == []


def test_source_code_is_not_an_error():
    code = ["def load(path):", "try:", "return pd.read_csv(path)", "except FileNotFoundError:",
            'print("error: file not found")', 'raise ValueError("no data")', "ValueError: is how it reads",
            "console.log('TypeError: x')", "// fatal: comment"]
    assert find_errors([Row(c) for c in code]) == []
    assert find_errors([Row(c) for c in code], browser=True) == []


def test_chained_traceback_is_one_block_ending_on_the_last_error():
    rows = [Row(x) for x in """Traceback (most recent call last):
  File "/Users/sam/app.py", line 4, in load
    return int(s)
ValueError: invalid literal for int() with base 10: 'x'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/Users/sam/app.py", line 9, in <module>
    load("x")
RuntimeError: could not load x""".splitlines()]
    got = find_errors(rows)
    assert len(got) == 1 and got[0].title == "RuntimeError: could not load x" and got[0].line == 9


def test_library_frames_point_at_the_learners_file():
    rows = [Row(x) for x in """Traceback (most recent call last):
  File "/Users/sam/proj/main.py", line 7, in <module>
    df = pd.read_csv("nope.csv")
  File "/Users/sam/proj/.venv/lib/python3.12/site-packages/pandas/io/parsers/readers.py", line 1026, in read_csv
    return _read(filepath_or_buffer, kwds)
FileNotFoundError: [Errno 2] No such file or directory: 'nope.csv'""".splitlines()]
    f = find_errors(rows)[0]
    assert (f.file, f.line) == ("/Users/sam/proj/main.py", 7)


def test_syntax_error_without_a_traceback():
    rows = [Row(x) for x in ['  File "/Users/sam/app.py", line 3', '    print("hi"', '         ^',
                             "SyntaxError: '(' was never closed"]]
    f = find_errors(rows)[0]
    assert (f.kind, f.line, f.title) == ("python_traceback", 3, "SyntaxError: '(' was never closed")


def test_other_compilers():
    paren = find_errors([Row("src/app.tsx(3,10): error TS2304: Cannot find name 'useStat'.")])[0]
    assert (paren.kind, paren.file, paren.line, paren.col) == ("compiler", "src/app.tsx", 3, 10)
    gcc = find_errors([Row("main.c:5:12: error: expected ';' after expression"), Row("    5 |   int x = 3"),
                       Row("      |            ^")])[0]
    assert (gcc.kind, gcc.lang, gcc.line, gcc.title) == ("compiler", "c", 5, "error: expected ';' after expression")
    rust = find_errors([Row("error[E0308]: mismatched types"), Row(" --> src/main.rs:4:18"), Row("  |")])[0]
    assert (rust.kind, rust.lang, rust.file, rust.line) == ("compiler", "rust", "src/main.rs", 4)


def test_browser_console_and_node_missing_module():
    up = find_errors([Row("Uncaught TypeError: Cannot read properties of null (reading 'addEventListener')"),
                      Row("at main.js:14:9")], browser=True)[0]
    assert up.kind == "js_error" and up.title.startswith("TypeError") and up.line == 14
    nm = find_errors([Row(x) for x in """node:internal/modules/cjs/loader:1228
  throw err;
  ^

Error: Cannot find module 'express'
Require stack:
- /Users/sam/api/server.js
    at Module._resolveFilename (node:internal/modules/cjs/loader:1225:15)
    at Object.<anonymous> (/Users/sam/api/server.js:1:17)
Node.js v22.11.0""".splitlines()])[0]
    assert (nm.kind, nm.module, nm.line) == ("js_error", "express", 1)


def test_shell_basics():
    nf = find_errors([Row("sam@mac app % pyhton app.py"), Row("zsh: command not found: pyhton")])[0]
    assert (nf.kind, nf.command) == ("shell_exit", "pyhton app.py")
    fatal = find_errors([Row("% git status"), Row("fatal: not a git repository (or any of the parent directories): .git")])[0]
    assert fatal.title.startswith("fatal: not a git repository") and fatal.command == "git status"
    pep = find_errors([Row("% pip install requests"), Row("error: externally-managed-environment"),
                       Row("× This environment is externally managed")])[0]
    assert pep.title == "error: externally-managed-environment"
