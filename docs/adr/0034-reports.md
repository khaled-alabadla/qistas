# ADR-0034 — Reports: a read/export layer that owns no data

Status: **Accepted** 2026-09-10 (owner: Khaled; architect: Claude)
Phase: 10
Builds on: ADR-0007 (capabilities), ADR-0008 (all-staff visibility),
ADR-0009 (audit redaction), ADR-0018/0019 (layering + scoped querysets),
ADR-0020 (audit), ADR-0032 (finance — not all-staff, per-currency),
ADR-0033 (dashboard — read layer, no models).

## Context

Spec §43–44 asks for operational reports (cases / clients / hearings / tasks /
financial) with filters and CSV / print / "PDF where useful" export. The
dashboard (Phase 9) already established the pattern for a read-only analytics
surface over existing domain data. Reports differ in three ways: they are
**tabular and exhaustive** (not a bounded "right now" summary), they **export**,
and one export format (spreadsheets) introduces a new injection class.

## Decision

### 1. `reports` owns **no models**

`reports/` is `framework.py` (typed result + CSV writer) + `registry.py`
(the catalogue) + `forms.py` + `selectors.py` (one `build_*_report` per report)
+ thin views + templates. No `Report`, no `ReportRun`, no cached-result table
(spec §23). A report is computed on request from the domains' own
`for_user()`-scoped managers and existing selectors/helpers. `makemigrations
--check` is clean; a regression test asserts the app registers zero models.

### 2. Every report is gated on its **domain** capability, in the view

`registry.Report.capability` names the domain capability
(`cases.view` / `clients.view` / `hearings.view` / `tasks.view` /
**`finance.view`**). `ReportView.get` checks `can(user, report.capability)`
**before any query runs or any file is generated**. The index page lists only
the reports whose capability the viewer holds. `reports.view` exists purely as
an all-staff nav/entry capability (like `dashboard.view` / `agenda.view`); it is
**not** "see every report" — it never bypasses the per-report gate. It is not in
`sync_roles` (no `reports` model permission exists).

### 3. Financial reports are strict (ADR-0032)

`revenue` / `payments` / `outstanding` / `expenses` / `case-financials` require
`finance.view`. A **paralegal gets 403** on the page *and* the CSV endpoint — a
dedicated regression test asserts this for all five. No finance total is
re-implemented: builders reuse `finance.selectors._invoice_totals_by_currency`,
`Invoice.objects.with_balances()` / `.open()` / `.overdue()`, `Payment.net_amount`
semantics and `core.money.quantize`. `Decimal` end to end.

### 4. Currencies are never summed (ADR-0032)

Every financial report renders **per-currency total blocks** (`CurrencyTotals`)
side by side — ILS and USD are separate columns/blocks, there is no combined
figure anywhere (rows, metrics, CSV). Regression-tested (`1000 ILS + 500 USD`
must never surface as `1500`).

### 5. Date semantics (spec §8)

`date_from` / `date_to` are **inclusive on both ends**. A DateField
(`due_date`, `spent_on`, `issue_date`, `paid_on`) is compared directly. A
DateTimeField (`Case.created_at`, `Hearing.scheduled_at`) uses
`[from 00:00, (to + 1 day) 00:00)` in the **active timezone** (Asia/Hebron) —
`reports.framework.datetime_range_filter`, never a naive/aware mix.

### 6. Filter resolution — the bug-055 rule, generalised

The filter form carries a hidden `_run=1`. When present the user actually
submitted the form and cleaned values are used verbatim (an unchecked box, a
cleared date really mean "off"). When absent — a fresh load, a pagination link,
a bare "export CSV" link — field `initial`s and the default 90-day window apply.
So report **page 2 never disagrees with page 1**, and a CSV exported from an
unfiltered page uses the same window the page showed.

### 7. Exports: CSV + browser print; **PDF deferred**

- **CSV** — one clean table (header row + data rows), UTF-8 **with BOM** (Excel
  opens Arabic correctly), `\r\n`, Western digits, money as plain dot-decimal
  `Decimal` strings with no grouping and no currency glued on. Same view,
  `?format=csv`, same capability gate, **audited**. Server-generated filename
  `qistas-<slug>-<YYYY-MM-DD>.csv` — no user input, no stored file, no
  predictable public path.
- **Print** — a `@media print` stylesheet on the result page (hides chrome +
  filters). "PDF where useful" (spec §44) is served by the browser's
  print-to-PDF for now.
- **Server-side PDF (WeasyPrint) is deferred** — it needs system libraries
  (Cairo / Pango), is the same Docker-only constraint as `compilemessages`, and
  the spec hedges ("where useful" / "where appropriate") while §13 says "do not
  add a heavyweight PDF stack unless required". Revisit when the Linux/Docker
  toolchain is available; the `ReportResult` shape already separates data from
  rendering, so it is an additive renderer.

### 8. Spreadsheet formula injection (spec §12)

`reports.framework.csv_safe` prefixes any cell (and header) whose text starts
with `= + - @` or a leading control char with `'`. Applied to every text cell
and every column label. Money / number / date cells are formatted by the
framework and cannot begin with those characters.

### 9. Performance (spec §14)

Each builder issues a **bounded** number of queries: one row query
(`select_related` for every FK a row renders) sliced to `MAX_ROWS = 5000`, plus
a handful of aggregate queries for the summary. **No per-row query.** A capped
result is flagged `truncated` and the UI asks the user to narrow the filters.
The HTML table paginates the in-memory capped list (no extra query); the CSV
writes the whole capped list. Query-count regression tests assert flatness
across a 3→12-row population for five representative builders.

### 10. Audit (spec §17)

Every CSV export writes one `AuditAction.REPORT_EXPORTED` event — **metadata
only**: report slug, format, row count, `truncated`, `financial` flag, and the
**scalar** filter values (dates as ISO, FK ids, choice values). No row content,
no money figures. `redact()` runs via `log_event`. Viewing the HTML page is not
audited.

## Consequences

- Reports is the third read-only surface (after the case workspace tabs and the
  dashboard) that consumes domain selectors without adding schema.
- The dashboard's `firm_financials` and the reports' `_invoice_totals_by_currency`
  reuse keep one definition of "invoiced / paid / credited / outstanding".
- `reports.view` joins `dashboard.view` / `agenda.view` / `notifications.view` as
  capability-layer-only (no Django model permission, not in `sync_roles`).
- A future server-side PDF renderer plugs into `ReportResult` without touching
  the builders.
- No trend / period-over-period analysis, no saved report definitions, no
  scheduled report delivery (that last is Phase 11 territory and explicitly out
  of scope).
