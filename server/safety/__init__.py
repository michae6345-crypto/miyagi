"""Guards between untrusted lesson / model output and the learner's Mac (OWASP LLM06 excessive agency, A08).

  commands.parse_run_command(cmd, workdir)  -> Allowed(argv) | Manual(reason): what "Run it for me" may run
  paths.safe_lesson_path(workdir, rel, write=False) -> Path | None: reads and writes stay in the lesson folder
  packages.verdict(name)                    -> allow | confirm | refuse | invalid: what pip may install
  child_env(**extra)                        -> the environment for any process the engine starts for a lesson
"""
from __future__ import annotations

import re

from .commands import Allowed, Manual, parse_run_command
from .paths import safe_lesson_path

# Never handed to a learner's process even if config.safe_env() lets it through (the engine's own per-launch token
# and where it lives, the admin token). config.safe_env() strips the provider keys and the cloud token.
_ENGINE_ONLY = ("MIYAGI_ENGINE_TOKEN", "MIYAGI_ADMIN", "X_MIYAGI", "ADMIN_TOKEN", "SUPABASE_SERVICE")


def child_env(base: dict | None = None, **extra: str) -> dict[str, str]:
    """config.safe_env() (every provider key, the cloud token and URL removed) without the engine's own secrets, then
    `extra` (PATH / VIRTUAL_ENV for the lesson's .venv) added."""
    from server import config

    env = config.safe_env(base)
    for var in list(env):
        if var.upper().startswith(_ENGINE_ONLY):
            env.pop(var, None)
    env.update(extra)
    return env


# Sites the engine may open in the learner's browser besides the setup catalog's own pages (docs, package indexes).
DOCS_HOSTS = frozenset({"python.org", "docs.python.org", "pypi.org", "nodejs.org", "npmjs.com", "github.com",
                        "code.visualstudio.com", "youtube.com",
                        "colab.research.google.com"})  # a Colab lesson's notebook button (the setup card's web app)


# Never opened, whatever the catalog lists: Michael's rule, miyagi never opens, names or offers Cursor (editor.py).
BANNED_HOSTS = frozenset({"cursor.com", "cursor.sh", "cursor.so", "anysphere.inc"})
# github.com pages that start a file download when opened (a release asset, a source archive, a raw file), and the
# hosts that serve them: shown as text, never opened
_GITHUB_DOWNLOAD = re.compile(r"^/[^/]+/[^/]+/(?:releases/download|archive|raw|zipball|tarball|blob/[^?#]*\?raw=)",
                              re.I)
_DOWNLOAD_HOSTS = frozenset({"codeload.github.com", "objects.githubusercontent.com", "raw.githubusercontent.com",
                             "github-releases.githubusercontent.com", "release-assets.githubusercontent.com"})
# a link straight to an installer or archive, on any host: the learner downloads it themselves from the official page
_DOWNLOAD_SUFFIX = re.compile(r"\.(?:zip|tar|tgz|gz|bz2|xz|7z|rar|dmg|pkg|mpkg|exe|msi|deb|rpm|appimage|whl|jar|"
                              r"sh|command|app|iso|img)$", re.I)


def _under(host: str, hosts) -> bool:
    return any(host == a or host.endswith("." + a) for a in hosts)


def _host(url: str) -> str | None:
    from urllib.parse import urlsplit

    try:
        u = urlsplit((url or "").strip())
        port = u.port
    except ValueError:
        return None
    if u.scheme != "https" or not u.hostname or u.username or u.password or port not in (None, 443):
        return None
    h = u.hostname.lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def allowed_hosts() -> frozenset[str]:
    """DOCS_HOSTS plus every host the setup catalog (server.workspace.setup.CATALOG) links to."""
    hosts = set(DOCS_HOSTS)
    try:
        from server.workspace.setup import CATALOG

        for entry in CATALOG.values():
            if (h := _host(str(entry.get("url") or ""))) is not None:
                hosts.add(h)
    except Exception:  # noqa: BLE001 - the docs list alone
        pass
    return frozenset(h for h in hosts if not _under(h, BANNED_HOSTS))


def browser_url_allowed(url: str) -> bool:
    """May the engine open `url` in the learner's browser? https only, no user:password@, the default port, a host
    that is (or is under) a catalog / docs host and never a banned one (cursor.com), and a page, not a download
    (github.com release assets and archives, codeload / raw hosts, a path ending .zip / .dmg / .pkg ...). Anything
    else is shown to the learner as text."""
    from urllib.parse import unquote, urlsplit

    h = _host(url)
    if h is None or _under(h, BANNED_HOSTS) or h in _DOWNLOAD_HOSTS:
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    path = unquote(parts.path or "/")
    if _DOWNLOAD_SUFFIX.search(path.rstrip("/")):
        return False
    if _under(h, {"github.com"}) and (_GITHUB_DOWNLOAD.search(path + ("?" + parts.query if parts.query else ""))
                                      or h != "github.com" and h != "gist.github.com"):
        return False  # a release asset / archive / raw file, or a github.com subdomain that serves files
    return _under(h, allowed_hosts())


__all__ = ["Allowed", "Manual", "browser_url_allowed", "child_env", "parse_run_command", "safe_lesson_path"]
