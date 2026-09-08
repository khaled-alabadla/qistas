# ADR-0016 — Western digits for numbers, dates, money

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0003, ADR-0024, grill J3, J4

## Context

Django's `ar` locale can format numbers with Arabic-Indic digits (٠١٢٣…). MENA business and legal software practice varies; the owner wants consistency and unambiguous financial/identifier display.

## Decision

**Use Western digits (0–9) for:**
- IDs and reference numbers (case, client, invoice, contract).
- Dates (where technically appropriate).
- Monetary values.

Arabic UI text remains Arabic and RTL. **Do not force Arabic-Indic digits anywhere.**

Implementation:
- `USE_L10N` behaviour is pinned via an explicit `FORMAT_MODULE_PATH` so locale changes never flip digit systems.
- Numbers, identifiers, money, and dates are rendered through a bidi-safe helper (`{% num %}` / `<bdi>`) so they display left-to-right correctly inside RTL text (ADR-0024).

## Consequences

- Consistent, unambiguous financial and identifier display.
- Predictable string matching/search on numbers.
- If a future requirement wants Arabic-Indic digits for a specific document type (e.g. a printed legal filing), that is a localized formatting choice at that template, not a global change.
