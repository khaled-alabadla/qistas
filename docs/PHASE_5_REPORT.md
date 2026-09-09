━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      5 — Tasks + Deadlines
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
            (same environment blocker as Phases 1–4; every other DoD item met)
Branch:     phase/5-tasks-deadlines — based on master @ 9557168 (Phase 4 merge, PR #3),
            NOT merged. One commit: phase(5): complete tasks and deadlines
Design:     docs/adr/0029-tasks-and-deadlines.md (Accepted)

════════════════════════════════════════
1. WHAT WAS IMPLEMENTED  (spec §31–33, §19, §48, §82 Phase 5)
════════════════════════════════════════

## `tasks` app — two models

### Task (spec §31) — a unit of work assigned to a person
- `title` / `description`, FK `assigned_to` → User (SET_NULL), optional FK
  `case` / `client` (SET_NULL — "may belong to Case / Client"), `priority`
  (low/medium/high/urgent — reuses the case set), `due_date` **DateField**
  (spec §32 compares dates), `completed_at` DateTimeField set by the service on
  → `done`, cleared on re-open.
- **Status enum `new` / `in_progress` / `done` / `cancelled` — NO `overdue`**
  (docs/adr/0006). "Overdue" is a computed `is_overdue` property **and** a
  `TaskQuerySet.overdue()` filter (`due_date < today AND status not closed`).
- **Soft-deletable** via a manual `deleted_at` + `deleted_by` (the
  `cases.CaseNote` idiom — `SoftDeleteModel` owns the default manager and cannot
  compose with `ScopedManager`). Set only by `tasks.services.delete_task`; the
  row is kept, the selector filters `.alive()`, a deleted task 404s.
- 7 indexes. `TaskQuerySet(ScopedQuerySet)` — `for_user` (all staff, ADR-0008),
  `alive` / `open` / `overdue` / `assigned_to` / `search`.

### Deadline — a procedural / statutory cut-off
- `title` / `description`, optional FK `case` / `client` (SET_NULL), **required**
  `due_date` DateField, `completed_at` set when met/missed recorded.
- Status enum `pending` / `met` / `missed` / `cancelled`. `is_overdue`
  (`pending AND due_date < today`) + `DeadlineQuerySet.overdue()`.
- **Never hard-deleted** (a missed deadline is legally significant, ADR-0022):
  `default_permissions = ("add", "change", "view")`, admin delete disabled,
  "cancel" is a status transition — same treatment as `Hearing`.

## `tasks.services` — transactional, audited
`create_task` / `update_task` (freshly-fetched diff + no-op guard, cf. bug-027) /
`change_task_status` (toggles `completed_at`) / `delete_task` (soft, idempotent) ·
`create_deadline` / `update_deadline` / `change_deadline_status`. Every mutation
writes an `audit.AuditLog` event; a **case-linked** row also records a `CaseEvent`
on the case timeline (spec §26) via `cases.services.record_case_event`.

## `tasks.selectors` — permission-scoped reads
`task_list` / `deadline_list` (search + status + priority + assignee + overdue +
`mine` filters, open-by-default, pagination), `case_tasks` / `case_deadlines`,
`my_open_tasks`, `overdue_tasks`, `upcoming_deadlines(days=30)`, and
`calendar_items(user, start, end)` for the agenda aggregator.

## Calendar integration (docs/adr/0028 — extend the one function)
`agenda.selectors.calendar_events` now merges **hearings + tasks + deadlines**.
Task rows (with a `due_date`) and Deadline rows become normalised
`{start, title, kind, all_day, status, done, url, meta}` dicts (`kind` =
`task` / `deadline`, `all_day = True`); the month/week/day templates render
all-day items without a time and colour overdue items red.

## Dashboard integration (modest — the full dashboard is Phase 9)
`core:landing` (`LandingView`) now shows three real, queried sections for staff:
**مهامي المفتوحة**, **مهام متأخرة** (with a count), **مواعيد نهائية قادمة (30 يومًا)**.

## Case workspace
The disabled **المهام** tab is now real — case tasks + case deadlines + "add"
buttons (`?case=` prefill, which stays valid even for a closed case).

## Permissions
- Capabilities **`tasks.view`** (all staff) / **`tasks.manage`** (office_manager,
  lawyer, paralegal, admin_clerk — finance_clerk view-only). **One pair covers
  both `Task` and `Deadline`** (docs/adr/0029).
- `sync_roles` extended: `_TASK_VIEW` = `tasks.view_task` + `tasks.view_deadline`;
  `_TASK_MANAGE` adds add/change for both + `tasks.delete_task` (Django model
  perm mirroring the soft-delete action; admin hard-delete stays disabled).

## Audit / navigation / other
- 7 `AuditAction` members (`TASK_CREATED/UPDATED/STATUS_CHANGED/DELETED`,
  `DEADLINE_CREATED/UPDATED/STATUS_CHANGED`); 5 `CaseEventType` members
  (`TASK_ADDED/STATUS_CHANGED/REMOVED`, `DEADLINE_ADDED/STATUS_CHANGED`).
- Nav (spec §16): `المكتب` group gains **المهام** + **المواعيد النهائية**
  (permission-aware) alongside `التقويم`.
- `Task` + `Deadline` registered with django-auditlog. `seed_demo_tasks` command.
- New shared helper **`core.forms.with_current_choice`** (see §5).

════════════════════════════════════════
2. FILES CHANGED
════════════════════════════════════════

New — `tasks/` app:
  tasks/__init__.py  apps.py  models.py  services.py  selectors.py  forms.py
  views.py  urls.py  admin.py  audit.py
  tasks/migrations/0001_initial.py  0002_task_search_indexes.py  __init__.py
  tasks/management/commands/seed_demo_tasks.py  (+ __init__ files)
  tasks/tests/  factories.py  test_models.py  test_services.py  test_views.py
                test_permissions.py  test_search.py  test_smoke.py  __init__.py

New — templates:
  templates/tasks/  _badges.html  _deadline_badge.html
                    task_list.html  task_detail.html  task_form.html
                    deadline_list.html  deadline_detail.html  deadline_form.html

New — other:
  docs/adr/0029-tasks-and-deadlines.md
  docs/PHASE_5_REPORT.md
  core/forms.py  (shared `with_current_choice`)

Modified:
  config/settings/base.py            + "tasks" in LOCAL_APPS
  config/urls.py                     + path("tasks/", …)
  core/permissions/capabilities.py   + TASKS_VIEW / TASKS_MANAGE, _TASK_HANDLERS
  accounts/management/commands/sync_roles.py  + _TASK_VIEW / _TASK_MANAGE
  core/navigation.py                 + المهام / المواعيد النهائية nav items
  core/views.py                      LandingView widgets
  templates/core/landing.html        real task/deadline widgets
  audit/models.py                    + 7 TASK_*/DEADLINE_* AuditAction
  cases/models.py                    + 5 TASK_*/DEADLINE_* CaseEventType
  cases/views.py                     المهام tab (case_tasks / case_deadlines)
  templates/cases/case_detail.html   المهام tab content
  agenda/selectors.py                calendar_events merges tasks + deadlines
  templates/agenda/_event.html       all-day + task/deadline styling
  cases/forms.py, hearings/forms.py  delegate _with_current → core.forms
  static/src/app.css + static/css/app.css  (rebuild; no source change beyond P4)

════════════════════════════════════════
3. DATABASE / MIGRATIONS
════════════════════════════════════════

- `tasks/0001_initial` — `Task` + `Deadline` tables (10 indexes total;
  `Deadline` has `default_permissions = ("add","change","view")` — no delete).
- `tasks/0002_task_search_indexes` — trigram GIN on `tasks_task(title,
  description)` + `tasks_deadline(title, description)`. **PostgreSQL-only,
  vendor-guarded** (no-op on SQLite). A regression test keeps
  `TASK_TRGM_COLUMNS`/`DEADLINE_TRGM_COLUMNS` == the `*_SEARCH_FIELDS` tuples.
- `cases/0005_caseevent_task_types` — widen `CaseEvent.event_type` choices
  (metadata only; no column change).
- `makemigrations --check --dry-run` — **no changes detected**.

════════════════════════════════════════
4. TESTS & RESULTS
════════════════════════════════════════

**337 passed / 0 failed / 3 skipped** (SQLite). The 3 skipped are
`@pytest.mark.postgres` (real-DB row-locking / extensions).

New `tasks` tests (47):
- `test_models` — `for_user` scoping; **computed `is_overdue`** (task + deadline)
  and matching `overdue()` querysets; `"overdue" not in TaskStatus.values`;
  `.alive()` excludes soft-deleted; `Deadline` has no `delete` permission.
- `test_services` — audit + `CaseEvent` on create; no case event when
  case-less; `done` sets/clears `completed_at`; update no-op vs change;
  status-change case events; **soft-delete keeps the row**, is idempotent,
  emits `TASK_REMOVED` + `TASK_DELETED`; deadline met/missed/cancel lifecycle.
- `test_views` — login required; all-staff view; closed + soft-deleted hidden;
  **pagination keeps the filter on page 2**; `mine` / `overdue` filters;
  `?case=` prefill incl. **a closed case**; 403 for finance_clerk on every
  manage action; status action is POST-only; soft-delete → 404 afterwards;
  edit keeps an archived client; deadline CRUD + status flow.
- `test_permissions` — capability matrix; manage actions 403 without
  `tasks.manage`; finance_clerk can view; `sync_roles --check` clean.
- `test_search` — selector search/filter; `calendar_items` yields task +
  deadline all-day events; trigram/SEARCH_FIELDS sync.
- `test_smoke` — 13 Phase-5 URLs render 200 through the real WSGI/template
  stack; landing widgets populated.

Existing suite: cases tests updated (المهام is now a real tab).

Other gates: `ruff check` ✅ · `ruff format --check` ✅ · `pip-audit` — no known
vulnerabilities · `manage.py check` ✅ · `check --deploy --fail-level WARNING`
(prod settings, ephemeral key) — no issues (1 silenced) · seed chain +
`sync_roles --check` clean.

════════════════════════════════════════
5. CODE-REVIEW FINDINGS & FIXES
════════════════════════════════════════

1. **`_with_current` picker helper crashed on a `.distinct()` base queryset** —
   `Model.objects.filter(pk=…) | distinct_qs` raises *"Cannot combine a unique
   query with a non-unique query"*. It surfaced on the task edit form
   (`assigned_to` picker uses a `groups__name__in` join → `.distinct()`), and was
   a **latent bug in `cases`/`hearings` forms** too (their lawyer pickers use the
   same join, just never exercised by a test).
   → Extracted a shared, distinct-safe **`core.forms.with_current_choice`**
   (forces both sides `.distinct()` before the union — stays lazy); `cases.forms`
   and `hearings.forms` now delegate to it. Regression:
   `test_task_edit_keeps_archived_client`.

2. **A task could not be created against a closed case from the case page** — the
   `?case=` link on a closed case's المهام tab pre-selected nothing (the picker
   lists only open cases) and the case was absent from the dropdown.
   → `TaskCreateView` / `DeadlineCreateView` widen the `case` field to include a
   `?case=` value the user can see (even a closed one), after verifying it
   against `Case.objects.for_user`. Regression:
   `test_task_create_on_closed_case_via_query`.

════════════════════════════════════════
6. SECURITY-REVIEW RESULT  —  PASS
════════════════════════════════════════

- **Object-level authz** — every task/deadline view routes through
  `Model.objects.for_user()` + `assert_scoped`; `_get_task` also filters
  `.alive()` so a soft-deleted row 404s. `CapabilityRequiredMixin` /
  `@require_capability` gate read (`tasks.view`) vs. write (`tasks.manage`);
  missing pk → 404, denied capability → 403, anonymous → login redirect.
  `_widen_case_field` verifies the `?case=` value against the scoped case
  queryset before trusting it.
- **URL tampering** — `?case=` / `?client=` / `?assignee=` are digit-checked and
  resolved through scoped querysets / `ModelChoiceField` validation; a bogus id
  is ignored, never 500s.
- **Mass-assignment** — `TaskForm` / `DeadlineForm` have explicit `Meta.fields`;
  the services filter `data` to hardcoded `TASK_EDITABLE` / `DEADLINE_EDITABLE`
  tuples; `status`, `completed_at`, `deleted_at`, `deleted_by`, `created_by` are
  never form-settable — status changes only via the dedicated POST action.
- **CSRF** — every mutating form carries `{% csrf_token %}`; `task_status`,
  `task_delete`, `deadline_status` are `@require_POST` + `@require_capability`.
- **Audit coverage** — all 7 lifecycle transitions write an append-only
  `AuditLog` row (actor, entity, field-name-only change dict). Tasks/deadlines
  carry no `SENSITIVE_FIELDS`, so nothing is redacted-by-omission.
- **No sensitive-data leakage** — the landing widgets and calendar are all
  scoped; anonymous callers get nothing. No new dependencies.
- **No hard-delete of legal records** — deadlines are cancel-only; tasks
  soft-delete (row retained, audited, recoverable).

════════════════════════════════════════
7. PERFORMANCE-REVIEW RESULT  —  PASS (single-office scale)
════════════════════════════════════════

- `task_list` / `deadline_list` — `select_related` covers every template FK
  access; `is_overdue` reads in-memory fields (no query); `.alive()` / `.open()`
  / `.overdue()` hit the `deleted_at` / `status` / `due_date` indexes;
  pagination caps size; one query per submitted GET filter.
- `LandingView` — 4 queries (my-open, overdue list + count, upcoming deadlines),
  each `select_related` and `[:8]`-sliced.
- `calendar_items` — 2 queries (tasks, deadlines) added to the agenda's 1
  (hearings) = 3 per calendar view; `select_related(case, assigned_to)`; no N+1.
- Case detail — +2 queries (`case_tasks`, `case_deadlines`, both lazy in the
  template).
- `with_current_choice` stays lazy (`.distinct() | .distinct()`), no eager
  id-collection.
- `assertNumQueries` guards deferred to Phase 13 (consistent with Phases 2–4).

════════════════════════════════════════
8. PHASE 5 DoD VERIFICATION
════════════════════════════════════════

| DoD item (spec §82 Phase 5 + house rules)        | Status |
|--------------------------------------------------|--------|
| Task model, assignment, status, priority, due    | ✅ |
| Overdue logic (server-side, not JS-only, §32)    | ✅ computed property + queryset (ADR-0006) |
| Case / client relationships                      | ✅ optional FKs both models |
| Deadlines                                        | ✅ distinct `Deadline` model |
| Dashboard integration                            | ✅ landing widgets (full dashboard = P9) |
| Calendar integration                             | ✅ `calendar_events` merges tasks + deadlines |
| Filtering / search / pagination                  | ✅ both list views |
| Permissions / capability layer + sync_roles      | ✅ `tasks.view` / `tasks.manage` |
| Audit coverage                                   | ✅ 7 AuditAction + 5 CaseEventType |
| No mass assignment                               | ✅ explicit fields + service allowlists |
| No hard-delete of legal records                  | ✅ deadline cancel-only; task soft-delete |
| Timezone-aware datetimes                         | ✅ `completed_at`, calendar `combine()` (due dates are DateField by design) |
| Decimal for money                                | n/a (no money in Phase 5) |
| PostgreSQL-compatible schema/indexes             | ✅ + guarded trigram migration |
| Arabic-first, native RTL UI                      | ✅ logical utils, `{% translate %}`, `<bdi>`/`{% num %}` |
| Western digits for ids/dates                     | ✅ `{% num %}` / `{% datestr %}` |
| Tests (unit + view + permission + security)      | ✅ 47 new, 337 total |
| ruff / format / pip-audit / check --deploy       | ✅ all clean |

════════════════════════════════════════
9. DEFERRED / UNVERIFIED
════════════════════════════════════════

Environment blocker (identical to Phases 1–4 — this machine cannot run Docker or
PostgreSQL: low RAM, network stalls). Owner has accepted these each phase:

1. **Full suite not run against PostgreSQL 16** — SQLite only.
2. **`tasks/migrations/0002_task_search_indexes` not executed** — PG-only,
   vendor-guarded → skipped on SQLite.
3. **`@pytest.mark.postgres` tests unverified** (3 skipped).
4. **`docker compose` full-stack smoke** — not run (equivalent verified via the
   Django test client HTTP smoke).
5. **`compilemessages`** — Docker-only (gettext); harmless (ships `ar`).

Exact remaining PostgreSQL checks:
```
docker compose build
docker compose run --rm web python manage.py migrate     # tasks 0001 + 0002, cases 0005 apply
docker compose run --rm web pytest                        # expect 340 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/tasks/    # 302 -> /accounts/login/
```

Deferred to later phases (scope, not gaps):
- Task/deadline reminders & "task overdue" / "deadline approaching" notifications
  — Phase 11 (a scanning command over the computed predicate).
- Task reports (pending / completed / overdue / by-employee) — Phase 10.
- Full operational dashboard (today's hearings, case analytics, financials,
  charts) — Phase 9.
- Meeting / contract-expiration calendar sources — Phases 7+ (extend
  `calendar_events`).
- `assertNumQueries` guards on the new pages — Phase 13.

════════════════════════════════════════
10–13. GIT
════════════════════════════════════════

10. Commit hash:   bcf4968  ("phase(5): complete tasks and deadlines" —
                   54 files changed, +2930 / −43; parent 9557168 = master @ Phase 4 merge)
11. Push result:   pushed to origin/phase/5-tasks-deadlines (new branch, tracking set).
12. Current branch: phase/5-tasks-deadlines
13. Final git status: working tree clean; branch up to date with
                   origin/phase/5-tasks-deadlines; 1 commit ahead of origin/master;
                   NOT merged.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMITTED + PUSHED — WAITING FOR USER APPROVAL OF PHASE 5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
