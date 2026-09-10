━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:      7 — Contracts
Status:     COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
            (same environment blocker as Phases 1–6; every other DoD item met)
Branch:     phase/7-contracts — based on master @ 46dc56e (Phase 6 merge, PR #5)
Design:     docs/adr/0031-contracts.md (Accepted)

════════════════════════════════════════
1. WHAT WAS IMPLEMENTED  (spec §37, §21, §33, §82 Phase 7)
════════════════════════════════════════

## `contracts` app — one model

### Contract (spec §37)
`contract_number` (`CT-YYYY-NNNN` via `core.numbering`, scope `"contract"`,
`editable=False`, `unique`, gaps acceptable — ADR-0021) · `title` (human label —
§37's field list is "potential", every other top-level record has one) ·
`contract_type` (`ContractType` `TextChoices`: retainer / engagement / services /
consulting / lease / employment / nda / settlement / other — stable legal
vocabulary, a configurable table is a later change) · `client` FK **PROTECT,
required** · `case` FK **SET_NULL, optional** (§97 — a contract may be tied to a
matter or stand alone) · `start_date` (required) · `end_date` (**nullable** —
open-ended retainers) · `value` (`DecimalField(14,2)`, nullable) + `currency`
(`Currency` `TextChoices` ILS / JOD / USD / EUR, default ILS) — a **single stored
amount, no arithmetic** (Phase 8 builds invoicing on top additively) ·
`status` (`ContractStatus` exactly per §37: draft `مسودة` / active `ساري` /
expired `منتهي` / cancelled `ملغى`) · `description`, `notes` (`TextField`, blank).
`TimeStampedModel` + `AuthoredModel`.

- **No soft-delete.** A contract is legally significant (ADR-0022 — same class as
  `Hearing` / `Deadline`): `default_permissions = ("add", "change", "view")`,
  admin `has_delete_permission = False`. "cancel" is a status transition; there
  is no delete path in the app.
- **`CheckConstraint`s** (mirrored in `Contract.clean()`): `value` null or `>= 0`;
  `end_date` null or `>= start_date`.
- `ContractQuerySet(ScopedQuerySet)` — `for_user` (all staff, ADR-0008),
  `active`, `open`, `past_due`, `expiring_soon(within_days=30)`, `search`.
  6 indexes.
- **`notes` and `value` are excluded from search + the trigram index** (spec §4).
  `SEARCH_FIELDS = (contract_number, title, description)`; `contracts/0002`
  trigram guard `TRGM_COLUMNS == SEARCH_FIELDS` (regression-tested).

## Expiration — a real status + a computed "past due" flag (ADR-0006)

- **Computed, never stored:** `Contract.is_expiring_soon` / `is_past_due` /
  `days_until_expiry` properties, and `ContractQuerySet.expiring_soon()` /
  `.past_due()` filters. The list, the calendar and the landing widget read
  these.
- **Status transition:** `contracts.services.expire_due_contracts` — flips
  `active` contracts whose `end_date` has passed to `expired`; audited; one
  `CaseEvent` per case-linked row; **idempotent**. Exposed as the
  `expire_contracts` management command (ADR-0005 / architecture §12 — running
  it on cron is a Phase 14 deployment concern; the command exists + is tested
  now).
- Manual transitions go through `contracts.services.change_contract_status`
  (`draft↔active↔expired` reachable; **`cancelled` is terminal** — a further
  transition raises `ValidationError`, surfaced as a form message). The create
  form offers only `draft` / `active`; `status` is **not** on the edit form and
  **not** in the service's `EDITABLE` set.

## `contracts.services` — transactional writes (ADR-0018)

`create_contract` / `update_contract` / `change_contract_status` /
`expire_due_contracts`. `AuditLog` carries **metadata only** (`contract_number`,
`title`, `contract_type`, `status`, or changed field names — never
`notes` / `description` / `value` bodies, ADR-0009). A **case-linked** contract
records a `CaseEvent` (`CONTRACT_ADDED` on create, `CONTRACT_STATUS_CHANGED` on
status change / auto-expiry) — metadata edits do **not** emit a `CaseEvent`
(same rule as documents). `update_contract` re-fetches the persisted row for the
diff (ModelForm `_post_clean` mutates the instance — cf. bug-027).

## `contracts.selectors` — scoped reads (ADR-0019)

`contract_list` (search + status/type filters + "expiring soon" toggle;
default branch hides closed rows — the `else` branch, cf. bug-055),
`case_contracts`, `client_contracts`, `expiring_contracts`, and
`calendar_items(user, start, end)` (one all-day event per **active** contract
whose `end_date` falls in the window — appended to
`agenda.selectors.calendar_events`, ADR-0028, fulfils §33).

## Documents link (spec §34)

`documents.Document` gains a nullable `contract` FK (SET_NULL,
`related_name="documents"`) — migration `documents/0003`. Wired into the upload /
edit forms (a third scoped picker via `_DocLinksMixin`, `with_current_choice` on
edit), `documents.selectors` (`contract_documents`, a `contract_id` list filter),
`documents.services` (`METADATA_EDITABLE`). The contract detail page lists its
documents with an upload link (`?contract=&client=`). No new capability —
document access stays `documents.view` / `documents.manage`.

## Permissions (ADR-0007, ADR-0031)

- **`contracts.view`** — all staff (incl. finance_clerk: a contract's value and
  term are billing context; §21). List + detail.
- **`contracts.manage`** — office_manager, lawyer, admin_clerk (**the client-
  handler set**, NOT the case-handler set — **paralegal is view-only** here,
  §12). Create / edit / status.
- `core.permissions.capabilities` — `CONTRACTS_VIEW` added to `_ALL_STAFF`,
  `_CONTRACT_HANDLERS = {CONTRACTS_MANAGE}` on lawyer / admin_clerk / office_manager.
- `sync_roles` maps `contracts.{view,add,change}_contract` (no `delete`
  codename). `sync_roles --check` clean.
- `audit.AuditAction`: 3 `CONTRACT_*` members. `cases.CaseEventType`: 2 new
  members (`CONTRACT_ADDED`, `CONTRACT_STATUS_CHANGED`) — migration `cases/0007`.

## UI

`contracts` app: list (search + type/status filters + "expiring soon" toggle,
pagination), detail (terms + linked documents + status action + "cancelled is
terminal" note), create/edit form. Case workspace gains a real **العقود** tab;
the client profile gains a contracts card (العقود removed from `disabled_tabs`).
Nav: **المستندات والعقود → العقود** is now a live link (+ **عقد جديد**).
`core:landing` gains a **عقود قريبة من الانتهاء** widget (next 30 days) for users
with `contracts.view`. Arabic-first RTL, Western digits via `{% num %}`, `<bdi>`
for the value, existing components — no new frontend anything.
`seed_demo_contracts` management command.

════════════════════════════════════════
2. TESTS
════════════════════════════════════════

**437 pass / 3 skipped** (SQLite) — was 388/3; **+49 contracts tests**
(`test_models`, `test_services`, `test_selectors`, `test_views`,
`test_permissions`, `test_smoke`). Existing 388 unchanged and still green.

Covered: number allocation · CheckConstraints + `clean()` (value, dates) ·
computed flags (`is_past_due` / `is_expiring_soon` / `days_until_expiry`) ·
queryset filters · metadata-only audit (notes body never logged) ·
status transition guard + `cancelled` terminal · `expire_due_contracts`
idempotency + scope (only `active` rows) · capability matrix (paralegal
view-only) · IDOR / anon / mass-assignment (`contract_number` server-side,
`status` not editable) · case-tab + client-card + landing-widget integration ·
agenda aggregator includes contracts · trigram columns == SEARCH_FIELDS ·
`expire_contracts` + `seed_demo_contracts` commands run.

`ruff check` / `ruff format --check` / `makemigrations --check` /
`manage.py check` — all clean.

════════════════════════════════════════
3. DEFERRED / UNVERIFIED  (unchanged environment blocker — Phases 1–7)
════════════════════════════════════════

1. Full suite on **PostgreSQL 16** (SQLite only here).
2. Guarded trigram / `pg_trgm` migrations never executed on real PG
   (`core/0002`, `clients/0002`, `cases/0003`, `courts/0003`, `tasks/0002`,
   `documents/0002`, **`contracts/0002`**).
3. `@pytest.mark.postgres` tests (3 skipped).
4. `docker compose` full-stack smoke.
5. `compilemessages` (Docker-only; harmless).
6. Real-FS `PrivateFileSystemStorage` on Linux prod.

Run on a PG-capable machine / CI:
```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest      # expect 440 pass, 0 skipped
docker compose run --rm web python manage.py sync_roles --check
```

════════════════════════════════════════
4. FILES
════════════════════════════════════════

New: `contracts/` (app: models, services, selectors, forms, views, urls, admin,
audit, apps, 2 migrations, 2 management commands, 6 test modules + factories),
`templates/contracts/` (list, detail, form, _badges),
`docs/adr/0031-contracts.md`, `docs/PHASE_7_REPORT.md`.

Changed: `core/permissions/capabilities.py`, `accounts/.../sync_roles.py`,
`audit/models.py`, `cases/models.py` + `cases/0007`, `cases/views.py`,
`templates/cases/case_detail.html`, `clients/views.py`,
`templates/clients/client_detail.html`, `agenda/selectors.py`, `core/views.py`,
`templates/core/landing.html`, `core/navigation.py`,
`documents/{models,forms,selectors,services,views,admin}.py` + `documents/0003`,
`templates/documents/{document_detail,document_form}.html`,
`config/settings/base.py`, `config/urls.py`.
