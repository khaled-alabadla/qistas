# ADR-0035 — Notifications: a thin in-app inbox fed by idempotent reminder scans

Status: **Accepted** 2026-09-10 (owner: Khaled; architect: Claude)
Phase: 11
Builds on: ADR-0005 (no async worker — management commands + cron),
ADR-0006 (overdue is computed), ADR-0007 (capabilities),
ADR-0008 (all-staff visibility), ADR-0009 (audit redaction / no sensitive bodies),
ADR-0018/0019 (layering + scoped querysets), ADR-0020 (audit),
ADR-0028 (hearings), ADR-0029 (tasks + deadlines), ADR-0031 (contracts),
ADR-0032 (finance — **not all-staff**, per-currency), ADR-0033/0034 (read layers).

## Context

Spec §45 + §99 ask for **useful, actionable** in-app notifications with a
read/unread state, a list, and links that lead to the relevant record. The
Phase 11 scope list (spec, "PHASE 11 — NOTIFICATIONS") is narrow:

> Notification model · In-app notifications · Hearing reminders · Task reminders
> · Invoice reminders · Contract reminders · Deadline notifications · Read/unread
> state

§45's broader "Potential events" list (case assignment, document uploaded,
important case update) is a wishlist, not the phase scope. The dashboard
(Phase 9) and reports (Phase 10) deliberately built **no** notification /
delivery / scheduling — all of it is Phase 11.

## Decision

### 1. One model, `notifications.Notification` — a per-user inbox row

Fields: `recipient` (FK User, **CASCADE** — a notification is personal data that
dies with the account), `category` (`NotificationCategory` `TextChoices`),
`title`, `body` (short server-generated Arabic sentence — §99), `url` (target
link, server-generated with `reverse`), `entity_type` / `entity_id` (a
**reference**, like `AuditLog` — never a copy of domain state), `dedupe_key`,
`read_at` (null = unread), `created_at`.

Indexes: `(recipient, read_at)` (the unread-count query + inbox filter),
`(recipient, -created_at)` (the inbox list), `category`, and a **`UniqueConstraint(recipient, dedupe_key)`** — the idempotency backstop.

**No sensitive domain data is stored in a notification.** Invoice notifications
carry the invoice **number**, client display name and due date — **never the
amount / balance** (ADR-0009; the figure would also go stale on payment). The
body is regenerated display text; the live record is one click away and its own
view re-checks authorization.

`default_permissions = ("add", "change", "view")` (no `delete`; house style).
Not registered in `sync_roles` — there is no "manage another user's inbox"
concept; access is *your own rows only*, gated by `NOTIFICATIONS_VIEW`
(already all-staff) + recipient scoping. Not registered with django-auditlog
(an inbox row is not a domain record; spec §46 does not list notifications).

### 2. Generation = five idempotent reminder scans in one management command

Per ADR-0005 (no worker/broker): `notifications/generation.py` holds plain
callables, wrapped one-line by `manage.py generate_notifications` (system cron
in deployment — a Phase 14 concern; the command + tests exist now). Categories,
each with a **deterministic `dedupe_key`** so a re-run creates nothing new:

| category | source | window (setting) | `dedupe_key` |
|---|---|---|---|
| `hearing_upcoming` | `Hearing` scheduled, future | `NOTIFY_HEARING_WITHIN_DAYS` (3) | `hearing_upcoming:{id}:{scheduled_date}` |
| `task_overdue` | `Task.objects.overdue()` (computed, ADR-0006) | — | `task_overdue:{id}:{due_date}` |
| `deadline_approaching` | `Deadline` pending, due ≤ today+N **or already past** | `NOTIFY_DEADLINE_WITHIN_DAYS` (7) | `deadline_approaching:{id}:{due_date}` |
| `invoice_overdue` | `Invoice.objects.overdue()` (computed, ADR-0006) | — | `invoice_overdue:{id}:{due_date}` |
| `contract_expiring` | `Contract.objects.expiring_soon(N)` | `NOTIFY_CONTRACT_WITHIN_DAYS` (30) | `contract_expiring:{id}:{end_date}` |

The `dedupe_key` embeds the **date that matters**, so a genuine change
(reschedule, new due date) legitimately produces one fresh notification while a
stable event never re-notifies — "avoid notification spam" (§45). Generation is
`filter(dedupe_key__in=…)` to find what already exists, then one
`bulk_create(…, ignore_conflicts=True)` per category (the unique constraint is
the race backstop). No per-row query; no per-recipient query.

### 3. Recipients are resolved to the people who can act — and re-checked

- **case-linked** hearing / deadline / contract → the case team
  (`assigned_lawyer` + `supporting_lawyers`); `hearing.lawyer` too.
- **task** → `assigned_to`.
- **invoice** → the finance-responsible set (office manager + finance clerk).
- **fallback** when the above is empty → the office manager(s).

Every candidate recipient is then intersected with
`users_with_capability(<domain>.view)` **before** the row is created — a
defence-in-depth backstop on top of "who we picked". For `invoice_overdue` the
gate is **`finance.view`**, so a **paralegal can never receive or see a finance
notification** (ADR-0032), even if a future recipient rule were widened. The
stored `url` points at the domain detail view, which enforces the same gate
again if the link is ever followed.

This means a notification is **never a side channel** around domain
authorization (spec Phase 11 §14): generation respects the domain's visibility
rules, the recipient must hold the domain capability, and the target view
re-checks.

### 4. Lifecycle: list · open · mark read · mark all read — recipient-scoped

`Notification.objects.for_user(user)` (`ScopedQuerySet`, ADR-0019) returns
`recipient=user` rows only. Every view and action goes through it;
`get_object_or_404(Notification.objects.for_user(request.user), pk=…)` →
**404 on URL tampering** (strict per-user siloing — unlike the all-staff
domains where denial is 403). A user can never mark, open, or read another
user's notification. Mark-read is `POST` + CSRF; "open" (`GET` the target)
marks read as a side effect then redirects.

No delete, no archive, no retention/cleanup — the spec defines none and §18
says do not invent one.

### 5. Badge = one indexed COUNT in the existing context processor

`core.context_processors` gains `unread_notification_count` (0 for anonymous;
one `WHERE recipient_id=? AND read_at IS NULL` COUNT, served by the
`(recipient, read_at)` index). The sidebar `الإشعارات` item becomes a live link;
the topbar gets a bell + count. No new middleware, no per-request query
explosion.

### 6. Channels: in-app only

Spec §45 describes an in-app list; it does not require email or SMS. Per the
Phase 11 brief ("if the specification requires only in-app notifications, do NOT
add email/SMS") none is built. `core/tasks.py` remains the seam if a digest or
email channel is ever specified.

## Consequences

- **Positive:** tiny surface; no duplicate domain state; re-running the cron is
  always safe; finance isolation holds by construction (recipient rule + capability
  intersection + target-view re-check); no new dependency, worker, or endpoint.
- **Negative:** notifications appear only as often as cron runs (acceptable —
  the dashboard and calendar are the real-time surfaces); "important case
  update" / "document uploaded" / "case assignment" from §45's wishlist are
  **not** built this phase (no event hook into completed domains) — a later
  phase can add event-driven categories through `notifications.services.notify`
  without a schema change.
- The `notifications` app **does** own a model (unlike dashboard/reports), so it
  ships a migration.

## Alternatives considered

- **Event-driven creation wired into every domain's `services.py`** — rejected
  for Phase 11: it means editing five completed domains, and the scope list is
  reminder-shaped. The `notify()` service is the seam when it is wanted.
- **A generic `django-notifications`-style actor/verb/target schema** — more
  than §45 needs; our five categories are closed and each has a bespoke Arabic
  sentence.
- **Re-notify daily while an item stays overdue** — rejected as spam (§45); the
  date-keyed `dedupe_key` notifies once per meaningful state.
- **Store the outstanding amount on the invoice notification** — rejected
  (ADR-0009 + it goes stale); reference the number, link to the record.
