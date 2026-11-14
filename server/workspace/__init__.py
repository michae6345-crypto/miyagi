"""Per-lesson workspace: what the lesson needs on this Mac, a folder under ~/miyagi/lessons, VS Code.

    from server.workspace import requirements, editor_needed, install, prepare, open_editor, open_file_for
    reqs = requirements(graph)                 # read-only: tools + installed/version/install recipe
    install(item, on_line=print)               # only after the learner says yes
    wd = prepare(graph, goal)                  # Path; the hero lesson gets demo/pinn-lab
    if editor_needed(reqs): open_editor(wd, open_file_for(wd))   # only after the learner says yes
"""

from .core import open_file_for, prepare, read_state
from .editor import open_editor
from .paths import build_workdir, folder_name, hero_workdir, lessons_root
from .setup import editor_needed, install, missing, requirements, setup_card

__all__ = [
    "build_workdir", "editor_needed", "folder_name", "hero_workdir", "install", "lessons_root", "missing",
    "open_editor", "open_file_for", "prepare", "read_state", "requirements", "setup_card",
]
