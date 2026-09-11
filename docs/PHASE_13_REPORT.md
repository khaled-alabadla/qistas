━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        13 — Final Integration, Production Readiness & Release Candidate
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–12; see §13/§14 below for
              the corrected, more precise account of exactly what is and
              isn't available on this machine).
Branch:       phase/13-release-readiness — based on master @ cee051e
              (Phase 12 merge, PR #11)
Commit:       phase(13): complete release readiness

**This is not a feature phase.** No product functionality was added, no
architecture was changed, no code was refactored for style. The entire diff
is two new test files (`tests/test_integration_workflows.py`,
`tests/test_edge_cases.py`) plus documentation.

════════════════════════════════════════
1. PHASE OBJECTIVE
════════════════════════════════════════

Treat Phases 1–12 as one product and answer one question: **does Qistas now
behave like one coherent production application**, not twelve isolated phase
implementations glued together? Verify complete user journeys across module
boundaries, re-derive important claims from the current code rather than
trusting prior phase reports, and assess release readiness precisely —
distinguishing what was actually verified from what remains
environment-blocked.

════════════════════════════════════════
2. STARTING COMMIT / BRANCH
════════════════════════════════════════

Started from `master` @ `cee051e` (merge of PR #11, Phase 12 hardening).
Confirmed via `git fetch` + `git log --oneline origin/master` before
branching — Phase 12 was genuinely merged, not merely claimed. Branch:
`phase/13-release-readiness`.

════════════════════════════════════════
3. INTEGRATION AREAS REVIEWED
════════════════════════════════════════

Traced the full domain lifecycle end to end: Client → Case → Court →
Hearings → Tasks/Deadlines → Documents → Contracts → Finance →
Notifications → Dashboard → Reports → Audit. Every integration point listed
in the phase brief was walked with real data and real service calls (not
mocked): Case↔Client, Case↔lawyers (lead + supporting), Case↔Court,
Case↔Hearings, Case↔Tasks, Case↔Deadlines, Case↔Documents, Case↔Contracts,
Case↔FeeAgreement, Case↔Invoices, Case↔Payments, Case↔Expenses,
Client↔Cases, Client↔Finance, Agenda↔(Hearings/Tasks/Deadlines/invoice due
dates), Notifications↔target objects, Dashboard↔selectors, Reports↔scoped
domain data, Audit↔mutations. All of Phase 12's own re-audit (authorization,
IDOR, finance concurrency, mixed-currency, document security, audit
integrity, notification/report/dashboard authorization, N+1, DB integrity,
auth/session, deployment config) was re-confirmed unchanged — the codebase
this phase touches is the same one that phase already re-derived from the
code, not re-read from a report.

════════════════════════════════════════
4. TESTS ADDED
════════════════════════════════════════

**`tests/test_integration_workflows.py` — 10 realistic, multi-step workflows
(spec Phase 13 §4 A–I)**, each asserting on real state at every step, not
just "no exception":

- **A. Client** — create → edit → archive (status flips, audit event, drops
  out of the active list) → restore (status flips back, audit event).
- **B. Case** — create → assign lead + supporting lawyer → add party → add
  note → change status → verify the timeline recorded every step → verify
  office_manager/lawyer/paralegal all see it (all-staff visibility, ADR-0008).
- **C. Hearing** — schedule → appears in the agenda and `upcoming_hearings` →
  cancel with a reason → reason is persisted, hearing drops out of both the
  agenda and the upcoming list → both `HEARING_SCHEDULED` and
  `HEARING_CANCELLED` land on the case timeline.
- **D. Task/Deadline** — overdue task → `is_overdue` computed correctly
  (ADR-0006) → `scan_overdue_tasks` generates exactly one notification →
  marking it done clears `is_overdue`. Deadline approaching →
  `scan_approaching_deadlines` notifies → marking it met flips status and
  `is_overdue`.
- **E. Document** — upload (private storage, case-linked, `DOCUMENT_ADDED`
  timeline event) → authorized download (200, audited) → retire → download
  now 404s (soft-deleted, not gone from the DB) → unauthenticated download
  redirects to login without ever touching the file.
- **F. Contract** — create (number allocated, starts `draft`) → activate →
  appears in `expiring_soon` → `expire_due_contracts` flips it to `expired`
  at the right date → paralegal can view but gets 403 on create/status-change
  (view-only, ADR-0031).
- **G. Finance** — fee agreement → draft invoice → line item → issue (number
  allocated, immutable — adding a line item after issue raises
  `ValidationError`) → payment → correct `PARTIALLY_PAID` status and
  outstanding balance → overpayment rejected → a same-case `Expense` never
  touches the invoice's `total`/`amount_paid`/`subtotal` → `case_financials`
  produces a real breakdown → the dashboard and an "outstanding" report CSV
  both show the invoice for a finance-capable user → **a paralegal has zero
  access to any of it** (403 on the invoice, the finance dashboard section
  hidden, the invoice number never appears in the paralegal's landing-page
  HTML), while still seeing the same case's non-financial tabs fine.
- **H. Notification** — generate (idempotent — a second scan creates zero
  duplicates) → open marks read and redirects to the hearing → a different
  user cannot open or mark someone else's notification (404 / scoped no-op).
- **I. Reports** — issue invoices in two different currencies → the revenue
  report never sums them into one combined figure (mixed-currency guard,
  re-confirmed) → a paralegal can run the non-financial `cases` report but
  403s on the financial `revenue` report.

**`tests/test_edge_cases.py` — 12 tests (spec Phase 13 §16)**, targeting
edge cases not already covered by a phase's own suite:

- Malformed (non-numeric) pk in 7 different URL families → the Django
  resolver itself 404s before any view/ORM code runs (parametrized, includes
  an injection-shaped string `"1;drop table"` as a sanity check — still just
  a 404, confirming there is no string-interpolated path handling to attack).
- Negative / zero / absurdly large numeric pks → 404, never 500.
- **Double-submit an invoice issue** (two rapid POSTs to `invoice_issue`) →
  the second bounces back with an error, no duplicate invoice number, status
  stays correct — exercises the `select_for_update` double-submit guard
  `finance.services.issue_invoice` already documents in its own comment.
- Double-archive a client → idempotent, exactly one `CLIENT_ARCHIVED` audit
  row (not two).
- Double "mark all notifications read" → second call is a clean no-op.
- **A notification's target becomes inaccessible after generation**: a
  finance clerk legitimately receives an `invoice_overdue` notification, is
  then reassigned to `paralegal` (loses `finance.view`, keeps
  `notifications.view`) — opening the notification still succeeds (it's
  their own row) but the finance target it redirects to now correctly 403s.
  This is the concrete proof that a notification carries no standing access
  of its own; every open still re-runs the target's own authorization.

Total: **+22 tests**, all passing on first stabilization (one test file
needed two small self-inflicted fixes — a nonexistent `ClientQuerySet.open()`
→ `.active()`, and a `Group.objects.set()` call given the wrong type — both
caught and fixed immediately; neither was a product defect).

════════════════════════════════════════
5. BUGS FOUND
════════════════════════════════════════

**None.** Every one of the 10 integration workflows and 12 edge cases passed
against the Phase 12-hardened code on the first correctly-written attempt (2
of the 22 new tests needed a trivial self-correction in the test code itself,
not the product — see §4). This is the expected, honest result of Phase 13
following directly after a genuinely thorough Phase 12 re-audit on the same
unchanged codebase: there was no new code between the two phases for a new
class of bug to hide in, and Phase 12 already re-derived (not re-read) every
area Phase 13's brief asks about again.

════════════════════════════════════════
6. BUGS FIXED
════════════════════════════════════════

None required (see §5) — no production code was changed this phase.

════════════════════════════════════════
7. SECURITY VERIFICATION
════════════════════════════════════════

Re-confirmed via the new tests, not merely re-asserted from Phase 12: private
document storage still 404s at the download boundary once retired and never
via a guessed path; the finance boundary holds project-wide including through
a notification's redirect target and a group re-assignment; malformed/
negative/oversized URL ids never reach application code; double-submission of
a money-mutating action is safely rejected, not silently duplicated. No new
XSS/CSRF/SQLi/mass-assignment surface was introduced (no new views, forms, or
models this phase).

════════════════════════════════════════
8. AUTHORIZATION VERIFICATION
════════════════════════════════════════

Every new workflow test exercises at least one authorization boundary as
part of its realistic journey (see §4: paralegal-vs-finance appears in
workflows B, F, G, H, I; unauthenticated-vs-authenticated in workflow E and
the edge-case malformed-pk sweep). Combined with Phase 12's own dedicated
`tests/test_capability_boundary_sweep.py` (still green, unchanged), the
project now has authorization coverage at three levels: per-URL matrices
(each app's own tests), a dedicated cross-cutting sweep (Phase 12), and
realistic multi-step workflows that cross module boundaries (Phase 13) — the
three together are why this phase is confident claiming the boundary holds
under real usage patterns, not just isolated requests.

════════════════════════════════════════
9. FINANCE VERIFICATION
════════════════════════════════════════

Workflow G re-derives, with real objects, everything §7 of the phase brief
asks for: `Decimal` arithmetic throughout, correct outstanding-balance
computation, overpayment rejection, issued-invoice immutability, invoice
numbering, fee-agreement vs. expense separation (an expense on the same case
is asserted to never touch the invoice's `total`/`subtotal`/`amount_paid`),
row-locked concurrent-safe payment recording (re-read in Phase 12, exercised
again here), and the double-submit issue guard (`test_edge_cases.py`). The
real `select_for_update` contention test
(`test_concurrent_payments_cannot_overpay`) remains PostgreSQL-only — see
§13; this phase did not fake that result.

════════════════════════════════════════
10. DOCUMENT-SECURITY VERIFICATION
════════════════════════════════════════

Workflow E: upload → authorized download (200, audited) → retire → download
404s (soft-deleted, not physically removed) → an unauthenticated request
never reaches the file at all (redirected to login before any storage code
runs). Combined with Phase 12's live `/media/` 404 test (re-run, still
green, unchanged), the private-storage boundary is verified both at the
application layer (this phase) and the static/media-serving layer (Phase 12).
Filesystem permissions on a real production disk remain, as always,
environment-dependent and cannot be exercised from this development machine
— documented, not claimed.

════════════════════════════════════════
11. PERFORMANCE VERIFICATION
════════════════════════════════════════

All 10 pre-existing query-count regression tests (dashboard, reports,
notifications, contracts, finance) re-run and pass unchanged. No new query
pattern was introduced this phase (test-only diff), so no new performance
regression test was needed. Premature optimization was deliberately avoided,
per the phase brief.

════════════════════════════════════════
12. DATABASE / MIGRATION VERIFICATION
════════════════════════════════════════

`manage.py makemigrations --check --dry-run` → no changes (no model touched
this phase). `manage.py check` → no issues (1 silenced, `axes.W006`,
intentional per ADR-0026). Both re-run clean on the freshly-merged master.

════════════════════════════════════════
13. POSTGRESQL STATUS
════════════════════════════════════════

**BLOCKED — no PostgreSQL server reachable from this machine.** A precision
correction on this phase's own investigation: the `psycopg` **driver** *is*
installed and importable in the project's virtualenv
(`psycopg 3.2.13`, matching the pin) — an earlier check in Phase 12 reported
`ModuleNotFoundError` only because that one invocation ran outside the
activated venv, not because the driver is genuinely absent. The real,
confirmed blocker is that **no PostgreSQL server is reachable**: no `psql`
binary on `PATH`, no Docker daemon (`docker info` fails), and a direct
`psycopg.connect("postgres://qistas:qistas@localhost:5432/qistas", …)`
attempt hangs/times out rather than connecting — nothing is listening on
5432. Consequently, still unverified:

- The full suite on PostgreSQL 16 (expect ~777 pass, 0 skipped).
- The 4 `@pytest.mark.postgres` tests, in particular
  `test_concurrent_payments_cannot_overpay` — the only test in the suite that
  actually exercises `select_for_update` under real concurrent row-level
  locking (SQLite substitutes a sequential guard test for the non-concurrent
  path, which does pass).
- The `pg_trgm`/`unaccent` extension migrations and trigram search indexes
  (all guarded, PostgreSQL-only, no-op on SQLite).

Nothing here is claimed as passed. See §14 for the exact commands to run on
a machine that has either.

════════════════════════════════════════
14. DOCKER STATUS
════════════════════════════════════════

**BLOCKED — no Docker daemon running** (`docker info` fails; same blocker
carried since Phase 1 — this machine's RAM/network constraints). Not run:
`docker compose build`, a full migrate-from-zero against a clean PostgreSQL
container, the complete containerized test run, or a `docker compose up`
smoke test. Exact commands for a capable machine / CI:

```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest                                  # expect ~777 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/                    # -> 302 /accounts/login/
```

════════════════════════════════════════
15. COMPILEMESSAGES STATUS
════════════════════════════════════════

**BLOCKED — GNU gettext not available on this Windows host** (`make
compilemessages` / `manage.py compilemessages` require it; Docker-only in
this project's own documented workflow). Harmless in practice: the app ships
`ar` only and all source strings are already Arabic (`LANGUAGE_CODE = "ar"`);
there is no missing-translation risk in the shipped language.

════════════════════════════════════════
16. DEPLOYMENT-CHECK STATUS
════════════════════════════════════════

`manage.py check --deploy` re-run against **real `config.settings.prod`
values** (genuine 64-byte random secret, real `ALLOWED_HOSTS`, real
`CSRF_TRUSTED_ORIGINS`; `DATABASE_URL` substituted with SQLite since the
deploy check never touches the database engine): **0 warnings, 1
intentionally-silenced** (`axes.W006` — lockout-by-username-not-IP,
ADR-0026). Identical, reproduced result to Phase 12 — the production settings
module has not regressed. `config.settings.test` still shows its usual 5
warnings, confirmed test-settings-only by the same comparison.

════════════════════════════════════════
17. DEPENDENCY STATUS
════════════════════════════════════════

`pip-audit`: **no known vulnerabilities.** Every dependency remains pinned to
an exact version (unchanged from Phase 12's list). **No dependency was
upgraded** — none was needed, per the instruction to only change dependencies
for a concrete correctness/security/compatibility reason.

════════════════════════════════════════
18. KNOWN REMAINING ENVIRONMENT BLOCKERS
════════════════════════════════════════

1. PostgreSQL 16 — no reachable server (§13).
2. Docker — no daemon (§14).
3. `compilemessages` — no GNU gettext on this host (§15, harmless).
4. Real production filesystem/storage permissions for the private document
   store — inherently environment-dependent, cannot be exercised from a
   development machine regardless of Docker/PostgreSQL availability.
5. `/code-review high` — the command/tool is **not available in this
   environment** (`.claude/commands/` holds only `designqc` / `handoff` /
   `reframe` / `security-audit`), consistent with every phase since Phase 4.
   A rigorous self code/security/architecture review was performed instead
   (this report + Phase 12's own ADR-0036 together constitute it).

════════════════════════════════════════
19. FINAL TEST COUNTS
════════════════════════════════════════

**777 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`, SQLite) —
**+22 tests this phase** (10 integration workflows + 12 edge cases), on top
of the 755 inherited from the freshly-merged Phase 12 master. `ruff check .`
clean. `ruff format --check .` clean (310 files). No warnings surfaced by
pytest beyond the pre-existing, expected skip reasons.

════════════════════════════════════════
20. FINAL RELEASE-READINESS ASSESSMENT
════════════════════════════════════════

**Release candidate — production-ready subject to the environment blockers
in §18.** Qistas behaves as one coherent product across the full client →
case → hearing/task/document/contract/finance → notification →
dashboard/report → audit lifecycle, verified this phase with real,
multi-step workflows rather than isolated unit checks, on top of Phase 12's
independent re-derivation of every authorization, integrity, and
configuration claim from the current code. The application-level surface
(code, tests, settings, dependencies) is verified clean on every gate this
environment can run. What remains before an unqualified "production ready"
claim is exclusively **environment verification that requires infrastructure
this development machine does not have**: a real PostgreSQL 16 instance (the
target production database — ADR-0023) and a Docker daemon (the target
deployment mechanism). Nothing was skipped by choice; nothing was claimed
that was not actually run.
