"""Per-lesson workspace: what the lesson needs on this Mac, a folder under ~/miyagi/lessons, VS Code.

    from server.workspace import requirements, editor_needed, install, prepare, open_editor, open_file_for
    reqs = requirements(graph)                 # read-only: tools + installed/version/install recipe
    install(item, on_line=print)               # only after the learner says yes
    wd = prepare(graph, goal)                  # Path; the hero lesson gets demo/pinn-lab
    if editor_needed(reqs): open_editor(wd, open_file_for(wd))   # VS Code, only after the learner says yes
"""

from .active import active_editor, adopt_folder, folder_on_screen, vscode_windows, wrong_folder
from .core import open_file_for, prepare, read_state
from .editor import (
    editor_label,
    editor_line_location,
    editor_line_rect,
    goto_argv,
    installed_editors,
    open_editor,
    open_editor_report,
    preferred_editor,
)
from .paths import build_workdir, folder_name, hero_workdir, lessons_root
from .resources import NO_RESOURCES, download_resources, find_resources
from .resources import summary as download_summary
from .setup import editor_needed, install, missing, requirements, setup_card

__all__ = [
    "active_editor", "adopt_folder", "folder_on_screen", "vscode_windows", "wrong_folder",
    "NO_RESOURCES",
    "build_workdir",
    "download_resources",
    "download_summary",
    "editor_label",
    "editor_line_location",
    "editor_line_rect",
    "editor_needed",
    "find_resources",
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
