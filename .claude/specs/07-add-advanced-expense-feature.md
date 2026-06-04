# Spec: Add Advanced Expense Feature

## Overview

Steps 1–6 delivered the data layer, auth, dashboard with period filtering, and a profile page with custom date-range activity. Step 7 promotes all three expense stub routes to full implementations and adds a dedicated `/expenses` list page, giving users complete CRUD control over their spending records. "Advanced" here means the expense form goes beyond a bare minimum: it supports all eight categories, free-text notes, a user-chosen date (defaulting to today), and inline Pydantic validation with helpful error messages echoed back on the same form. The edit flow reloads the existing record into the same form component; the delete flow is a CSRF-protected POST that guards against accidental or forged deletions. All DB logic lives in `database/services.py`, all validation in `database/schemas.py`, and routes stay thin. The expenses list page doubles as a quick audit trail — newest expenses first, with category badge, formatted amount, and direct Edit/Delete links.

## Depends on

- **Step 1 (Database Setup)** — `expenses` table with `user_id`, `title`, `amount` (`Numeric(10, 2)`), `category`, `date`, `notes`; the `CATEGORIES` tuple in `database/db.py`; `Expense` model with `to_dict()`.
- **Step 2 (Registration)** — `User.default_currency` used as the display currency in the form and list.
- **Step 3 (Login and Logout)** — `@login_required`, `current_user`, CSRF tokens in templates.
- **Step 5 (Backend for Dashboard)** — `database/services.py` module and the route → schema → service pattern reused here.
- **Step 6 (Date Filter)** — `DateRangeSchema`, `profile_activity` service, and CSS component conventions already established (`.profile-card`, `.form-group`, `.form-input`, `.btn-submit`, `var(--…)` tokens).

## Routes

- `GET /expenses` — expense list page, newest first, for the signed-in user. Access — **logged-in**.
- `GET /expenses/add` — render the blank add-expense form. Access — **logged-in**.
- `POST /expenses/add` — validate and persist a new expense; redirect to `/expenses` on success, re-render form with errors on failure. Access — **logged-in**.
- `GET /expenses/<int:id>/edit` — load the expense (owner-checked) into the edit form. Access — **logged-in**.
- `POST /expenses/<int:id>/edit` — validate and update the expense; redirect to `/expenses` on success. Access — **logged-in**.
- `POST /expenses/<int:id>/delete` — CSRF-protected delete of a single expense (owner-checked); redirect to `/expenses`. Access — **logged-in**.

**The existing stub `GET /expenses/<int:id>/delete` is replaced by `POST /expenses/<int:id>/delete`.** The old GET stub is removed; the delete action must always be a form POST to satisfy CSRF protection.

## Database changes

No database changes. All required columns (`title`, `amount`, `category`, `date`, `notes`, `user_id`) already exist in the `expenses` table with correct types, constraints, and indexes. Verified against `database/db.py` lines 95–136. No migration needed.

## Templates

- **Create:** `templates/expenses.html`
  - `{% extends "base.html" %}`.
  - Page heading "My Expenses" with a right-aligned "Add expense" button linking to `{{ url_for('add_expense') }}`.
  - A `<table>` with columns `Date`, `Description`, `Category`, `Amount`, `Actions`.
  - Each row: `date` formatted `%d %b %Y`; `title`; category badge (reuse dashboard's `.category-badge` or equivalent); `amount` formatted `"{:,.2f}".format(amount) + " " + currency`; Edit link → `url_for('edit_expense', id=expense.id)`, Delete button → a tiny `<form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}">` with a hidden CSRF input and a `<button type="submit">` styled as a danger link.
  - Empty state: "You have no expenses yet. Add your first one."
  - No pagination in this step — render all expenses.

- **Create:** `templates/expense_form.html`
  - `{% extends "base.html" %}`.
  - A single `<form method="POST">` with CSRF token (`{{ csrf_token() }}`).
  - Fields (each in `.form-group` with `<label>`):
    - `title` — `<input type="text" name="title" maxlength="200">`, pre-filled from `form_data.title`.
    - `amount` — `<input type="number" name="amount" min="0.01" step="0.01">`, pre-filled from `form_data.amount`.
    - `category` — `<select name="category">` iterating `categories` context variable; pre-selected from `form_data.category`.
    - `date` — `<input type="date" name="date">`, pre-filled from `form_data.date` (ISO format); defaults to today if blank.
    - `notes` — `<textarea name="notes" maxlength="1000">`, pre-filled from `form_data.notes`.
  - Submit button (`.btn-submit`) with label from `submit_label` context variable ("Add Expense" or "Save Changes").
  - A "Cancel" link → `{{ url_for('expenses_list') }}`.
  - Page `<h1>` driven by `page_title` context variable ("Add Expense" or "Edit Expense").
  - Flash messages rendered the same way as other pages (reuse the flash block from `base.html`).

- **Modify:** None (other templates remain unchanged).

## Files to change

- `app.py`
  - Remove the three stub route functions (`add_expense`, `edit_expense`, `delete_expense`) and replace with six new handlers inside `_register_main_routes()`:
    1. `GET /expenses` → `expenses_list()`: call `list_user_expenses(current_user)`, render `expenses.html` with `expenses=`, `currency=current_user.default_currency`.
    2. `GET /expenses/add` → `add_expense_form()`: render `expense_form.html` with blank `form_data`, `categories=CATEGORIES`, `page_title="Add Expense"`, `submit_label="Add Expense"`.
    3. `POST /expenses/add` → `add_expense_submit()`: parse form, validate with `ExpenseSchema`, call `create_expense(current_user, data)`, redirect to `expenses_list` on success or re-render form with errors.
    4. `GET /expenses/<int:id>/edit` → `edit_expense_form(id)`: call `get_expense_for_user(id, current_user.id)` (404 if not found/wrong owner), render `expense_form.html` pre-filled.
    5. `POST /expenses/<int:id>/edit` → `edit_expense_submit(id)`: validate, call `update_expense(expense, data)`, redirect.
    6. `POST /expenses/<int:id>/delete` → `delete_expense(id)`: call `destroy_expense(id, current_user.id)`, flash confirmation, redirect to `expenses_list`.
  - Add imports: `CATEGORIES` from `database.db`; `ExpenseSchema` from `database.schemas`; `create_expense`, `update_expense`, `destroy_expense`, `list_user_expenses`, `get_expense_for_user` from `database.services`.
  - Keep the existing `GET /expenses/add` route name `add_expense` — rename the new GET handler to `add_expense` and the POST handler to `add_expense_post` to preserve any existing `url_for('add_expense')` references in other templates (or update those references — verify with grep before deciding).

- `database/schemas.py`
  - Append `ExpenseSchema(BaseModel)`:
    ```python
    class ExpenseSchema(BaseModel):
        title: str
        amount: Decimal
        category: str
        date: date
        notes: str | None = None
    ```
    With field validators:
    - `title`: strip, 1–200 characters.
    - `amount`: must be > 0 and ≤ 9_999_999.99; coerce to `Decimal` quantised to `Decimal("0.01")`.
    - `category`: must be in `CATEGORIES` (imported from `database.db`).
    - `date`: already a `date` after Pydantic parses `YYYY-MM-DD` from a string input; no further validation needed.
    - `notes`: strip; if empty string, coerce to `None`; max 1000 characters.
  - Import `Decimal` from `decimal` and `CATEGORIES` from `database.db` at the top of the file.

- `database/services.py`
  - Append five service functions:
    1. `list_user_expenses(user: User) -> list[Expense]` — `select(Expense).where(Expense.user_id == user.id).order_by(Expense.date.desc(), Expense.id.desc())`.
    2. `get_expense_for_user(expense_id: int, user_id: int) -> Expense | None` — `select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id)`, returns `scalar_one_or_none()`.
    3. `create_expense(user: User, data: ExpenseSchema) -> Expense` — construct `Expense(user_id=user.id, title=data.title, amount=data.amount, category=data.category, date=data.date, notes=data.notes)`, `db.session.add`, `db.session.commit`, return the new record.
    4. `update_expense(expense: Expense, data: ExpenseSchema) -> Expense` — mutate fields, `db.session.commit`, return the record.
    5. `destroy_expense(expense_id: int, user_id: int) -> bool` — fetch by `(expense_id, user_id)`, delete if found, commit, return `True`; return `False` if not found (wrong owner or already gone).

## Files to create

- `templates/expenses.html` — see *Templates* section.
- `templates/expense_form.html` — see *Templates* section.

## New dependencies

No new dependencies. `decimal.Decimal`, `datetime.date`, and all required SQLAlchemy/Flask constructs are already in use.

## Rules for implementation

- **Parameterised queries only** — all five service functions use SQLAlchemy 2.0 `select(...)` with `.where(Expense.user_id == user_id, ...)`. Never build SQL with f-strings.
- **Passwords hashed with werkzeug** — no auth code is touched in this step; the pattern is unchanged.
- **Use CSS variables — never hardcode hex values** — any new CSS in `static/css/style.css` for the expenses list table or the form must reference existing `var(--…)` tokens only.
- **All templates extend `base.html`** — both `expenses.html` and `expense_form.html` must start with `{% extends "base.html" %}`.
- **Always use `url_for()`** — all internal links and form `action` attributes use `{{ url_for('...') }}`. Never hardcode `/expenses`.
- **Owner isolation** — every read, update, and delete operation checks `Expense.user_id == current_user.id`. A user must never be able to view, edit, or delete another user's expense. The `get_expense_for_user` helper encapsulates this check; routes must use it for edit and delete.
- **404 on wrong owner or missing record** — if `get_expense_for_user` returns `None` for edit or delete, call `flask.abort(404)`. Do not reveal whether the record exists but belongs to another user.
- **CSRF on all state-changing requests** — `POST /expenses/add`, `POST /expenses/<id>/edit`, and `POST /expenses/<id>/delete` all require a valid CSRF token (Flask-WTF enforces this automatically). The delete button is a `<form method="POST">` with `{{ csrf_token() }}` — never a plain `<a href>` or GET request.
- **`Decimal` discipline** — `amount` is stored and returned as `Decimal`. The template formats via `"{:,.2f}".format(expense.amount)`. Never cast to `float`.
- **Re-render on validation error** — POST handlers for add and edit must re-render the form with the validated/echoed field values (not a redirect) so the user does not lose their input. Pass `form_data` as a simple object or dict with the submitted field values.
- **Service layer owns DB logic** — route bodies contain only: parse form, validate schema, call service, handle `SQLAlchemyError`, redirect or render. No `select(...)` or `db.session.*` in route functions.
- **No promoting remaining stubs** — `edit_expense` and `delete_expense` stubs ARE promoted in this step (they are in scope). No other stubs are touched.
- **`amount` input precision** — `<input type="number" step="0.01">` on the form. The Pydantic schema parses the raw string to `Decimal` (not `float`) via `Decimal(v.strip())` inside a field validator, then quantises to two decimal places.

## Definition of done

- [ ] `GET /expenses` as a logged-out user redirects to `/login`.
- [ ] `GET /expenses` as `demo@spendly.dev` renders HTTP 200 and lists all 8 seed expenses, newest first, each row showing date, title, category badge, and formatted amount with the user's `default_currency`.
- [ ] `GET /expenses/add` renders an empty form at HTTP 200 with all required fields and the CSRF token present.
- [ ] Submitting `POST /expenses/add` with valid data (`title="Lunch"`, `amount=250.50`, `category="Food"`, `date=today`) creates a new row in `expenses`, redirects to `/expenses` (HTTP 302 → 200), and the new expense appears at the top of the list.
- [ ] Submitting `POST /expenses/add` with `amount=-5` or `amount=0` returns HTTP 200 with the form re-rendered and an error message; no row is inserted.
- [ ] Submitting `POST /expenses/add` with an empty `title` returns HTTP 200 with the form re-rendered and an error; the user's other field values are preserved in the form inputs.
- [ ] `GET /expenses/<id>/edit` for an expense owned by the signed-in user renders the form pre-filled with the expense's existing values at HTTP 200.
- [ ] `GET /expenses/<id>/edit` for an expense belonging to a different user returns HTTP 404.
- [ ] `POST /expenses/<id>/edit` with valid data updates the record, redirects to `/expenses`, and the updated values appear in the list.
- [ ] `POST /expenses/<id>/delete` for an owned expense deletes the row, redirects to `/expenses` with a flash confirmation, and the expense no longer appears in the list.
- [ ] `POST /expenses/<id>/delete` for another user's expense returns HTTP 404 and does not delete any row.
- [ ] A GET request to `/expenses/<id>/delete` (accidental direct URL hit) is rejected — the route does not exist; Flask returns 405.
- [ ] Submitting any POST route without a valid CSRF token returns HTTP 400 (Flask-WTF default behaviour).
- [ ] A brand-new user with zero expenses sees "You have no expenses yet. Add your first one." on `/expenses`.
- [ ] User A's expenses never appear in User B's `/expenses` list or edit form, regardless of known IDs.
- [ ] Every amount in the list and form displays with exactly two decimal places and the currency code matches `default_currency`.
- [ ] The dashboard and profile activity totals still reflect the correct values after adding/editing/deleting an expense (regression check against Step 5 and Step 6).
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in → `/expenses` lists 8 seed rows → "Add expense" → fill form → submit → confirm new row → edit it → change amount → confirm update → delete it → confirm gone → log in as a second user → confirm expenses list is isolated → directly visit first user's expense edit URL as second user → confirm 404.
