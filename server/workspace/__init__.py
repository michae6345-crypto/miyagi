"""Per-lesson workspace: what the lesson needs on this Mac, a folder under ~/miyagi/lessons, VS Code.

    from server.workspace import requirements, editor_needed, install, prepare, open_editor, open_file_for
    reqs = requirements(graph)                 # read-only: tools + installed/version/install recipe
    install(item, on_line=print)               # only after the learner says yes
    wd = prepare(graph, goal)                  # Path; the hero lesson gets demo/pinn-lab
    if editor_needed(reqs): open_editor(wd, open_file_for(wd))   # Cursor or VS Code, only after the learner says yes
"""

from .core import open_file_for, prepare, read_state
from .editor import (
    editor_label,
    goto_argv,
    installed_editors,
    open_editor,
    open_editor_report,
    preferred_editor,
)
from .paths import build_workdir, folder_name, hero_workdir, lessons_root
from .setup import editor_needed, install, missing, requirements, setup_card

__all__ = [
    "build_workdir",
    "editor_label",
    "editor_needed",
    "folder_name",
    "goto_argv",
    "hero_workdir",
    "install",
    "installed_editors",
    "lessons_root",
    "missing",
    "open_editor",
    "open_editor_report",
    "open_file_for",
    "preferred_editor",
    "prepare",
    "read_state",
    "requirements",
    "setup_card",
]
