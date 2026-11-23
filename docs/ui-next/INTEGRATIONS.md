# Blender and CAD in miyagi: how the checks should work

Written Nov 22 2026. This is a scope, not code. Items marked "check on a Mac" could not be run on the Windows machine it was written on.

## Where it stands today

- The engine already knows app lessons. `server/lesson/app_lesson.py` turns a lesson whose title names an app (AutoCAD, Blender, Photoshop...) into an app lesson: step copy says "in Blender", and every file, command and output check is removed so nothing gates forever.
- That leaves one way to check 3D work: look at the window. A screenshot can tell that Blender is open and roughly what is selected. It cannot tell that the mug has a Subdivision modifier at level 2, that a sketch has no free movement, or that a plate is 5 mm thick.
- Setup already offers FreeCAD beside AutoCAD ("Get it / Try FreeCAD / I have it").

So Blender and CAD lessons run today, but their checks are the least exact. The plans in `catalog/` (Intro to Blender, Intro to CAD, Intro to Fusion, Intro to Onshape and four follow-ups) each state a `passes` line per lesson. Almost none of those can be verified from pixels.

## Three ways to check, in the order to build them

| Level | How it reads the work | Needs from the learner | Apps |
|---|---|---|---|
| Screen | Looks at the app window | Nothing | Any app. This is today. |
| File | Opens the saved file with the app's own Python, with no window, and reads the model | Save (Cmd S), or press Check | Blender, FreeCAD, any STL |
| Live | A small add-on inside the app reports the model as it changes | Install the add-on once | Blender, FreeCAD, Fusion |

File level is the one to build first. It needs no add-on, it is exact, and it works the day the learner installs Blender.

### File level

The lesson opens or creates its file in the lesson folder (`~/miyagi/<lesson>/mug.blend`), so the engine knows the path. When the file's modified time changes, or the learner presses Check, the engine runs the app with no window and a script of ours that prints one JSON document.

**Blender.** `Blender --background <file.blend> --python dump_scene.py` (on a Mac the binary is inside `Blender.app/Contents/MacOS/`; check on a Mac). The script walks `bpy.data` and prints:

- objects: name, type, location, rotation, scale, dimensions, parent
- meshes: vertex, edge and face counts, whether faces are smooth shaded, whether the mesh is one connected piece
- modifiers per object: type and the settings that matter (Subdivision levels, Bevel width and segments, Mirror axes)
- materials: the Principled BSDF inputs (base color, roughness, metallic), which objects use them
- lights (type, energy), the camera (location, rotation, lens), the render engine and output size
- images saved next to the file (for "a render is saved")

It takes a second or two per run. Blender 4.2 LTS and newer; the script should read settings by name and skip what a version does not have.

**FreeCAD.** `FreeCADCmd <script>` (also spelled `freecadcmd`; inside `FreeCAD.app/Contents/Resources/bin/`, check on a Mac). The script opens the `.FCStd` and prints:

- bodies and their features in order, with type (`PartDesign::Pad`, `Pocket`, `Fillet`, `LinearPattern`, `Mirrored`) and their main number (pad length, fillet radius, pattern count)
- sketches: support plane, constraint count, and degrees of freedom left (the sketch solver reports 0 when it is fully constrained)
- the final shape: volume, bounding box, whether it is one valid solid
- whether every feature recomputes with no error

**STL (any CAD app).** A pure Python reader, no app needed: triangle count, bounding box, volume, and whether it is watertight (every edge shared by exactly two triangles). This covers "export an STL to print" for FreeCAD, Fusion, Onshape and Tinkercad alike.

### Live level

Same JSON, sent by an add-on inside the app to the engine on localhost each time the model changes, so a step turns green the moment it is right with no save.

- **Blender add-on** (Python): listens for scene changes (`bpy.app.handlers.depsgraph_update_post`), waits a beat (`bpy.app.timers`), sends the scene JSON. It can also select or frame an object when the coach points at it. Shipped as one zip the app installs; the learner switches it on once.
- **FreeCAD**: a document observer (`FreeCAD.addDocumentObserver`) that sends the same model JSON after each recompute.
- **Fusion**: a Python add-in that reads the timeline and bodies after each command. Fusion files live in Autodesk's cloud, so file level does not apply there; it is live or screen.
- **Onshape**: no local app. It would be the Onshape REST API after the learner signs in, which is a cloud feature. Later.
- **AutoCAD, Tinkercad, Figma, Excel, Sheets**: screen only for now.

## New check kinds (contract ask)

Each takes the scene JSON and a few numbers. `tol` is a tolerance. These map one to one onto the `passes` lines in the catalog.

| Kind | Reads | Example from a plan |
|---|---|---|
| `scene.object` | type, name, count | "The document has one empty body" |
| `scene.transform` | location, rotation, scale, tol | "The cube is at X 2, the cone is turned 90 degrees" |
| `mesh.count` | verts or faces, compare, n | "The mug has two new edge loops" |
| `mesh.one_piece` | connected | "The handle joins the mug and the mesh is one piece" |
| `modifier` | type, settings | "A Subdivision modifier at level 2" |
| `shading.smooth` | object | "Smooth shading is on" |
| `material` | input ranges | "A material with roughness under 0.3" |
| `light` | type, count | "The scene has an area light" |
| `camera.sees` | object inside the camera frame | "The camera sees the whole mug" |
| `file.saved` | extension, newer than the step | "A PNG render is saved next to the .blend file" |
| `cad.sketch` | plane, closed, degrees of freedom | "The sketch has no free movement" |
| `cad.feature` | type, length or radius, count, tol | "A pad 5 mm long", "At least four edges carry a 2 mm fillet" |
| `cad.size` | bounding box, tol | "A 60 by 40 by 5 mm solid" |
| `cad.rebuilds` | no recompute errors | "Every feature still rebuilds" |
| `stl.watertight` | closed mesh, bounding box | "A watertight STL is saved" |

## What the app needs to show (contract ask)

Mocked in `ui-next/mock` (screens `settings-apps`, `plan`, `lesson-blender`).

- Per app, a state: `connected` (file or live level works), `available` (installed, not connected), `screen_only`. Plus the app version and add-on version. Settings > Apps lists them with one Connect button each.
- Per lesson, how it is checked: `screen`, `file` or `live`. The lesson and plan pages show it as one row, "Checked by: reading your scene".
- A setup row, "Connect Blender", beside the install rows that exist today.
- When a check needs a save and the file is older than the step: one line, "Save to check (Cmd S)".

## Order

1. Blender, file level, with `scene.object`, `scene.transform`, `modifier`, `shading.smooth`, `material`, `file.saved`. That alone covers 9 of the 10 lessons in Intro to Blender.
2. FreeCAD, file level, with `cad.sketch`, `cad.feature`, `cad.size`, `cad.rebuilds`. Covers Intro to CAD.
3. STL reader. Covers the last lesson of every CAD plan.
4. Blender live add-on.
5. FreeCAD observer, then Fusion add-in. Onshape with the cloud.

## What could go wrong

- The learner has not saved. Handle with the "Save to check" line, never a silent wait.
- Two Blender versions installed, or Blender not in /Applications. The setup scan already finds apps; reuse its path.
- A long headless run on a heavy scene. Lessons use small scenes; cap the run at a few seconds and fall back to screen.
- API names differ between Blender 4.2 and 5.x, and between FreeCAD 0.21 and 1.0. Read by name, skip what is missing, and test both.
- A file the learner made outside the lesson folder. Ask once which file to check, then remember it for the lesson.
