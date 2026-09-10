# ADR-0033 — Dashboard: a read/analytics layer, capability-gated per widget

- **Status:** Accepted — 2026-09-10
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0006 (computed states — overdue is never stored),
  ADR-0007 / ADR-0008 (capabilities; all-staff visibility with per-view gates),
  ADR-0018 (layering — selectors for reads), ADR-0019 (object-level authz),
  ADR-0020 (audit — the recent-activity source),
  ADR-0028/0029/0031 (`agenda` / task / contract calendar surfaces),
  ADR-0032 (finance — **not all-staff**; `with_balances()`; per-currency, never
  summed), spec §17–19, §82 Phase 9.
- **Phase:** 9

## Context

Spec §17–19 + §82 Phase 9: the operational dashboard ("ما الذي يحتاج إلى
انتباهي اليوم؟") — KPIs, today's hearings, attention-required, case analytics,
financial overview, recent activity, upcoming deadlines, and "Charts". Phases
5/7/8 already put partial widgets on `core:landing` (my-tasks / overdue /
expiring-contracts / outstanding-invoices). Open questions:

1. Is the dashboard a new page or does it replace the landing page?
2. Where does the query logic live — a new app, or `core`?
3. How is authorization enforced, given the dashboard aggregates **every**
   domain and finance is not all-staff (ADR-0032)?
4. Chart.js or not?
5. How are mixed currencies handled in the "Financial Overview"?

## Decision

### The dashboard **is** the landing page

`core:landing` renders `dashboard/dashboard.html`. There is no second home page
and no `/dashboard/` URL. The Phase 5–8 landing widgets are folded into the
dashboard's KPI row + Attention + Deadlines sections and their bespoke context
keys (`has_widgets`, `overdue_count`, `outstanding_invoices_count`, …) are gone
— `templates/core/landing.html` is deleted.

### A `dashboard` app that owns **no models**

`dashboard/selectors.py` is the whole of it — a **read/analytics layer**. It
imports the domains' own `for_user()`-scoped managers and existing selectors
(`tasks.selectors.overdue_tasks`, `contracts.selectors.expiring_contracts`,
`hearings.selectors.today_hearings` / `upcoming_hearings` [new],
`finance.selectors.outstanding_invoices` / `overdue_invoices` [new] /
`firm_financials` [new]) and shapes them into a context dict. It creates **no
domain data** — no `DashboardKPI` table, no cached-count model, no second
ledger. `core.views.LandingView` is a thin shell: `{**build_dashboard(user)}`.

New domain-owned selectors added in this phase (each lives with its domain, not
in `dashboard`): `hearings.selectors.today_hearings` / `upcoming_hearings`,
`finance.selectors.overdue_invoices` / `firm_financials` (firm-wide per-currency
totals — the definition stays in Finance, ADR-0032).

### Authorization — **every widget is gated in the query**

The landing page itself is every authenticated user's home (no capability gate
on the view — there is no authenticated non-staff user). But **a widget's data
is only computed if the user holds that domain's `*.view` capability**
(`build_dashboard` reads `capabilities_for(user)` once):

- cases KPIs / analytics / recent-cases → `cases.view`
- today's + upcoming hearings → `hearings.view`
- overdue tasks / deadlines / upcoming deadlines → `tasks.view`
- expiring contracts → `contracts.view`
- total clients → `clients.view`
- **financial overview, the outstanding-invoices KPI, the overdue-invoices
  attention block, and finance rows in "recent activity" → `finance.view`**
  (ADR-0032 — finance is not all-staff; **a paralegal's dashboard never runs a
  finance query**). `firm_financials` *also* self-checks `finance.view` as a
  defence-in-depth backstop.
- **recent activity** is an allow-list of domain lifecycle actions grouped by
  the capability that gates each group; `CASE_CONFIDENTIAL_UPDATED` is always
  excluded for a non-`cases.view_confidential` viewer (ADR-0008, buglog bug-042).

A group-less user (no capabilities) gets a valid, empty dashboard — never an
error, never a leak.

### Overdue stays computed (ADR-0006)

Every "overdue" figure (`overdue_tasks`, `Deadline.overdue()`,
`Invoice.overdue()`, `is_past_due`) is read from the domain's computed
property / queryset method. The dashboard stores nothing.

### Case analytics — CSS bar charts, **no Chart.js**

"Cases by status / type / lawyer / priority" (§19) render as compact CSS
horizontal bars (`dashboard/_bars.html`, `{% widthratio %}`). The spec allows
Chart.js; we chose CSS bars because they are **RTL-native**, print correctly,
add **no ~200 KB vendored asset or CSP surface**, need no `<script>` on the
page, and match the spec's own guidance ("do not build a dashboard consisting
only of decorative KPI cards"; "primarily lists, counts, status summaries" —
spec §17, Phase-9 anti-pattern notes). Chart data is server-rendered into the
page, so it inherits the page's authorization — **no unprotected chart JSON
endpoint** (spec §18). A JS charting library is a drop-in later change if
richer interactivity is ever needed.

### Financial Overview — per currency, never summed (ADR-0032)

`firm_financials(user)` returns a **per-currency** breakdown
(`by_currency: [{currency, invoiced, paid, credited, outstanding}]` +
`expenses_by_currency`), over **issued** invoices, **credit-note aware**
(`outstanding = max(invoiced − credited − paid, 0)` per currency). ILS and USD
are shown as separate blocks; there is no combined total. The outstanding KPI is
the **count** of open invoices, not a sum. Reuses `Invoice.objects.overdue()` /
`.open()` / `.with_balances()` and `core.money.quantize` — no re-implementation.

### Performance (spec Phase 9 §10)

`build_dashboard` runs a **bounded** number of queries (~30–45), **flat** with
respect to row count, and never re-runs an identical query — the shared counts
(`active_cases`, `overdue_tasks`, `expiring_contracts`) are computed once in
`_attention` and handed to `_kpis`. Each list block fetches one bounded slice
(`[:_LIST_LIMIT+1]`) and derives its count from that fetch unless it overflows
(then one extra `COUNT`). Regression tests in `dashboard/tests/test_performance.py`
assert flatness across an 8→24-row population.

### No caching

No Redis, no `cache_page`, no per-user dashboard cache (spec Phase 9 §11). The
queries are cheap and bounded; a cache keyed wrong would risk serving one
user's finance numbers to another. If it is ever needed it will be a scoped,
explicit follow-up.

## Consequences

- `core:landing` is now the dashboard for good; Phase 10 (Reports) and Phase 11
  (Notifications) build **beside** it, not on it. "Missing documents" (a §19
  attention example) is **not** implemented — there is no "required documents"
  concept in the domain to define it from (spec §80 — no invented definitions);
  a future `RequiredDocument` checklist would add it.
- Adding a domain later means one capability check + one selector call in
  `build_dashboard`; the dashboard never grows a model.
- A richer charting need is a contained change (swap `_bars.html` for a
  library + keep the server-rendered `json_script` data).
