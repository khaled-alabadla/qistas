# ADR-0029 — Tasks and deadlines

- **Status:** Accepted — 2026-09-09
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0006 (overdue is computed), ADR-0008 (all staff see all),
  ADR-0018 (`agenda` aggregator), ADR-0020 (audit), ADR-0022 (soft-delete /
  no-hard-delete), ADR-0028 (`agenda.selectors.calendar_events` is the one
  extension point), spec §31–33, §19, §48, §82 Phase 4.
- **Phase:** 5

## Context

Phase 5 is titled **"Tasks + Deadlines"**. Spec §31–32 fully describe **Tasks**;
"Deadlines" appears only in the phase title, the §33 calendar source list
(Hearings / Tasks / Meetings / Deadlines / Contract expirations — all distinct)
and the §19 "Upcoming Deadlines" dashboard section. Several things are unsettled:

1. Is a `Deadline` a `Task`, or a distinct record?
2. Spec §31 lists `متأخرة` (overdue) as a Task **status**, but ADR-0006 already
   ruled overdue is a computed state.
3. ADR-0022 lists `Task` in the soft-delete set, but `core.models.SoftDeleteModel`
   owns the default manager and cannot compose with `core.querysets.ScopedManager`.
4. "Dashboard integration" is Phase 5 scope, but the operational dashboard is
   Phase 9.

## Decision

### One app, `tasks`, two models

- **`Task`** (spec §31) — a unit of work assigned to a person.
  - Status enum `new` / `in_progress` / `done` / `cancelled` — **no `overdue`**
    (ADR-0006). Priority reuses the four case values (low/medium/high/urgent).
  - FK `assigned_to` → User (SET_NULL); optional FK `case` / `client` (SET_NULL) —
    "may belong to Case / Client" (§31). `due_date` is a **`DateField`** (§32
    compares dates, not times). `completed_at` `DateTimeField` set by the service
    when status → `done`, cleared on re-open.
  - **Soft-deletable** via a manual `deleted_at` field + a `deleted_by` FK, set
    only by `tasks.services.delete_task` — the same idiom as `cases.CaseNote`
    (not `SoftDeleteModel`, whose manager cannot be a `ScopedManager`). The
    selector filters `.alive()`; the list never shows deleted rows.
- **`Deadline`** — a procedural / statutory cut-off (appeal window, filing
  deadline, response deadline). Distinct from a Task: **no assignee**, it is not
  "worked", it is *met* or *missed*.
  - Status enum `pending` / `met` / `missed` / `cancelled`. Required `due_date`
    (`DateField`). Optional FK `case` / `client` (SET_NULL). `completed_at` set
    when met/missed is recorded.
  - **Never hard-deleted** (a missed deadline is legally significant, ADR-0022):
    `default_permissions = ("add", "change", "view")`, admin delete disabled,
    "cancel" is a status transition — same treatment as `Hearing`.

### Overdue is computed (ADR-0006)

- `Task.is_overdue` / `Deadline.is_overdue` — properties
  (`due_date < today AND status not in {done/met/cancelled/missed}`).
- `TaskQuerySet.overdue()` / `DeadlineQuerySet.overdue()` — the same predicate as a
  queryset filter, used by list filters, the landing widgets and (Phase 10)
  reports. No stored flag, no cron (ADR-0005/0006).

### Visibility — all staff (ADR-0008)

- `Task.objects.for_user` / `Deadline.objects.for_user` return everything for an
  authenticated user, `.none()` for anonymous — the v1 "all staff see all" model.
  A user's *own* tasks are a **filter** (`assigned_to=user`), never a visibility
  boundary.
- Capabilities: **`tasks.view`** (all staff) / **`tasks.manage`** (office_manager,
  lawyer, paralegal, admin_clerk — the case handlers; finance_clerk is view-only).
  **One capability pair covers both `Task` and `Deadline`** — same feature area,
  same handlers. `sync_roles` maps `tasks.{add,change}_task` and
  `tasks.{add,change}_deadline`.

### Audit + case timeline

- Every `Task` / `Deadline` mutation writes an `audit.AuditLog` event
  (`TASK_*` / `DEADLINE_*` `AuditAction` members).
- When the row is **case-linked**, the mutation also records a `CaseEvent`
  (`TASK_ADDED` / `TASK_STATUS_CHANGED` / `TASK_REMOVED` / `DEADLINE_ADDED` /
  `DEADLINE_STATUS_CHANGED`) via `cases.services.record_case_event`, so the case
  workspace timeline (spec §26) shows task/deadline activity. Client-only rows do
  not (there is no client timeline in v1).

### Calendar integration — extend the one function (ADR-0028)

- `agenda.selectors.calendar_events` gains two more sources:
  `tasks.selectors.calendar_items(user, start, end)` yields Task rows with a
  `due_date` and Deadline rows, as normalised `{start, title, kind, all_day,
  status, done, url, meta}` dicts (`kind` = `task` / `deadline`). Date-only items
  carry `all_day = True`; the calendar renders them without a time.
- Cancelled / done-in-the-past items are still shown (struck through) so the
  calendar is a faithful record; the selector excludes nothing by status (the
  view decides styling).

### Dashboard integration — modest, on the existing landing page

Phase 9 builds the analytical dashboard. Phase 5 makes the **landing page**
(`core:landing`) show three real, queried sections for staff: **مهامي** (my open
tasks), **مهام متأخرة** (all overdue tasks), **مواعيد قادمة** (deadlines due in the
next 30 days). Selectors live in `tasks.selectors`; the landing view stays thin.

### Navigation (spec §16)

`المكتب` group gains **المهام** (`tasks:list`) and **المواعيد النهائية**
(`deadlines:list`) alongside `التقويم`. The case workspace `المهام` tab becomes
real (case tasks + case deadlines).

## Consequences

- Diverges from the literal §31 status enum (drops `متأخرة`) — already covered by
  ADR-0006, restated here.
- `Task` soft-delete uses the `CaseNote` idiom, not `SoftDeleteModel`; the ADR-0022
  "soft-delete set" is satisfied in spirit (recoverable, audited) without the
  manager conflict.
- Adding meeting / contract-expiration calendar sources later is again one change
  to `calendar_events` (ADR-0028).
- Task/deadline reminders and "overdue" / "deadline approaching" notifications are
  Phase 11 (a scanning command over the computed predicate — the notification is
  the artifact, not a status change).
