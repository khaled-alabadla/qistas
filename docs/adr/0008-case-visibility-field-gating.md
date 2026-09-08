# ADR-0008 — Case visibility + independent sensitive-field gating; no siloing in v1

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0007, ADR-0019, grill C3, C4, X4

## Context

Spec §15 demands strict per-object authorization (changing `/cases/15/` to `/cases/16/` must fail). Spec §17/§43 show office-wide dashboards and reports ("cases by lawyer", "all cases by status"). These pull in opposite directions. Separately, spec §92 requires that internal legal notes and financial data not be exposed to staff who don't need them.

## Decision

**v1 case visibility:**
- **All staff (all groups) can see all office cases** in lists, detail pages, and aggregates.
- **Editing** a case is gated by capability + (later) assignment.
- **Object-level authorization is still enforced** structurally (via `for_user()` scoped querysets and `get_object_or_404` on the scoped queryset — ADR-0019) so the pattern is in place from day 1 and tightening it later is config, not rework.
- **No strict lawyer-to-assigned-case siloing in v1.**

**Sensitive-field gating (independent of case visibility):**
- `internal_notes` / `legal_notes` and financial figures are gated by **separate** capabilities (e.g. `cases.view_legal_notes`, `finance.view`), not by "can you see the case".
- Case confidential fields are stored on a **`CaseConfidential` 1:1 side model** (built in Phase 3) so a field that was never selected cannot leak into exports, HTMX partials, `__str__`, audit diffs, search snippets, or error pages.
- A single `case.for_display(user)` projection is the only rendering path for a case.

## Consequences

- Denial response is **HTTP 403** with a clear Arabic message (not 404) — v1 has no enumeration threat and 404 hurts operability.
- The permission-matrix test suite covers: capability checks, object-level structural checks, field-level gating, and URL-tampering — from the phase each entity appears.
- Moving to stricter siloing later = changing the `for_user()` scoper for `Case` and flipping the 403/404 policy; the call sites don't change.
