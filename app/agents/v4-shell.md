# v4 shell lane: the frame and the tokens

Branch `michael/v4-shell` (from `origin/michael/app-ui-v4`). Source: Adrian's ui-next mock (`docs/ui-next/mock`, v4 shots `22-desktop-ui-v4-*`).

## Status (Nov 24)

Done:
- **Frame** (`features/shell/Shell.tsx`): no inset pane and no dot grid. The sidebar and the page share the window's paper with one hairline between them; a 44 px top bar over every page carries the breadcrumb (the page's name, then a trail a page sets with `setCrumbs`, or the open lesson's title).
- **Sidebar** (`Sidebar.tsx`): 240 wide (216 under a 1100 window, icons only under 860). Brand row with New lesson (compose) on the right; Search with the launcher keycap; Home, Library, Skills, Progress; Plans (from `useSidebarFeed`, hidden while empty); Recent (the library's last three lessons with progress: ink ring, green tick once passed); Settings and the account row at the foot. The engine status line shows only while miyagi is not ready. A page can swap the list for its own (`setSidebarList`: Settings' "one sidebar on screen").
- **Tokens** (`core/theme.ts`): `v4` (sizes), `v4c` (colors, palette `v4-*` in both themes), `v4type` (type ramp). Light keeps the cream paper (#F6F6F3) for page and sidebar; dark sidebar #1D1D1B over the #1B1B1A page (faint ink stays 4.5:1 on both).
- **Primitives** (`features/shell/ui.tsx`) for the page lanes: `PageFrame`, `PageHeader`, `Section` (+ `SectionLink`), `TwoCol` (684 + 316 rail), `Columns` (settings), `Rows` / `ListRow` / `RowChev` / `RowName` / `RowMeta`, `Table<T>`, `Stats`, `Bar`, `Tag`, `PassedMark`, `ProgressRing`, `TopBar`, `setCrumbs`, `setSidebarList`, `setSidebarFeed`. CSS in `styles.css` (`.mg-v4-*`).
- A page opts in by rendering `<PageFrame>`: the shell's legacy title hides for it (CSS `:has`), so the page owns its title, actions and lede. Pages not moved yet keep the shell's title (now 32 / 700, 44 under the top bar).

## How to use (page lanes)

```tsx
<PageFrame>
  <PageHeader title="Library" lede="…" right={<PrimaryButton … />} />
  <TwoCol main={<Section title="Up next" link={{ label: 'Library', onClick }}><Rows><ListRow onClick={…}>…</ListRow></Rows></Section>} rail={…} />
  <Table columns={[…]} rows={…} rowKey={(r) => r.id} />
</PageFrame>
```

## Left / differences vs the mock

- Plans in the sidebar wait for the ui-v4 contract (plans + activity): `setSidebarFeed({ plans })` once it lands.
- Page content (Home, Library, Progress, Settings, Plans) belongs to the page lanes; until they adopt `PageFrame` they sit on the old 720 column.
- Intentional: cream page in light (mock is white), the macOS traffic-light strip above the brand row (40 px; 24 in full screen), no "…" button in the top bar (nothing to put in it), lucide icons for the mock's custom glyphs, keycap text from `platform.keys` ("⌥Space").
- The account avatar is round (AccountSheet's shared avatar, not this lane's file); the mock's is a 22 px rounded square.

## Shots

`app/agents/shots/v4-shell-r3-{ours,mock}-{home,library}-{light,dark}.png`, `v4-shell-r3-ours-w{1024,1280,1728}-light.png`. Stage: `http://localhost:5251/?scenario=full&window=library&size=1440x900&appearance=dark`.

## Core requests

None (theme.ts and styles.css are this lane's).
