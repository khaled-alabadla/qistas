# ADR-0027 — Password reset: email flow + admin temporary password

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0004, ADR-0005, grill L3

## Context

Spec §14 requires a password-reset architecture. Login identity is work email (ADR-0004), so self-service email reset works for all users — but an office still needs a fallback when a user cannot access their mailbox, and there is no async worker to lean on (ADR-0005).

## Decision

- **Self-service:** Django's built-in password-reset flow (`PasswordResetView` → email → `PasswordResetConfirmView` → complete), with themed Arabic RTL templates. Email is sent **synchronously in the request** (acceptable at office volume).
  - Dev: `console` email backend.
  - Production: a real SMTP/provider, configured via env vars — **wired in Phase 14**, not Phase 1.
- **Admin fallback:** an admin action (capability-gated, audited) — "issue temporary password" — that sets a random password and forces a change on next login (`must_change_password` flag + middleware redirect).
- All reset events (requested, completed, admin-issued) are audited via `log_event` (ADR-0020).
- Reset tokens use Django's default generator and timeout (configurable).

## Consequences

- Every user has a self-service path; the office is not blocked when email is unavailable.
- No dependency on a background worker for reset email.
- Phase 1 implements both paths (with console email) and tests them; the production email provider is a Phase 14 configuration task.
