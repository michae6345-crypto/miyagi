"""miyagi bridge: lets the miyagi tutor read the open Blender scene over a loopback HTTP server.

register() starts the server (server.py) and the bpy.app.timers pump that runs its main-thread jobs; unregister()
stops both. Nothing starts at import. It draws nothing: no panel, no menu, no header, no status text. The scene
dumper (scene_dump.py) is imported only when GET /state asks for it (server.state_payload: from . import scene_dump).
"""

bl_info = {
    "name": "miyagi bridge",
    "author": "miyagi",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Runs in the background, no UI",
    "description": "Local HTTP server on 127.0.0.1 so the miyagi tutor can read the scene",
    "category": "System",
}


def register():
    import bpy

    from . import server

    server.start()
    if not bpy.app.timers.is_registered(server.pump):
        bpy.app.timers.register(server.pump, first_interval=server.PUMP_INTERVAL_S, persistent=True)


def unregister():
    import bpy

    from . import server

    if bpy.app.timers.is_registered(server.pump):
        bpy.app.timers.unregister(server.pump)
    server.stop()
