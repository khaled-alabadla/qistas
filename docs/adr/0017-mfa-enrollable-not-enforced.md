# ADR-0017 — MFA enrollable in Phase 1, not enforced

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0010, ADR-0026, grill L1

## Context

Legal data is a high-value target, so MFA matters — but forcing it during early development and demos is disruptive, and enforcement policy is better decided once the app is real.

## Decision

- **`django-otp` + TOTP is installed and wired in Phase 1.**
- **Enrollment is available in Phase 1**: a working "set up authenticator app" flow (QR + verification), per-user opt-in, with recovery codes.
- An **enforcement middleware exists but is setting-gated and OFF by default** (`REQUIRE_MFA` / `MFA_ENFORCED_GROUPS` settings, both empty/false in v1).
- **MFA is NOT mandatory for anyone in v1 — including office managers.**
- Global or per-group MFA enforcement is decided during the **security hardening phase (Phase 12)**.

## Consequences

- Security-conscious users can protect their accounts immediately.
- No friction imposed on the office before they choose it.
- Turning enforcement on later is a settings change + a user-comms exercise, not a code project.
- Phase 1 tests cover: enrollment, TOTP verification, recovery codes, and that the (disabled) enforcement middleware correctly gates when the setting is flipped in a test.

### Refinement (Phase 1 implementation, 2026-09-08)

"Not enforced" applies to **enrollment**, not to **completion**. Once a user has
a confirmed authenticator, passing the OTP step is **mandatory** for that user on
every session — `MFAEnforcementMiddleware` bounces an enrolled-but-unverified
session to `accounts:mfa_token` regardless of `REQUIRE_MFA` /
`MFA_ENFORCED_GROUPS`. Otherwise opt-in MFA would give no real protection (a
`/code-review` finding). The setting-gated part is only *forcing enrollment* on
users who have not opted in.
