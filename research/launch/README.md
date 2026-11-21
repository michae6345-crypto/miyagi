# miyagi launch risk research

Adrian's claim for Michael's launch-risk brief (Nov 21, 2026, v2, which replaces the edge-case brief).
Big launch risks only. Small UI edge cases are parked in `later.md`.

| Area | Files |
|---|---|
| A. Security and money | `security.md` |
| B. Privacy and legal | `privacy-legal.md`, `cookies.md` (banner yes or no), `privacy-review.md` (review of #199's `web/privacy.md`), `../../web/terms.md` |
| C. Distribution and deploy | `distribution.md` |
| D. Landing page and launch | `launch.md` |
| E. Product failures | `product.md` |
| Consolidated | `RISKS.md` (ranked register), `launch-checklist.md`, `later.md` |

Register columns: id, area, risk, evidence (link), applies to miyagi (where), severity (P0, P1, P2), fix, owner, status.

Rules
- Security findings that could be exploited stay out of this public repo until fixed. The register gets a one-line placeholder and the details go to Michael directly.
- Engine and cloud findings are written up for Michael, not patched.
- Offline only: no lessons through miyagi-cloud, no paid API calls.
- Not legal advice. Items that need a lawyer are marked.

Inputs: #202 (first pass: `docs/BUG-RISKS.md`, `docs/legal/`) and #201 (suggested edits to `web/privacy.md` for #199).
