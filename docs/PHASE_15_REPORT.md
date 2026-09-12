━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        15 — UI/UX Visual Refinement (owner-defined; not in the
              original spec sequence — added after Phase 13 was declared
              the final planned phase)
Status:       COMPLETE (technical)
Branch:       phase/15-design-refinement — based on master @ 08d5f5f
              (Phase 13 merge, PR #12)
Commit:       phase(15): refine UI to design reference (+ follow-up fixes:
              Cairo font, sidebar/dashboard refinement — see §10)

**This is a pure UI/visual phase.** No model, view, service, selector, form,
URL, or permission was changed. The diff is templates, `core/navigation.py`
(one-word icon-name changes only), `core/context_processors.py` (a display-only
field added to the nav dict), two new template tags (`icon`, `donut_chart`,
`chart_color` in `core/templatetags/qistas.py`), `static/src/app.css`,
`tailwind.config.js`, vendored font files, and documentation.

════════════════════════════════════════
1. PHASE OBJECTIVE
════════════════════════════════════════

Bring Qistas's existing UI closer to the visual language of a supplied
reference image (`static/src/Design.png`) — a light, flat, white-surface RTL
admin screen with a blue accent, restrained borders instead of shadows, pill
status badges, and comfortable table density — while preserving 100% of
Qistas's existing functionality, architecture, permissions, and domain
information architecture. The screenshot is a visual reference, not a
product spec.

The owner reviewed the first pass and asked for two corrections/additions,
which make up the second half of this report: use the **Cairo** font instead
of the originally-swapped IBM Plex Sans Arabic, and continue refining until
it actually converged with the reference (the first pass had shipped with no
real rendered screenshot ever taken — see §8/§10 for what that cost).

════════════════════════════════════════
2. DESIGN AUDIT — REFERENCE vs. CURRENT
════════════════════════════════════════

**Reference (`Design.png`):** white page canvas; white sidebar with a small
blue logo badge, plain icon + label nav items, a light-blue pill for the
active item; white topbar with a page title, date, and avatar; a flat white
table with a light-gray header row, generous row padding, pill status badges,
a cream/yellow info banner, and a bordered pill "refresh" button; virtually
no shadows — structure comes from thin gray borders; moderate corner radius;
plain, restrained sans-serif type.

**Qistas before this phase:** already had a real component kit (`templates/
components/*`), a data-driven capability-filtered sidebar, and a consistent
token system (`docs/adr/0024`) — sound, reusable architecture. Gaps against
the reference: a filled dark-navy sidebar instead of white-with-blue-accent;
gold as the primary interactive color instead of blue; emoji/glyph
placeholders instead of a real icon system (despite `NavItem.icon` already
carrying semantic names that were never rendered); heavier radius and a few
stray shadows; `uppercase tracking-wide` on Arabic headers (inert for Arabic,
harms letter-joining readability); tighter table density than the reference.

════════════════════════════════════════
3. DESIGN SYSTEM EXTRACTED / APPLIED
════════════════════════════════════════

Full rationale in `docs/DESIGN_SYSTEM.md`. Summary:

- **Colors**: `navy` redefined to blue (`#1d4ed8`, from the reference) with
  light tints and a separate `navy-900` for full-bleed dark surfaces (login,
  error pages) so those read as premium rather than a flat blue billboard.
  `sand`/`mist`/`line`/`ink`/`slate` cooled to neutral light-gray/near-black.
  `bronze` kept, deliberately narrowed to its existing "pending/in-between
  state" semantic — see `docs/DESIGN_SYSTEM.md` §"Why bronze survives".
- **Radius**: `xl` token 0.9rem → 0.75rem; `card.html`/`modal.html` →
  `rounded-lg`.
- **Shadows**: removed from `card.html`; `auth_base.html`/`modal.html`
  reduced to `shadow-lg`. Everywhere else already border-only.
- **Typography**: switched to **Cairo** (self-hosted, `static/fonts/cairo-
  {400,500,600,700}.woff2`), per explicit request — and because the prior
  IBM Plex Sans Arabic `@font-face` rules pointed at files that had never
  existed in the repo (`static/fonts/` was empty; nothing in `Dockerfile`/
  `Makefile` ever fetched them), so the app had silently been rendering in
  the OS Arabic fallback the entire time this phase started from. Also
  removed `uppercase tracking-wide` project-wide (27 headings/table headers).
- **Spacing**: table `<th>`/`<td>` padding `px-3 py-2` → `px-4 py-3` (16
  templates).
- **Icons**: new dependency-free inline-SVG icon set (`{% icon "name" %}`),
  20 hand-authored stroke icons, wired up against `NavItem.icon` (existed,
  was never rendered). Two icons added mid-phase (`file-text`, `wallet`) once
  screenshots revealed three unrelated sidebar sections shared one icon.
- **Forms**: focus ring moved to `navy`; `input[type=search]`/`select` gained
  CSS-only inline-SVG affordances.
- **Sidebar/topbar rewritten**: white surface, blue logo mark, real icons,
  light-blue active-pill state; topbar icons instead of emoji.
- **Sidebar made collapsible** (added after visual review — see §10.3): each
  section with children is now an Alpine disclosure, expanded by default only
  when the current page lives inside it (`core/context_processors.py`'s
  `is_active_group`, a display hint alongside the pre-existing `disabled`
  field — never an authorization signal).
- **Two dependency-free dashboard charts added** (added after the owner's
  request — see §10.4): an SVG donut for the case-status breakdown, and the
  pre-existing ranked-bar lists re-colored from a shared categorical palette.

════════════════════════════════════════
4. WHAT WAS DELIBERATELY NOT CHANGED
════════════════════════════════════════

- Any Python code path with product logic: views, services, selectors, forms,
  models, URLs, permissions/capabilities, object scoping, audit logging.
  (`core/navigation.py` and `core/context_processors.py` were touched, but
  only their display-only `icon` string values and a new display-only
  `is_active_group` boolean — see their own module docstrings, which already
  state the nav structure is "a display aid only — never the authorization
  boundary.")
- Finance capability gating / paralegal isolation.
- The information architecture of any domain page.
- `templates/components/dropdown.html`, `tabs.html`, `file_upload.html`,
  `confirm_dialog.html`, `loading_state.html` — confirmed unused outside the
  dev-only `/styleguide/` page.

════════════════════════════════════════
5. FILES CHANGED
════════════════════════════════════════

Config/CSS: `tailwind.config.js`, `static/src/app.css`, `static/fonts/cairo-
{400,500,600,700}.woff2` (new, vendored — same pattern as `static/vendor/
htmx.min.js`).

Python: `core/templatetags/qistas.py` (`icon`, `donut_chart`, `chart_color`,
`CHART_COLORS`), `core/navigation.py` (2 icon-name strings), `core/
context_processors.py` (`is_active_group` field).

Templates (structural): `base.html` (favicon color), `auth_base.html`,
`errors/_base.html`, `partials/sidebar.html` (rewritten twice — palette pass,
then collapsible-groups + the two RTL bugs in §10.3), `partials/topbar.html`
(icons + the aria-label bug fix), `components/card.html`, `empty_state.html`,
`alert.html`, `modal.html`, `donut_chart.html` (new), `dashboard/_bars.html`,
`dashboard/dashboard.html`.

Templates (mechanical — table density/typography, 27 files): every list/
detail page with a table or a "section eyebrow" heading — full list in the
diff (`git diff --stat` against `master`).

Docs: `docs/DESIGN_SYSTEM.md`, `docs/PHASE_15_REPORT.md` (this file),
`docs/architecture.md` (§11 updated to match), `PROJECT_STATUS.md`.

════════════════════════════════════════
6. SHARED COMPONENTS IMPROVED
════════════════════════════════════════

`card.html`, `alert.html`, `empty_state.html`, `modal.html`, the shared
`input`/`select` CSS, `.btn-*` CSS, the sidebar and topbar partials, and the
new `icon`/`donut_chart`/`chart_color` tags. `badge.html` and
`pagination.html` were verified already reference-aligned and left untouched.

════════════════════════════════════════
7. RTL / ACCESSIBILITY REVIEW
════════════════════════════════════════

- No physical `left`/`right` utility was introduced, except the two
  decorative CSS `background-image` positions (search/select icons) — static
  assets on an RTL-only project with no LTR mode, documented as the one
  deliberate exception.
- **Two real RTL bugs found and fixed** in the sidebar — see §10.3 for the
  full technical account: (1) the mobile drawer was anchored with `end-0`,
  which resolves to physical `left` in `dir="rtl"` (confirmed by direct DOM
  measurement), not `right` — it opened flush against the wrong edge of the
  screen, inconsistent with the desktop sidebar and the rest of the app;
  (2) independent of that, the open/close *toggle itself* was a no-op due to
  a Tailwind `:where()`-specificity tie between static and Alpine-applied
  classes — clicking the hamburger updated `aria-expanded` but never visibly
  moved the drawer. Both predate this phase and were only surfaced because
  this is the first time real rendered screenshots were taken (§8/§10.1).
- Removing `tracking-wide` from Arabic text is itself a readability fix.
- All new icons are `aria-hidden="true"`, always paired with visible text or
  an existing `aria-label`.
- Focus-visible outline changed color only, same 2px offset contrast ring.
- No `<label>`/`for`, semantic heading, or ARIA attribute was removed.

════════════════════════════════════════
8. VISUAL VALIDATION
════════════════════════════════════════

**This phase went through two distinct verification passes, and the
difference between them is the main lesson worth recording.**

**First pass**: no browser was reachable (`claude-in-chrome` reported "the
extension is not connected"; no headless-browser library in the venv), so
verification relied on rebuilding CSS, curling pages for HTTP 200, and
reading rendered HTML text for the presence of expected classes/markup. That
pass shipped a commit that *looked* correct by every check available, but
had two live defects a human immediately caught by eye: it was still
rendering in a system-fallback font (because the previous phase's font files
had never actually existed — nothing about that phase's own diff could have
caught it, since HTML/class inspection can't detect a missing static asset
that 404s silently into a font fallback), and it had a garbled string of text
next to the notification bell on every page.

**Second pass** (this section describes what actually closed the gap):
found that Chrome itself is installed on this machine and can be driven
headless via the DevTools Protocol directly (`chrome.exe --headless=new
--remote-debugging-port --remote-allow-origins=*`), without needing the
`claude-in-chrome` extension or Playwright. Built a small script
(`scratchpad/shot.py`) that opens a CDP websocket, injects the authenticated
session cookie, navigates, and captures a real PNG screenshot — then actually
looked at the pixels. This is what found:

1. The font fallback (visually obvious once actually rendered).
2. The garbled `aria-label` text next to the bell (§10.2) — invisible to
   `curl`/HTML inspection because the malformed attribute only breaks when a
   real HTML parser (a browser) recovers from it.
3. Three sidebar sections sharing one icon (a `grep` could have found this
   too, in hindsight, but it took looking at the rendered sidebar to notice
   it read as a design flaw).
4. Both RTL sidebar bugs in §10.3 — found by noticing, at a mobile viewport
   screenshot, that a chunk of white sidebar was visibly overlapping the
   content on the wrong side. Diagnosed to a certainty (not a guess) by
   querying `getComputedStyle`/`getBoundingClientRect` on the live `<aside>`
   element via `Runtime.evaluate`, before and after a programmatic click on
   the real hamburger button.

Every fix from this pass was re-verified the same way (a fresh screenshot or
DOM query), not just re-read.

**One process note, disclosed rather than glossed over**: killing the first
headless Chrome instance used `taskkill /IM chrome.exe`, which targets every
process with that image name on the machine, not just the one this session
started — if the user had another Chrome window open, it would have been
force-closed. This was caught immediately, flagged to the user in the same
turn it happened, and every subsequent Chrome/Django process was stopped by
exact PID (cross-checked against `netstat`) instead.

════════════════════════════════════════
9. VERIFICATION
════════════════════════════════════════

- **Tests: 777 pass / 0 fail / 4 skipped** (SQLite) — identical to the Phase
  13 baseline, re-run after every round of changes in this phase (three full
  runs total). No test was added, removed, or modified.
- `ruff check .` — clean. `ruff format --check .` — clean, 310 files.
- `manage.py makemigrations --check --dry-run` — "No changes detected."
- `manage.py check` — "System check identified no issues (1 silenced)."
- `manage.py check --deploy` against real `config.settings.prod` (SQLite
  `DATABASE_URL` override, the established Phase-12/13 technique) — clean.
- All throwaway artifacts (a seeded SQLite preview DB, a headless-Chrome
  profile directory, scratch Python scripts) live outside the repo or are
  gitignored (`*.sqlite3`) and were deleted before commit — confirmed via
  `git status --porcelain` showing only the intended files.

════════════════════════════════════════
10. NOTABLE FINDINGS (beyond the visual refresh itself)
════════════════════════════════════════

**10.1 — IBM Plex Sans Arabic was never actually loading.** `static/fonts/`
was empty and no build step ever populated it; every page had been silently
falling back to the OS Arabic stack since whichever earlier phase introduced
the `@font-face` rules. Switching to Cairo fixed this by construction (the
`.woff2` files are now genuinely vendored in the repo), but the underlying
lesson — a missing static asset degrades silently and no amount of
HTML/class inspection catches it — is why §8 above matters.

**10.2 — bug-134** (`.wolf/buglog.json`): `templates/partials/topbar.html`'s
notification-bell `aria-label` interpolated `{% num unread_notification_count
%}`, which renders `<bdi dir="ltr">6</bdi>` (safe HTML) directly inside an
HTML attribute string. The unescaped `"` in `dir="ltr"` prematurely closed
the `aria-label="..."` attribute; the browser's error-recovery parsing then
spilled the tag's tail into the page as visible garbled text next to the bell
icon, for every user with an unread count, on every page. Predates this
phase — fixed with plain `{{ unread_notification_count }}` (a `<bdi>` bidi
wrapper is meaningless in a non-visual attribute anyway).

**10.3 — two independent, pre-existing sidebar RTL bugs**, both only visible
at mobile/tablet viewport widths (desktop never showed either symptom because
`lg:static` takes the sidebar out of fixed positioning and RTL flex ordering
places it correctly regardless):

- The off-canvas drawer was anchored with `end-0`. In `dir="rtl"`,
  `inset-inline-end` resolves to physical **left**, not right — confirmed by
  direct `getComputedStyle` measurement, not assumption. It opened flush
  against the left edge of the screen, inconsistent with every other
  right-anchored element in the app (desktop sidebar, toast region). Fixed:
  `end-0` → `start-0`, `border-s` → `border-e` (the divider had the same
  problem, on the outer instead of the content-facing edge).
- Independently, the open/close **toggle was a no-op**: the drawer was hidden
  by an always-present static class, and Alpine additively appended the
  "show" classes on top without ever removing the "hide" ones. Tailwind
  compiles the `rtl:` variant with a `:where()`-wrapped selector, which
  carries zero specificity, so the four competing classes tied and the
  browser's tie-break (source order in the compiled stylesheet) always
  favored the hidden state — clicking the hamburger updated Alpine's
  internal state and `aria-expanded` correctly, but the drawer never visibly
  moved. Fixed by making Alpine's `:class` binding the single source of
  truth for the transform (no competing static classes), keeping only the
  real-`@media`-based `lg:translate-x-0` for the desktop override. Verified
  in all three states (mobile closed / mobile open via a real click /
  desktop) via `getComputedStyle`+`getBoundingClientRect`, not just visually.

**10.4 — sidebar and dashboard follow-up requests.** After reviewing the
first pass, the owner asked to "improve the sidebar" and "add simple charts
to the dashboard." The sidebar work is §3/§10.3 above (collapsible groups +
the two bug fixes, discovered *while* implementing the collapsible behavior
and testing it at mobile width). The dashboard gained an SVG donut chart for
the case-status breakdown and re-colored the existing ranked bars from a
shared palette — see `docs/DESIGN_SYSTEM.md` §"Charts" for the implementation
(no JS charting library; server-computed SVG geometry).

════════════════════════════════════════
11. DEFERRED / UNVERIFIED
════════════════════════════════════════

Everything already deferred from Phase 13 for the same standing environment
reason (no PostgreSQL server, no Docker daemon reachable from this machine):
full suite on PostgreSQL 16, the 4 `@pytest.mark.postgres` tests, `docker
compose` full-stack smoke, `compilemessages`. None are UI-related and none
regressed — listed only for continuity with `PROJECT_STATUS.md`.

No further visual gaps are known at this time — unlike the first pass, this
report is not asserting completeness from HTML inspection alone; it is based
on real rendered screenshots and live DOM queries across desktop and mobile
viewports for every major page family.

════════════════════════════════════════
12. FINAL ASSESSMENT
════════════════════════════════════════

Qistas's UI has been **implemented to closely follow the visual language and
structure of `Design.png`** — not made identical to it, and not restructured
around its specific (unrelated) domain content. Beyond the visual refresh
itself, this phase surfaced and fixed three genuine pre-existing defects
(missing font files, a broken `aria-label` producing visible garbled text,
and two independent RTL positioning/interaction bugs in the mobile sidebar)
that no amount of test-suite or lint checking would have caught, precisely
because they are the class of bug that only a rendered browser reveals. The
gap between the first pass (verified only by HTML/class inspection) and the
second (verified by actual pixels and live DOM state) is the most important
finding of this phase, independent of the visual outcome itself.

**Phase 15 is technically complete and pushed, but NOT merged. Awaiting
APPROVE PHASE 15.**
