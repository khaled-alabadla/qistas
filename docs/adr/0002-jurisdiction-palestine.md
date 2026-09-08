# ADR-0002 — Target jurisdiction: Palestine; extensible jurisdiction rules

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0003, ADR-0016

## Context

Jurisdiction drives national-ID formats, commercial-registration formats, court hierarchy and naming, tax model, invoice legal requirements, data-retention rules, and whether Hijri dates are expected. The spec did not name a country.

## Decision

**The target jurisdiction is Palestine.** Jurisdiction-specific rules (ID validation, court structure, tax) are designed to be **extensible** — isolated behind small, replaceable modules/config — but are **not built out in Phase 1**. Phase 1 introduces no jurisdiction logic at all (no domain models).

Specifics deferred until their phase:
- National-ID / registration-number validation → Clients phase (Phase 2), permissive by default.
- Court hierarchy / naming → Courts phase (Phase 4).
- Tax model (VAT rate, invoice requirements) → Finance phase (Phase 8).
- **Hijri date display** → deferred; Gregorian is primary. Extension point: a date-formatting helper that can gain a secondary calendar.

## Consequences

- No premature investment in a jurisdiction rules engine.
- Currency default: ILS (with a configurable setting; multi-currency is out of scope for v1 but a `currency` field is stored — see architecture §13).
- Locale conventions (week start, date format) follow Palestine norms; digits are Western (ADR-0016).
- Should the office also operate under another jurisdiction later, the isolated modules are the change surface.
