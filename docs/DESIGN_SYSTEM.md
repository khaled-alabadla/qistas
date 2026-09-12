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

Unchanged font stack: **IBM Plex Sans Arabic** (self-hosted, `docs/adr/0024`), falling
back to Segoe UI / Tahoma / Arial. No new fonts introduced (reference uses a plain
system sans; Qistas's existing Arabic-first stack already serves that role better).

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

## RTL conventions (unchanged, verified still correct)

Logical properties only (`ms/me`, `ps/pe`, `start/end`, `border-s/border-e`) — no
physical `left/right` was introduced anywhere in this phase's changes, with the sole
exception of the two decorative CSS `background-image` positions above, which are
static image assets on an RTL-only project (`dir="rtl"` is hardcoded in `base.html`;
there is no LTR mode to break, per `docs/adr/0024`).

## Responsive

No structural changes — the existing mobile sidebar (Alpine `x-show`/backdrop),
responsive grid breakpoints on the dashboard, and `overflow-x-auto` table wrappers
were already reference-aligned and were left in place.

## What intentionally did not change

- Business logic, URLs, permissions, object scoping, forms' server-side validation.
- Any model, view, selector, or service.
- Finance capability gating / paralegal isolation.
- The information architecture of any domain page (no page was redesigned around
  the screenshot's specific content — see "Visual reference" above).
