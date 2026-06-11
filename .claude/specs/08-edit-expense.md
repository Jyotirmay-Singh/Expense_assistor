# Spec: Edit Expense Feature

## Overview

Step 7 delivered working CRUD for expenses, but the editing experience has two friction points that hurt daily usability. First, editing an expense requires navigating to a separate full page — even for a quick typo fix or category change. Second, deleting an expense fires immediately with no confirmation, making accidental deletions easy to trigger. Step 8 addresses both: it adds HTMX-powered inline editing so users can update any expense directly within the list table without leaving the page, and an Alpine.js confirmation modal that intercepts the delete form and asks the user to confirm before the POST is sent. No new routes are added — the existing `GET/POST /expenses/<int:id>/edit` routes gain an HTMX-partial response mode, and the delete button gains a client-side confirmation guard.

## Depends on

- **Step 7 (Add Advanced Expense Feature)** — `GET/POST /expenses/<int:id>/edit` routes, `expense_form.html`, `expenses.html`, `get_expense_for_user`, `update_expense`, `destroy_expense` services.
- **Step 1 (Database Setup)** — `Expense` model and `CATEGORIES` tuple.
- **Step 3 (Login and Logout)** — `@login_required`, CSRF tokens.

## Routes

No new routes. The two existing edit routes gain an HTMX partial mode.

- `GET /expenses/<int:id>/edit` — if `HX-Request` header is present, render `partials/_edit_expense_row.html` (the inline form row) instead of the full `expense_form.html`. Access — **logged-in**.
- `POST /expenses/<int:id>/edit` — if `HX-Request` header is present and the update succeeds, render `partials/_expense_row.html` (the updated read-only row) for HTMX to swap in. On validation failure, render `partials/_edit_expense_row.html` with flash errors. Access — **logged-in**.

## Database changes

No database changes.

## Templates

- **Create:** `templates/partials/_expense_row.html`
  - A single `<tr>` representing one expense in read-only mode.
  - Columns: formatted date (`%d %b %Y`), title, category badge, amount with currency code, actions (Edit + Delete).
  - The Edit cell uses `hx-get="{{ url_for('edit_expense', id=expense.id) }}"` with `hx-target="closest tr"` and `hx-swap="outerHTML"` — no `<a href>` navigation.
  - The Delete cell wraps the existing CSRF-protected `<form method="POST">` inside an Alpine.js confirmation guard (see below).
  - Does **not** `{% extends %}` — it is an includable fragment.

- **Create:** `templates/partials/_edit_expense_row.html`
  - A `<tr>` containing an inline edit form.
  - Form attributes: `hx-post="{{ url_for('edit_expense_post', id=expense.id) }}"`, `hx-target="closest tr"`, `hx-swap="outerHTML"`.
  - Fields (compact, inline): `title` (`<input type="text">`), `amount` (`<input type="number" step="0.01" min="0.01">`), `category` (`<select>` iterating `categories`), `date` (`<input type="date">`).
  - A hidden `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
  - A "Save" `<button type="submit">` and a "Cancel" button that re-fetches the read-only row via `hx-get="{{ url_for('edit_expense', id=expense.id) }}?cancel=1"` with `hx-target="closest tr"` and `hx-swap="outerHTML"`.
  - Flash error messages rendered inline above the form inputs (since the full base layout is not rendered).
  - Does **not** `{% extends %}` — it is an includable fragment.

- **Modify:** `templates/expenses.html`
  - Replace each hardcoded table row with `{% include 'partials/_expense_row.html' %}`, passing `expense` as context.
  - Alternatively, inline the row markup directly (matching `_expense_row.html`) if Jinja2 include with scoped variable proves awkward — either way the row HTML must be identical to the partial.
  - Add Alpine.js CDN link if `base.html` does not already include it (check before adding).

- **Modify:** `templates/base.html`
  - Add Alpine.js `<script defer src="...">` CDN tag if not already present. Place after the existing HTMX script tag so load order is predictable.

## Alpine.js delete confirmation pattern

Wrap each delete form in:

```html
<span x-data="{ open: false }">
  <button type="button" class="btn-danger-link" @click="open = true">Delete</button>
  <span x-show="open" x-cloak>
    <span class="confirm-text">Delete this expense?</span>
    <form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}" style="display:inline">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn-danger-link">Yes</button>
    </form>
    <button type="button" class="btn-cancel-link" @click="open = false">No</button>
  </span>
</span>
```

The original `<form>` with CSRF token must remain inside the confirmation span — do not remove it.

## Cancel inline edit — GET route variant

Add a `cancel` query-param branch to `edit_expense` (GET): if `request.args.get("cancel")` is truthy **and** `HX-Request` is set, render `partials/_expense_row.html` directly (no redirect). This avoids a round-trip through the edit-form logic when the user clicks Cancel.

## Files to change

- `app.py` — update `edit_expense` (GET) and `edit_expense_post` (POST) to detect `request.headers.get("HX-Request")` and return partial templates when present. Add cancel-mode branch to `edit_expense` GET.
- `templates/expenses.html` — update each table row to match `_expense_row.html` markup; Edit button becomes HTMX trigger; Delete button wrapped in Alpine.js confirmation.
- `templates/base.html` — add Alpine.js CDN script tag if missing.

## Files to create

- `templates/partials/_expense_row.html`
- `templates/partials/_edit_expense_row.html`

## New dependencies

No new pip packages. Alpine.js is loaded via CDN `<script>` tag only.

## Rules for implementation

- **Parameterised queries only** — no new queries are introduced; all DB work goes through the existing `get_expense_for_user` and `update_expense` services.
- **Passwords hashed with werkzeug** — no auth code touched in this step.
- **Use CSS variables — never hardcode hex values** — any new inline-form CSS must use `var(--…)` tokens.
- **Partials do NOT extend base.html** — `_expense_row.html` and `_edit_expense_row.html` are fragments; they must not include `{% extends %}`.
- **HTMX partial detection** — `request.headers.get("HX-Request")` returns `"true"` for HTMX requests. Use this in both GET and POST edit handlers to choose between full-page and partial responses.
- **CSRF on inline edit** — the `_edit_expense_row.html` form must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Flask-WTF validates this the same way as a full-page form.
- **CSRF on delete** — the Alpine.js confirmation wrapper must keep the hidden CSRF input inside the `<form>`. Never move the delete action to a GET request or `<a href>`.
- **Progressive enhancement** — direct navigation to `GET /expenses/<id>/edit` (non-HTMX) must still render the full-page `expense_form.html`. `POST /expenses/<id>/edit` from the full-page form must still redirect to `/expenses` on success.
- **No flash messages in HTMX partials for success** — on a successful inline edit, returning the updated `_expense_row.html` is sufficient feedback. Flash messages are only rendered in full-page responses; do not attempt to push flashes through HTMX swaps.
- **Validation errors in inline edit** — on a failed `POST` with `HX-Request`, re-render `_edit_expense_row.html` with the submitted `form_data` and render error messages inline (iterate `get_flashed_messages` or pass error strings directly from `extract_messages`).
- **No new JS files** — all interactivity via HTMX attributes and Alpine.js directives on HTML elements only.
- **`x-cloak` on confirmation spans** — add `[x-cloak] { display: none !important; }` to `static/css/style.css` to prevent Alpine.js confirmation spans from flashing visible before Alpine initialises.

## Definition of done

- [ ] Clicking the Edit button on an expense row replaces it in-place with an inline edit form (no full-page navigation).
- [ ] The inline form is pre-filled with the expense's existing `title`, `amount`, `category`, and `date`.
- [ ] Saving a valid inline edit replaces the row with the updated read-only row without a full-page reload; the new values are visible immediately.
- [ ] Saving an inline edit with an invalid amount (e.g., `0` or `-5`) shows an error inline and keeps the edit form open; no row is mutated.
- [ ] Saving an inline edit with an empty title shows an inline error and keeps the form open.
- [ ] Clicking Cancel on the inline edit restores the original read-only row with no data change.
- [ ] The inline edit form includes a CSRF token and the POST is accepted by Flask-WTF.
- [ ] Clicking Delete on any expense row shows the Alpine.js confirmation dialog ("Delete this expense? Yes / No").
- [ ] Clicking "No" in the confirmation dismisses it without submitting the form or deleting the expense.
- [ ] Clicking "Yes" fires the CSRF-protected POST, deletes the expense, and redirects to `/expenses`; the expense no longer appears.
- [ ] Direct navigation to `GET /expenses/<id>/edit` (full-page, no HTMX header) still renders `expense_form.html` at HTTP 200.
- [ ] `POST /expenses/<id>/edit` submitted via the full-page form still redirects to `/expenses` on success (non-HTMX path unchanged).
- [ ] `GET /expenses/<id>/edit` for an expense owned by another user returns HTTP 404 (owner isolation unchanged).
- [ ] Alpine.js confirmation spans do not flash visible on page load (`x-cloak` applied correctly).
- [ ] No hardcoded hex values in any new or modified CSS; all colours reference `var(--…)` tokens.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in → expenses list visible → click Edit on a row → inline form appears pre-filled → change title → Save → row updates in place → click Edit again → click Cancel → original row restored → click Delete → confirmation appears → click No → expense still in list → click Delete → click Yes → expense removed.
