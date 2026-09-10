# Architecture Decision Records — Qistas

Each ADR records one decision: its context, the decision, and its consequences.
Format: lightweight (Nygard-style). Status is one of `Proposed` / `Accepted` / `Superseded by ADR-XXXX` / `Deprecated`.

All ADRs below were **Accepted 2026-09-08** (owner: Khaled; architect: Claude) as the outcome of `QISTAS_GRILL_REVIEW.md`.

| ADR | Title | Blocks Phase 1? |
|---|---|---|
| [0001](0001-single-tenant.md) | Single-tenant architecture for v1 | Yes |
| [0002](0002-jurisdiction-palestine.md) | Target jurisdiction: Palestine; extensible jurisdiction rules | Yes |
| [0003](0003-i18n-ready-arabic-first.md) | i18n-ready architecture, Arabic-first UI | Yes |
| [0004](0004-login-identifier-email.md) | Work email is the authentication identifier | Yes |
| [0005](0005-no-async-worker-v1.md) | No async worker in v1 — management commands + cron | Yes |
| [0006](0006-overdue-is-computed.md) | "Overdue" is a computed state, not a stored status | Yes |
| [0007](0007-rbac-groups-capabilities.md) | RBAC via Django Groups + centralized capability layer | Yes |
| [0008](0008-case-visibility-field-gating.md) | Case visibility + independent sensitive-field gating; no siloing in v1 | Yes |
| [0009](0009-sensitive-data-no-app-encryption-v1.md) | No app-level encryption in v1; sensitive-field handling rules | Yes |
| [0010](0010-security-in-every-phase-dod.md) | Security/audit/testing/a11y/perf in every phase DoD; 12/13 are hardening | Yes |
| [0011](0011-invoice-numbering-not-gap-free.md) | Invoice numbering: transaction-safe unique, not gap-free | No (Phase 8) |
| [0012](0012-issued-invoices-immutable.md) | Issued invoices are immutable; corrections via credit note | No (Phase 8) |
| [0013](0013-fee-agreement-not-expense.md) | "رسوم القضايا" modelled as FeeAgreement, not Expense | No (Phase 8) |
| [0014](0014-conflict-of-interest-deferred.md) | Conflict-of-interest checking deferred | No |
| [0015](0015-client-portal-deferred.md) | Client portal deferred | No |
| [0016](0016-western-digits.md) | Western digits for numbers, dates, money | Yes |
| [0017](0017-mfa-enrollable-not-enforced.md) | MFA enrollable in Phase 1, not enforced | Yes |
| [0018](0018-package-and-app-layout.md) | Package/app layout, naming, and layering | Yes |
| [0019](0019-object-level-authz-pattern.md) | Object-level authorization enforcement pattern | Yes |
| [0020](0020-audit-mechanism.md) | Audit mechanism: django-auditlog + explicit events + allowlist | Yes |
| [0021](0021-reference-number-generation.md) | Reference-number generation (NumberSequence) | No (Phase 2) |
| [0022](0022-soft-delete-and-on-delete-policy.md) | Soft-delete, archival, and on_delete policy | Yes (policy) |
| [0023](0023-dev-prod-parity-docker-postgres.md) | Dev/prod parity: Dockerized dev + PostgreSQL 16 baseline | Yes |
| [0024](0024-ui-rtl-foundation.md) | UI / RTL foundation (Tailwind logical utilities, bidi, font) | Yes |
| [0025](0025-testing-strategy-tiered.md) | Tiered testing strategy | Yes |
| [0026](0026-ci-and-vcs-workflow.md) | CI pipeline and VCS workflow | Yes |
| [0027](0027-password-reset-mechanism.md) | Password reset: email flow + admin temporary password | Yes |
| [0028](0028-hearings-calendar-and-derived-next-hearing.md) | Hearings, calendar, derived `Case.next_hearing` | Yes (Phase 4) |
| [0029](0029-tasks-and-deadlines.md) | Tasks + deadlines: two models, computed overdue, calendar | Yes (Phase 5) |
| [0030](0030-documents-storage-and-access.md) | Documents: private storage, validated uploads, audited downloads | Yes (Phase 6) |
| [0031](0031-contracts.md) | Contracts: real status lifecycle + computed expiry, never deleted, `Document.contract` seam | Yes (Phase 7) |
| [0032](0032-finance.md) | Finance: stored totals frozen at issue, row-locked overpayment guard, credit-note / reversal corrections, computed overdue, finance is NOT all-staff | Yes (Phase 8) |
| [0033](0033-dashboard.md) | Dashboard: it *is* the landing page; a read/analytics layer owning no models; every widget capability-gated in the query; CSS bar charts (no Chart.js); per-currency, never summed | Yes (Phase 9) |
