# Qistas — Design System

> Written for Phase 15 (UI/UX visual refinement). Describes the design tokens and
> shared component conventions actually implemented in `tailwind.config.js`,
> `static/src/app.css`, and `templates/components/` — not an aspirational spec.

## Visual reference

`static/src/Design.png` is the visual reference used for this phase: a light,
flat, white-surface admin screen (RTL, Arabic UI) with a white sidebar, a blue
brand/active-state accent, restrained borders instead of shadows, pill status
badges, and comfortable table row spacing.

**The reference defines visual language only — colors, spacing, density, border/shadow
treatment, typographic hierarchy — not Qistas's information architecture.** Qistas's
real domain surfaces (finance isolation, hearings, deadlines, documents, capability
gating) were preserved as-is; nothing in the reference dictated product scope.

## Colors (`tailwind.config.js`)

| Token | Value | Use |
|---|---|---|
| `navy` (DEFAULT) | `#1d4ed8` | Primary brand/accent — buttons, links, active nav state, logo mark, focus ring. Extracted from the reference's blue accent. |
| `navy-50` / `navy-100` | `#eef4ff` / `#dbe7ff` | Light tints — active nav pill background (`bg-navy/10` etc. also used via opacity). |
| `navy-900` | `#132a63` | Deep navy for full-bleed dark surfaces (auth screen, error pages) — kept distinct from the interactive `navy` so a whole-page fill reads as premium/serious rather than a flat SaaS-blue billboard. |
| `slate` | `#5b6472` | Muted/secondary text. |
| `ink` | `#101828` | Primary text, headings. |
| `sand` | `#f7f8fa` | Page canvas background (very light neutral, per reference). |
| `mist` | `#f1f4f8` | Subtle surfaces: table headers, hover states, muted chips. |
| `line` | `#e5e8ee` | Borders — the reference relies on borders, not shadows, for structure. |
| `bronze` | `#b8863b` / `#8a6428` | Secondary/legal accent, kept deliberately (see "Why bronze survives" below). |
| `danger` | `#b3261e` | Errors, destructive actions, overdue indicators. |
| success / warning / info | Tailwind `emerald` / `amber` / `slate` scales via `badge.html` / `alert.html` | Status semantics — restrained, not project-specific hues, matching the reference's soft green/amber tones. |

### Why bronze survives

The reference screenshot is a generic attendance/automation tool with a single
blue accent. Section 3/21 of this phase's brief ask for a *legal, premium, not-generic-SaaS*
feel while treating the screenshot as visual-language, not literal spec. Bronze/gold
was already Qistas's secondary accent (pending/new/prospect-type statuses, the
confidential-case callout, error-page branding). It is now used only for that narrow,
pre-existing "attention/in-between-state" semantic — never for primary structural
chrome (sidebar, primary buttons, focus rings all moved to the reference-derived blue).
This keeps one coherent system while avoiding an all-blue, indistinct-from-any-SaaS-app look.

## Typography

**Switched to Cairo** (self-hosted, Arabic-subset `woff2`, `static/fonts/cairo-{400,500,600,700}.woff2`),
replacing IBM Plex Sans Arabic. Two reasons: it was explicitly requested to match
`Design.png`'s typography, and — independently — **the IBM Plex Sans Arabic
`@font-face` rules had never had real font files behind them**: `static/fonts/`
was empty and nothing in the build (`Dockerfile`, `Makefile`) ever fetched them, so
every page had silently been rendering in the `Segoe UI`/`Tahoma` system fallback
the whole time. Cairo's files are vendored directly in the repo (same pattern as
`static/vendor/htmx.min.js`/`alpine.min.js` — no CDN, no Node build step, per
ADR-0024) so this doesn't regress into the same silent-fallback trap.

Change made this phase: **`uppercase tracking-wide` was removed from every heading/label
that used it** (table headers, section eyebrows, `styleguide.html`). Arabic has no
letter case, so `uppercase` was dead weight, and `tracking-wide` (extra letter-spacing)
actively hurts Arabic readability by disrupting cursive letter-joining. Section eyebrows
now rely on `font-semibold` + `text-slate` for hierarchy instead.

Scale (unchanged, already correct): page titles `text-xl font-semibold`, section
headers `text-base font-semibold`, body `text-sm`, meta/help text `text-xs`.

## Spacing & density

- Table cells/headers: `px-3 py-2` → **`px-4 py-3`** (16 templates) for a more
  comfortable, reference-matched row height, without turning tables into cards.
- Filter/section cards keep their existing `p-4`/`p-5` rhythm.
- No column collapsing or table→card conversion — the brief explicitly asks to keep
  tables dense enough for a professional legal system, not to inflate them.

## Radius

`borderRadius.xl` tightened from `0.9rem` to **`0.75rem`** (12px) — the reference's
cards/table wrappers read closer to a tight `lg`/`xl` than to the very rounded
"SaaS card" look. `card.html` and `modal.html` moved from `rounded-xl` to `rounded-lg`
(8px) to match the reference's table/panel corners more closely; large content
sections that use the raw `rounded-xl` utility inherit the new, tighter value directly
from the token — no per-template edits needed.

## Shadows

Flattened to match the reference's border-only structure:
- `card.html`: `shadow-sm` removed entirely.
- `templates/auth_base.html`, `templates/components/modal.html`: `shadow-xl`/`shadow-2xl`
  → `shadow-lg` (floating surfaces over a colored/backdrop still get *some* separation,
  but restrained).
- Everywhere else (tables, list filter panels, dashboard cards) already relied on
  `border border-line` with no shadow — left untouched, it already matched the reference.
- The one surviving `hover:shadow-sm` (dashboard KPI tiles) is an intentional, subtle
  interactive affordance, not a resting-state shadow.

## Borders

Unchanged usage pattern — `border-line` everywhere structure needs a boundary
(tables, cards, filter panels, dropdowns). This was already the dominant technique
in Qistas and matches the reference directly.

## Icons

**New**: a single coherent inline-SVG icon set (`{% icon "name" %}` template tag,
`core/templatetags/qistas.py`), hand-authored, stroke-based, 24×24, no external
icon library/dependency (spec §14/§11). Replaces every emoji/glyph placeholder
(`☰`, `🔔`, `✓`, `▲`, etc.) across the sidebar, topbar, alerts, and empty states.

The sidebar/topbar icons render the semantic `icon` field that `core/navigation.py`'s
`NavItem` already carried (`home`, `users`, `folder`, `calendar`, `chart`, `bell`,
`cog`) — that field existed before this phase but was never rendered; wiring it up
is a pure UI fix, not a new feature.

Three of the seven top-level sections originally shared the identical `"folder"`
icon (`القضايا`/cases, `المستندات والعقود`/documents, `المالية`/finance) — visually
indistinguishable at a glance in the sidebar. Added two more icons (`file-text`,
`wallet`) and reassigned documents→`file-text` and finance→`wallet`, keeping
`folder` for cases. This is a one-word data change in `core/navigation.py` (the
`icon` field is a display hint, never the authorization boundary — see the
module's own docstring), not a logic change.

**Bug found and fixed while screenshotting for visual QA**: the notifications
bell's `aria-label` in `templates/partials/topbar.html` interpolated
`{% num unread_notification_count %}`, which renders `<bdi dir="ltr">6</bdi>` —
safe HTML markup — directly inside an HTML *attribute* string. The unescaped
`"` inside `dir="ltr"` prematurely closed the `aria-label="..."` attribute,
so the browser's error-recovery parsing spilled the tag's tail (`<bdi dir="`)
into the page as visible garbled text (`<"(6`) next to the bell icon on every
page, for every user with an unread count. This predates Phase 15 — `{% num %}`
was never touched by this phase's edits — but was caught only now because this
phase is the first time real rendered screenshots were taken. Fixed by using
plain `{{ unread_notification_count }}` in the attribute (a `<bdi>` bidi
wrapper is meaningless inside a non-visual `aria-label` anyway). Logged as
bug-134 in `.wolf/buglog.json`.

## Buttons, badges, forms

- `.btn-*` classes (`static/src/app.css`) re-pointed at the new `navy` (blue) token;
  shapes/sizes unchanged (`rounded-md`, `px-4 py-2`).
- `badge.html` unchanged structurally — pill shape and tone palette already matched
  the reference's status-chip style.
- `input`/`select`/`textarea`: focus ring/border moved from `bronze` to `navy` (the
  reference's clear blue focus language); `:focus-visible` outline likewise.
- `input[type="search"]` and `select` gained inline SVG affordances (search glyph,
  chevron) via CSS `background-image` — no JS, no template changes, works across
  all 12 filter forms that already used `type="search"` for their `q` field.

## RTL conventions

Logical properties only (`ms/me`, `ps/pe`, `start/end`, `border-s/border-e`) — no
physical `left/right` was introduced anywhere in this phase's changes, with the sole
exception of the two decorative CSS `background-image` positions (search icon, select
chevron), which are static image assets on an RTL-only project (`dir="rtl"` is
hardcoded in `base.html`; there is no LTR mode to break, per `docs/adr/0024`).

**A real, pre-existing positioning bug was found and fixed here**: `templates/
partials/sidebar.html` anchored the off-canvas mobile drawer with `end-0`
(`inset-inline-end: 0`), on the assumption that `end` maps to the physical right
edge in RTL. It doesn't — confirmed by direct DOM measurement (`getComputedStyle`)
in a real browser: in `dir="rtl"`, `inset-inline-end` resolves to physical `left`
(inline progression in RTL runs right→left, so "inline end" is the left edge —
the opposite of the LTR-intuition mistake this class name invites). Desktop never
showed the symptom because at `lg:` the sidebar becomes `position: static` and is
placed correctly by RTL flex ordering regardless of the inset property; only the
`fixed`-positioned mobile drawer used the inset value directly, so it opened
anchored to the *left* edge of the screen while everything else in the app (topbar,
desktop sidebar, toast region) is right-anchored. Fixed by swapping to `start-0`
(and `border-s`→`border-e` for the divider, which was on the wrong/outer edge for
the same reason). See "Sidebar & navigation" below for the related open/close fix.

## Sidebar & navigation

Two changes beyond the color/icon refresh described above:

**Collapsible groups.** Each top-level section with children (`العملاء`, `القضايا`,
`المكتب`, `المستندات والعقود`, `المالية`) is now an Alpine-driven disclosure: a
`<button>` header with a rotating chevron toggles a `x-show` panel of children. A
group starts **expanded only if the current page is inside it** — computed
server-side in `core/context_processors.py` (`_resolve` now takes the current
`resolver_match.view_name` and returns `is_active_group` per parent; a pure
display hint, same category as the pre-existing `disabled`/`icon` fields, never
an authorization signal) — and collapsed otherwise. Previously every group's
children were always rendered open, so a single sidebar rendered ~20 links at
once; now only the relevant ~3-5 are visible by default, closer to the reference's
flat simplicity while keeping Qistas's real (larger) information architecture
intact, per the brief's §21 "don't overfit" guidance.

**Mobile drawer open/close was silently broken, independent of the anchor-edge
bug above.** The original markup layered a static base class (`-translate-x-full
rtl:translate-x-full`) with Alpine additively appending `translate-x-0
rtl:translate-x-0` on top when open — never removing the base classes. Tailwind
compiles the `rtl:` variant as `.rtl\:translate-x-full:where([dir=rtl],[dir=rtl]
*){...}`; `:where()` contributes **zero specificity**, so all four classes
(`-translate-x-full`, `translate-x-0`, and their `rtl:` twins) end up tied in
specificity, and the browser breaks the tie by **source order in the compiled
stylesheet** — not by which class Alpine most recently added. `rtl:translate-x-full`
happened to compile after `rtl:translate-x-0`, so it won regardless of
`sidebarOpen`: clicking the hamburger button updated Alpine's state and the
`aria-expanded` attribute correctly, but the drawer's `transform` never visibly
changed. Confirmed with `getComputedStyle`/`getBoundingClientRect` before and
after a programmatic click. Fixed by removing the competing static classes
entirely and making Alpine's `:class` the single source of truth
(`sidebarOpen ? 'translate-x-0' : 'translate-x-full'`, no `rtl:` prefix needed —
the project has no LTR mode to disambiguate from), keeping only the
media-query-based `lg:translate-x-0` (real `@media`, not `:where()`, so it
reliably overrides at desktop widths regardless of `sidebarOpen`). Verified all
three states (mobile closed / mobile open via a real click / desktop) by reading
back the resolved `transform` matrix and bounding rect in a live headless-Chrome
session — not just visually.

## Charts

Two dependency-free, inline-SVG/CSS chart primitives (spec §14 — no charting
library), added to the dashboard's existing "تحليلات القضايا" (case analytics)
section, which previously only had the ranked-bar-list part:

- **`{% donut_chart rows %}`** (`core/templatetags/qistas.py` + `components/
  donut_chart.html`): a ring chart for the "حسب الحالة" (by status) breakdown —
  a natural fit since case statuses are mutually-exclusive parts of one whole.
  Uses the classic `r=15.9155` SVG-circle trick (`2πr ≈ 100`), so each segment's
  percentage of the total *is* its `stroke-dasharray` length directly, computed
  once in Python and handed to the template as plain numbers — no client-side
  math, no JS.
- **Ranked bars** (`dashboard/_bars.html`, pre-existing, kept for priority/type/
  lawyer): now cycle through the same 8-color categorical palette
  (`CHART_COLORS` in `qistas.py`, shared with the donut so the two read as one
  system) via a new `chart_color` filter, instead of a single flat navy tone —
  and got a touch more visual weight (`h-2` bars, `rounded-full`, tighter label
  spacing).

Neither introduces a JS charting dependency; both degrade to a plain "لا بيانات"
message when a breakdown is empty, matching the existing `_bars.html` behavior.

## Responsive

Existing mobile sidebar (Alpine-driven off-canvas + backdrop), responsive grid
breakpoints on the dashboard, and `overflow-x-auto` table wrappers were already
reference-aligned; the off-canvas drawer's actual open/close *behavior* is the
one thing that changed here, described above — verified working at a 390×844
mobile viewport and unchanged at desktop.

## What intentionally did not change

- Business logic, URLs, permissions, object scoping, forms' server-side validation.
- Any model, view, selector, or service.
- Finance capability gating / paralegal isolation.
- The information architecture of any domain page (no page was redesigned around
  the screenshot's specific content — see "Visual reference" above).
