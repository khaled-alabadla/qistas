# ADR-0023 — Dev/prod parity: Dockerized dev + PostgreSQL 16 baseline

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0025, ADR-0026, grill K1, K2, G4

## Context

The dev machine is Windows 11; production will be Linux. Running Django natively on Windows while only Postgres is containerized creates a parity gap that surfaces at deploy: `libmagic`, file-path case sensitivity, PostgreSQL collation, future `WeasyPrint` (Cairo/Pango, effectively unavailable on Windows), and cron.

## Decision

- **The application runs in Docker in development.** `docker-compose.yml` defines `web` (Django, Linux image, non-root) and `db` (`postgres:16`). Code is bind-mounted; commands run via `docker compose exec web ...`. Windows is the editor host only; Django is never run natively on Windows.
- **PostgreSQL 16** pinned. Extensions `pg_trgm` and `unaccent` are enabled via `CreateExtension` migrations in Phase 1. An ICU collation is used for Arabic-aware sorting on text columns where sort order matters.
- A named `media` volume is declared in compose from Phase 1 (uploads arrive in Phase 6) so file data survives container rebuilds.
- `settings/test.py` targets PostgreSQL — **tests never run on SQLite** (the schema relies on PG-specific constraints, partial/functional indexes, and extensions).
- CI uses the same PostgreSQL 16 (service container), so CI ≈ dev ≈ prod.

## Consequences

- One-command onboarding (`docker compose up`); no "works on my Windows machine".
- Deploy-time surprises are minimized; PDF work (Phase 10) is developable locally.
- Slightly heavier local resource use; acceptable.
- Production compose adds `nginx` and swaps settings; documented in Phase 14.
