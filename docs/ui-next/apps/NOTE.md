# MIC-87: show the apps miyagi works in

Nov 24 2026. Adrian reviewed the draft and picked what is below. Screens: `mock/apps.js`, renders in `shots/apps/`. HTML mock rendered to PNG, not Figma.

**The pattern.** On a new learner's Home, "Start here" becomes **Learn in**: one table, a row per app. A row says what the app is for, the plan to start with, and whether the app is on this Mac. A returning learner gets the same list as a short block at the foot of the rail.

**Why.**
- It adds no box. The three "Start here" cards were already one per app (Python in VS Code, Blender, CAD in FreeCAD). The table is the same content with the app in front, and Fusion gets a row it never had.
- One row holds the app, where to start and its state. A row of icons has no room for state. A "Connect your apps" card would be a second setup box beside Set up.
- A list grows by a row: 4 apps is 4 rows, 10 apps is 8 rows and a "Soon" line. Nothing is redesigned.
- "Projects grouped by app" is where a row leads, not Home.

**A click** opens the app's page (Library / Browse plans / Blender): its first plan with one Start button, the first five lessons with what passes each, its other plans, and "make your own" from a video or a goal. Start opens the app and shows step one. A click never starts a lesson straight from Home and never opens the app with nothing to do in it.

**States.**
| State | On Home | On the app's page |
|---|---|---|
| Installed | check, "Installed" | Start button |
| Not installed | "Get Fusion", opens the owner's download page | lessons stay visible; "Get Fusion" and "I have it", the two actions the setup card already has |
| Soon | one line of names under the table, no rows, no click. Off today: it shows once an app is really coming (the ten-app screens show it) | no page |
| In your browser | appears when a web app (Onshape, Google Sheets) joins | Start button |

**What it replaces on Home.** New learner: the three plan cards, and the "VS Code · Found" row in Set up (the table says it for every app). Returning learner: nothing; one block is added under Keep fresh, at most five rows.

**The alternative (B), not picked.** One line under the ask field, "Learn in VS Code, Blender, FreeCAD, Fusion", the same on both Homes, Home otherwise untouched. It is the smallest change. State is only a tone and an arrow, it says the same apps the cards below it say, and at 10 apps it wraps to two lines.

**Marks: names only.** Not legal advice.
- VS Code (Microsoft): the brand page allows the icon in tutorials or articles about VS Code and in links to its site, and lists as not OK using it "to identify or promote your own product". Doubtful; ask vscode@microsoft.com.
- Fusion (Autodesk): product icons need permission and an agreement. Name only, written "Autodesk Fusion" in full the first time.
- Blender: could not be confirmed, blender.org blocked the fetch. Reported rule: the logo complete with its wordmark, unaltered, your own brand larger; use inside a commercial product on request.
- FreeCAD: allowed unmodified, 32 px or larger in color, pointing to freecad.org.
One mark out of four would look broken, so every row is a name. The row has a slot for a mark if they are cleared later.

**Still open, for Michael.** Which apps are really coming, so the "Soon" line has names (the ten-app screens use stand-ins). Whether notebook and terminal lessons count as VS Code (the mock assumes yes). "Checked by" on the app's page says "Reading your scene" for Blender and "Looking at the window" for FreeCAD and Fusion, which needs his yes.
