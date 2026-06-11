# Spec: Delete Expense (Soft Delete with Undo)

## Overview

`/expenses` already supports a CSRF-protected, owner-checked delete via `POST /expenses/<id>/delete`, guarded by an Alpine.js "Delete? Yes/No" confirmation. However, deletion is currently permanent and irreversible the instant "Yes" is clicked — a single misclick destroys data with no recovery path. Step 9 converts expense deletion from a hard delete into a **soft delete**: the row is flagged with a `deleted_at` timestamp instead of being removed from the database, and is immediately hidden from every list, total, and chart. A flash banner on redirect tells the user the expense was deleted and offers an **Undo** button that restores the record if clicked within a short grace window (8 seconds). After the window elapses, the record stays soft-deleted permanently (no purge job in this step) and can no longer be restored via the UI.

## Depends on

- **Step 1 (Database Setup)** — `Expense` model in `database/db.py`.
- **Step 5 (Backend for Dashboard)** — `database/services.py`, `_where_user_and_period`, dashboard aggregation functions.
- **Step 6 (Date Filter)** — `profile_activity`, `list_expenses_in_range`.
- **Step 7 (Add Advanced Expense Feature)** — `POST /expenses/<id>/delete`, `destroy_expense`, `get_expense_for_user`, `list_user_expenses`.
- **Step 8 (Edit Expense)** — Alpine.js confirmation pattern on the delete button in `partials/_expense_row.html`, `x-cloak` styling.

## Routes

- `POST /expenses/<int:id>/delete` — **modified** (existing route). Now performs a soft delete (sets `deleted_at`) instead of removing the row, then flashes a message containing an inline "Undo" form before redirecting to `/expenses`. Access — **logged-in**.
- `POST /expenses/<int:id>/restore` — **new**. Restores a soft-deleted expense owned by the current user if it was deleted within the last `UNDO_WINDOW_SECONDS` (8s); otherwise flashes a "can no longer be restored" message. Redirects to `/expenses`. Access — **logged-in**.

## Database changes

- Add `deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)` to the `Expense` model in `database/db.py` (after `updated_at`).
- New Alembic migration generated via `flask --app app db migrate -m "add deleted_at to expenses"` and applied with `flask --app app db upgrade`. No data backfill needed (existing rows get `NULL`, meaning "not deleted").

## Templates

- **Modify:** `templates/base.html` — no structural change to the flash block required (Jinja does not escape `Markup` instances), but verify the `.flash` div can host an inline form without breaking layout.
- **Modify:** `static/css/style.css` — add styles for `.flash-undo-form`, `.flash-undo-btn`, and a `.flash-countdown` progress bar, all using existing `var(--…)` tokens (e.g. `var(--accent)`, `var(--radius-sm)`).
- **Modify:** `static/js/main.js` — add `initFlashUndo()`: for each `.flash-undo-form[data-undo-seconds]`, start a CSS-driven countdown bar and remove/disable the form once the window elapses (purely visual; the server independently enforces the same window).

No new template files.

## Files to change

- `database/db.py`
  - Add `deleted_at` column to `Expense` (see Database changes).

- `database/services.py`
  - Add module constant `UNDO_WINDOW_SECONDS = 8`.
  - `_where_user_and_period(uid, lo, hi)` — append `Expense.deleted_at.is_(None)` to the returned clauses. This single change excludes soft-deleted rows from dashboard totals, category breakdown, daily series, recent expenses, and profile activity.
  - `list_user_expenses(user)` — add `.where(Expense.user_id == user.id, Expense.deleted_at.is_(None))`.
  - `get_expense_for_user(expense_id, user_id)` — add `Expense.deleted_at.is_(None)` to the filter, so edit/delete on an already soft-deleted expense behaves as "not found".
  - `destroy_expense(expense_id, user_id) -> bool` — replace `db.session.delete(expense)` with `expense.deleted_at = datetime.now(timezone.utc)`, then `db.session.commit()`. Still returns `True`/`False` based on `get_expense_for_user` lookup.
  - Add `restore_expense(expense_id, user_id) -> bool`:
    - Query `Expense` where `id == expense_id`, `user_id == user_id`, `deleted_at.is_not(None)`.
    - If not found, return `False`.
    - If `datetime.now(timezone.utc) - expense.deleted_at > timedelta(seconds=UNDO_WINDOW_SECONDS)`, return `False` (too late).
    - Otherwise set `expense.deleted_at = None`, `db.session.commit()`, return `True`.
  - Import `timezone` and `timedelta` if not already imported (`timedelta` is already imported; add `timezone`).

- `app.py`
  - Import `restore_expense` and `UNDO_WINDOW_SECONDS` from `database.services`.
  - Import `Markup` from `markupsafe` and `generate_csrf` from `flask_wtf.csrf`.
  - `delete_expense(id)` — on success (`destroy_expense` returns `True`), build the flash message with `Markup`:
    ```python
    restore_url = url_for("restore_expense", id=id)
    flash(
        Markup(
            "Expense deleted. "
            f'<form method="POST" action="{restore_url}" '
            f'class="flash-undo-form" data-undo-seconds="{UNDO_WINDOW_SECONDS}">'
            f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'
            '<button type="submit" class="flash-undo-btn">Undo</button>'
            "</form>"
        ),
        "info",
    )
    ```
    Keep the existing `abort(404)` and `SQLAlchemyError` handling unchanged.
  - Add `restore_expense_route(id)` for `POST /expenses/<int:id>/restore`:
    - Call `restore_expense(id, current_user.id)`.
    - If `True`, `flash("Expense restored.", "success")`.
    - If `False`, `flash("This expense can no longer be restored.", "error")`.
    - Wrap in `try/except SQLAlchemyError` per project convention (rollback, log, flash generic DB error).
    - Redirect to `url_for("expenses_list")`.

## Files to create

- New Alembic migration file under `migrations/versions/` (auto-generated by `flask db migrate`, filename determined by Alembic).

## New dependencies

No new dependencies. `markupsafe.Markup` and `flask_wtf.csrf.generate_csrf` are already transitive dependencies of Flask / Flask-WTF, already installed.

## Rules for implementation

- **Parameterised queries only** — all new/modified queries use SQLAlchemy 2.0 `select(...).where(...)`. Never build SQL with f-strings.
- **Soft delete, never hard delete** — `destroy_expense` must no longer call `db.session.delete()`. Existing `cascade="all, delete-orphan"` on `User.expenses` is unrelated and untouched (only relevant if a user account itself is deleted).
- **Exclude soft-deleted rows everywhere** — every read path (list, edit, dashboard aggregates, profile activity) must filter `Expense.deleted_at.is_(None)`. Centralise this in `_where_user_and_period`, `list_user_expenses`, and `get_expense_for_user` as described above — do not duplicate the filter ad hoc in route bodies.
- **`Markup` usage is restricted** — only construct `Markup(...)` from strings built entirely from server-controlled values (`url_for(...)`, `generate_csrf()`, the integer `UNDO_WINDOW_SECONDS`, and literal HTML). Never interpolate user-supplied input (titles, notes, etc.) into a `Markup(...)` call — that would be an XSS vector.
- **CSRF on restore** — `POST /expenses/<id>/restore` must include and validate `csrf_token`, exactly like delete.
- **No information leakage** — if `restore_expense` returns `False` (window expired, already restored, or not owned by the user), respond identically regardless of the underlying reason: `flash("This expense can no longer be restored.", "error")` and redirect. Do not `abort(404)` from the restore route — a soft-deleted expense outside the undo window is an expected state, not an error.
- **Use CSS variables** — `.flash-undo-form`, `.flash-undo-btn`, `.flash-countdown` must reference existing `var(--…)` tokens; no hardcoded hex values.
- **Keep the undo window single-sourced** — `UNDO_WINDOW_SECONDS` is defined once in `database/services.py` and imported into `app.py` for the `data-undo-seconds` attribute, so the client-side countdown and server-side enforcement never drift apart.
- **No new JS files / frameworks** — `initFlashUndo()` goes in the existing `static/js/main.js`, called from the existing `DOMContentLoaded` listener alongside `initAOS()`, `initLucide()`, `initMockBars()`.

## Definition of done

- [ ] `flask --app app db upgrade` applies cleanly; the `expenses` table has a nullable `deleted_at TIMESTAMPTZ` column defaulting to `NULL`.
- [ ] Deleting an expense from `/expenses` redirects back to `/expenses` and the expense no longer appears in the table.
- [ ] The flash banner after delete reads "Expense deleted." and contains a working "Undo" button.
- [ ] Clicking "Undo" within 8 seconds restores the expense: it reappears in `/expenses` with all original values (title, amount, category, date, notes) intact, and a "Expense restored." success flash is shown.
- [ ] Immediately after deleting an expense, the Dashboard's total spent, transaction count, average, category breakdown, daily spend chart, and "Recent expenses" no longer include it.
- [ ] Immediately after deleting an expense, the Profile page's activity total, count, and table no longer include it.
- [ ] After restoring an expense, the Dashboard and Profile figures return to their pre-delete values.
- [ ] `GET /expenses/<id>/edit` for a soft-deleted expense returns HTTP 404.
- [ ] `POST /expenses/<id>/delete` for an already soft-deleted expense returns HTTP 404 (cannot double-delete).
- [ ] `POST /expenses/<id>/restore` for an expense whose `deleted_at` is more than 8 seconds in the past flashes "This expense can no longer be restored." and the expense remains hidden everywhere.
- [ ] `POST /expenses/<id>/restore` for an expense belonging to another user has no effect (no restore, no data exposed, generic flash message).
- [ ] `POST /expenses/<id>/restore` without a valid CSRF token returns HTTP 400.
- [ ] The "Undo" button's countdown bar visually depletes over 8 seconds and the button becomes disabled/hidden client-side once expired, without a page reload.
- [ ] No hardcoded hex colours in any new or modified CSS; all colours reference `var(--…)` tokens.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in → `/expenses` → delete an expense → confirm via Alpine "Yes" → flash shows "Expense deleted." with Undo → click Undo immediately → expense reappears, dashboard totals match pre-delete values → delete the same expense again → wait 10+ seconds without clicking Undo → reload `/expenses` → expense remains gone → dashboard totals reflect the deletion.
