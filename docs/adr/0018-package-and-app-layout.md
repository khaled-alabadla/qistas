# ADR-0018 — Package/app layout, naming, and layering

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0019, grill A1, A2, A3, A4, X6

## Context

The Phase 0 proposal scaffolded 16 apps up front, nested under `apps/`, renamed the spec's `core/` to `common/`, and mandated `services.py` + `selectors.py` in every app. The grill flagged over-structuring, an unjustified rename, and premature abstraction against spec §10/§298.

## Decision

**Layout**
- Project package: `config/` (`settings/{base,dev,prod,test}.py`, `urls.py`, `wsgi.py`, `asgi.py`).
- Apps at repo root, **created only when their phase starts.**
- **Phase 1 creates exactly three apps: `core`, `accounts`, `audit`.**
- `core` (per spec §11), **not** `common`.
- The calendar app will be named **`agenda`** — `calendar` shadows the Python standard-library module. This rename is justified and recorded (spec §11 permits structural adjustment when justified).

**Layering**
- Per-app: `models.py`, `forms.py`, `views.py` (thin), `urls.py`, `admin.py`, `templates/<app>/`, `tests/`.
- `selectors.py` (permission-scoped read queries) and `services.py` (multi-step transactional writes) are introduced **only where they earn their place** — e.g. payment recording, hearing completion, document upload. Trivial CRUD uses fat models + forms.
- The **one** always-on cross-cutting pattern is permission-scoped querysets (`for_user()`) and the view mixins that require them (ADR-0019).

## Consequences

- No empty/dead apps (spec §64).
- No import cycles created "to be ready".
- Contributors read a lean structure; abstraction appears where complexity does.
- `docs/architecture.md` keeps the informational app roadmap.
