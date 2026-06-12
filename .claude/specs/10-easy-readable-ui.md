# Spec: Easy Readable UI

## Overview

FinCheck's core flows (registration, login, dashboard, profile, expenses CRUD) are all functionally complete after steps 1-9, but the UI was built quickly and has accumulated readability and accessibility gaps: low-contrast muted text (`--ink-muted`, `--ink-faint`), dense stat/table layouts with little visual hierarchy, missing focus-visible states for keyboard users, and icon-only controls without accessible labels. Step 10 is a **global, CSS- and template-driven readability and accessibility pass** — no new routes, no database changes, and no behavior changes. The goal is that every existing page is easier to scan, meets WCAG AA contrast for text, supports visible keyboard focus, and exposes proper labels for icon-only buttons and nav links to screen readers.

## Depends on

- **Step 1 (Database Setup)** through **Step 9 (Delete Expense)** — this step touches the shared `base.html`, `static/css/style.css`, and the templates produced by every prior step (`landing.html`, `register.html`, `login.html`, `dashboard.html`, `profile.html`, `expenses.html`, `expense_form.html`, and the `partials/` used by edit/delete). All of those must already exist and render correctly before this pass begins.

## Routes

No new routes.

## Database changes

No database changes.

## Templates

- **Create:** none.
- **Modify:**
  - `templates/base.html` — add a "Skip to main content" link as the first focusable element, add `aria-label`/`aria-current` to nav links, add `aria-label` to the icon-only sign-out button and any icon-only controls in the navbar/footer.
  - `templates/dashboard.html` — simplify the stat/card grid (`db-section`, `db-card-title` blocks around lines 12-160): clearer heading hierarchy (one `h1` greeting, `h2` per card section, no skipped levels), increase spacing between stat cards, ensure numeric stats have a visible label (not just an icon).
  - `templates/profile.html` — simplify the profile/activity layout (`profile-section`, `profile-card-title` blocks around lines 9-150): group related fields, increase line-height/spacing in the activity table, ensure form labels are visible (not placeholder-only).
  - `templates/expenses.html` and `templates/partials/_expense_row.html` / `partials/_edit_expense_row.html` — improve table readability: consistent column padding, right-align amount column, ensure category/date columns have enough contrast, add `scope="col"` to table headers.
  - `templates/login.html`, `templates/register.html` — verify label/input contrast and spacing against the new typography scale; no structural changes beyond spacing/contrast.
  - `templates/landing.html`, `templates/terms.html`, `templates/privacy.html` — only affected via shared CSS variables (typography scale, spacing scale, focus styles); no template edits expected unless a contrast issue is found during manual review.

## Files to change

- `static/css/style.css`
  - Add a typography scale to `:root` (e.g. `--fs-xs`, `--fs-sm`, `--fs-base`, `--fs-lg`, `--fs-xl`, `--fs-2xl`, `--fs-display`) and a spacing scale (e.g. `--space-1` through `--space-6`) so templates can reference consistent sizes instead of ad-hoc `rem` values.
  - Audit `--ink-muted` (`#6b6b6b`) and `--ink-faint` (`#a0a0a0`) against `--paper` (`#f7f6f3`) and `--paper-card` (`#ffffff`); darken either value if needed so body-size muted text reaches at least 4.5:1 contrast and large/icon-only text reaches at least 3:1. Keep both as named CSS variables — do not introduce new hardcoded hex values.
  - Add a global `:focus-visible` style (using `--accent` for the outline/ring) applied to links, buttons, inputs, and nav items, so keyboard users can see focus.
  - Add `.skip-link` styles (visually hidden until focused, then fixed to top-left) for the new skip-to-content link in `base.html`.
  - Increase line-height and vertical spacing on dense blocks: dashboard stat cards (`db-card-title` and surrounding containers), profile activity table, expenses table rows — using the new spacing scale.
  - Add `scope`/header styling for `<th>` elements in the expenses table if not already styled.

- `templates/base.html`
  - Add `<a href="#main-content" class="skip-link">Skip to main content</a>` immediately after `<body>`, and `id="main-content"` on the `<main class="main-content">` element.
  - Add `aria-current="page"` alongside the existing `is-active` class logic on nav links.
  - Add `aria-label="Sign out"` to the icon+text sign-out button (icon-only buttons elsewhere get the same treatment).

- `templates/dashboard.html`, `templates/profile.html`, `templates/expenses.html`, `templates/partials/_expense_row.html`, `templates/partials/_edit_expense_row.html`, `templates/login.html`, `templates/register.html`
  - Apply the new typography/spacing variables and heading-hierarchy/label fixes described above. No changes to Jinja logic, form actions, or `url_for()` usage — purely markup/class/CSS adjustments.

## Files to create

No new files.

## New dependencies

No new dependencies.

## Rules for implementation

- **Parameterised queries only** — n/a (no DB queries touched in this step), but if any service file is touched accidentally, this rule still applies.
- **Passwords hashed with werkzeug** — n/a, no auth logic changes.
- **Use CSS variables — never hardcode hex values.** All new typography, spacing, contrast, and focus-style values must be defined as `--…` custom properties in `:root` and referenced via `var(--…)`.
- **All templates extend `base.html`** — already true; do not break this when editing nav/skip-link markup.
- **No behavior changes** — do not alter route handlers, form actions, HTMX endpoints, or JS logic in `static/js/main.js` beyond what's strictly needed for the skip link to function (plain anchor + `id`, no JS required).
- **No new hardcoded URLs** — skip link uses `#main-content`, an in-page anchor, which is acceptable (not an internal route).
- Maintain WCAG AA: body text ≥ 4.5:1 contrast, large text (≥ 1.25rem / bold ≥ 1rem) and icons ≥ 3:1 contrast against their background.
- Do not remove or rename existing CSS classes that other templates depend on — add new variables/classes alongside, and only repoint existing selectors to new variables where it's a like-for-like value swap.

## Definition of done

- [ ] `style.css` defines a typography scale (`--fs-*`) and spacing scale (`--space-*`) in `:root`, with no new hardcoded hex values anywhere in the diff.
- [ ] Pressing `Tab` immediately after page load on any page reveals a visible "Skip to main content" link; activating it moves focus to `<main id="main-content">`.
- [ ] Tabbing through the navbar, forms (login/register/expense form), and buttons shows a clearly visible focus ring (via `:focus-visible`) on every interactive element.
- [ ] Using a contrast-checker on `--ink-muted` and `--ink-faint` text against `--paper`/`--paper-card` shows ≥ 4.5:1 for body-size text and ≥ 3:1 for large/icon elements.
- [ ] `/dashboard` stat cards and section headings have clear visual hierarchy (one `h1`, properly nested `h2`s) and increased spacing — verified by loading the dashboard as the seeded demo user.
- [ ] `/profile` activity table and form sections have visible labels and improved row spacing — verified by loading `/profile` and applying a date filter.
- [ ] `/expenses` table headers use `scope="col"`, the amount column is right-aligned, and rows have consistent padding — verified by loading `/expenses` with the seeded demo data.
- [ ] Sign-out button and any icon-only controls have an accessible name (verified via browser dev tools accessibility tree).
- [ ] All existing functional flows (login, add/edit/delete expense, profile update, dashboard period switch) continue to work unchanged — verified by manual smoke test.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings (no Python files should need changes, but run to confirm).
