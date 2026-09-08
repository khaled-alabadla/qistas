# ADR-0019 — Object-level authorization enforcement pattern

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0007, ADR-0008, grill C1, C2

## Context

Spec §15 requires object-level authorization that URL tampering cannot bypass. The grill flagged that "use `for_user()` everywhere" is convention, not enforcement, and one unscoped queryset in one view is a confidentiality breach.

## Decision

**A defence-in-depth pattern, established in Phase 1 as a framework (no entities yet):**

1. **Explicit scoped queryset.** Every model that has per-object visibility exposes `Model.objects.for_user(user)`. It is an **explicit method** — never the default manager behaviour (so shell, admin, imports, and management commands are not silently filtered, and `.objects.all()` never silently under-returns in a system context).
2. **View mixins require it.** `ScopedListMixin` / `ScopedDetailMixin` obtain the queryset via `for_user(self.request.user)` and `get_object_or_404(scoped_qs, ...)`. A view that renders a per-object model without going through a scoped queryset is a bug.
3. **DEBUG guard.** A `ScopedQuerySet` base tracks whether `for_user` was applied; in `DEBUG`/tests, rendering an un-scoped per-object queryset in a scoped view raises.
4. **Denial → HTTP 403** with a clear Arabic message (v1 has no enumeration threat; 404-on-forbidden hurts support/operability). If strict siloing is adopted later, the policy flips to 404 for the siloed models only — call sites don't change.
5. **Tests.** A permission-matrix test module per entity: `(group × entity × action × ownership)` → allow/deny, plus explicit URL-tampering tests. Helpers: `assert_forbidden` (403), `assert_not_found`, `assert_login_required`.
6. **FK dropdowns, autocomplete, and search** also use `for_user()` — never a raw queryset.
7. **System code** (cron management commands, data imports) uses unscoped `.objects` **deliberately** and is called out in review.

## Consequences

- The safe path is the easy path; the unsafe path fails loudly in dev/test.
- Phase 1 delivers the base classes, mixins, guard, and their tests against a throwaway model.
- Every subsequent entity phase wires its model into this pattern as part of its DoD (ADR-0010).
