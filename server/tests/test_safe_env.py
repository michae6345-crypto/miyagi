"""No subprocess the engine starts inherits a provider key, the cloud token or the engine token (claude/eng-keys-ssrf).

Keys from .env or the shell the engine was started from live in os.environ; a child started without `env=` gets
all of them. The worst case is the `code` CLI: when it starts VS Code, VS Code passes that environment on to every
integrated terminal, task and extension, so `echo $ANTHROPIC_API_KEY` in the learner's terminal would print it.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from server import config

SERVER = Path(__file__).resolve().parents[1]

SECRETS = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "GEMINI_API_KEY": "gm-test",
    "ELEVENLABS_API_KEY": "el-test",
    "MIYAGI_ENGINE_TOKEN": "engine-test",
    "FOO_SECRET": "foo-test",
}


@pytest.fixture
def secret_env(monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/Users/learner")
    return SECRETS


def test_safe_env_drops_every_secret_and_keeps_the_basics(secret_env):
    env = config.safe_env()
    for k in secret_env:
        assert k not in env
    assert env["PATH"] == "/usr/bin:/bin" and env["HOME"] == "/Users/learner"
    assert not set(secret_env.values()) & set(env.values())


@pytest.mark.parametrize("name", [
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI", "ELEVENLABS_API_KEY", "OPENAI_API_KEY", "OPENAI_ORG_ID", "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY", "MIYAGI_ENGINE_TOKEN", "MIYAGI_TOKEN", "MIYAGI_TOKEN_FILE", "MIYAGI_CLOUD_TOKEN",
    "MIYAGI_CLOUD_URL", "MIYAGI_CLOUD_HOSTS", "TUT_ENV", "TIGER_DATABASE_URL", "GITHUB_TOKEN", "FOO_SECRET",
    "STRIPE_API_KEY", "ADMIN_PASSWORD", "DB_PASSWORD", "anthropic_api_key",
])
def test_secret_names(name):
    assert config.SECRET_ENV_RE.search(name), name
    assert name not in config.safe_env({name: "x", "PATH": "/bin"})


@pytest.mark.parametrize("name", [
    "PATH", "HOME", "LANG", "LC_ALL", "USER", "SHELL", "TMPDIR", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONUNBUFFERED",
    "MIYAGI_LESSONS_DIR", "MIYAGI_EDITOR", "MIYAGI_DEV_CLOUD", "TOKENIZERS_PARALLELISM", "SSH_AUTH_SOCK", "TERM",
])
def test_ordinary_names_survive(name):
    assert not config.SECRET_ENV_RE.search(name), name
    assert config.safe_env({name: "v"}) == {name: "v"}


def test_extra_is_added_after_stripping():
    env = config.safe_env({"ANTHROPIC_API_KEY": "x", "PATH": "/bin"}, PYTHONUNBUFFERED="1")
    assert env == {"PATH": "/bin", "PYTHONUNBUFFERED": "1"}


def test_code_cli_launch_gets_no_keys(secret_env, monkeypatch, tmp_path):
    """The editor's `code` launch (subprocess mocked) receives an environment without the keys."""
    from server.workspace import editor

    seen: list[dict] = []

    def fake_run(argv, **kw):
        seen.append({"argv": argv, "env": kw.get("env")})
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(editor.subprocess, "run", fake_run)
    assert editor._run(["/usr/local/bin/code", "-n", str(tmp_path)])
    assert seen and seen[0]["argv"][0].endswith("code")
    env = seen[0]["env"]
    assert env is not None, "the code CLI must get an explicit env (else it inherits os.environ)"
    for k in secret_env:
        assert k not in env
    assert env["PATH"] == "/usr/bin:/bin" and env["HOME"] == "/Users/learner"


def test_open_editor_report_launch_gets_no_keys(secret_env, monkeypatch, tmp_path):
    """The real open path (open_editor_report -> the default runner) hands `code` the stripped env too."""
    from server.workspace import editor

    envs: list[dict | None] = []

    def fake_run(argv, **kw):
        envs.append(kw.get("env"))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(editor.subprocess, "run", fake_run)
    ed = {**editor.EDITORS["vscode"], "id": "vscode", "cli": "/usr/local/bin/code", "bundled_cli": "/nonexistent/code"}
    editor.open_editor_report(tmp_path, editor=ed, arrange_windows=False, wait=True, trusted=lambda: False,
                              previous={"name": "Terminal", "pid": 1})
    assert envs, "open_editor_report ran nothing"
    for env in envs:
        assert env is not None and not set(secret_env) & set(env)


def test_where_row_raise_gets_no_keys(secret_env, monkeypatch):
    from server.orchestrator import where_row

    seen: list[dict] = []
    monkeypatch.setattr(where_row.subprocess, "run", lambda argv, **kw: seen.append(kw.get("env")))
    where_row._raise_window("/tmp/lesson", last_focused=True)
    assert seen and seen[0] is not None and not set(secret_env) & set(seen[0])


# --------------------------------------------------------------------------- every launch passes env=

# Findings still allowed, in files other lanes own: file -> (at most this many findings, who fixes it). A finding is a
# launch with no env=, a launch whose env= is os.environ (or a name assigned from it in the same function), or a
# child environment copied from os.environ (dict(os.environ), {**os.environ}, os.environ.copy()). Any finding in
# another file, or one more in these, fails. When a lane merges its fix, lower the count or delete the entry.
# The counts hold on origin/integration/live and on origin/claude/eng-harden.
PENDING: dict[str, tuple[int, str]] = {
    # claude/eng-harden (with the engine-agency lane) owns session.py: "run it for me" builds env = dict(os.environ)
    # for the learner's command, and the `pbcopy` clipboard helper passes no env.
    "orchestrator/session.py": (3, "claude/eng-harden"),
    # the engine-agency lane owns orchestrator/workspace.py: the background `code` / `open` launch (Popen), no env.
    "orchestrator/workspace.py": (1, "engine-agency lane"),
    # the engine-agency lane owns workspace/setup.py: the tool probe runner and `xcode-select -p` pass no env, and
    # install() / ensure_venv() copy os.environ for pip, brew and `python -m venv`.
    "workspace/setup.py": (4, "engine-agency lane"),
    # claude/eng-harden owns workspace/core.py: the `git` helper runs with {**os.environ, GIT_AUTHOR_...}.
    "workspace/core.py": (2, "claude/eng-harden"),
}
# config.py builds safe_env() itself from os.environ.
_ENV_COPY_OK = {"config.py"}

_SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "call", "check_call", "getoutput", "getstatusoutput"}
_ASYNCIO_FUNCS = {"create_subprocess_exec", "create_subprocess_shell"}
_OS_FUNCS = {"system", "popen", "spawnl", "spawnlp", "spawnv", "spawnvp", "execv", "execvp", "execl", "execlp"}


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Bare names imported from subprocess / asyncio / os (`from subprocess import run`) -> module."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "asyncio", "asyncio.subprocess", "os"):
            for a in node.names:
                out[a.asname or a.name] = node.module.split(".")[0]
    return out


def _launch(call: ast.Call, bare: dict[str, str]) -> str | None:
    f = call.func
    if isinstance(f, ast.Attribute):
        base = f.value
        mod = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
        if mod == "subprocess" and f.attr in _SUBPROCESS_FUNCS:
            return f"subprocess.{f.attr}"
        if mod in ("asyncio", "subprocess") and f.attr in _ASYNCIO_FUNCS:
            return f"asyncio.{f.attr}"
        if mod == "os" and f.attr in _OS_FUNCS:
            return f"os.{f.attr}"
    elif isinstance(f, ast.Name) and f.id in bare:
        mod = bare[f.id]
        if (mod == "subprocess" and f.id in _SUBPROCESS_FUNCS) or (mod == "asyncio" and f.id in _ASYNCIO_FUNCS) \
                or (mod == "os" and f.id in _OS_FUNCS):
            return f"{mod}.{f.id}"
    return None


def _has_env(call: ast.Call) -> bool:
    return any(k.arg == "env" for k in call.keywords) or any(k.arg is None for k in call.keywords)  # **kw: trust it


def _mentions(node: ast.AST) -> tuple[bool, bool]:
    """(reads os.environ, calls safe_env) anywhere inside `node`."""
    environ = safe = False
    for n in ast.walk(node):
        if _is_environ(n) or (isinstance(n, ast.Name) and n.id == "environ"):  # os.environ, or `from os import environ`
            environ = True
        elif isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == "safe_env") or (isinstance(f, ast.Attribute) and f.attr == "safe_env"):
                safe = True
    return environ, safe


def _inherits(value: ast.AST, scope: ast.AST) -> bool:
    """env=<value> hands the child os.environ (a copy of it, or a name assigned from it in the same function) without
    passing it through safe_env."""
    environ, safe = _mentions(value)
    if safe:
        return False
    if environ:
        return True
    if isinstance(value, ast.Name):
        sources = [n.value for n in ast.walk(scope) if isinstance(n, ast.Assign) and n.value is not None
                   and any(isinstance(t, ast.Name) and t.id == value.id for t in n.targets)]
        sources += [n.value for n in ast.walk(scope) if isinstance(n, ast.AnnAssign) and n.value is not None
                    and isinstance(n.target, ast.Name) and n.target.id == value.id]
        seen = [_mentions(s) for s in sources]
        return any(e for e, _ in seen) and not any(s for _, s in seen)
    return False


def _scopes(tree: ast.Module):
    """(call, the innermost function around it, or the module)."""
    stack: list[tuple[ast.AST, ast.AST]] = [(tree, tree)]
    while stack:
        node, scope = stack.pop()
        for child in ast.iter_child_nodes(node):
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            if isinstance(child, ast.Call):
                yield child, inner
            stack.append((child, inner))


def _injected(call: ast.Call, scope: ast.AST) -> str | None:
    """A call through a parameter that defaults to a subprocess function (`def f(..., popen=subprocess.Popen)`)."""
    if not isinstance(call.func, ast.Name) or not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    a = scope.args
    params = [*a.posonlyargs, *a.args]
    pairs = list(zip(params[len(params) - len(a.defaults):], a.defaults)) + [
        (p, d) for p, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
    for p, d in pairs:
        if p.arg == call.func.id and isinstance(d, ast.Attribute) and isinstance(d.value, ast.Name) \
                and d.value.id == "subprocess" and d.attr in _SUBPROCESS_FUNCS:
            return f"subprocess.{d.attr} (as {p.arg})"
    return None


def _is_environ(n: ast.AST) -> bool:
    return (isinstance(n, ast.Attribute) and n.attr == "environ" and isinstance(n.value, ast.Name)
            and n.value.id == "os")


def _env_copy(node: ast.AST) -> str | None:
    """dict(os.environ ...), os.environ.copy(), {**os.environ, ...}: a child environment made from the engine's."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id == "dict" and node.args and any(_is_environ(n) for n in ast.walk(node.args[0])):
            return "dict(os.environ)"
        if isinstance(f, ast.Attribute) and f.attr == "copy" and _is_environ(f.value):
            return "os.environ.copy()"
    if isinstance(node, ast.Dict) and any(k is None and _is_environ(v) for k, v in zip(node.keys, node.values)):
        return "{**os.environ}"
    return None


def scan(src: str, rel: str) -> list[str]:
    """Every launch with no env=, with env= from os.environ, and every copy of os.environ in one module's source."""
    tree = ast.parse(src, filename=rel)
    bare = _imported_names(tree)
    out = []
    for node, scope in _scopes(tree):
        what = _launch(node, bare) or _injected(node, scope)
        if not what:
            continue
        env = next((k.value for k in node.keywords if k.arg == "env"), None)
        if not _has_env(node):
            out.append(f"{rel}:{node.lineno} {what} (no env=)")
        elif env is not None and _inherits(env, scope):
            out.append(f"{rel}:{node.lineno} {what} (env from os.environ)")
    if rel not in _ENV_COPY_OK:
        out += [f"{rel}:{n.lineno} {c} (a child env copied from os.environ)" for n in ast.walk(tree) if (c := _env_copy(n))]
    return out


def launches_without_env() -> dict[str, list[str]]:
    """file (relative to server/) -> its findings, for every engine module (tests excluded)."""
    found: dict[str, list[str]] = {}
    for path in sorted(SERVER.rglob("*.py")):
        rel = path.relative_to(SERVER).as_posix()
        parts = path.relative_to(SERVER).parts
        if "tests" in parts or path.name.startswith("test_") or path.name == "conftest.py" or ".venv" in parts:
            continue
        if hits := scan(path.read_text(encoding="utf-8"), rel):
            found[rel] = hits
    return found


def test_every_subprocess_launch_passes_env():
    found = launches_without_env()
    bad = []
    for rel, hits in found.items():
        if len(hits) > PENDING.get(rel, (0, ""))[0]:
            bad += hits
    assert not bad, ("a subprocess would inherit every key in os.environ; pass env=safe_env(...) "
                     "(server.config):\n  " + "\n  ".join(bad))


def test_owned_files_are_clean():
    """This lane's files pass env=safe_env(...) on every launch, and are never in PENDING."""
    found = launches_without_env()
    for rel in ("workspace/editor.py", "orchestrator/where_row.py", "workspace/live_fresh_mac.py", "screen/macos.py"):
        assert rel not in found, found.get(rel)
        assert rel not in PENDING


def test_pending_names_only_other_lanes_files():
    lanes = {"claude/eng-harden", "engine-agency lane"}
    assert set(PENDING) <= {"orchestrator/session.py", "orchestrator/workspace.py", "workspace/setup.py",
                            "orchestrator/missing_module.py", "workspace/core.py"}
    for rel, (_n, owner) in PENDING.items():
        assert owner in lanes, rel
        assert (SERVER / rel).is_file(), f"{rel} is gone: drop it from PENDING"


def test_the_scan_catches_each_kind_of_leak():
    src = ("import subprocess, asyncio, os\nfrom subprocess import Popen\n"
           "subprocess.run(['x'])\n"                                  # 3: no env
           "Popen(['x'])\n"                                           # 4: no env (bare name)
           "asyncio.create_subprocess_exec('x')\n"                    # 5: no env
           "os.system('x')\n"                                         # 6: no env possible
           "subprocess.run(['x'], env={**os.environ, 'A': '1'})\n"    # 7: env from os.environ (+ the copy)
           "def f(popen=subprocess.Popen):\n"
           "    env = dict(os.environ)\n"                             # 9: a copy
           "    popen(['x'], env=env)\n"                              # 10: env assigned from os.environ
           "def g():\n"
           "    env = safe_env({'PATH': os.environ['PATH']})\n"
           "    subprocess.run(['x'], env=env)\n"                     # clean
           "subprocess.run(['x'], env=safe_env())\n")                 # clean
    lines = sorted(int(h.split(":")[1].split()[0]) for h in scan(src, "x.py"))
    assert lines == [3, 4, 5, 6, 7, 7, 9, 10]


def test_config_docstring_matches_safe_env():
    """The module docstring used to say safe_env "strips the rest" while nothing called it; it now says who does."""
    doc = config.__doc__ or ""
    assert "env=safe_env(...)" in doc and "SECRET_ENV_RE" in doc and "test_safe_env.py" in doc
