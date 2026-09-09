# ADR-0028 — Hearings, calendar, and derived next-hearing

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0018 (app layout — `agenda`), ADR-0022 (on_delete / no-delete for `Hearing`), ADR-0019 (object scoping), ADR-0020 (audit), spec §28–30, §33
- **Phase:** 4

## Context

Phase 4 adds the full **Courts** UI, the **Hearings** model + workflow, and a
**calendar**. Several schema/behaviour questions are not settled by the spec:

1. Spec §29 lists `date` and `time` as separate hearing fields, but Phase 4's
   brief requires **timezone-aware** hearing datetimes and a calendar that sorts
   and buckets events correctly.
2. Spec §26 shows a `next_hearing` on the case workspace and §30 says a completed
   hearing that sets a next date must "update the case" — but a stored
   `Case.next_hearing` field would drift the moment a hearing is rescheduled,
   cancelled, or completed.
3. Spec §11 lists a `calendar/` app and §33 says the calendar aggregates
   hearings **and** tasks, meetings, deadlines, contract expirations — none of
   which exist yet.
4. ADR-0022 already says `Hearing` is never soft-deleted or routinely deleted.

## Decision

### Hearing schema

- **One timezone-aware `scheduled_at = DateTimeField`** is the source of truth for
  scheduling, ordering, and calendar bucketing. `USE_TZ` is already on; values are
  stored in UTC and rendered in `settings.TIME_ZONE` (`Asia/Hebron`).
  The create/edit form splits it into a **required date** + an **optional time**
  input (time defaults to `09:00`, the typical Palestinian court start); the
  service combines them with `django.utils.timezone.make_aware`.
- `hearing_type` is a small `TextChoices` (`first_session`, `pleading`,
  `evidence`, `deliberation`, `verdict`, `other`) — not free text, not a
  configurable table (unlike `CaseType`, hearing types are stable court
  vocabulary).
- `status` `TextChoices`: `scheduled` / `held` / `postponed` / `cancelled`
  (مجدولة / تمت / مؤجلة / ملغاة — spec §29).
- Outcome fields filled at completion: `result` (TextField), `next_action`
  (CharField), `next_hearing_date` (DateField, nullable) — the last records "the
  judge set the next date" even when a follow-up row also exists.
- `case` → `on_delete=PROTECT` (ADR-0022: `PROTECT` for references to legally
  significant records; a `Hearing` is one and is never deleted anyway).
  `court` → `SET_NULL`; `lawyer` → `SET_NULL` (matches `Case.court` /
  actor-reference policy).
- `AuthoredModel` + `TimeStampedModel`. Registered with `django-auditlog`.

### Hearing lifecycle — all through `hearings.services`, never a row delete

- **schedule** → new `scheduled` row.
- **reschedule** (before it happens) → mutate `scheduled_at`, status stays
  `scheduled`; records old→new.
- **complete** (`held`) → set `result` / `notes` / `next_action` /
  `next_hearing_date`; if a next date is given, **create a new `scheduled`
  Hearing** for the same case (so it lands on the calendar, the timeline, and the
  derived next-hearing automatically).
- **postpone** (`postponed`) → like complete but a new date is required → creates
  the follow-up row.
- **cancel** (`cancelled`) → status change + reason; **no row deleted** (ADR-0022).

Every mutation writes a `CaseEvent` (spec §26 timeline) via
`cases.services.record_case_event` **and** an `audit.AuditLog` event.

### `Case.next_hearing` is **derived, never stored**

```python
def next_hearing(self):
    return (self.hearings
            .filter(status="scheduled", scheduled_at__gte=timezone.now())
            .order_by("scheduled_at").first())
```

The case list annotates the same value for its column. Nothing to keep in sync;
rescheduling / cancelling / completing a hearing changes the answer for free.

### `agenda` app — a derived-event **aggregator**, no model

- `agenda` has **no `Event` model**. `agenda.selectors.calendar_events(user,
  start, end)` returns a normalised list of `{start, end, title, kind, url,
  meta}` dicts. In Phase 4 the only source is `hearings`; Phase 5+ add tasks,
  deadlines, contract expirations by extending that one function.
- Every event dict carries a `url` back to its source entity (spec §33).
- Three server-rendered views — **month / week / day** — built with the stdlib
  `calendar` module (`firstweekday = 5`, i.e. **Saturday**, matching
  `FORMAT.FIRST_DAY_OF_WEEK`). No JS calendar library.
- Scoped: events come only from `Hearing.objects.for_user(user)` (→ `Case`
  visibility, ADR-0008 — all staff see all).

### Courts (full)

- The Phase 3 minimal `Court` gains `department`, `address`, `phone`, `notes`
  (spec §28) and a `ScopedQuerySet` (`for_user` / `active` / `search`).
- Capabilities `courts.view` (all staff) / `courts.manage` (office_manager only —
  courts are shared reference data). Deactivation is an `is_active` toggle, never
  a delete (a court is referenced by historical hearings/cases).
- Registered with `django-auditlog`.

### Permissions

- New capabilities: `hearings.view` (all staff), `hearings.manage`
  (office_manager, lawyer, paralegal, admin_clerk — the case handlers),
  `courts.view` (all staff), `courts.manage` (office_manager), `agenda.view`
  (all staff).
- Object-level: hearings scope through their `Case` (`Hearing.objects.for_user`
  delegates to `Case` visibility). Missing pk → 404.

## Consequences

- The calendar and the case workspace never show a stale next-hearing.
- Adding task/deadline/contract events later is a change to one selector, not a
  schema migration.
- A hearing's history (postponements, cancellations) is fully reconstructable
  from `CaseEvent` + auditlog `LogEntry` without soft-delete plumbing.
- `next_hearing` is an unindexed reverse query per case; the list view annotates
  it in one pass and detail loads one row — acceptable at single-office scale,
  revisited in Phase 13 if hearing volume grows.
