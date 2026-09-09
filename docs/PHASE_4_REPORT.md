━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      4 — Hearings + Courts (full) + Calendar / Agenda
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
            (same environment blocker as Phases 1–3; every other DoD item met)
Branch:     phase/4-courts-hearings — based on master @ 83674a7 (Phase 3 merge, PR #2),
            NOT merged. One commit: phase(4): complete courts and hearings
Design:     docs/adr/0028-hearings-calendar-and-derived-next-hearing.md (Accepted)

---

Implemented (spec §28–30, §33, §16, §46, §82 Phase 4):

## Courts — promoted to the full model (spec §28)

- `Court` gains `department`, `address`, `phone`, `notes` (migration
  `courts/0002_court_full_fields`) + 3 indexes.
- `CourtQuerySet(ScopedQuerySet)` — `for_user` (all authenticated staff — courts
  are shared reference data), `active()`, `search()` (`icontains` over
  name/city/department/address).
- `courts/services.py` — `create_court`, `update_court` (freshly-fetched diff +
  no-op guard, cf. bug-027), `set_active` toggle. Each writes an `AuditLog`
  event; no `CaseEvent` (courts are not case-scoped).
- `courts/selectors.py` — `court_list(user, query, type, include_inactive)`.
- Views: list (search + type filter + include-inactive + pagination), detail
  (shows linked case/hearing counts), create, update, `set_active` POST action.
- Capabilities: `courts.view` (**all staff**) / `courts.manage`
  (**office_manager only** — shared reference data, ADR-0028).
- `sync_roles` extended: `_COURT_MANAGE` for office_manager, `_COURT_VIEW` for the
  rest. Registered with django-auditlog. Admin `has_delete_permission = False`.
- Trigram GIN migration `courts/0003_court_search_indexes`
  (`TRGM_COLUMNS == SEARCH_FIELDS`, PG-only, vendor-guarded; regression test keeps
  them in sync).
- `seed_demo_courts` updated with department/phone.

## Hearings — new `hearings` app (spec §29–30)

- **`Hearing(TimeStampedModel, AuthoredModel)`**
  - **one timezone-aware `scheduled_at = DateTimeField`** — the single source of
    truth for scheduling, ordering and calendar bucketing (spec §29 lists
    `date` + `time`; the forms keep that split — a required date + an optional
    time defaulting to `09:00` — and the service recombines via
    `timezone.make_aware`).
  - `hearing_type` `TextChoices` (first_session / pleading / evidence /
    deliberation / verdict / other) — stable court vocabulary, not a configurable
    table.
  - `status` `TextChoices` — `scheduled` / `held` / `postponed` / `cancelled`
    (مجدولة / تمت / مؤجلة / ملغاة — spec §29).
  - `room` (spec §29), `notes`; outcome fields `result` / `next_action` /
    `next_hearing_date` filled at completion (spec §30).
  - `previous_hearing` self-FK (SET_NULL) linking a follow-up row to its parent.
  - `case` → **PROTECT** (legally significant, never deleted — ADR-0022);
    `court` / `lawyer` → SET_NULL.
  - `HearingQuerySet(ScopedQuerySet)` — `for_user` delegates to Case visibility
    (v1: all staff), `upcoming()`, `in_range(start, end)`, `search()` (case
    number/title, court name, room).
  - `default_permissions = ("add", "change", "view")` — no delete; admin
    `has_delete_permission = False`.
- **`hearings/services.py`** — every mutation writes a `CaseEvent` on the case
  timeline (via `cases.services.record_case_event`) **and** an `AuditLog` event;
  **no row is ever deleted**:
  - `schedule_hearing` → new `scheduled` row.
  - `update_hearing` → edits a still-scheduled hearing; a `scheduled_at` change is
    recorded as `HEARING_RESCHEDULED`, other field changes as `HEARING_UPDATED`;
    freshly-fetched diff + no-op guard; rejected on a closed hearing
    (`HearingStateError`).
  - `complete_hearing` → status `held` + outcome fields; if a next date is given,
    **spawns a new `scheduled` Hearing** for the same case (lands on the calendar,
    the timeline and the derived next-hearing automatically).
  - `postpone_hearing` → status `postponed`, next date **required** → spawns the
    follow-up row.
  - `cancel_hearing` → status `cancelled` + reason; **no row deleted**.
- **`Case.next_hearing` — derived, never stored** (ADR-0028): a property returning
  the soonest still-`scheduled` future hearing; `cases.selectors.case_list`
  annotates the same value (`next_hearing_at`, correlated `Subquery`) for the list
  column. Rescheduling / cancelling / completing changes the answer for free —
  nothing to keep in sync.
- Views: global list (search + when[upcoming/past/all] + status + type + court
  filters + pagination), detail (actions + outcome + follow-ups), schedule
  (`?case=` prefill — disabled, scoped case field), update/reschedule, complete,
  postpone, cancel (POST + reason).
- Capabilities: `hearings.view` (**all staff**) / `hearings.manage`
  (**office_manager, lawyer, paralegal, admin_clerk** — the case handlers,
  ADR-0028). `sync_roles` extended (`hearings.add/change/view_hearing`).
- 6 `HEARING_*` `AuditAction` members; 6 `HEARING_*` `CaseEventType` members
  (migration `cases/0004_caseevent_hearing_types`).
- `seed_demo_hearings` command.

## Agenda — new `agenda` app (spec §33) — a derived-event aggregator, **no model**

- `agenda/selectors.calendar_events(user, start, end)` → normalised, time-ordered
  `{start, title, kind, status, done, url, meta}` dicts. Phase 4 source =
  `hearings` only (cancelled excluded); every dict carries a `url` back to its
  entity. Later phases extend this one function (tasks, deadlines, contract
  expirations).
- Three server-rendered views — **month / week / day** — built on the **stdlib
  `calendar` module** (`firstweekday = 5` → Saturday). **No JS calendar library.**
  Arabic month + weekday names, prev/next/today navigation, view switcher.
- Scoped: events come only from `Hearing.objects.for_user(user)`.
- Capability `agenda.view` (**all staff**).

## Case integration

- Case workspace (spec §26): the disabled **الجلسات** tab is now real — lists all
  hearings for the case + a "schedule hearing" button. Overview shows the derived
  next hearing.
- Case list: a **الجلسة القادمة** column (from the annotation).
- Navigation (spec §16): **الجلسات** + **المحاكم** under القضايا (permission-aware);
  a **المكتب → التقويم** group.
- `input[type="time"]` added to the global form-control style; `static/css/app.css`
  rebuilt.

---

Verification:

- **Tests: 295 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`) on SQLite.
  New: `hearings` 39, `courts` 27, `agenda` 8, plus the end-to-end HTTP smoke
  (`hearings/tests/test_smoke.py` — 16 Phase-4 URLs render 200 through the real
  WSGI + template stack). Existing `cases` tests updated (الجلسات is now a real
  tab; unknown-tab example changed to `invoices`).
- `ruff check` clean · `ruff format --check` clean · `pip-audit` — no known
  vulnerabilities · `makemigrations --check --dry-run` — no changes ·
  `manage.py check` clean · `manage.py check --deploy --fail-level WARNING`
  (prod settings, ephemeral key) — no issues (1 silenced).
- Seeds: `seed_demo_courts` (7) → `seed_demo_clients` (8) → `seed_demo_cases` (4)
  → `seed_demo_hearings` (4, idempotent on re-run). `sync_roles --check` clean
  after sync.

Code Review (self — spec §70) — issues found & fixed during the pass:
1. **Paginated `hearings:list` page 2 leaked past/closed rows** — a bound filter
   form with no `when` cleaned it to `""`, which matched no branch → the default
   `upcoming` filter was dropped on page 2+. Fixed: the selector now treats any
   unrecognised `when` as `upcoming` (explicit `past` / `all` only). Regression
   test added (`test_list_paginates` now asserts page 2).
2. **A "next hearing" date could be set in the past** on complete / postpone →
   `clean_next_hearing_date` rejects past dates on both forms.
3. **Unused `cancel_form` context / inline confirm-only cancel** → the detail page
   now renders a real cancel form with an optional reason field
   (`<details>` disclosure + `confirm()`); `test_cancel_with_reason_via_view`.
4. **`CourtFactory` lived in `cases.tests.factories`** → moved to
   `courts/tests/factories.py`; `cases` re-exports it (back-compat).

Security Review (self — spec §70):
- **Object-level authz** — every hearing/court view routes through
  `Model.objects.for_user()` + `assert_scoped`; `CapabilityRequiredMixin` /
  `@require_capability` gate read vs. write; missing pk → 404, denied capability →
  403 (anonymous → login redirect via `LoginRequiredMiddleware`). Sub-resources
  (follow-ups) are always reached via the scoped parent.
- **Mass-assignment** — hearing forms are plain `forms.Form` with explicit fields;
  `update_hearing` filters `data` to a hardcoded `EDITABLE_FIELDS` tuple; `status`
  / `case` / `created_by` are only ever set by the service. `CourtForm` has an
  explicit field list.
- **CSRF** — every mutating form has `{% csrf_token %}`; every function action is
  `@require_POST` + `@require_capability`.
- **Audit** — all 6 hearing lifecycle transitions + all 3 court mutations write an
  append-only `AuditLog` row (actor, entity, formatted change dict — no sensitive
  values; hearings/courts have no `SENSITIVE_FIELDS`). Nothing deletes a hearing
  or a court row.
- **Calendar disclosure** — `calendar_events` is scoped; anonymous → `[]`
  (test). `agenda` query params (`year`/`month`/`date`) are parsed with
  `int()` / `date.fromisoformat()` inside try/except and fall back to today —
  no injection, no 500 on garbage (`test_month_view_ignores_bad_params`).
- **SQL** — ORM only; the trigram migration interpolates a hardcoded column tuple.
- No new dependencies.

Performance Review (self):
- `hearing_list` — `select_related("case", "case__client", "court", "lawyer")`;
  `upcoming()` / `past` use the `(status, scheduled_at)` / `scheduled_at` indexes;
  pagination caps size; one query per submitted GET filter.
- `case_list.next_hearing_at` — one correlated `Subquery` served by the
  `(case, -scheduled_at)` index; fine at page size 25 (revisited Phase 13 with
  `assertNumQueries` guards, same as Phases 2–3).
- `agenda` — a single `in_range` query per view (`scheduled_at` index),
  `select_related`, bucketed in Python; no N+1.
- Case detail adds 2 queries (`next_hearing` + `case_hearings`, the latter lazy);
  court detail adds 2 `count()` queries. Acceptable at single-office scale
  (ADR-0028 "Consequences").

---

Known Issues — DEFERRED / UNVERIFIED (same environment blocker as Phases 1–3:
the session machine cannot run Docker or PostgreSQL — low RAM, network stalls):
1. **Full suite not run against PostgreSQL 16** — SQLite only.
2. **`courts/migrations/0003_court_search_indexes` not executed** — PG-only,
   vendor-guarded → skipped on SQLite.
3. **`@pytest.mark.postgres` tests unverified** (3 skipped).
4. **`docker compose` full-stack smoke** — not run (equivalent verified via the
   Django-test-client HTTP smoke).
5. **`compilemessages`** — Docker-only (gettext); harmless (ships `ar`).

Exact remaining PostgreSQL checks:
```
docker compose build
docker compose run --rm web python manage.py migrate        # courts 0003 + cases 0004 + hearings 0001 apply
docker compose run --rm web pytest                          # expect 298 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/hearings/   # 302 -> /accounts/login/
```

---

Deferred Items (carried forward):
- Calendar aggregation of tasks / deadlines / contract expirations — Phases 5 / 7
  (extend `agenda.selectors.calendar_events` — one function, no schema change).
- Hearing reminders / "hearing approaching" notifications — Phase 11 (spec §45).
- Hearing reports (upcoming / completed / postponed / cancelled) — Phase 10.
- Dashboard "today's hearings" widget — Phase 9.
- `assertNumQueries` guards on the new list/detail pages — Phase 13.
- `pg_trgm` search ranking (currently unranked `icontains`) — Phase 13 if needed.
- Hearing conflict detection (same lawyer, overlapping time) — revisit if the
  office asks; not in spec.

Assumptions:
- All staff see all cases → all hearings (ADR-0008); no per-hearing gate.
- A hearing may be **back-dated** on schedule (recording a session already held);
  only *next* dates (complete / postpone) are forced to be non-past.
- `09:00` is the default hearing time when none is entered (ADR-0028).
- A court is deactivated, never deleted; a hearing is cancelled, never deleted.
- The Palestinian working week starts **Saturday** (`FORMAT.FIRST_DAY_OF_WEEK`).

Ready for Approval:
Owner to accept the deferred PostgreSQL/Docker items (as with Phases 1–3) — every
other DoD item is met.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMITTED + PUSHED — WAITING FOR USER APPROVAL OF PHASE 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
