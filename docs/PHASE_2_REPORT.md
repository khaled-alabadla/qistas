━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      2 — Clients
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED (same
            environment blocker as Phase 1; all other DoD items met)
Branch:     phase/2-clients — one commit `phase(2): complete clients`, pushed.
            NOT merged to master. Based on master @ 4c320ec.

---

Implemented (spec §20–21, §48, §82 Phase 2):

- **`clients` app** — `core`, `accounts`, `audit`, `clients` are the tracked apps.
- **`Client` model**
  - individual / company; `client_number` (`CL-YYYY-NNNN`, transaction-safe via
    `core.numbering`, gaps acceptable — ADR-0021, editable=False)
  - fields per spec §20: type, full_name, company_name, national_id,
    registration_number, phone, secondary_phone, email, address, city, status, notes
  - `status`: active / inactive / prospect / archived
  - **DB `CheckConstraint`** `client_name_matches_type` + mirrored `Model.clean()`
  - indexes: client_number, phone, status, type, -created_at
  - custom `view_sensitive_client` permission
- **CRUD + profile**
  - list — search + type filter + status filter + pagination (25/page); realistic
    Arabic empty state with a "add client" CTA
  - detail — profile header (name + type + status badges + number), overview
    section (all fields, sensitive gated), Notes, Activity (from `AuditLog`),
    financial-summary placeholder, and disabled tabs for
    القضايا/المستندات/العقود/الفواتير/المدفوعات (their modules don't exist yet)
  - create / update — `ClientForm` with individual↔company toggle (Alpine),
    conditional validation, sensitive fields removed for users without the capability
  - **archive** (confirm page → POST) and **restore** — status changes, audited;
    **no delete** (ADR-0022)
- **Authorization (ADR-0007, 0008, 0019)**
  - `Client.objects.for_user()` — all rows for any authed staff, none for anonymous;
    `assert_scoped` enforced in every list/detail view
  - missing pk → **404** (no per-row siloing to conceal)
  - capability gates: `clients.view` (all 5 groups) · `clients.manage`
    (office_manager, lawyer, admin_clerk) · `clients.view_sensitive` (same as manage)
  - `sync_roles` extended: Django model perms (`view/add/change_client`,
    `view_sensitive_client`) mapped to the right groups; `--check` drift still clean
- **Sensitive data — `national_id` + `registration_number` (ADR-0009)**
  - both added to `core.sensitive.SENSITIVE_FIELDS` (a `/code-review` finding: the
    UI gated `registration_number` but it wasn't registered, so it leaked into the
    audit diff + logs)
  - excluded from `SEARCH_FIELDS` and from the trigram GIN index
  - never rendered in the list; hidden ("محجوب") on detail without the capability
  - removed from the form for users without the capability (can't read or blank them)
  - masked in the django-auditlog diff — `clients/audit.py` derives `mask_fields`
    from `SENSITIVE_FIELDS`
  - `AuditLog` "client.updated" logs changed **field names**, not values
- **Audit (ADR-0020)** — `Client` registered with django-auditlog (excludes
  timestamps + notes, masks national_id + registration_number via SENSITIVE_FIELDS). `clients/services.py` additionally emits
  readable `AuditLog` events: `client.created/updated/archived/restored` — new
  `AuditAction` members + an `action_label` property.
- **Search** — `icontains` OR across client_number / full_name / company_name /
  phone / secondary_phone / email / city (portable SQLite + PostgreSQL).
  `clients/migrations/0002` adds `pg_trgm` GIN indexes for every searched column, guarded to PostgreSQL.
- **Nav** — "العملاء › جميع العملاء / إضافة عميل" added to `core.navigation.NAV`,
  capability-filtered (spec §16).
- **Demo data** — `python manage.py seed_demo_clients` — 8 realistic Palestinian
  clients (شركة الوفاق التجارية، محمود أحمد درويش، …), idempotent (spec §61).

---

Files Changed (all in the single `phase(2): complete clients` commit):
- new: `clients/` (models, services, selectors, forms, views, urls, admin, audit,
  2 migrations, seed command, 8 test modules, factories) + `templates/clients/` (4)
- edited: `config/settings/base.py` (+`clients`), `config/urls.py`, `conftest.py`
  (role fixtures), `core/navigation.py`, `core/permissions/capabilities.py`
  (+3 capabilities), `core/sensitive.py` (national_id + registration_number), `audit/models.py` (client actions +
  `action_label`), `accounts/management/commands/sync_roles.py`,
  `accounts/tests/test_sync_roles.py`
- 41 files, ~1.95k insertions

Database Changes:
- `clients.Client` (+ 5 indexes, unique `client_number`, CheckConstraint,
  `view_sensitive_client` permission)
- `clients` migration 0002 — trigram GIN indexes on every searched column (PostgreSQL only, guarded)
- No changes to any Phase 1 table (audit `AuditAction` additions are Python-only).

---

Tests:
Total:   161 collected
Passed:  158
Failed:  0
Skipped: 3  — `@pytest.mark.postgres` (client-number concurrency + the 2 Phase 1
             PG tests); run only on a PostgreSQL backend.
(59 of the 161 are new client tests.)

New client coverage (59 tests): model (numbering, uniqueness, name/type
constraint at both layers, display_name, `for_user` scoping, active()),
concurrency (PG-marked), views (list/detail/create/update/archive/restore,
pagination, filters, validation), permission matrix (5 roles × view/manage,
403/404/login-redirect), search (field matches + **national_id never matched**),
sensitive (`national_id` hidden/shown by capability, absent from list, redacted in
logs + `log_event`, masked in auditlog), audit (4 lifecycle events + status
transition + idempotency), selectors (always scoped, filters compose).

Run on **SQLite** — canonical PostgreSQL run **DEFERRED** (see Known Issues).

Also clean: `ruff check` · `ruff format --check` · `pip-audit` ·
`makemigrations --check` · `manage.py check --deploy` (prod settings).

---

Code Review:
PASS — `/code-review` (high) returned **3 findings, all fixed before the commit**
with regression tests:
1. `registration_number` was gated in the UI (form + detail) but not added to
   `core.sensitive.SENSITIVE_FIELDS` / auditlog `mask_fields`, so its values were
   written verbatim to the auditlog diff and not scrubbed from logs (ADR-0009).
   → added to `SENSITIVE_FIELDS`; `clients/audit.py` now derives `mask_fields`
   from it automatically.
2. `update_client`'s "changed fields" list was always `[]` when called from
   `ClientUpdateView` — the `ModelForm` mutates the shared instance during
   `is_valid()`, so the service's `getattr(client, f) != v` diff saw no change;
   a no-op save also wrote a spurious `CLIENT_UPDATED` event.
   → the service now diffs against a freshly-fetched row and returns early on a
   true no-op. Tests cover the direct-call **and** the form-view path.
3. `SEARCH_FIELDS` included three columns (`client_number`, `secondary_phone`,
   `email`) that migration 0002 did not trigram-index → an un-indexed column in
   the `icontains` OR forces a sequential scan on PostgreSQL.
   → `TRGM_COLUMNS` now equals `SEARCH_FIELDS` (all 7 indexed); a test keeps them
   in sync.

Security Review:
PASS (self-review — `national_id` is PII, spec §70).
- national_id: not searchable, not indexed for trgm, not in list HTML, capability-gated
  on detail + form, masked in auditlog, in `SENSITIVE_FIELDS` (log redaction),
  `log_event` records field names not values, `object_repr` carries only name+number.
- Object-level: every view routes through `Client.objects.for_user()` + `assert_scoped`;
  capability gate on read + write; write views also 404 on missing object.
- CSRF on every form incl. archive/restore (POST + `{% csrf_token %}`); `@require_POST`.
- Mass-assignment: `client_number` `editable=False` + not in form; `created_by`/
  `updated_by` set by the service, never the form.
- SQL: ORM only; the trigram migration f-strings interpolate a hardcoded column tuple.

Performance Review:
PASS.
- `client_list` — one query per submitted filter form (GET, not live). `select_related`
  on `created_by`. Pagination caps result size. Trigram GIN index (PG) for scale.
- Detail — `select_related("created_by","updated_by")`; Activity capped at 20 rows.
- `assertNumQueries` not yet added to the list/detail pages — noted for Phase 13.

---

Known Issues — DEFERRED / UNVERIFIED (same environment blocker as Phase 1:
the session machine cannot run Docker or PostgreSQL — ~0.2 GB free RAM, network
stalls on large pulls):
1. **Full suite not run against PostgreSQL 16** — SQLite only.
2. **`clients/migrations/0002_client_search_indexes` not executed** — PostgreSQL-only,
   vendor-guarded → skipped on SQLite. Needs a real `migrate` on PG.
3. **`@pytest.mark.postgres` tests unverified** — client-number concurrency, extensions.
4. **`docker compose` full-stack smoke** — not run (equivalent verified via `runserver`).
5. **`make compilemessages`** — Docker-only (gettext); harmless (ships `ar`).

Exact remaining PostgreSQL checks:
```
docker compose build
docker compose run --rm web python manage.py migrate        # clients 0002 applies
docker compose run --rm web pytest                          # expect 161 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/clients/    # 302 -> /accounts/login/
```
CI (`.github/workflows/ci.yml`) runs the suite against a PostgreSQL 16 service on
the first push / PR.

---

Deferred Items (carried forward):
- Client profile tabs for cases / documents / contracts / invoices / payments —
  built when those modules exist (Phase 3, 6, 7, 8)
- Real financial summary on the client profile — Phase 8
- Office-wide Party directory (opposing parties / counsel) — Phase 3
- `pg_trgm` search *ranking* (currently unranked `icontains`) — Phase 13 if needed
- `assertNumQueries` guards on the client list/detail pages — Phase 13
- Client hard-delete (rare admin action with dependent reassignment) — deferred (ADR-0022)

Technical Debt:
- `ClientListView` paginates manually (not `ListView.paginate_by`) so the filter form
  can be built once — acceptable; revisit if list views multiply.
- `_allocate_client_number` (leading underscore) is imported by `seed_demo_clients` —
  it is effectively package-internal API; fine for now.

Assumptions:
- All staff may see all clients; `national_id` visibility is the only per-field gate
  in Phase 2 (ADR-0008/0009).
- `client_number` gaps are acceptable (ADR-0021).
- Palestinian ID / registration formats are free-text in v1 (no validation — ADR-0002).

Ready for Approval:
Owner to accept the deferred PostgreSQL/Docker items (as with Phase 1) — every
other DoD item is met.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMITTED + PUSHED — WAITING FOR USER APPROVAL OF PHASE 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
