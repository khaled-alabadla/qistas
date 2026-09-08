# ADR-0003 — i18n-ready architecture, Arabic-first UI

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0016, ADR-0024, grill J1

## Context

Arabic is the primary language. The spec (§63) warns against wasting effort on unneeded i18n, but the owner confirms English must be supportable later. Retrofitting `gettext` across 14 phases of templates and models is far more expensive than being disciplined from the start.

## Decision

**Build i18n-ready from day 1; ship Arabic only.**

- `USE_I18N = True`, `LocaleMiddleware` enabled, `locale/` directory in the repo.
- Every human-facing string goes through `gettext`: `_()` in Python, `{% translate %}` / `{% blocktranslate %}` in templates. Model `TextChoices` labels are translatable.
- `LANGUAGE_CODE = "ar"`. Only the `ar` catalog is maintained and shipped in v1. An `en` catalog may be stubbed but is not a Phase 1 deliverable and is not kept current.
- Phase 1 UI is Arabic-first and RTL.
- No language switcher UI in v1.

## Consequences

- Small ongoing discipline cost (wrap strings, compile messages) with a clean path to English later.
- Forces separation of copy from logic — a net positive.
- `makemessages` / `compilemessages` become part of the build; CI can check for un-wrapped strings later.
- Translators can be engaged for English without touching code.
