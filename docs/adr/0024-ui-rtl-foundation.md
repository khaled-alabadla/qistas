# ADR-0024 — UI / RTL foundation

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0003, ADR-0016, grill J2, J3

## Context

Spec §7 demands native RTL, not a superficial `direction: rtl`. The grill flagged that `tailwindcss-rtl` is largely unmaintained and that mixed Arabic/Latin content (case numbers, money, dates, emails) scrambles without bidi isolation.

## Decision

- `<html lang="ar" dir="rtl">`.
- **Tailwind CSS (standalone CLI build), using native logical utilities only** — `ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start` / `text-end`, `start-*` / `end-*`, `border-s` / `border-e`. **No RTL plugin.**
- **Bidi isolation:** every number, identifier, monetary value, date, email, and phone number is rendered through a `{% num %}` template helper that wraps it in `<bdi>` (with `dir="ltr"` where appropriate). Reviewed against realistic mixed data.
- **Self-hosted IBM Plex Sans Arabic** (`@font-face`, `font-display: swap`, subset, `unicode-range`). One primary family, used consistently (spec §6).
- **Design tokens** as CSS custom properties + Tailwind theme extension: deep navy, dark slate, warm off-white, neutral gray, subtle bronze accent — restrained, no heavy gradients/glass/blobs (spec §5, §95).
- **Reusable component kit** in `core/templates/components/` covering the spec §49 list (button, input, textarea, select, date field, card, table, badge, modal, dropdown, tabs, breadcrumb, alert, toast, pagination, empty-state, loading-state, confirm-dialog, file-upload). A dev-only `/styleguide` page renders them all.
- **HTMX + Alpine.js vendored** into `static/vendor/` (not CDN). Global CSRF wiring for HTMX in `base.html`.
- **Themed error pages** 400 / 403 / 404 / 500 — Arabic, RTL, on-brand.
- **Navigation** is data-driven and filtered through the capability layer (ADR-0007); mobile-collapsible via Alpine.

## Consequences

- Getting RTL right once, in the kit, means templates in later phases inherit it.
- No dependency on an unmaintained RTL plugin.
- The component kit and styleguide are Phase 1 deliverables.
