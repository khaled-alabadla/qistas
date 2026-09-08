━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      3 — Cases (+ minimal Courts)
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
            (same environment blocker as Phases 1–2; all other DoD items met)
Branch:     phase/3-cases — based on master @ f011d20 (merged Phase 2), pushed, NOT merged.
            One commit: phase(3): complete cases

---

Implemented (spec §22–28, §48, §82 Phase 3):

- **`cases` app** + **`courts` app (minimal)** added to `LOCAL_APPS`.
- **`Case` model** (central object — spec §22)
  - `case_number` = `CS-YYYY-NNNN` (transaction-safe via `core.numbering`, ADR-0021,
    `editable=False`, gaps acceptable)
  - `internal_reference` (office file number) **and** `court_case_number` (court
    docket, `db_index`) as separate fields — resolves grill P3
  - FK `type` → configurable **`CaseType`** table (spec §23); 7 Arabic defaults
    (`مدنية، تجارية، عمالية، جزائية، أحوال شخصية، إدارية، أخرى`) seeded by a
    reversible data migration
  - FK `client` **PROTECT**; `assigned_lawyer` (SET_NULL) + `supporting_lawyers`
    M2M through `CaseLawyer` (`through_fields=("case","lawyer")`)
  - FK `court` (SET_NULL, minimal `courts.Court`)
  - `status` (new / in_progress / in_trial / on_hold / concluded / closed),
    `priority` (low / medium / high / urgent), `stage`, `department`
  - `claim_amount` `Decimal(14,2)` with DB `CheckConstraint` (≥ 0 or NULL)
  - 8 indexes; **no `next_hearing`** — deferred to Phase 4 (Hearings) for a clean
    phase boundary
  - closing = a `status` change, never a delete (ADR-0022)
- **`CaseConfidential`** (1:1) — `legal_notes` / `internal_notes`, both added to
  `core.sensitive.SENSITIVE_FIELDS`. Isolated row: never selected by the list
  selector, search, or the timeline; only fetched when the viewer has
  `cases.view_confidential`; masked in the django-auditlog diff. `set_confidential`
  writes an **`AuditLog` event only — deliberately no `CaseEvent`** so the
  staff-visible timeline never reveals that privileged notes changed.
- **`CaseParty`** — per-case relationship model (client / opponent / counsel /
  representative / other), optional link to a `Client` or `User` (spec §27).
- **`CaseNote`** — general note / correspondence; soft-deletable (`deleted_at`, ADR-0022).
- **`CaseEvent`** — append-only human-readable timeline (spec §26). Every
  `cases.services` mutation records one; `_AppendOnlyQuerySet` + `.delete()` raise
  `PermissionError`. Later phases (hearings, tasks, documents) will emit events too.
- **Workspace detail view** — tabbed: نظرة عامة / الأطراف / الملاحظات / المراسلات /
  الخط الزمني (all real), plus disabled placeholders الجلسات / المهام / المستندات /
  الفواتير / المدفوعات (their modules don't exist yet).
- **CRUD + actions** — list (search + status/priority/type/lawyer filters,
  open-only by default, pagination 25/page, Arabic empty state), create, edit,
  status change (own POST action → `change_status`, emits CLOSED / REOPENED /
  STATUS_CHANGED), supporting-lawyer add/remove, party add/remove, note add,
  confidential-notes edit page (capability-gated).
- **Authorization (ADR-0007, 0008, 0019)**
  - `Case.objects.for_user()` — all rows for an authed user, none for anonymous;
    every view routes through it + `assert_scoped`; missing pk → **404**
  - capabilities: `cases.view` (all 5 groups) · `cases.manage` (office_manager,
    lawyer, paralegal, admin_clerk) · `cases.view_confidential` (office_manager,
    lawyer) — wired into `GROUP_CAPABILITIES`
  - `sync_roles` extended with `cases.*` + `courts.*` Django model perms
    (`view/add/change_case`, `view_confidential_case`, `caseparty`, `casenote`,
    `caselawyer`, `casetype`, `court`); `--check` drift still clean
  - `Case.Meta.permissions = [("view_confidential_case", …)]`
- **Audit (ADR-0020)** — `Case`, `CaseParty`, `CaseConfidential` registered with
  django-auditlog (timestamps excluded; `CaseConfidential` masks the two note
  fields via `SENSITIVE_FIELDS`). 7 new `AuditAction` members
  (`CASE_CREATED/UPDATED/STATUS_CHANGED/LAWYER_CHANGED/PARTY_CHANGED/NOTE_ADDED/
  CONFIDENTIAL_UPDATED`). `cases/services.py` emits readable `AuditLog` events.
- **Layering** — `cases/services.py` (all transactional writes; `update_case`
  diffs against a **freshly-fetched** `Case` row and no-ops when nothing changed —
  the bug-027 pattern) + `cases/selectors.py` (`case_list`, `case_parties`).
- **Search** — `icontains` OR over case_number / title / court_case_number /
  internal_reference / department (portable SQLite + PostgreSQL).
  `cases/migrations/0003` adds trigram GIN indexes with
  `TRGM_COLUMNS == SEARCH_FIELDS`; a test keeps them in sync (bug-028 pattern).
- **`courts` (minimal)** — `Court` (name / type / city / is_active,
  `(name, city)` unique) + admin + `seed_demo_courts` (7 realistic Palestinian
  courts). Full court management UI + address/phone/notes fields are Phase 4.
- **Nav** — "القضايا › جميع القضايا / إضافة قضية / الجلسات (disabled)" added to
  `core.navigation.NAV`, capability-filtered.
- **Demo data** — `seed_demo_cases` (4 realistic cases; needs clients + courts;
  idempotent-guard on any existing case).

---

Files Changed (single `phase(3): complete cases` commit):
- new: `cases/` (models, services, selectors, forms, views, urls, admin, apps,
  audit, 3 migrations, seed command, factories, 7 test modules),
  `courts/` (models, admin, apps, 1 migration, seed command, 1 test module),
  `templates/cases/` (7 templates + `_notes.html` partial)
- edited: `config/settings/base.py` (+`courts`, +`cases`), `config/urls.py`,
  `core/navigation.py`, `core/permissions/capabilities.py` (+3 capabilities),
  `core/sensitive.py` (+`legal_notes`, `internal_notes`), `audit/models.py`
  (+7 `CASE_*` actions), `accounts/management/commands/sync_roles.py`,
  `PROJECT_STATUS.md`, `docs/architecture.md`

Database Changes:
- `courts.Court` (+ `(name, city)` unique)
- `cases.CaseType` (+ 7 seeded rows), `cases.Case` (+ 8 indexes, unique
  `case_number`, `claim_amount` CheckConstraint, `view_confidential_case` perm),
  `cases.CaseConfidential` (1:1), `cases.CaseLawyer`, `cases.CaseParty`,
  `cases.CaseNote`, `cases.CaseEvent`
- `cases` migration 0003 — trigram GIN indexes on every searched column
  (PostgreSQL only, vendor-guarded)
- No changes to any Phase 1/2 table (audit `AuditAction` additions are Python-only).

---

Tests:
Total:   227 collected
Passed:  224
Failed:  0
Skipped: 3  — `@pytest.mark.postgres` (the 2 Phase 1 PG tests + client-number
             concurrency); run only on a PostgreSQL backend.
(69 of the 227 are new cases/courts tests, incl. 6 code-review regressions.)

New coverage (64 tests):
- **models** — `for_user` scoping (authed / anon), `open()` excludes terminal
  statuses, search hits title + docket, `case_number` uniqueness,
  `get_confidential` idempotent, `CaseEvent` append-only, `claim_amount`
  constraint, `CaseType.__str__`
- **services** — number allocation + audit, lawyer-assignment event, `update_case`
  no-op guard **and** real-diff, status → CLOSED / REOPENED events, party
  add/remove, supporting-lawyer add (idempotent) / remove, note add,
  `set_confidential` is audit-only (no `CaseEvent`) + no-op guard
- **views** — list login-required / any-staff / hides-closed / pagination, detail
  200 + 404, every tab renders, unknown tab → overview, create (number +
  `created_by`), create forbidden for finance_clerk (403), update, status action,
  status GET → 405, party add/remove, note add (paralegal)
- **permissions** — 5-role × view/manage/confidential matrix, edit forbidden
  without manage, confidential view 403 without capability / 200 for lawyer,
  `sync_roles --check` clean after sync
- **confidential** — secret absent from detail for unprivileged + `confidential`
  not in context, visible to privileged, never in timeline, masked in the
  auditlog `LogEntry` diff, edit-via-view persists
- **search** — selector search + filters compose, closed excluded unless asked,
  `TRGM_COLUMNS == SEARCH_FIELDS`
- **audit** — `Case` / `CaseParty` / `CaseConfidential` registered, create writes
  a `LogEntry`, confidential note content masked in `LogEntry.changes`
- **courts** — `__str__` with/without city, `(name, city)` unique, seed idempotent

Run on **SQLite** — canonical PostgreSQL run **DEFERRED** (see Known Issues).

Also clean: `ruff check` · `ruff format --check` · `pip-audit` ·
`makemigrations --check` · `manage.py check --deploy --fail-level WARNING`
(config.settings.prod, strong ephemeral SECRET_KEY).

HTTP smoke (`runserver` + SQLite, superuser login): `/cases/` list, `/cases/1/`
workspace, `?tab=parties|notes|timeline`, `/cases/new/`, `/cases/1/edit/`,
`/cases/1/confidential/`, `/cases/1/parties/new/` — all **200**. `seed_demo_courts`
(7), `seed_demo_clients` (8), `seed_demo_cases` (4), `sync_roles` — all run clean.

---

Code Review:
`/code-review` (high) — **6 findings, all fixed before the commit** with
regression tests:
1. **`CaseForm` (reused for edit) restricted `type` / `client` / `court` /
   `assigned_lawyer` to active/non-archived rows** → editing an unrelated field
   on a case whose `CaseType` was later deactivated (or lawyer set inactive, or
   client archived) silently NULLed `court` / `assigned_lawyer` and hard-locked
   the save on the required `type` / `client`. → `_with_current()` widens each
   picker's queryset to always include the value the case already holds. Tests:
   `test_edit_case_with_deactivated_type_keeps_value`,
   `test_edit_form_offers_current_inactive_type`.
2. **The detail "activity" panel showed `CASE_CONFIDENTIAL_UPDATED` audit rows to
   every `cases.view` user** — leaking that privileged notes exist and who edits
   them, contradicting the ADR-0008 isolation intent. → the panel now excludes
   that action unless the viewer has `cases.view_confidential`. Test:
   `test_activity_panel_hides_confidential_event_from_unprivileged`.
3. **`Case.get_confidential()` did `get_or_create()` and was called on GET**
   (detail view + confidential form) → merely viewing a case wrote an empty
   `CaseConfidential` row + a django-auditlog "created" `LogEntry` attributed to
   the viewer, on a non-CSRF-protected GET. → added `Case.confidential_or_none()`
   (read-only); GET paths use it; the row is created only by
   `services.set_confidential` on save. Test:
   `test_reading_a_case_never_creates_a_confidential_row`.
4. **`remove_supporting_lawyer` / `case_lawyer_remove` reported success on a
   no-op** (double submit, or a valid user who isn't a supporting lawyer). →
   `add_/remove_supporting_lawyer` return `bool`; the views show a distinct
   info message when nothing changed. Test updated in `test_services.py`.
5. **`CaseDetailView` ran `case.lawyer_links.select_related("lawyer")` twice**
   per render (context var + `case_parties`). → fetched once into a list and
   passed to `case_parties(case, lawyer_links=…)`.
6. **`update_case` re-fetched the row without `select_related`** → up to 4 extra
   per-FK SELECTs on every edit. → `stored` is now loaded with
   `select_related("type","client","assigned_lawyer","court")`.

Self security review below.

Security Review (self — spec §70):
- **Confidential isolation** — `legal_notes` / `internal_notes` live on a separate
  1:1 row, never in `SEARCH_FIELDS`, never selected by `case_list`, never rendered
  outside the `cases.view_confidential` branch, masked in the auditlog diff, in
  `SENSITIVE_FIELDS` (log redaction). `set_confidential` emits no `CaseEvent`, so
  the timeline (visible to all staff) cannot even hint that they changed.
- **Object-level** — every case view routes through `Case.objects.for_user()` +
  `assert_scoped`; `CapabilityRequiredMixin` gates read (`cases.view`) and write
  (`cases.manage` / `cases.view_confidential`); sub-resources (`CaseParty`,
  `CaseLawyer`) are always reached via the scoped parent case.
- **CSRF** — every mutating form has `{% csrf_token %}`; every function action is
  `@require_POST` + `@require_capability`.
- **Mass-assignment** — `CaseForm` has an explicit field list (no `status`,
  `case_number`, `created_by`); `status` changes only through the dedicated action
  → `change_status`. `case_number` / `created_by` / `updated_by` are set by the
  service, never the form.
- **SQL** — ORM only; the trigram migration interpolates a hardcoded column tuple.

Performance Review:
- `case_list` — `select_related("type","client","assigned_lawyer","court")`;
  one query per submitted filter (GET form, not live); pagination caps size;
  trigram GIN (PG) for scale.
- Detail — `select_related` on the case; timeline capped at 100, activity at 20,
  notes fetched once and partitioned in Python.
- `assertNumQueries` guards not yet added — noted for Phase 13 (same as Phase 2).

---

Known Issues — DEFERRED / UNVERIFIED (same environment blocker as Phases 1–2:
the session machine cannot run Docker or PostgreSQL — low RAM, network stalls):
1. **Full suite not run against PostgreSQL 16** — SQLite only.
2. **`cases/migrations/0003_case_search_indexes` not executed** — PostgreSQL-only,
   vendor-guarded → skipped on SQLite.
3. **`@pytest.mark.postgres` tests unverified**.
4. **`docker compose` full-stack smoke** — not run (equivalent verified via `runserver`).
5. **`compilemessages`** — Docker-only (gettext); harmless (ships `ar`).

Exact remaining PostgreSQL checks:
```
docker compose build
docker compose run --rm web python manage.py migrate        # cases 0003 applies
docker compose run --rm web pytest                          # expect 227 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/cases/      # 302 -> /accounts/login/
```

---

Deferred Items (carried forward):
- Full `courts` management UI + address/phone/notes fields — Phase 4
- `hearings` + `Case.next_hearing` computed/related display — Phase 4
- Standalone office-wide Party directory (P3 ships per-case `CaseParty`) — Phase 4+
- Case ↔ documents / contracts / invoices / payments tabs — Phases 6 / 7 / 8
- Case optimistic-locking UI on concurrent edit — Phase 8 (grill F5)
- `pg_trgm` search ranking (currently unranked `icontains`) — Phase 13 if needed
- `assertNumQueries` guards on the case list/detail pages — Phase 13
- Case status **state machine** (any→any allowed in v1) — revisit if the office asks

Assumptions:
- All staff see all cases; `legal_notes` / `internal_notes` are the only
  per-field gate in Phase 3 (ADR-0008 / 0009).
- `case_number` gaps are acceptable (ADR-0021).
- A `Case` always has a `client` and a `type`; `court` / `assigned_lawyer` are optional.

Ready for Approval:
Owner to accept the deferred PostgreSQL/Docker items (as with Phases 1–2) — every
other DoD item is met.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMITTED + PUSHED — WAITING FOR USER APPROVAL OF PHASE 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
