# Spec: Profile Page Design

## Overview

Steps 1–3 established the data layer, registration, and secure session management. Step 4 promotes the `/profile` stub into a fully functional, server-rendered page where authenticated users can view their account details and update their display name and preferred currency. The page surfaces the data already stored on the `User` model (`name`, `display_name`, `email`, `default_currency`, `created_at`, `last_login_at`) and accepts a `POST` to update the two user-editable fields. A second, separate `POST` form handles password changes (current password required, plus confirmation). The profile route also becomes the first interior page that can serve as a design reference for the dashboard and expense pages that follow.

## Depends on

- Step 1 (Database Setup) — `users` table, `db.session`, Flask-Login integration.
- Step 2 (Registration) — `User` model with `display_name`, `default_currency`; Pydantic schemas pattern; `ALLOWED_CURRENCIES` constant.
- Step 3 (Login and Logout) — `last_login_at` column; `@login_required` decorator; CSRF token pattern.

## Routes

- `GET /profile` — renders the profile page with the current user's data — **logged-in**
- `POST /profile` — updates `display_name` and/or `default_currency` — **logged-in**
- `POST /profile/change-password` — validates current password and sets a new one — **logged-in**

## Database changes

No new tables, columns, or constraints. All required columns (`name`, `display_name`, `email`, `default_currency`, `created_at`, `last_login_at`) already exist on `users`.

## Templates

- **Create:** `templates/profile.html`
  - Extends `base.html`.
  - Page header: user avatar placeholder (initials in a styled circle using `display_name`), `display_name` as headline, `email` as subtext.
  - **Read-only info card:** displays full `name`, `email`, `member_since` (formatted `created_at`), and `last_login_at` (formatted, or "Never" if null).
  - **Edit profile form** (`POST /profile`, CSRF token):
    - Display name field (pre-filled, max 60 chars).
    - Default currency `<select>` (pre-selected, iterates `ALLOWED_CURRENCIES`).
    - Submit button: "Save changes".
  - **Change password form** (`POST /profile/change-password`, CSRF token):
    - Current password field.
    - New password field.
    - Confirm new password field (client-side match check via vanilla JS).
    - Submit button: "Update password".
  - Flash messages are inherited from `base.html`.

## Files to change

- `app.py`
  - Inside `_register_main_routes()`, replace the `/profile` stub with a full implementation:
    - `GET /profile` — pass `user=current_user` and `currencies=ALLOWED_CURRENCIES` to `render_template("profile.html", ...)`.
    - `POST /profile` — read `display_name` and `default_currency` from the form, validate with `ProfileUpdateSchema`, call `update_profile(current_user, data)` service function, `flash(...)`, redirect to `GET /profile`.
    - `POST /profile/change-password` — read `current_password`, `new_password`, `confirm_password` from form, validate with `ChangePasswordSchema`, call `change_password(current_user, data)` service function, `flash(...)`, redirect to `GET /profile`.
  - Import `ProfileUpdateSchema`, `ChangePasswordSchema` from `database/schemas.py`.
  - Import `update_profile`, `change_password` from `database/services.py`.

- `database/schemas.py`
  - Add `ProfileUpdateSchema` — fields: `display_name: str`, `default_currency: str`. Reuse the existing `validate_display_name` and `validate_default_currency` logic verbatim.
  - Add `ChangePasswordSchema` — fields: `current_password: str`, `new_password: str`, `confirm_password: str`. Validators: `new_password` must be 8–72 chars; `confirm_password` must equal `new_password` (use a `model_validator` on `"after"` mode).

- `static/css/style.css`
  - Append profile-specific CSS using only existing `var(--…)` tokens — no new hex literals.
  - Sections to add: `.profile-header` (avatar circle, headline, subtext), `.profile-card` (info card and form card layout), `.avatar-circle` (initials badge).
  - Reuse existing `.form-group`, `.form-input`, `.form-select`, `.btn-primary`, `.btn-outline` classes where already defined.

## Files to create

- `database/services.py` — new module. Contains:
  - `update_profile(user: User, data: ProfileUpdateSchema) -> None` — sets `user.display_name` and `user.default_currency`, calls `db.session.commit()`. Raises `SQLAlchemyError` on failure (caught in the route).
  - `change_password(user: User, data: ChangePasswordSchema) -> bool` — verifies `user.check_password(data.current_password)`; if false, returns `False` without touching the DB. If true, calls `user.set_password(data.new_password)`, `db.session.commit()`, returns `True`. Raises `SQLAlchemyError` on DB failure.

- `templates/profile.html` — see Templates section above.

## New dependencies

No new dependencies.

## Rules for implementation

- **Parameterised queries only** — no raw f-string SQL. Use `db.session.get(...)` / `db.session.execute(select(...))` inside service functions.
- **Passwords hashed with werkzeug** — use `user.set_password(...)` and `user.check_password(...)`. Never store or log plain-text passwords.
- **Use CSS variables — never hardcode hex values.** All colors, radii, and font families must reference existing `var(--…)` tokens.
- **All templates extend `base.html`** — `profile.html` must begin with `{% extends "base.html" %}`.
- **Always use `url_for()`** — never hardcode `/profile` or `/profile/change-password` in templates or redirects.
- **CSRF on every POST form** — both the edit-profile and change-password forms must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- **Post-Redirect-Get** — both POST handlers must end with `redirect(url_for("profile"))` on success to prevent double-submit on browser refresh.
- **Service layer for DB logic** — no non-trivial DB writes inside the route function body. Route calls service function; service function owns the session commit.
- **Current password verification before any change** — `change_password` must verify the existing password before calling `set_password`. Return `False` and flash a generic error; do not reveal whether the account exists.
- **`display_name` and `default_currency` are the only user-editable fields** — `name` and `email` are read-only on this page. Do not add fields for them.
- **No promoting other stub routes** — `/dashboard`, `/expenses/*` remain plain-string stubs.

## Definition of done

- [ ] `GET /profile` for a logged-out user redirects to `/login` (Flask-Login `@login_required`).
- [ ] `GET /profile` for a logged-in user renders `profile.html` showing correct `display_name`, `email`, full `name`, formatted `created_at`, and `last_login_at` (or "Never" when null).
- [ ] The default currency `<select>` on the edit form has the user's current currency pre-selected.
- [ ] Submitting the edit-profile form with a valid display name and currency updates both fields in the DB, flashes a success message, and redirects to `GET /profile` with the new values visible.
- [ ] Submitting the edit-profile form with an invalid display name (e.g., 1 character) flashes a validation error and does not update the DB.
- [ ] Submitting the change-password form with the correct current password, a valid new password, and matching confirmation updates the password hash, flashes success, and redirects to `GET /profile`.
- [ ] After a successful password change, signing out and signing back in with the new password succeeds.
- [ ] Submitting the change-password form with an **incorrect** current password flashes a generic error and does not modify the password hash.
- [ ] Submitting the change-password form where new password and confirmation do not match flashes a validation error and does not modify the DB.
- [ ] Both POST forms return HTTP 400 (CSRF failure) when the CSRF token is missing or invalid.
- [ ] The `.profile-name` heading and avatar initials update on the next page load after a display name edit (the navbar shows `name`, which is read-only on this page and does not change).
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in → view profile → change display name → verify new name appears in navbar → change currency → verify select shows new value → change password → sign out → sign in with new password → success.
