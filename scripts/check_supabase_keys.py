"""Refuse secret Supabase keys in the app (launch risk R46). Stdlib only.

The app may carry the project URL and its publishable ("anon") key, which Supabase documents as safe in a client.
It must never carry a secret key: an `sb_secret_...` key, or a legacy JWT key whose payload says
`"role": "service_role"`. Either one bypasses row-level security for anyone who unzips the app.

    python3 scripts/check_supabase_keys.py app            # the app's sources (node_modules skipped)
    python3 scripts/check_supabase_keys.py --env          # MAIN_VITE_* / VITE_* / ... build variables, before a build
    python3 scripts/check_supabase_keys.py app/out        # the built app, after `npm run build`
    python3 scripts/check_supabase_keys.py --self-test    # the check itself catches a made-up key

Exit 1 on a hit. A hit names the file and line, or the variable, and the kind of key. It never prints the value.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Split so this file is not itself a hit, and so a scanner reading it sees no key-shaped literal.
SECRET_PREFIX = "sb_" + "secret_"
SECRET_KEY = re.compile(re.escape(SECRET_PREFIX) + r"[A-Za-z0-9_-]{16,}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]*")
# electron-vite / Vite put variables with these prefixes into the bundle at build time (app/electron.vite.config.ts).
BUILD_ENV_PREFIXES = ("MAIN_VITE_", "PRELOAD_VITE_", "RENDERER_VITE_", "VITE_")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".mp3", ".mp4", ".wav", ".mov", ".woff", ".woff2",
                 ".ttf", ".otf", ".zip", ".gz", ".tar", ".dmg", ".pdf"}
MAX_BYTES = 50 * 1024 * 1024


def _jwt_role(payload_b64: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        role = json.loads(raw).get("role")
    except (ValueError, AttributeError):
        return None
    return role if isinstance(role, str) else None


def find_keys(text: str) -> list[tuple[int, str]]:
    """(line number, kind) for every secret Supabase key in text."""
    hits: list[tuple[int, str]] = []
    for m in SECRET_KEY.finditer(text):
        hits.append((text.count("\n", 0, m.start()) + 1, f"{SECRET_PREFIX} secret key"))
    for m in JWT.finditer(text):
        if _jwt_role(m.group(1)) == "service_role":
            hits.append((text.count("\n", 0, m.start()) + 1, "service_role JWT"))
    return sorted(hits)


def scan_paths(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for root in paths:
        if not root.exists():
            problems.append(f"{root}: missing (nothing to scan)")
            continue
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for f in files:
            if SKIP_DIRS & set(f.parts) or f.suffix.lower() in SKIP_SUFFIXES or f.stat().st_size > MAX_BYTES:
                continue
            text = f.read_bytes().decode("utf-8", errors="ignore")
            problems += [f"{f}:{line}: {kind}" for line, kind in find_keys(text)]
    return problems


def scan_env(env: dict[str, str]) -> list[str]:
    return [f"${name}: {kind}" for name, value in sorted(env.items()) if name.startswith(BUILD_ENV_PREFIXES)
            for _, kind in find_keys(value)]


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def self_test() -> list[str]:
    """Made-up keys, built here at run time (none sits in the repo): the secret ones are caught, the public ones are not."""
    head = _b64({"alg": "HS256", "typ": "JWT"})
    service = f"{head}.{_b64({'iss': 'supabase', 'ref': 'madeup', 'role': 'service_role'})}.c2lnbmF0dXJl"
    anon = f"{head}.{_b64({'iss': 'supabase', 'ref': 'madeup', 'role': 'anon'})}.c2lnbmF0dXJl"
    secret = SECRET_PREFIX + "MadeUpForTheSelfTest_0123456789"
    publishable = "sb_" + "publishable_" + "MadeUpForTheSelfTest_0123456789"
    failures: list[str] = []

    def expect(name: str, got: list, want: int) -> None:
        if len(got) != want:
            failures.append(f"self-test {name}: {len(got)} hits, expected {want}")

    expect("secret key", find_keys(f"const k = '{secret}'"), 1)
    expect("service_role JWT", find_keys(f'key: "{service}"'), 1)
    expect("publishable key", find_keys(f"const k = '{publishable}'"), 0)
    expect("anon JWT", find_keys(f"const k = '{anon}'"), 0)
    expect("prefix alone", find_keys(f"// keys starting {SECRET_PREFIX} never ship"), 0)
    expect("env secret", scan_env({"MAIN_VITE_SUPABASE_ANON_KEY": secret}), 1)
    expect("env service_role", scan_env({"MAIN_VITE_SUPABASE_ANON_KEY": service}), 1)
    expect("env publishable", scan_env({"MAIN_VITE_SUPABASE_ANON_KEY": publishable, "MAIN_VITE_SUPABASE_URL": "https://x.supabase.co"}), 0)
    expect("env not bundled", scan_env({"SUPABASE_SERVICE_ROLE_KEY": service}), 0)
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "out" / "main").mkdir(parents=True)
        (Path(d) / "out" / "main" / "index.js").write_text(f"a\nb\nconst k = '{service}'\n")
        (Path(d) / "node_modules").mkdir()
        (Path(d) / "node_modules" / "dep.js").write_text(f"'{secret}'")
        got = scan_paths([Path(d)])
        expect("built file", got, 1)
        if got and not got[0].endswith(":3: service_role JWT"):
            failures.append(f"self-test built file: wrong location {got[0]!r}")
        if any(service in g or secret in g for g in got):
            failures.append("self-test: a hit printed the key")
    return failures


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        failures = self_test()
        print("\n".join(failures) or "check_supabase_keys self-test: ok")
        return 1 if failures else 0
    paths = [Path(a) for a in argv if not a.startswith("--")]
    if not paths and "--env" not in argv:
        print(__doc__)
        return 2
    problems = scan_env(dict(os.environ)) if "--env" in argv else []
    problems += scan_paths(paths)
    if problems:
        print("Secret Supabase key found. The app may only carry the URL and the publishable key (R46):")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print(f"no secret Supabase keys in {', '.join(['build env'] * ('--env' in argv) + [str(p) for p in paths])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
