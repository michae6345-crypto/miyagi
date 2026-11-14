"""Per-lesson workspace: a folder under ~/miyagi/lessons with starter files, opened in VS Code.

    from server.workspace import prepare, open_editor, open_file_for
    wd = prepare(graph, goal)          # Path; the hero lesson gets demo/pinn-lab
    open_editor(wd, open_file_for(wd))
"""

from .core import open_file_for, prepare, read_state
from .editor import open_editor
from .paths import build_workdir, folder_name, hero_workdir, lessons_root

__all__ = ["build_workdir", "folder_name", "hero_workdir", "lessons_root", "open_editor", "open_file_for", "prepare", "read_state"]
