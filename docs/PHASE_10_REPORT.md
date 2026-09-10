━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        10 — Reports
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–9); server-side PDF deferred
              by design (ADR-0034 §7).
Branch:       phase/10-reports — based on master @ 21ff0ea (Phase 9 merge, PR #8)
Design:       docs/adr/0034-reports.md (Accepted)

════════════════════════════════════════
1. IMPLEMENTATION SUMMARY  (spec §43–44, §82 Phase 10)
════════════════════════════════════════

`reports` app — a **read/export layer over the Phase 1–9 domains**. It owns
**no models** (spec §23): every figure is an aggregate or a bounded, capability-
scoped slice of the domains' own `for_user()` managers and existing selectors.

- `reports/framework.py` — a typed `ReportResult` (`Column` / `Cell` /
  `CurrencyTotals` / `Metric`), the inclusive date-range helpers, the
  formula-injection guard `csv_safe`, and `csv_response`.
- `reports/registry.py` — the catalogue: each `Report` binds a URL slug to its
  filter form, its builder, its display group, and **its gating domain
  capability**.
- `reports/forms.py` — all-optional filter forms; `BaseReportForm.resolved_filters()`
  implements the bug-055 filter-resolution rule (§below).
- `reports/selectors.py` — one `build_<name>_report(*, user, filters)` per report.
- `reports/views.py` — `ReportsIndexView` (menu, filtered to runnable reports) +
  `ReportView` (HTML paginated table OR `?format=csv`, audited).
- `reports/templates/reports/` — `index.html`, `report.html` (+ `@media print`
  stylesheet), `_summary.html`, `_table.html`.

Integration: nav gains `التقارير` (between `المالية` and `الإشعارات`);
`Capability.REPORTS_VIEW` added to `_ALL_STAFF` and the office-manager set
(capability-layer only — no `reports` model, so nothing in `sync_roles`);
`AuditAction.REPORT_EXPORTED` added.

════════════════════════════════════════
2. REPORT TYPES  (spec §43 — implemented exactly, nothing invented)
════════════════════════════════════════

General (each gated on its domain `*.view`):

| slug | capability | rows | summary |
|---|---|---|---|
| `cases` | `cases.view` | case · client · type · status · priority · lawyer · court · open-date | count + by-status + by-priority |
| `clients` | `clients.view` | client · type · status · active-case count · total-case count | total / with-active-cases / active / prospect / archived |
| `hearings` | `hearings.view` | datetime · case · client · court · type · status · lawyer | count per status |
| `tasks` | `tasks.view` | task · case/client · employee · priority · status · due · overdue? | count per status + overdue + **by employee** |
| `deadlines` | `tasks.view` | deadline · case · status · due · overdue? | count per status + overdue |

Financial (all gated on **`finance.view`**):

| slug | rows | per-currency totals |
|---|---|---|
| `revenue` | issued invoice · client · case · issue-date · currency · status · total · paid · outstanding | count · invoiced · credited · paid · outstanding |
| `payments` | payment · invoice · client · date · currency · method · amount · reversed · net | gross · reversals · net |
| `outstanding` | open invoice · client · case · issue · due · currency · status · days-overdue · total · outstanding | exact outstanding + 0–30 / 31–60 / 61–90 / 90+ aging |
| `expenses` | expense · description · category · case · client · date · currency · amount | total + per-category |
| `case-financials` | case × currency: invoiced · credited · paid · outstanding · expenses | per-currency roll-up across cases |

════════════════════════════════════════
3. FILTERS  (spec §44)
════════════════════════════════════════

Implemented per report: **date range** (`date_from` / `date_to`), **status**,
**type**, **priority**, **lawyer** / **employee**, **client**, **case**,
**court**, **currency**, **payment method**, **expense category**, plus the
boolean toggles `open_only` / `overdue_only` / `with_active_cases`.

- Every field is **optional** and **bounded** — `ChoiceField` (fixed choices),
  `ModelChoiceField` (scoped queryset), `DateField`, `BooleanField`. **No
  free-text field, no user-supplied field name or ORM lookup** (spec §7).
- Server-side validation: reversed range → form error; unparseable date → field
  error; unknown choice → field error; out-of-scope FK pk → field error (never
  widens the query).
- **Date semantics (spec §8):** inclusive both ends. DateField compared
  directly; DateTimeField (`Case.created_at`, `Hearing.scheduled_at`) →
  `[from 00:00, (to+1 day) 00:00)` in Asia/Hebron — no naive/aware mix.
- **Filter resolution (bug-055 generalised):** the form carries a hidden
  `_run=1`. Present ⇒ real submission, cleaned values verbatim (an unchecked box
  / cleared date means "off"). Absent ⇒ fresh load / pagination link / bare
  "export CSV" link ⇒ field `initial`s + the default 90-day window apply — so
  **page 2 never disagrees with page 1**, and a CSV exported from an unfiltered
  page uses the same window the page showed.

════════════════════════════════════════
4. AUTHORIZATION MODEL  (spec Phase 10 §6)
════════════════════════════════════════

- **Per-domain, in the view, before any query or file generation.**
  `ReportView.get` looks up the `Report` (unknown slug → 404), then
  `can(user, report.capability)` → 403 on failure — for the HTML page **and**
  the `?format=csv` endpoint.
- The Reports **index lists only the reports whose capability the viewer holds**
  (`registry.visible_reports`). A group-less user gets a valid empty index and
  403 on every report URL.
- `reports.view` is an **all-staff nav/entry capability only** (joins
  `dashboard.view` / `agenda.view` / `notifications.view`). It is **not** in
  `sync_roles` (no `reports` model permission exists) and it **never** bypasses
  the per-report gate.
- **IDOR / tampering:** reports take a validated `slug` and validated,
  scope-checked filter pks; all row data flows through
  `Model.objects.for_user(user)`. No `Model.objects.get(request.GET[...])`. The
  `format` param only switches HTML↔CSV; `page` is clamped by `Paginator`.
- Aggregate-level leakage: ADR-0008 makes cases/clients/hearings/tasks all-staff,
  so a report over them exposes nothing a domain list page does not. **Finance
  is the one restricted domain and it is gated** — see §5.

════════════════════════════════════════
5. FINANCIAL-REPORT ISOLATION  (spec Phase 10 §6, §9, §10)
════════════════════════════════════════

- **`revenue` / `payments` / `outstanding` / `expenses` / `case-financials`
  require `finance.view`.** A **paralegal receives 403 on the page and on the
  CSV export** — `test_paralegal_blocked_from_financial_reports` asserts this for
  all five (page + `?format=csv`). The index hides them from a paralegal.
- **No finance total is re-implemented.** Builders reuse
  `finance.selectors._invoice_totals_by_currency`,
  `Invoice.objects.with_balances()` / `.open()` / `.overdue()`,
  `Payment.net_amount` semantics, `core.money.quantize`. `Decimal` end to end,
  never `float`.
- **Credit notes reflected** — `outstanding = max(invoiced − credited − paid, 0)`
  per currency; the credit-note sum is aggregated in a separate query (no
  join fan-out). Regression-tested.
- **Payments are net of reversals** — per-row `annotate(Sum("reversals__amount"))`,
  and the per-currency totals compute gross and reversals in **two** queries.
- **Mixed currencies are never summed** (ADR-0032) — every financial report
  renders per-currency `CurrencyTotals` blocks side by side; no combined figure
  appears in any row, metric or CSV cell.
  `test_revenue_report_never_sums_across_currencies` asserts `1000 ILS + 500 USD`
  never surfaces as `1500`.

════════════════════════════════════════
6. EXPORT FORMATS  (spec Phase 10 §11–13)
════════════════════════════════════════

- **CSV** — `?format=csv` on the same view, same capability gate. One clean
  table: header row + data rows (summary metrics / per-currency totals stay on
  the HTML page — derivable, and a single table avoids ambiguous parsing).
  UTF-8 **with BOM** (Excel opens Arabic correctly), `\r\n`, `X-Content-Type-
  Options: nosniff`. Western digits; money as plain dot-decimal `Decimal`
  strings — no grouping, no currency glued on. **Server-generated filename**
  `qistas-<slug>-<YYYY-MM-DD>.csv` — no user input, no stored file, no
  predictable public path.
- **Print** — a `@media print` block on `report.html` hides the sidebar / topbar
  / filter form and shrinks the table. "PDF where useful" (spec §44) → browser
  print-to-PDF.
- **Server-side PDF (WeasyPrint) — DEFERRED** (ADR-0034 §7): needs Cairo/Pango
  system libraries (Docker-only, same class as `compilemessages`); spec §44
  hedges ("where useful"/"where appropriate") and §13 says "no heavyweight PDF
  stack unless required". The `ReportResult` shape already separates data from
  rendering, so it is a contained additive renderer later.
- **Spreadsheet formula injection (spec §12):** `reports.framework.csv_safe`
  prefixes any cell **and header** whose text starts with `= + - @` or a leading
  control char with `'`. Money/number/date cells are framework-formatted and
  cannot start with those. Regression-tested (`=SUM(...)` in a case title comes
  back as `'=SUM(...)`).

════════════════════════════════════════
7. SECURITY REVIEW  (spec Phase 10 §16, §20)   —   PASS (no Critical / High)
════════════════════════════════════════

- **Report-level authorization** — gate is in the view, before any query/file;
  HTML + CSV; per-domain capability; financial = `finance.view`. Tested.
- **Aggregate / cross-client leakage** — all row data via `for_user()`; ADR-0008
  domains expose nothing new; finance gated. No `firm_financials`-style
  firm-wide surface without the gate.
- **Financial exports** — same gate as the page; paralegal 403 returns no file
  (`text/csv` never in the response). Tested.
- **Spreadsheet injection** — `csv_safe` on every cell + header. Tested +
  parametrized unit tests.
- **Generated-file access** — nothing is written to disk; the CSV is streamed in
  the gated response. No `/media/` route, no predictable path, no
  `<a download>` to a static file.
- **Path traversal / unsafe filename** — filename is
  `f"qistas-{slug}-{date}.csv"`, slug from the fixed registry. No user input.
- **User-controlled filters** — only bounded `ChoiceField` /
  `ModelChoiceField(scoped)` / `DateField` / `BooleanField`; filter kwargs are
  built from **hardcoded** field names (`date_range_filter` /
  `datetime_range_filter` / `_apply_finance_scope`). No `**{user_input: ...}`.
- **XSS** — templates auto-escape; **no `|safe`, no `mark_safe`** anywhere in
  `reports/` (grep-verified). `Cell.display` returns plain strings.
- **SQL injection** — pure ORM; `.values(<literal>)` only.
- **No chart / JSON endpoint** — every figure is server-rendered into the page
  (spec §16).
- **Audit** — export logged, **metadata only** (`redact()` via `log_event`); no
  row content, no money figures (`test_financial_export_is_audited_metadata_only`
  asserts `"1000.00"` / `"500.00"` are absent from the audit blob).

════════════════════════════════════════
8. PERFORMANCE REVIEW  (spec Phase 10 §14)   —   PASS
════════════════════════════════════════

- Each builder: **one** row query (`select_related` for every FK a row renders)
  sliced to `MAX_ROWS + 1` = 5001, plus a small fixed set of aggregate queries
  for the summary metrics / per-currency totals. **No per-row query** anywhere.
- A result over the cap is flagged `truncated`; the UI tells the user to narrow
  the filters. Bounds memory and query cost.
- The HTML table paginates the in-memory (already capped) list — **no extra
  query** for pagination. The CSV writes the whole capped list.
- `case-financials` builds from 3 aggregate queries (invoices / credit notes /
  expenses) merged in Python by `(case, currency)` — no per-case query.
- `payments` computes per-currency gross and reversals in **two** queries to
  avoid fanning `amount` over the reversal join (the Finance pattern).
- **Query-count regression tests** (`test_builder_query_count_is_flat`): for
  `cases` / `hearings` / `tasks` / `revenue` / `expenses`, a **2→8-row**
  population yields an **identical** query count, and the count is `≤ 15`.
  `test_report_page_is_bounded` asserts the HTML page is flat too.

════════════════════════════════════════
9. TESTS  (exact results)
════════════════════════════════════════

**689 pass / 0 fail / 4 skipped** (SQLite, `DJANGO_TEST_ENGINE=sqlite`) — was
560; **+129 `reports/tests/`**:

- `test_access.py` (34) — index + every report require login; CSV requires
  login; unknown slug → 404; paralegal sees the 5 general reports, **403 on all
  5 financial reports (page + export)**; finance_clerk reaches all 5; index
  hides financial reports from a paralegal / shows them to the office manager;
  **group-less user → safe empty index + 403 on every report**; `format=pdf`
  renders HTML; `page` out-of-range clamped.
- `test_filters.py` (14) — reversed range rejected; equal from/to valid; garbage
  date rejected; unknown choice rejected; empty filters valid + run;
  out-of-scope FK pk rejected; **date boundary inclusive both ends**; combined
  filters narrow together; invalid filter → HTML 200 with the "correct the
  filters" panel; **CSV with invalid filter → 400**; finance form scopes its
  pickers; **page 2 keeps the `open_only` default (bug-055)**; **default page
  and its CSV export use the same window**; an explicit `_run` submission
  respects an unchecked `open_only`.
- `test_general_reports.py` (17) — open-only excludes terminal; status filter
  overrides open-only; lawyer+court filter; count-by-status metric; date window
  = registration date; client active-case count; with-active-cases filter;
  client status metrics; hearing ordering + every-status count; **computed**
  task overdue; task status filter; by-employee metric; task excludes
  soft-deleted; deadline overdue-only / status counts / missed filter.
- `test_financial_reports.py` (15) — **currencies separated**; **never summed
  (`1500` absent)**; amounts are `Decimal`; currency filter; drafts excluded;
  **payment net of reversal**; method filter; outstanding per-currency;
  **aging buckets**; overdue-only; expense per-currency + category filter;
  case-financials one row per (case × currency); **credit note reduces
  outstanding**; case-financials totals never cross currency.
- `test_exports.py` (17) — CSV headers + rows (open-only respected); money
  cells plain decimal; **UTF-8 BOM**; **server-generated filename**;
  **formula injection neutralised** + parametrized `csv_safe` unit tests;
  **paralegal financial export → 403, no file**; anon → login; **financial
  export audited, metadata only**; general export audited; viewing HTML not
  audited.
- `test_performance.py` (6) — **flat query count** for 5 builders (2→8 rows
  identical, ≤ 15); HTML page bounded.
- `test_views.py` (26) — index renders; **every report renders with data**;
  **every report renders for an empty office** (empty state, no crash);
  per-currency blocks shown (no grand total); nav link present; pagination.

All Phase 1–9 tests unchanged and green. `AuditAction` gained a member — no
migration (the `action` column has no `choices=`); `makemigrations --check`
clean.

════════════════════════════════════════
10. QUALITY GATES
════════════════════════════════════════

- `pytest` (SQLite) — **689 pass / 4 skipped** (the 4 are `@pytest.mark.postgres`).
- `ruff check .` — **clean**
- `ruff format --check .` — **clean**
- `pip-audit` — **No known vulnerabilities found**
- `manage.py makemigrations --check --dry-run` — **No changes detected**
  (`reports` has no models; the `AuditAction` member needs no migration).
- `manage.py check` (test settings) — **no issues (1 silenced)**
- `manage.py check --deploy` — 5 warnings
  (`security.W004/W008/W009/W012/W016`), **all test-settings-only** —
  `config/settings/prod.py` sets HSTS, SSL redirect, secure cookies and takes
  `DJANGO_SECRET_KEY` from the environment. Not run against prod settings here
  (needs `DJANGO_SECRET_KEY` + PostgreSQL — see §11).

════════════════════════════════════════
11. POSTGRESQL STATUS   (DEFERRED — same environment blocker as Phases 1–9)
════════════════════════════════════════

This machine cannot run PostgreSQL (RAM + network). NOT executed:

1. Full suite on **PostgreSQL 16** (SQLite only here).
2. The 4 `@pytest.mark.postgres` tests (finance payment concurrency, numbering
   concurrency, `pg_trgm`) — **none new in Phase 10; reports adds no migration**.
3. Report / export tests against PostgreSQL — the reports use portable ORM only
   (`__gte`/`__lte`/`__lt` date lookups, `Count`/`Sum`/`Coalesce`,
   `values().annotate()`), no PG-specific feature; behaviour is expected to match.
4. `manage.py check --deploy` against **prod settings**.

Run on a PG-capable machine / CI:
```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest            # expect ~693 pass, 0 skipped
```

════════════════════════════════════════
12. DOCKER STATUS   (DEFERRED — same blocker)
════════════════════════════════════════

`docker compose build` + `docker compose up` full-stack smoke NOT run.
Equivalent verified via the Django test client (`reports/tests/test_views.py`,
`test_exports.py` — real request/response, CSV bytes, headers, audit rows).

════════════════════════════════════════
13. DEFERRED CHECKS  (explicitly NOT claimed as passed)
════════════════════════════════════════

- Full suite on PostgreSQL 16.
- The 4 `@pytest.mark.postgres` tests.
- `docker compose` full-stack smoke.
- `compilemessages` (Docker/gettext only; harmless — Arabic source strings).
- `manage.py check --deploy` against prod settings.
- **Server-side PDF export** (WeasyPrint) — deferred by design (ADR-0034 §7).

════════════════════════════════════════
14. KNOWN LIMITATIONS
════════════════════════════════════════

- **No PDF export** — browser print-to-PDF is the interim; WeasyPrint is a
  contained additive renderer once the Docker/Linux toolchain is available.
- **No saved report definitions, no trend / period-over-period analysis, no
  scheduled delivery.** Reports are a "right now, filter-and-read/export" tool;
  scheduled delivery is Phase 11 territory and explicitly out of scope.
- **`MAX_ROWS = 5000` cap** — a larger result set is truncated (flagged in the
  UI, which asks the user to narrow the filters). A real office is far below
  this; it bounds memory and query cost.
- **Outstanding-report aging sub-totals** are computed from the displayed
  (capped) rows; the **headline per-currency outstanding is exact**
  (`_invoice_totals_by_currency` over the full queryset).
- `/code-review high` — **the command is not available in this environment**
  (`.claude/commands/` holds only `designqc` / `handoff` / `reframe` /
  `security-audit`; `/code-review` / `/ultrareview` are user-triggered, billed,
  and cannot be launched here). A **rigorous self code-review** of the full diff
  was done instead — consistent with Phases 4–9's "`/code-review` (self)".
  Findings fixed pre-commit: (a) the default report view and its CSV export used
  different date windows / `open_only` defaults → unified via the `_run`-marked
  `resolved_filters()` (bug-055 generalised) + regression tests; (b) audit
  metadata was read from the bound form rather than the resolved filters →
  fixed; (c) added the aging-sub-total accuracy note above.

════════════════════════════════════════
15–18. GIT
════════════════════════════════════════

- Branch:        phase/10-reports  (one commit: `phase(10): complete reports`)
- Parent commit: 21ff0ea  (Merge pull request #8 from …/phase/9-dashboard — master)
- Commit:        see `git rev-parse HEAD` / the completion message — kept out of
                 the report so report + code stay one clean commit
- Working tree:  clean after the commit; local HEAD == origin/phase/10-reports
- **NOT merged.** No changes to master. Phase 11 (Notifications) NOT started.

════════════════════════════════════════
Assumptions
════════════════════════════════════════

- "PDF where useful" (spec §44) + "no heavyweight PDF stack unless required"
  (§13) ⇒ CSV + browser-print now, server-side PDF deferred (ADR-0034 §7).
- "Task Reports … By employee" (spec §43) ⇒ a by-employee count **metric** on
  the task report (not a separate report).
- Case "By date" (spec §43) ⇒ a range filter on `Case.created_at` (system
  registration date) — the only always-present case date; `filing_date` is
  optional.
- A `reports.view` all-staff capability for nav/index entry is consistent with
  `dashboard.view` (ADR-0033) — it does not weaken the per-report gate.

Ready for Approval: YES

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAITING FOR USER APPROVAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
