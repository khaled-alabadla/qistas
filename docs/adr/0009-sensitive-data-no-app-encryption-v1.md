# ADR-0009 — No app-level encryption in v1; sensitive-field handling rules

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0020, ADR-0023, grill D1, E2

## Context

`national_id`, internal/legal notes, and document contents are the system's most sensitive data. Application-level field encryption is a real project (key management, migration, loss of queryability). The grill flagged that no protection decision existed.

## Decision

**No application-level field encryption in v1.**

Confidentiality rests on:
1. **Infrastructure encryption** — PostgreSQL / disk-volume / object-storage encryption at rest (deployment concern, documented in Phase 14).
2. **Secure application handling** of a small, centrally-listed set of highly-sensitive fields (`core/sensitive.py::SENSITIVE_FIELDS`). For every field in that set:
   - **Never written to logs** (app logs, request logs, error reports) — enforced by a logging filter + review.
   - **Never surfaced** in UI, exports, notifications, `__str__`, or `object_repr` unless strictly required by the feature.
   - **Access is permission-gated** (its own capability).
   - **Not trigram-indexed** and **excluded from global search** — no incidental exposure via search.
   - Audit logs record *"changed"* without old/new values (ADR-0020).
3. `national_id` and equivalents are **optional** fields; collection must be justified per field.

**Extension point:** a pluggable encrypted-field wrapper (e.g. `pgcrypto` column-level, or `django-cryptography`) can be introduced later for the `SENSITIVE_FIELDS` set without a schema redesign, because the set is small and centrally defined.

## Consequences

- Faster v1; no key-management burden yet.
- The deployment's disk/DB encryption is a **hard requirement** for production sign-off (Phase 14 checklist).
- Any new sensitive field must be added to `SENSITIVE_FIELDS` in the same change, and the handling rules apply automatically where they're wired (logging filter, search exclusion, audit allowlist).
