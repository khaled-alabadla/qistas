━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        11 — Notifications
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–10).
Branch:       phase/11-notifications — based on master @ ac1b500 (Phase 10 merge, PR #9)
Design:       docs/adr/0035-notifications.md (Accepted)

════════════════════════════════════════
1. IMPLEMENTATION SUMMARY  (spec §45, §99, §82 Phase 11)
════════════════════════════════════════

`notifications` app — a thin **per-user in-app inbox** fed by idempotent
reminder scans. It owns **one model** (`Notification`); rows are *references* to
domain events, never copies of domain state.

- `notifications/models.py` — `Notification` (+ `NotificationCategory`,
  `NotificationQuerySet.for_user/unread/read`). `recipient` FK `CASCADE`,
  `category`, `title`, `body`, `url`, `entity_type` / `entity_id`, `dedupe_key`,
  `read_at`. `UniqueConstraint(recipient, dedupe_key)`; indexes
  `(recipient, read_at)`, `(recipient, -created_at)`, `category`.
- `notifications/services.py` — the only writer: `notify` (idempotent single
  create), `bulk_notify` (the scan path — two queries, no dupes), `mark_read`,
  `mark_all_read`.
- `notifications/generation.py` — the five `scan_*` callables + `generate_all`.
- `notifications/selectors.py` — `notification_list`, `unread_count`.
- `notifications/views.py` — `NotificationListView` + `notification_open` /
  `notification_mark_read` / `notification_mark_all_read`.
- `notifications/management/commands/generate_notifications.py` (cron entry,
  `--only`) + `seed_demo_notifications.py` (same, seed-chain name).
- `templates/notifications/notification_list.html` — the notification centre.
- `notifications/migrations/0001_initial.py` — portable ORM, no PG-specific DDL.

Integration:
- `core.navigation` — `الإشعارات` becomes a live link (`notifications:list`).
- `core.context_processors.navigation` — adds `unread_notification_count`
  (one indexed COUNT; 0 for anonymous; skipped without `notifications.view`).
- `templates/partials/sidebar.html` — count badge on the nav item.
- `templates/partials/topbar.html` — bell + count.
- `core.permissions.capabilities` — new helpers `groups_with_capability` /
  `users_with_capability` (recipient resolution + the capability-intersection
  backstop). `NOTIFICATIONS_VIEW` was already in `_ALL_STAFF`.
- `config/settings/base.py` (`notifications` app) · `config/urls.py`
  (`notifications/`).

No new dependency, middleware, worker, or JSON endpoint.

════════════════════════════════════════
2. NOTIFICATION MODEL  (spec §45)
════════════════════════════════════════

| field | purpose |
|---|---|
| `recipient` | FK User, **CASCADE** — a notification is personal data that dies with the account |
| `category` | `NotificationCategory` `TextChoices` — the closed Phase 11 set (5 values) |
| `title` | short label |
| `body` | one server-generated Arabic sentence — "should lead to action" (§99) |
| `url` | target link, generated with `reverse` |
| `entity_type` / `entity_id` | a **reference** to the source record (like `AuditLog`) — for navigation + dedupe |
| `dedupe_key` | deterministic idempotency key (see §4) |
| `read_at` | `null` = unread |
| `created_at` / `updated_at` | from `TimeStampedModel` |

Indexes: `(recipient, read_at)` (unread-count + inbox filter),
`(recipient, -created_at)` (inbox list), `category`.
Constraint: `UniqueConstraint(recipient, dedupe_key)`.

Deliberately **absent**: no per-recipient copy of amounts / balances / notes
(ADR-0009 — an invoice notification carries the number + client name + due date,
never the figure, which would also go stale); no `delete` codename; no
`archive`; no retention field (spec defines none — §18 "do not invent one").
`default_permissions = ("add", "change", "view")`. Not in `sync_roles` (no
"manage another user's inbox" concept). Not registered with django-auditlog
(an inbox row is not a domain record; spec §46 does not list notifications).

════════════════════════════════════════
3. NOTIFICATION TYPES / TRIGGERS  (spec §45 — implemented exactly)
════════════════════════════════════════

Five categories, each a scheduled scan with a clear source rule:

| category | source rule | window (setting, default) | recipients |
|---|---|---|---|
| `hearing_upcoming` | `Hearing` `status=scheduled`, `now ≤ scheduled_at < now+N` | `NOTIFY_HEARING_WITHIN_DAYS` = 3 | case team + `hearing.lawyer`; fallback office manager |
| `task_overdue` | `Task.objects.alive().overdue()` (computed — ADR-0006) | — | `task.assigned_to`; fallback office manager |
| `deadline_approaching` | `Deadline` `status=pending`, `due_date ≤ today+N` **or already past** | `NOTIFY_DEADLINE_WITHIN_DAYS` = 7 | case team; fallback office manager |
| `invoice_overdue` | `Invoice.objects.overdue()` (computed — ADR-0006) | — | office manager + finance clerk **(finance.view only)** |
| `contract_expiring` | `Contract.objects.expiring_soon(N)` (`status=active`) | `NOTIFY_CONTRACT_WITHIN_DAYS` = 30 | case team; fallback office manager |

§45's broader "Potential events" wishlist — **case assignment**, **document
uploaded**, **important case update** — is **not** built this phase: the Phase 11
scope list (spec) is reminder-shaped, and adding event-driven categories means
editing completed domains. `notifications.services.notify` is the seam if they
are wanted later (no schema change).

════════════════════════════════════════
4. IDEMPOTENCY STRATEGY
════════════════════════════════════════

Each scan derives a **deterministic `dedupe_key`** embedding *the date that
matters*:

```
hearing_upcoming:{hearing_id}:{local scheduled date}
task_overdue:{task_id}:{due_date}
deadline_approaching:{deadline_id}:{due_date}
invoice_overdue:{invoice_id}:{due_date}
contract_expiring:{contract_id}:{end_date}
```

`bulk_notify` collects the batch's keys, does one
`Notification.objects.filter(dedupe_key__in=…).values_list("recipient_id",
"dedupe_key")` to find what already exists, dedupes within the batch, and issues
one `bulk_create(rows, ignore_conflicts=True)` (the `UniqueConstraint` is the
race backstop). Consequences:

- Re-running `generate_notifications` immediately creates **0** rows (tested).
- A stable event (a hearing that stays scheduled for its 3 days in-window) is
  notified **once**, not daily — "avoid notification spam" (§45).
- A genuine change (reschedule → new date; a new due date) legitimately produces
  **one** fresh notification (tested).

════════════════════════════════════════
5. SCHEDULING / MANAGEMENT COMMAND  (ADR-0005 — no worker)
════════════════════════════════════════

`notifications/generation.py` holds plain, request-less, idempotent callables
(`scan_upcoming_hearings`, `scan_overdue_tasks`, `scan_approaching_deadlines`,
`scan_overdue_invoices`, `scan_expiring_contracts`, `generate_all`).
`manage.py generate_notifications` is the one-line cron wrapper
(`--only <categories>` to run a subset); it prints a per-category count and the
total. Timezone-aware throughout (`timezone.now()` / `localtime` / `localdate`,
`TIME_ZONE = Asia/Hebron`). System cron scheduling is a Phase 14 deployment
concern — the command + tests exist now. `seed_demo_notifications` is the same
under a seed-chain name.

════════════════════════════════════════
6. AUTHORIZATION  (spec Phase 11 §12–14, §13 finance)
════════════════════════════════════════

Four layers, none of them the UI:

1. **Recipient resolution** picks the people who can act on the event (case team
   = `assigned_lawyer` + `supporting_lawyers`; task assignee; the
   finance-responsible set; office-manager fallback).
2. **Capability intersection** — before *any* row is written the candidate set
   is `& users_with_capability(<domain>.view)`. `invoice_overdue` uses
   **`finance.view`** (ADR-0032). A superuser-only account is intentionally not
   a recipient.
3. **Recipient scoping on every read/action** —
   `Notification.objects.for_user(user)` returns `recipient=user` rows only
   (`ScopedQuerySet`, ADR-0019). `get_object_or_404` on it →
   **404 on URL tampering** (strict per-user siloing — 404, not the all-staff
   403; matches the spec's "URL tampering must result in 404").
4. **Target-view re-check** — the stored `url` is a normal domain detail URL
   whose view enforces its own capability + scope. Following a notification is
   never a bypass.

**Finance side-channel (§13):** a paralegal has no `finance.view`, is not in the
finance-responsible recipient set, and the invoice detail view would 403 them
anyway. Three dedicated regression tests assert a paralegal receives **zero**
finance notifications and that no monetary figure appears in any body.

════════════════════════════════════════
7. UI — THE NOTIFICATION CENTRE
════════════════════════════════════════

`notifications/notification_list.html` (Arabic-first, RTL, Qistas tokens):
header with the unread count + "تعليم الكل كمقروء"; an الكل / غير المقروءة
toggle + a category `<select>` (auto-submit, `<noscript>` fallback); a list
where each row shows a category badge (danger / warning / navy by severity), the
timestamp, the linked title, the body, an unread dot, and a per-row
"تعليم كمقروء" button. Paginated (`PAGE_SIZE = 20`). Distinct empty states for
"no notifications" vs "no unread". Clicking a title hits `notifications:open` —
marks read, then redirects to the (host-checked) target record.

Badge: sidebar `الإشعارات` shows the count; the topbar shows a bell + count.

════════════════════════════════════════
8. CHANNELS
════════════════════════════════════════

**In-app only.** Spec §45 describes an in-app list and requires no email or SMS;
per the Phase 11 brief none is built. `core/tasks.py` remains the seam if a
digest / email channel is ever specified.

════════════════════════════════════════
9. AUDIT
════════════════════════════════════════

None. Spec §46 does not list notifications, and an inbox row is not a domain
record. Notification bodies are never logged (ADR-0009). Bulk generation prints
a count to stdout for the cron log; it writes no `AuditLog` rows.

════════════════════════════════════════
10. PERFORMANCE REVIEW  — PASS
════════════════════════════════════════

- **Each scan is flat** regardless of data volume: one events query
  (`select_related` every rendered FK) + one `prefetch_related`
  (`case__supporting_lawyers`, read via the cache in `_case_team_ids` — **not**
  `.values_list()`, which would re-query) + two recipient-set queries
  (`users_with_capability`, office managers — computed once, outside the loop) +
  two write queries (`bulk_notify`: existing-key lookup + `bulk_create`).
- **No per-row query, no per-recipient query, no N+1.**
- **Badge** = one indexed `COUNT` (`(recipient, read_at)`), computed once per
  request in the existing context processor; 0 for anonymous with no query.
  Regression test: the COUNT stays one query for 10 notifications.
- **Inbox list** paginates a `for_user`-scoped, indexed, `-created_at`-ordered
  queryset.

════════════════════════════════════════
11. SECURITY REVIEW  — PASS (no Critical / High)
════════════════════════════════════════

| check | result |
|---|---|
| IDOR / recipient isolation | `for_user(user)` everywhere; tamper → 404; cross-user mark = silent no-op (never confirms the row). Tests: `test_cannot_mark_another_users_notification`, `test_open_another_users_notification_is_404`. |
| Finance side-channel | recipient rule + `finance.view` intersection + target-view re-check; paralegal → 0. Tests: `test_invoice_overdue_reaches_finance_users_only`, `test_paralegal_gets_zero_finance_notifications_from_generate_all`. |
| Sensitive data leakage | no amount / balance / notes in a body — only number + name + date (asserted in tests). |
| XSS | `title` / `body` rendered with auto-escaping; **no `|safe`, no `mark_safe`** anywhere in the app. |
| Open redirect | `notification_open` + `_safe_next` use `url_has_allowed_host_and_scheme`; offsite `url` / `next` fall back to the list. Tests: `test_open_rejects_offsite_url`, `test_mark_read_next_must_be_local`. |
| CSRF | mark-read / mark-all-read are `POST` + `{% csrf_token %}`; `require_POST`. |
| Mass assignment / forged read-state | rows are only ever created by the service from server-derived data; `read_at` is only set via `mark_read` / `mark_all_read` on a `for_user` queryset — a user cannot forge another's state. |
| SQL injection | ORM only; no raw SQL, no string-built queries. |
| Unsafe bulk ops | `bulk_create` is used only for row creation (no audit/business logic bypassed); `mark_all_read` `.update()` only flips `read_at` on the caller's own rows. |

════════════════════════════════════════
12. CODE REVIEW
════════════════════════════════════════

`/code-review high` is **not available in this environment** (`.claude/commands/`
holds only designqc / handoff / reframe / security-audit — same as Phases 4–10).
A rigorous **self code-review** was performed. Findings fixed pre-commit:

1. **N+1 in recipient resolution** — `_case_team_ids` originally called
   `case.supporting_lawyers.values_list(...)`, which bypasses the prefetch cache
   and fires one query per event. Changed to `case.supporting_lawyers.all()`
   (cache-served) + a docstring contract that callers must
   `prefetch_related("case__supporting_lawyers")`.
2. **Deadline scan `now` timezone** — `(now or timezone.now()).date()` takes the
   UTC date; changed to `timezone.localtime(now).date()` so a passed `now` is
   interpreted in the office timezone like every other path.
3. `bulk_notify` return-count caveat under a concurrent-scan race documented
   (rows are still correct — the unique constraint holds).

════════════════════════════════════════
13. TESTS  (+51 notification tests — 741 pass / 0 fail / 4 skipped, SQLite)
════════════════════════════════════════

- `test_models.py` (8) — unread default; `mark_read` idempotent; unique
  `(recipient, dedupe_key)`; same key different recipient OK; `for_user` scoping
  + anonymous-empty; unread/read filters; category set is closed.
- `test_services.py` (8) — `notify` creates-once-then-dedupes; `bulk_notify`
  inserts-missing-only + in-batch dedupe + empty; `mark_read` only touches own;
  `mark_all_read` scoped + no-op when nothing unread.
- `test_generation.py` (21) — every trigger: recipient + target + category +
  entity ref; outside-window ignored; done/draft ignored; **idempotent (re-run =
  0)**; reschedule → one fresh; no-team → office-manager fallback; overdue
  deadline still notified; **`invoice_overdue` finance-users-only + paralegal
  ZERO + no amount in body**; `generate_all` runs every scan.
- `test_command.py` (4) — creates then safe-to-rerun (count stable); `--only`;
  no-data no-op.
- `test_views.py` (12) — anon redirect; own-only list; unread filter;
  mark-one-read; `GET` rejected (405); cross-user mark = no-op; mark-all scoped;
  open marks read + redirects to target; open others' = 404; offsite `url` /
  `next` rejected.
- `test_context.py` (4) — badge per-user; 0 for anonymous; nav link live; badge
  is a single COUNT for many rows.

**Regression:** the full Phase 1–10 suite is green (690 → 741 with the new
tests; 4 `@pytest.mark.postgres` skips unchanged).

════════════════════════════════════════
14. QUALITY GATES
════════════════════════════════════════

| gate | result |
|---|---|
| `pytest` (SQLite) | **741 passed, 4 skipped** (`@pytest.mark.postgres`) |
| `ruff check .` | clean |
| `ruff format --check .` | clean (306 files) |
| `pip-audit` | no known vulnerabilities |
| `python manage.py makemigrations --check` | no changes (after `0001_initial`) |
| `python manage.py check` | no issues (1 silenced) |
| `python manage.py check --deploy` | 5 warnings — **test-settings only**; `config/settings/prod.py` sets HSTS / SSL redirect / secure cookies / env `SECRET_KEY` |

════════════════════════════════════════
15. POSTGRESQL / DOCKER STATUS — DEFERRED (environment blocker, Phases 1–11)
════════════════════════════════════════

This machine cannot run Docker or PostgreSQL (RAM + network). Not verified this
session:

1. Full suite on **PostgreSQL 16** (SQLite only) — expect ~741 pass, 0 skipped.
2. The 4 `@pytest.mark.postgres` tests (finance concurrency, numbering, trigram).
3. `docker compose` full-stack smoke; `manage.py generate_notifications` against
   PostgreSQL (the scan uses portable ORM only — `filter(__in)`, `bulk_create`,
   `values_list`; no PG-specific SQL).
4. `compilemessages` (GNU gettext — Docker-only; harmless, ships `ar`).
5. `check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY` + PG).

Exact commands to run on a PG machine / CI:

```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest                 # expect ~741 pass, 0 skipped
docker compose run --rm web python manage.py generate_notifications
docker compose run --rm web python manage.py generate_notifications   # -> created 0
```

════════════════════════════════════════
16. KNOWN LIMITATIONS
════════════════════════════════════════

- §45 wishlist categories not built: case assignment / document uploaded /
  important case update (see §3). The `notify` service is the seam.
- Notifications appear only as often as cron runs — the dashboard + agenda are
  the real-time surfaces (by design).
- `bulk_create(ignore_conflicts=True)` return count can slightly over-report on
  a genuine concurrent-scan race; the rows are still correct.
- `notification_open` marks-read on a `GET` (standard for a notification centre);
  a link-prefetching browser could mark an item read early — low harm, own row
  only.

════════════════════════════════════════
17. GIT
════════════════════════════════════════

Branch:          phase/11-notifications
Parent commit:   ac1b500  (Phase 10 merge, PR #9)
Final commit:    phase(11): complete notifications
Working tree:    clean after commit
Pushed:          origin/phase/11-notifications
Merged:          NO — awaiting "APPROVE PHASE 11"

════════════════════════════════════════
18. DEFINITION OF DONE
════════════════════════════════════════

[x] Notification domain implemented per QISTAS_PROJECT_SPEC.md §45 / §99
[x] Five triggers, each with a clear source rule; nothing invented
[x] Idempotency guaranteed (date-keyed `dedupe_key` + unique constraint + tests)
[x] Read/unread lifecycle (list / open / mark one / mark all)
[x] Recipient isolation enforced at every layer; 404 on tamper
[x] Domain authorization respected (capability intersection + target re-check)
[x] Finance notifications cannot leak to paralegals (3 regression tests)
[x] Scheduled generation via an idempotent management command (ADR-0005)
[x] UI integrated into nav + header (Arabic-first, RTL, badge)
[x] Performance review complete (flat scans, single-COUNT badge)
[x] Security review complete (IDOR / finance side-channel / XSS / open redirect)
[x] Self code review complete; findings fixed
[x] Comprehensive tests (+51); Phase 1–10 regression green
[x] Quality gates pass (ruff / format / pip-audit / makemigrations / check)
[x] PostgreSQL / Docker limitations documented (environment blocker)
[ ] Final commit + branch pushed  (next step)
[ ] APPROVE PHASE 11  (awaiting owner)
