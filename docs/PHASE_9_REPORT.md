━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        9 — Dashboard & Analytics
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–8; every other DoD item met)
Branch:       phase/9-dashboard — based on master @ 32e350b (Phase 8 merge, PR #7)
Design:       docs/adr/0033-dashboard.md (Accepted)

════════════════════════════════════════
1. IMPLEMENTATION SUMMARY  (spec §17–19, §82 Phase 9)
════════════════════════════════════════

## The dashboard *is* the landing page

`core:landing` now renders `dashboard/dashboard.html`. There is **no `/dashboard/`
URL and no second home page** — the primary question "ما الذي يحتاج إلى انتباهي
اليوم؟" is answered on `/`. The Phase 5–8 landing widgets (my-tasks / overdue /
upcoming-deadlines / expiring-contracts / outstanding-invoices) and their bespoke
context keys (`has_widgets`, `overdue_count`, `outstanding_invoices_count`, …)
are folded into the dashboard's KPI row + Attention + Deadlines sections;
`templates/core/landing.html` is **deleted**.

## `dashboard` app — a read/analytics layer, **no models**

`dashboard/selectors.py` is the whole app. It imports the domains' own
`for_user()`-scoped managers and existing selectors and shapes them into one
context dict. `core.views.LandingView` is a thin shell:
`{**super().get_context_data(**kwargs), **build_dashboard(self.request.user)}`.

- **No `DashboardKPI` / `DashboardTask` / cached-count model, no second ledger.**
  `dashboard.apps.DashboardConfig` registers zero models — regression-tested
  (`test_dashboard_owns_no_models`, `makemigrations --check` clean).
- New **domain-owned** selectors (each lives with its domain, not in dashboard):
  `hearings.selectors.today_hearings` / `upcoming_hearings`,
  `finance.selectors.overdue_invoices` / `firm_financials`.

## Widgets / KPIs

**KPIs (§18)** — `القضايا النشطة` · `جلسات اليوم` · `المهام المتأخرة` ·
`القضايا العاجلة` · `إجمالي العملاء` · `عقود قريبة من الانتهاء` ·
`الفواتير المستحقة` (a **count**, finance-gated). Each is a clickable card
linking to the relevant filtered list. Overdue / urgent / expiring carry a
danger/warning tone only when non-zero.

**Today's Hearings (§19)** — still-scheduled hearings whose `scheduled_at` is
today in the office timezone: time · case · client · court · lawyer · type ·
status. Cancelled/postponed excluded.

**Attention Required (§19)** — overdue tasks · overdue deadlines · hearings in
the next 7 days · high-priority (HIGH/URGENT) open cases · expiring contracts
(30d) · **overdue invoices (finance-gated)**. Empty blocks are hidden; when
every block is empty a single "كل شيء تحت السيطرة" state shows. Each block: a
count, up to 6 rows with a deep link, and an "الكل" link to the filtered list.

**Case Analytics (§19)** — by status (all cases) · by priority · by type · by
lawyer (open cases). Rendered as **CSS horizontal bar charts**
(`dashboard/_bars.html`, `{% widthratio %}`) — **no Chart.js**: RTL-native,
print-safe, no ~200 KB vendored asset, no CSP surface, no `<script>` on the
page. Chart data is server-rendered into the page — **no chart JSON endpoint**
(spec §18). Unassigned cases labelled `غير مُسندة`.

**Financial Overview (§19)** — `firm_financials(user)`: a **per-currency**,
**credit-note-aware** breakdown over **issued** invoices
(`{currency, invoiced, paid, credited, outstanding}` + `expenses_by_currency`).
ILS and USD are separate blocks; **there is no combined total** (ADR-0032 —
mixed currencies are never summed). `outstanding = max(invoiced − credited −
paid, 0)` per currency. Reuses `Invoice.objects.overdue()` / `.open()` /
`.with_balances()` and `core.money.quantize` — no re-implementation.

**Recent Activity (§19)** — an **allow-list** of domain lifecycle audit actions
(creations + status changes; not auth events, not noisy edits), **grouped by
the capability that gates each group**. `CASE_CONFIDENTIAL_UPDATED` is always
excluded for a non-`cases.view_confidential` viewer (ADR-0008, buglog bug-042).
Each row links to the entity where a detail URL exists.

**Upcoming Deadlines** — next 14 days, overdue flagged. **Recently Updated
Cases** — 6 most recently touched open cases.

════════════════════════════════════════
2. DASHBOARD ARCHITECTURE
════════════════════════════════════════

- `dashboard/selectors.py::build_dashboard(user)` → context dict. A dedicated
  `_shared_counts(user, caps)` helper computes the counts the KPI row and the
  Attention blocks both need (`active_cases`, `urgent_cases`, `overdue_tasks`,
  `expiring_contracts`) **once**; `build_dashboard` passes that dict to both
  `_attention()` and `_kpis()` — nothing is counted twice and the two can never
  disagree. (`today_hearings` is likewise counted once, in `_today_hearings_rows`.)
- `_list(qs, total=None)` fetches one bounded slice (`qs[:7]`); it reuses a
  known `total` when `_shared_counts` already has it, else derives the count
  from that fetch unless it overflows (then one extra `COUNT`).
- Today's-hearings table is bounded like every other list (first 6 rows; the
  KPI carries the true count, the calendar link covers the rest).
- Every list slice's underlying selector carries `select_related` for the fields
  the row render touches — the render does **no** per-row query.
- Templates receive **pre-evaluated lists / dicts**, never a lazy queryset.
- `core.views.LandingView` — thin `TemplateView` (login enforced by
  `LoginRequiredMiddleware`; no capability gate on the view itself — the page is
  every authenticated user's home).

════════════════════════════════════════
3. PERMISSIONS  (spec Phase 9 §5)
════════════════════════════════════════

**Every widget's data is computed only if the user holds that domain's `*.view`
capability** — enforced in the *query*, not the template. `build_dashboard`
reads `capabilities_for(user)` once:

| widget | capability |
|---|---|
| active/urgent-cases KPI, case analytics, high-priority block, recent cases | `cases.view` |
| today's + upcoming hearings | `hearings.view` |
| overdue tasks / deadlines, upcoming deadlines | `tasks.view` |
| expiring contracts | `contracts.view` |
| total-clients KPI | `clients.view` |
| **financial overview, outstanding-invoices KPI, overdue-invoices block, finance recent-activity rows** | **`finance.view`** |

- **Finance is strict (ADR-0032 — finance is not all-staff).** A **paralegal**'s
  `build_dashboard` never runs a finance query: `financial_overview` =
  `{"visible": False, …}`, no finance KPI, no finance attention block, no
  finance rows in recent activity. `firm_financials()` **also** self-checks
  `finance.view` as a defence-in-depth backstop. `test_paralegal_dashboard_has_
  no_finance_anywhere` asserts all four surfaces, plus an HTTP test checks the
  rendered body.
- A **group-less** authenticated user (no capabilities) gets a valid, empty
  dashboard — no KPIs, no analytics, no error, no leak
  (`test_no_capabilities_user_gets_a_safe_empty_dashboard`).
- This is **stricter** than the page it replaced — the old `LandingView` did no
  per-domain gating.

════════════════════════════════════════
4. FINANCE ISOLATION  (spec Phase 9 §3)
════════════════════════════════════════

- **No finance calculation is re-implemented.** `firm_financials` /
  `overdue_invoices` live in `finance.selectors` and reuse
  `_invoice_totals_by_currency`, `Invoice.objects.overdue()` / `.open()` /
  `.with_balances()`, and `core.money.quantize`.
- **Mixed currencies are never summed** (spec Phase 9 §7, ADR-0032) —
  per-currency rows; the outstanding KPI is a count, not a sum.
- **Credit notes reflected** — `outstanding` subtracts Σ credit notes per
  currency (aggregated in a separate query so `total` / `amount_paid` do not
  fan out over the credit-note join). Regression-tested.
- **No dashboard finance model** — the dashboard reads Finance, never stores.

════════════════════════════════════════
5. TESTS
════════════════════════════════════════

**560 pass / 0 fail / 4 skipped** (SQLite) — was 529/4; **+31 dashboard tests**
across `dashboard/tests/`:

- `test_selectors` — active-case KPI = open only; urgent-case KPI + tone;
  today's-hearings KPI + row shape (cancelled excluded); overdue-task KPI is
  computed not stored; expiring-contracts KPI; attention overdue-deadlines /
  upcoming-hearings-7d / empty-state; case-analytics breakdowns (status = all,
  priority/type/lawyer = open) + unassigned label; recent-activity shape +
  allow-list filtering (LOGIN / DOCUMENT_DOWNLOADED excluded); **per-currency +
  credit-note-aware financial overview**; dashboard owns no models.
- `test_permissions` — **`test_paralegal_dashboard_has_no_finance_anywhere`**
  (the critical regression: KPIs, attention blocks, `financial_overview`,
  recent-activity labels all finance-free) · finance user *does* see finance ·
  **capability matrix** (office_manager / finance_clerk / lawyer / admin_clerk =
  finance; **paralegal = none**) · group-less user → safe empty dashboard ·
  confidential-action excluded for non-privileged · dashboard requires login ·
  paralegal page renders with no finance markup.
- `test_performance` — **`build_dashboard` query count is flat** across an
  8→24-row population (identical count); page query count flat (± 1 for
  session); empty dashboard ≤ 30 queries; ceiling ≤ 45.
- `test_views` — full render (all seven section headings present) · renders for
  **every role** · empty-office empty states · KPI links resolve.

Regression: the two Phase 5/7 tests that asserted old landing-widget context
keys (`tasks/tests/test_smoke.py::test_landing_widgets_present`,
`contracts/tests/test_views.py::test_landing_expiring_widget`) were updated to
assert the equivalent dashboard KPI / attention data. All other Phase 1–8 tests
unchanged and green.

════════════════════════════════════════
6. QUERY / PERFORMANCE REVIEW  (spec Phase 9 §10)
════════════════════════════════════════

Self review — **PASS**.

- `build_dashboard` runs a **bounded** number of queries (~30–45), **flat** with
  respect to row count. Regression-tested (8→24 rows → identical query count).
- **No repeated identical query** — `capabilities_for(user)` resolved once in
  `build_dashboard` (and passed to `firm_financials(caps=…)` so it does not
  re-query group membership); shared counts computed once in `_shared_counts`
  and handed to both `_attention` and `_kpis`.
- **No N+1 in any render** — every list slice's selector carries
  `select_related` for the fields the row touches (`today_hearings` →
  `case`/`case__client`/`court`/`lawyer`; `overdue_tasks` →
  `assigned_to`/`case`/`client`; `overdue_invoices` →
  `client`/`case` + `.with_balances()`; `expiring_contracts` → `client`/`case`).
- **No whole-table loads** — every list is `[:6]`/`[:10]`; analytics are
  `.values().annotate(Count)` aggregates.
- Templates receive pre-evaluated lists — no lazy queryset iterated in a loop.
- **Known pre-existing (not introduced here):** the per-request `can()` /
  navigation capability checks issue ~1 `auth_group` query per nav item on every
  page — ADR-0010 defers this whole-app N+1 sweep to Phase 12; the dashboard's
  own `build_dashboard` resolves `capabilities_for(user)` **once**.

════════════════════════════════════════
7. SECURITY REVIEW  (spec Phase 9 §18)
════════════════════════════════════════

Self review — **PASS** (no Critical/High).

- **IDOR** — the dashboard takes no user-controlled object IDs; every query goes
  through a `for_user()`-scoped manager or an aggregate over one. No
  `Model.objects.get(request.GET[...])`.
- **Unauthorized / finance leakage** — per-domain capability gating in the query
  (see §3). A paralegal's dashboard runs **zero** finance queries;
  `financial_overview` is `{"visible": False}`. `_recent_activity`'s allow-list
  is grouped by gating capability; `CASE_CONFIDENTIAL_UPDATED` always excluded
  for non-`view_confidential`. Regression-tested.
- **Template XSS** — all dashboard templates auto-escape; **no `|safe`, no
  `mark_safe`**. `_bars.html` `style="width: {% widthratio %}%"` emits an
  integer. URLs come from `reverse()`, never user input. `AuditLog.object_repr`
  is stored text (redacted at write time, ADR-0009) rendered escaped.
- **No chart JSON / API endpoint** — analytics data is server-rendered into the
  page and inherits the page's authorization (spec §18).
- **SQL injection** — pure ORM; `.values(field)` fields are hardcoded literals.
- **Caching** — **none added** (spec Phase 9 §11); no risk of a wrongly-keyed
  cache serving one user's finance numbers to another.
- **No writes on GET** — `build_dashboard` is pure reads; no `get_or_create`.

════════════════════════════════════════
8. CODE REVIEW  (spec Phase 9 §19)
════════════════════════════════════════

`/code-review high` on the full branch diff — **no Critical / High findings**
("the change is well-tested"). Five lower-severity findings, **all fixed**:

| # | File | Finding | Fix |
|---|---|---|---|
| 1 | `finance/selectors.py` | `firm_financials` called `can()`, re-running the identical group-membership query `build_dashboard` had already issued (contradicts the "never re-runs an identical query" invariant). | `firm_financials(user, *, caps=None)` — `build_dashboard` passes the pre-computed capability set; falls back to `can()` for other callers. |
| 2 | `dashboard/selectors.py` | `_today_hearings_rows` emitted **every** scheduled hearing for the day — the only list widget with no `_LIST_LIMIT` cap. | Now goes through `_list()`: table shows the first 6, the `جلسات اليوم` KPI carries the true count, the calendar link covers the rest. |
| 3 | `templates/dashboard/dashboard.html` | `{% blocktranslate count %}` singular branch rendered the nonsensical "قضية نشطة واحدة من 1". | Replaced with a plain `{% blocktranslate with open=… total=… %}{{ open }} نشطة من {{ total }} إجمالًا{% endblocktranslate %}` — no `count`/`plural`. |
| 4 | `templates/dashboard/_bars.html` | Read an undocumented `scale` var while the header documented `total`; the `{% if scale %}` branch was dead (nothing passed either). | Removed the dead branch; bar width is `{% widthratio r.value rows.0.value 100 %}` (rows are value-desc sorted, so row 0 is the scale). Comment corrected. |
| 5 | `dashboard/selectors.py` | KPI counts were harvested from a dict populated as a **side effect** of `_attention()` — fragile ordering coupling (reorder `build_dashboard`, or add a KPI whose count no block produces → `KeyError`). | New `_shared_counts(user, caps)` helper owns those counts; `build_dashboard` passes the dict to both `_attention` and `_kpis`. `_block(total=…)` reuses them so no count query runs twice. |

All five changes are recorded in `.wolf/buglog.json` (bug-093…bug-096).

════════════════════════════════════════
9. QUALITY GATES
════════════════════════════════════════

- `ruff check .` — **clean**
- `ruff format --check .` — **clean**
- `pip-audit` — **no known vulnerabilities**
- `manage.py makemigrations --check --dry-run` — **no changes** (`dashboard`
  has no models)
- `manage.py check` (test settings) — **no issues**
- `manage.py check --deploy` — 5 warnings (`security.W004/W008/W009/W012/W016`),
  **all test-settings-only** — `config/settings/prod.py` sets HSTS, SSL redirect,
  secure cookies and takes `DJANGO_SECRET_KEY` from the environment.

════════════════════════════════════════
10. POSTGRESQL / DOCKER STATUS  (DEFERRED — same environment blocker as Phases 1–8)
════════════════════════════════════════

This machine cannot run Docker or PostgreSQL (RAM + network). NOT executed:

1. Full suite on **PostgreSQL 16** (SQLite only here).
2. The 4 `@pytest.mark.postgres` tests (finance payment concurrency, numbering
   concurrency, `pg_trgm` — none new in Phase 9; the dashboard adds no migration).
3. `docker compose build` + `docker compose run --rm web pytest` full-stack smoke.
4. `compilemessages` (Docker/gettext only; harmless).
5. `manage.py check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY`
   env + PostgreSQL).

Run on a PG-capable machine / CI:
```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest            # expect 564 pass, 0 skipped
docker compose up -d && curl -si localhost:8000/   # -> 302 /accounts/login/  (then the dashboard)
```

════════════════════════════════════════
11. KNOWN LIMITATIONS
════════════════════════════════════════

- **"Missing documents"** (a spec §19 Attention example) is **not** implemented.
  There is no "required documents" / checklist concept in the domain to define
  "missing" from (spec §80 — no invented definitions). A future `RequiredDocument`
  model + a case-completeness check would add it.
- **Case analytics are CSS bar charts, not an interactive JS chart** —
  deliberate (ADR-0033); a JS charting library is a contained drop-in later
  change (the server already renders the data).
- **"Recent activity" is firm-wide** (ADR-0008 — all-staff visibility), filtered
  by the domain-capability allow-list. There is no per-user activity stream.
- The dashboard has **no date-range selector** — it is a "right now" operational
  view (spec §17). Trend/period analysis is Phase 10 (Reports).

════════════════════════════════════════
12. FILES
════════════════════════════════════════

New: `dashboard/` (app — `__init__`, `apps`, `selectors`, 4 test modules),
`templates/dashboard/` (`dashboard.html` + `_bars.html` + `_attention.html`),
`docs/adr/0033-dashboard.md`, `docs/PHASE_9_REPORT.md`.

Changed: `core/views.py` (`LandingView` → thin dashboard shell),
`hearings/selectors.py` (+ `today_hearings` / `upcoming_hearings`),
`finance/selectors.py` (+ `overdue_invoices` / `firm_financials`),
`config/settings/base.py` (+ `dashboard` app), `PROJECT_STATUS.md`,
`docs/architecture.md`, `docs/adr/README.md`,
`tasks/tests/test_smoke.py` + `contracts/tests/test_views.py` (updated landing
assertions).

Deleted: `templates/core/landing.html` (replaced by `templates/dashboard/
dashboard.html`).

════════════════════════════════════════
13. GIT
════════════════════════════════════════

- Branch:        phase/9-dashboard  (one commit: `phase(9): complete dashboard`)
- Parent commit: 32e350b  (Merge pull request #7 from …/phase/8-finance — master)
- Commit hash:   see `git rev-parse HEAD` / the completion message (kept out of
                 the report so the report and the commit stay one clean commit)
- Working tree:  clean after the commit; local HEAD == origin/phase/9-dashboard
- **NOT merged.** No changes to master.
