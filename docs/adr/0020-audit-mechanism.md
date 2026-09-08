# ADR-0020 — Audit mechanism: django-auditlog + explicit events + field allowlist

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0009, ADR-0010, grill E1, E2, E3

## Context

Spec §46 wants an audit trail with actor, IP, and old/new value diffs; §93 wants it hard to tamper with. The grill flagged that "signals without thread-locals" can't capture actor+IP, that the diff store becomes an unprotected copy of the sensitive data, and that true immutability needs the DB.

## Decision

- **`django-auditlog`** for automatic model-change capture, **with its actor middleware** (thread-local for actor identity only — the standard, well-tested approach). Models are registered as each phase introduces them.
- **Explicit `log_event(request, action, obj=None, changes=None)`** for non-ORM events: login, logout, failed login, lockout, password change/reset, user created, group-membership change, and later document download (Phase 6), permission change, report export (Phase 10).
- **Field-diff allowlist.** Sensitive fields (`core/sensitive.py::SENSITIVE_FIELDS` — internal/legal notes, `national_id`, financial figures, document contents) are logged as *"changed"* with **no** old/new values. `object_repr` must not embed sensitive text.
- **Same-permission audit views.** Viewing an audit record enforces the same object/field permissions as the underlying record. "Viewed audit log" is itself audited.
- **IP is `REMOTE_ADDR`.** `X-Forwarded-For` is client-controlled and is used only when `AUDIT_TRUST_XFF=True` (a trusted proxy re-sets it); the value is validated as a real IP.
- **`AuditLog` model:** `actor` `on_delete=SET_NULL`; **no ORM/admin delete**; indexes on `created_at`, `(entity_type, entity_id)`, `actor`.
- **Deferred to Phase 12:** a DB-level `BEFORE DELETE/UPDATE` trigger (or a DELETE-less DB role) and monthly partitioning. The model is designed not to fight these.

## Consequences

- Actor + IP + user-agent captured reliably; automatic diffs for non-sensitive fields.
- The audit trail does not become a backdoor to privileged content.
- Phase 1 builds `AuditLog`, `log_event`, the auth-event receivers, the allowlist infrastructure, and read-only/delete-disabled admin — with tests. Model registration for domain entities happens in their phases.
