# miyagi launch risk research

Adrian's claim for Michael's launch-risk brief (Nov 21, 2026, v2, which replaces the edge-case brief).
Big launch risks only. Small UI edge cases are parked in `later.md`.

**Start here:** [`RISKS.md`](RISKS.md) for the ranked map and the top 10, then [`SOLUTIONS.md`](SOLUTIONS.md) for what
to do, in what order, and who does it.

### Consolidated (all areas)

| File | What it is |
|---|---|
| [`RISKS.md`](RISKS.md) | The ranked, deduped register: 44 risks (R01-R44) built from the 166 area rows, the top 10, what changed in severity and why, where the areas disagreed and which holds, a coverage table from every area row to its risk, and the independent review |
| [`SOLUTIONS.md`](SOLUTIONS.md) | The fix for each risk (steps, owner, effort, dependencies, how to verify), seven lanes, the plan by phase (Today, before private beta, before public launch, after launch), the critical path, and three lists: founders' decisions, needs a lawyer, needs Michael's Mac or consoles |
| [`launch-checklist.md`](launch-checklist.md) | Must be true before we post publicly, merged from every area: blockers first, then "should be true", each linked to its risk |
| [`later.md`](later.md) | Every area's Later section, merged and deduped, plus the register rows that wait |
| [`risks.json`](risks.json) | The register as data for the visual map: `{id, title, areas, severity, likelihood, owner, effort, phase, sourceRows, solution, decision, lawyer}` |

### By area (the research the register is built from)

| Area | Files |
|---|---|
| A. Security and money | `security.md` |
| B. Privacy and legal | `privacy-legal.md`, `cookies.md` (banner yes or no), `privacy-review.md` (review of #199's `web/privacy.md`), `privacy-legal/sources/` (full source notes), `../../web/terms.md` |
| C. Distribution and deploy | `distribution.md` |
| D. Landing page and launch | `launch.md` |
| E. Product failures | `product.md` (includes the Test 1 script for a clean Mac) |

Area register columns: id, area, risk, evidence (link), applies to miyagi (where), severity (P0, P1, P2), fix, owner,
status. The consolidated register adds likelihood, phase and source rows, and re-judges severity strictly.

Rules
- Security findings that could be exploited stay out of this public repo until fixed. The register gets a one-line placeholder and the details go to Michael directly.
- Engine and cloud findings are written up for Michael, not patched.
- Offline only: no lessons through miyagi-cloud, no paid API calls.
- Not legal advice. Items that need a lawyer are marked.

Inputs: #202 (first pass: `docs/BUG-RISKS.md`, `docs/legal/`) and #201 (suggested edits to `web/privacy.md` for #199).
