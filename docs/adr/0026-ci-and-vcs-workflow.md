# ADR-0026 — CI pipeline and VCS workflow

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0010, ADR-0023, ADR-0025, grill N1, N2

## Context

The spec is security-first (§54, §65) and process-heavy (per-phase code review, §69). The Phase 0 CI proposal was thin and there was no branching model; the repo is on `master` with no commits while the harness expects `main`.

## Decision

**CI — GitHub Actions, on every push and PR:**
- PostgreSQL 16 service container.
- `ruff` (lint) + `ruff format --check`.
- `pytest` + coverage (artifact uploaded).
- `python manage.py makemigrations --check --dry-run` (fails if a model change lacks a migration).
- `python manage.py check --deploy` against production settings.
- `pip-audit` (dependency vulnerabilities).
- `gitleaks` (committed-secret scan).

**Local:** `.pre-commit-config.yaml` mirrors the fast checks (ruff, ruff format, `makemigrations --check`, gitleaks).

**VCS:**
- Rename `master` → `main`.
- Work on `phase/N-<name>` branches.
- Open a PR into `main` per phase; CI + `/code-review` gate the merge.
- After explicit user approval of a phase, tag `phaseN-approved` on `main`.
- Commit style per spec §86 (`feat(scope):`, `fix(scope):`, `security(scope):`, `test(scope):`).
- No secrets committed; `.env` gitignored; `.env.example` committed.

## Consequences

- Every phase's work has a natural review/CI gate.
- Vulnerable dependencies and leaked secrets are caught automatically.
- Phase 1 delivers the CI workflow file, the pre-commit config, and performs the `master`→`main` rename as its first action.
