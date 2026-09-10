# ADR-0031 — Contracts

- **Status:** Accepted — 2026-09-09
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0006 (computed states, no cron for derived flags),
  ADR-0008 (all staff see all), ADR-0018 (app layout / layering),
  ADR-0019 (object-level authz), ADR-0020 (audit), ADR-0021 (reference numbers),
  ADR-0022 (soft-delete / no-hard-delete — `Contract` is legally significant),
  ADR-0028 (`agenda.selectors.calendar_events` is the one calendar extension point),
  ADR-0030 (documents — the `Document.contract` FK seam), spec §37, §21, §33, §97, §82 Phase 7.
- **Phase:** 7

## Context

Spec §37 + §82 Phase 7: a `Contract` model, CRUD, statuses, dates, values, a
client relationship, a link to documents, and expiration tracking. Spec §37 lists
the statuses verbatim (`مسودة` / `ساري` / `منتهي` / `ملغى`) and the potential
fields (`contract_number`, `client`, `contract_type`, `start_date`, `end_date`,
`value`, `status`, `description`, `notes`). Open questions:

1. Is a contract only client-linked, or also case-linked? (§37 says client; §97
   "case-centered workflow" lists Contracts among what a case reaches.)
2. `منتهي` (expired) is a **status** — but should it be flipped automatically, and
   how does that square with ADR-0006 ("overdue is computed, no cron")?
3. `value` — is this "money functionality" that pulls Finance (Phase 8) forward?
4. Which roles manage contracts?
5. Does the `Document.contract` link (spec §34) land now?

## Decision

### Model — `contracts.Contract`

`TimeStampedModel` + `AuthoredModel` (`created_by` / `updated_by`).

- `contract_number` — `CT-YYYY-NNNN` via `core.numbering` (scope `"contract"`),
  `editable=False`, `unique`, gaps acceptable (ADR-0021 / ADR-0011).
- `title` — a human label. **Not** in the §37 field list, but every other
  top-level record has one (`Case.title`, `Document.name`) and a contract list /
  calendar / timeline entry is unreadable without it. §37's list is "Potential
  fields", not a closed set.
- `contract_type` — a fixed `ContractType` `TextChoices` (retainer / engagement /
  services / consulting / lease / employment / nda / settlement / other) — stable
  legal vocabulary, like `DocumentCategory` / `HearingType`. A configurable table
  is a later change if the office asks.
- `client` — FK **PROTECT**, **required** (spec: "Client relationship"; a contract
  without a counterparty is meaningless). Same `on_delete` as `Case.client`.
- `case` — FK **SET_NULL**, optional (§97). A contract may be tied to a matter or
  stand alone (a retainer covering the whole relationship).
- `start_date` — `DateField`, required. `end_date` — `DateField`, **nullable**
  (open-ended retainers exist).
- `value` — `DecimalField(14, 2)`, **nullable**. `currency` — `Currency`
  `TextChoices` (ILS / JOD / USD / EUR — all circulate in Palestine), default ILS.
  This is a **single stored amount**, informational — there is **no arithmetic**,
  no totals, no invoicing. It is not "money functionality" (that is Phase 8);
  `Decimal` + a `value >= 0` `CheckConstraint` is the whole of it. A future
  `Invoice.contract` FK / fee roll-up is additive.
- `status` — `ContractStatus` `TextChoices` exactly per §37: `draft` (مسودة) /
  `active` (ساري) / `expired` (منتهي) / `cancelled` (ملغى).
- `description`, `notes` — `TextField`, blank. **`notes` and `value` are excluded
  from search and the trigram index** (§4 — "must not be unnecessarily
  searchable/indexed"); `SEARCH_FIELDS = (contract_number, title, description)`.
- **`CheckConstraint`s:** `value` null or `>= 0`; `end_date` null or
  `>= start_date` (mirrored in `Model.clean()`).
- **No soft-delete field.** A contract is legally significant (ADR-0022 — same
  class as `Hearing` / `Deadline`): `default_permissions = ("add", "change",
  "view")`, admin `has_delete_permission = False`, "cancel" is a status
  transition. There is no delete path in the app.

### Expiration — a real status, plus a computed "past due" flag (ADR-0006)

`منتهي` is a genuine lifecycle **status** (unlike task/deadline "overdue", which
ADR-0006 keeps computed). But the office should see a contract is *about to* or
*has* lapsed before anyone flips the status:

- **Computed, never stored:** `Contract.is_expiring_soon` / `is_past_due` /
  `days_until_expiry` properties, and `ContractQuerySet.expiring_soon(within_days=30)`
  / `.past_due()` filters. The list, the calendar and the landing widget read
  these — no stored flag.
- **Status transition:** `expire_contracts` — an **idempotent management command**
  (`contracts.services.expire_due_contracts`) that flips `active` contracts whose
  `end_date` has passed to `expired`, audited, one `CaseEvent` per case-linked
  row. This is the ADR-0005 / architecture §12 pattern ("contract-expiry scans …
  idempotent Django management commands invoked by system cron"). Running it is a
  Phase 14 deployment concern; the command exists now and is tested.
- Manual transitions go through `contracts.services.change_contract_status`
  (draft↔active↔expired reachable; **`cancelled` is terminal**). The create form
  offers only `draft` / `active`; `expired` / `cancelled` are reached through the
  status action. `status` is **not** a field on the edit form and **not** in the
  service's `EDITABLE` set — it can only move through the guarded transition.

### Documents link (spec §34)

`documents.Document` gains a nullable `contract` FK (SET_NULL, `related_name="documents"`)
— migration `documents/0003`. Wired into the upload / edit forms (a third scoped
picker), `documents.selectors` (`contract_documents`, a `contract_id` list
filter) and `documents.services` (`METADATA_EDITABLE`). The contract detail page
lists its documents with an upload link. No new capability — document access
stays `documents.view` / `documents.manage`.

### Calendar (ADR-0028)

`contracts.selectors.calendar_items(user, start, end)` yields one all-day event
per **active** contract whose `end_date` falls in the window (`kind="contract"`,
url → `contracts:detail`). Appended to `agenda.selectors.calendar_events` — the
same one-function extension ADR-0028/0029 describe. Fulfils §33 ("Contract
expirations" in the calendar).

### Landing widget (modest, like ADR-0029)

`core:landing` gains a **عقود قريبة من الانتهاء** widget (next 30 days) for users
with `contracts.view`, alongside the Phase 5 task/deadline widgets. The full
operational dashboard is still Phase 9; this is the same "modest landing
integration" ADR-0029 established, and §37 explicitly says approaching expiration
"should appear in relevant dashboard … areas". Notifications are Phase 11.

### Permissions

- **`contracts.view`** — all staff (incl. finance_clerk: a contract's value and
  term are billing context; §21 lists العقود beside الفواتير on the client
  profile). Covers list + detail.
- **`contracts.manage`** — office_manager, lawyer, admin_clerk — **the client
  handler set** (`clients.manage` holders), not the case-handler set. A contract
  is an engagement instrument with a client; **paralegal is view-only** here
  (§12 — "limited access to assigned work"), unlike documents/tasks. Covers
  create / edit / status.
- `sync_roles` maps `contracts.{view,add,change}_contract` (no `delete` codename).

### Audit + case timeline

- `log_event` on every mutation: `CONTRACT_CREATED` / `CONTRACT_UPDATED` /
  `CONTRACT_STATUS_CHANGED` — `changes` carries **metadata only**
  (`contract_number`, `title`, `contract_type`, `status`, or changed field
  names), never `notes` / `description` / `value` bodies.
- django-auditlog registers `Contract` (excludes `created_at` / `updated_at`);
  its `LogEntry` holds the ordinary field diff (same convention as `Case`).
- **Case timeline:** `CaseEventType.CONTRACT_ADDED` / `CONTRACT_STATUS_CHANGED`
  (two new members) when the contract is case-linked, via
  `cases.services.record_case_event` (`cases/0007`). Metadata edits do **not**
  emit a `CaseEvent` (minor; only the audit trail records them) — same rule as
  documents.

### UI

`contracts` app: list (search + type/status filters + "expiring soon" toggle,
pagination), detail (terms + linked documents + status action), create/edit form.
Case workspace gains a real **العقود** tab; the client profile gains a contracts
card. Nav: **المستندات والعقود → العقود** becomes a live link (+ **عقد جديد**).
Arabic-first RTL, Western digits for numbers / dates / money, `<bdi>` for the
value, existing components — no new frontend anything.

## Consequences

- A contract can be case-linked or free-standing; the case FK is `SET_NULL` so
  deleting a case (a rare admin action) never destroys a contract.
- "Expired" can lag reality until `expire_contracts` runs; the computed
  `is_past_due` flag + the calendar + the landing widget close that gap in the UI
  meanwhile.
- `value` establishes `Decimal` + `currency` on a contract with **no** finance
  logic; Phase 8 builds invoicing on top (a `contract` FK on `Invoice`, fee
  roll-ups) additively.
- `Document.contract` is the third optional owner FK; a future `Invoice`
  documents link (Phase 8) is the fourth, same shape.
- Adding a meeting / other calendar source later is again one change to
  `calendar_events` (ADR-0028).
- Contract reminders / "expiring" notifications are Phase 11 (a scan over
  `expiring_soon()` — the notification is the artifact, not a status change).
