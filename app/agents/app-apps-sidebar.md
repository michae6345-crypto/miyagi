# app-apps-sidebar

**Status:** first pass done (Nov 25) · **Port:** 5822 · **Branch:** `michael/app-apps-sidebar`

## Goal
Michael: "on the left side shouldn't some apps be there, and you can add the apps you want so you can have all the
lessons and info for those." The home window's sidebar gets an **Apps** section: the learner's apps with a glyph, a
click opens the app's page, and **Add app** opens a small picker to pin or unpin apps.

## What shipped
- **Sidebar** (`features/shell/Sidebar.tsx` feeds `features/apps/SidebarApps.tsx`): "Apps" right under Progress, one
  row per app (neutral line glyph + the catalog's name; "Not installed" on the right when the scan says so), the open
  app's row marked (Library is then not marked), then **Add app**. Compact sidebar: glyphs only, names as tooltips.
  Picking Library from an app's page (its row, the arrow keys or ⌘2) lands on the Library list (`apps/store.ts`
  `goToPage`, `model.ts` `libraryNavResets`); Library again from Browse plans or a plan also goes back to the list.
  `SideRow` / `SideLabel` moved from Sidebar.tsx into `shell/ui.tsx` so the section renders from plain data.
- **Default list** (`pinnedApps: null`): apps installed on this Mac, plus apps the learner has lessons or plans in
  that nothing says are missing; with nothing known at all, the four supported apps.
- **Picker** (`features/apps/Picker.tsx`): "Apps in your sidebar", a tick per supported app (VS Code, Blender,
  FreeCAD, Fusion) with its install state and an Open chevron, then **Soon**: one greyed line of the catalog's other
  tools (Arduino IDE ... Xcode), no clicks. "Reset to default" once the learner has pinned. Esc, click outside or
  window blur closes it.
- **Pins are an app pref** (`common/prefs.ts`): `pinnedApps: string[] | null` and `haveApps: string[]` ("I have it"),
  sanitized like the rest (ids `^[a-z0-9][a-z0-9-]{0,31}$`, each once, capped at 24; `null` resets). Saved by main in
  prefs.json, never sent to the engine.
- **Installed?** (`main/features/apps.ts`, `apps:installed`): a fixed list of bundle names checked with `existsSync`
  in /Applications and ~/Applications (Visual Studio Code.app, Blender.app, FreeCAD.app, Autodesk Fusion(.app / 360.app)).
  Off macOS it says nothing (unknown). VS Code also reads the engine's health rows (`vscode`, or the companion's fix
  `get_vscode` / `install_companion`). "I have it" wins over the scan.
- **App page** (`features/apps/AppPage.tsx`, plans view `{kind: 'app'}`, crumbs Library / Browse plans / Blender, the
  MIC-87 mock): the name (Autodesk Fusion in full), On this Mac / To learn / Checked by / Starts with, the start plan's
  picture and one action: **Start <plan>** (Continue when going; "Start plan" when the name is too long) or, when not
  installed, **Get <app>** (VS Code and Blender only: their pages are on main's setup list) and **I have it**; the
  lessons stay. Then the start plan's first five lessons (rows open the plan), **Yours in <app>** (Library lessons open
  their preview, own playlist/goal plans open the plan), **More in <app>** (other catalog plans, 8 then Browse plans),
  **Skills in <app>** (chips, link to Skills), **Make your own in <app>** (video / goal dialogs).
- **Home "Learn in"** (`features/apps/LearnIn.tsx`): Adrian's small block at the foot of the returning learner's rail,
  a row per app ("7 lessons", the plan to start with, or "Not installed" / "Get VS Code"); a click opens the app page.
  The first-run Home (his table replacing Start here) is left alone: it reshapes that page, the Home lane's call.

## Data (no lesson names in UI code)
`features/apps/model.ts`: apps from the plans catalog (`tool.id` / `tool.label`); Jupyter and Terminal plans count as
VS Code (Adrian's open question, the mock assumes yes). A Library lesson's app is inferred from its own fields: the
plan that holds it (PlanLesson.libraryId → plan tool), the skills it teaches/uses (catalog skill → plan tool), a
catalog lesson title, then `tools`. The start plan: the learner's plan going here, else START_HERE's, else the first
"start" plan.

## Test
`npm run dev:web -- --port 5822` →
- `http://localhost:5822/?scenario=apps&window=library&size=1440x900&page=home` (sidebar, Learn in; click Add app)
- `...&page=lessons&app=blender` / `&app=vscode` / `&app=fusion` (app pages)
- `&apps=all|none|unknown` changes the stand-in scan (`features/apps/web.ts`); `&appearance=dark`.
Tests: `test/appsSidebar.test.ts` (prefs sanitize, main scan, catalog apps, filtering by app, install state, sidebar
list and picker toggles, sidebar rendering). Shots: `agents/shots/apps-*.png` (sidebar, picker, Blender, VS Code in
light and dark; Fusion not installed in light).

## Open
- FreeCAD and Fusion have no Get button: freecad.org and autodesk.com are not on main's setup list (safeOpen.ts).
  Add their download pages there (a security review item) and set `getUrl` in model.ts.
- Adrian's "Checked by" wording for Blender / FreeCAD / Fusion needs Michael's yes; the page uses plans/catalog
  `checkedBy()` as the plan page does.
- Settings > Apps still has its own placeholder list (settings/v4/facts.ts); it could read model.ts later.

## Core requests
- `common/prefs.ts`: `pinnedApps`, `haveApps` (done in this lane, as the brief asked: "core prefs, like other Settings prefs").
