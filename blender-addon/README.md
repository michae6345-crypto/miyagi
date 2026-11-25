# miyagi bridge (Blender add-on)

A small Blender add-on that lets the miyagi tutor read the open scene. It runs a JSON HTTP server on
127.0.0.1 only, on the first free port of `MIYAGI_BLENDER_PORTS` (default `8801-8809`). The engine's client is
`server/workspace/blender_ext.py`; it returns `None` whenever no Blender answers.

It draws nothing: no panel, no menu, no header, no status text, and it never changes the scene. Nothing runs at
import; `register()` starts the server and a `bpy.app.timers` pump, `unregister()` stops them.

## Files

- `miyagi_bridge/__init__.py`: `bl_info`, `register()`, `unregister()`.
- `miyagi_bridge/blender_manifest.toml`: the extension manifest (Blender 4.2+), with the network and files permissions.
- `miyagi_bridge/server.py`: the server, guards and routes. Imports without `bpy` so tests can use a fake.
- `miyagi_bridge/ui_geom.py`: the pure projection behind `/ui`'s object boxes (no `bpy`, no `mathutils`).
- `miyagi_bridge/scene_dump.py`: the scene dumper (format `"dump_scene.py 1"`), owned by the dump lane.
- `start_bridge.py`: starts the bridge in a Blender that does not have the add-on installed.
- `dump_scene.py`: the headless dumper CLI, owned by the dump lane.

## Routes

All GET, JSON, `cache-control: no-store`.

| Route | Reply |
| --- | --- |
| `/health` | `{ok, app: "blender", name: "miyagi_bridge", version, blender, port, pid, file}` |
| `/state` | `{ok, app, port, file, dirty, mode, active, selected, frame_current, dump}`; `dump` is a `"dump_scene.py 1"` scene dump |
| `/ops?since=<seq>` | `{ok, last_seq, ops: [{seq, idname, name, props, t}]}`: operators the learner ran, newest 200 kept |
| `/ui` | `{ok, pixel_size, ui_scale, origin: "bottom-left", mode, active, windows: [{x, y, width, height, screen, workspace, areas: [{type, ui_type, x, y, width, height, regions: [{type, x, y, width, height}], objects?, properties?}]}]}` in raw Blender pixels (see below) |

### `/ui` fields

All rectangles are raw Blender pixels, origin bottom-left; area, region and object `x` / `y` are relative to the
window. The engine (`server/screen/app_target.py`) places them on the Blender window it sees on screen and drops
anything it cannot calibrate.

- `mode`: `bpy.context.mode` (`OBJECT`, `EDIT_MESH`, ...). `active`: the active object's name, or `null`.
- `regions`: every region of the area, hidden ones too (a hidden sidebar is 1 px wide; the engine drops regions
  under 6 pt).
- `objects` (a 3D Viewport with a single view; none in quad view): `[{name, type, x, y, width, height}]`, at most
  200, the visible objects' screen boxes in window pixels. Each box is the object's 8 world-space bound-box corners
  projected with the viewport's WINDOW region and `region_3d.perspective_matrix` (`ui_geom.project` mirrors
  `bpy_extras.view3d_utils.location_3d_to_region_2d`). An object is listed only when `visible_get()` is true for
  that viewport, every corner is in front of the view, its box's centre is inside the region and at least half of
  the box survives clipping to the region (the clipped box is sent). Lights, cameras, empties, speakers and light
  probes get a 24 px square around their origin. An object that raises while read is left out.
- `properties` (a Properties editor): `{context, tabs, contexts?}`. `context` is the tab shown (`OBJECT`,
  `MODIFIER`, ...), `tabs` the tab column (the `NAVIGATION_BAR` region) or `null`, and `contexts` the tabs shown now,
  top-down. Blender has no API for that list; an invalid `context` value is refused before anything is set, and the
  refusal names the valid ones, so the bridge reads them from it (`contexts` is left out when it cannot).

Blender's data may only be read on its main thread, so `/state` and `/ui` are queued for the timer, which runs
every 0.05 s. If the main thread does not get to them within 1.5 s (a long render, a modal operator), the reply is
`503 {"ok": false, "error": "busy"}`. `/health` and `/ops` come from cached values.

## Guards

The same as the VS Code companion's (`vscode-ext/extension.js` `refuse()`):

- a peer that is not loopback: `403 not_loopback`
- any `Origin` header: `403 origin_not_allowed`
- `Sec-Fetch-Site` other than `none`: `403 browser_not_allowed`
- a `Host` other than `127.0.0.1`, `localhost` or `[::1]`: `403 host_not_allowed`
- while a live miyagi engine has written its token (`~/.miyagi/engine-tokens/<port>.json` or
  `MIYAGI_ENGINE_TOKEN_DIR`), every route but `/health` needs `X-Miyagi-Token`: else `401 token_required`
- an unknown route: `404 no_route`

## Running it

Without installing: `<blender> /abs/lesson.blend --python blender-addon/start_bridge.py`
(`blender_ext.launch_argv(blend)` builds that argv; nothing in the engine runs it yet).

Installing it into the learner's Blender is a later step and needs Michael's OK first. The packaged app does not
ship this folder yet (`app/scripts/bundle-engine.mjs` would need `blender-addon` in its PATHS).

## Tests

`server/workspace/tests/test_blender_addon_server.py` loads this package by file path with a fake `bpy` and a fake
`scene_dump`; one smoke test runs the real Blender headless (`--background --factory-startup`) when it is installed.
`server/workspace/tests/test_blender_ui_headless.py` checks `ui_geom` against Blender's own
`location_3d_to_region_2d` and `world_to_camera_view` on the factory scene, and `/ui` on the factory screen, also
headless only.
