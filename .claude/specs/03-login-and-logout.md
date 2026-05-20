# Spec: Login and Logout

## Overview

Step 1 set up the database, and Step 2 polished registration. The `/login` and `/logout` routes already function end-to-end, but the current implementation has three gaps that should be closed before later steps (profile, dashboard, expenses CRUD) start relying on long-lived sessions: (a) no **Remember me** option — every session dies the moment the browser closes, (b) no `last_login_at` timestamp on the user row — the future profile view and any security-audit surface have no signal to display, and (c) `/logout` accepts plain `GET` requests via an `<a href>` link in the navbar, which is CSRF-unsafe for a state-changing action. This step closes those gaps by adding a Remember-me checkbox backed by hardened cookie settings, a nullable `last_login_at` column updated on every successful authentication, and a `POST`-only logout backed by a small inline form in the navbar. The result is a sturdier session lifecycle the rest of the app can trust.

## Depends on

Step 1 (Database Setup) — `users` table, Alembic migrations, `db.session`, `flask-login` integration, `werkzeug` password hashing.

Step 2 (Registration Enhancements) — the post-registration auto-login at the end of `POST /register` already calls `login_user(...)`; the same call site is updated here to also stamp `last_login_at`.

## Routes

No new routes. Two existing routes change behavior:

- `POST /login` — accept a new optional `remember_me` form field; on success, call `login_user(user, remember=data.remember_me)` and stamp `user.last_login_at = datetime.now(timezone.utc)`. Access remains **public**.
- `POST /logout` — restrict the methods list from the default `["GET"]` to `["POST"]` only. Access remains **logged-in** (`@login_required`). The navbar link becomes a tiny inline `<form>` carrying the CSRF token.

## Database changes

Modify the `users` table by adding one nullable column:

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `last_login_at` | `DateTime(timezone=True)` | `NULL` allowed | Updated on every successful `POST /login` and on the auto-login at the end of `POST /register`. `NULL` for users who have registered but never returned. |

Alembic migration adds the column as nullable — no backfill needed; existing rows (including the Step 1 demo user) start with `NULL` and acquire a value on their next sign-in. `downgrade()` drops the column.

No new tables. No new indexes. No new check constraints.

## Templates

- **Modify:** `templates/login.html`
  - Insert a **Remember me** checkbox row between the password `form-group` and the submit button. Markup mirrors the `.form-checkbox` block introduced in Step 2 (`<input type="checkbox" id="remember_me" name="remember_me" value="on" ...>` + label). Default unchecked.
  - On re-render after a failed login, restore the prior checkbox state from a `remember_me` template kwarg (`{% if remember_me %}checked{% endif %}`) alongside the existing preserved `email`.
  - Do **not** add a "Forgot password?" link — that flow is deferred to a later step.

- **Modify:** `templates/base.html`
  - Replace the authenticated-user `<a href="{{ url_for('logout') }}" class="nav-cta">…</a>` link inside the navbar with a small inline form:
    ```html
    <form method="POST" action="{{ url_for('logout') }}" class="nav-form">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" class="nav-cta nav-cta--button">
            <i data-lucide="log-out" class="icon-xs"></i>
            Sign out
        </button>
    </form>
    ```
  - Do not change the unauthenticated branch (Sign in / Get started links) or the rest of the navbar layout.

- **No new templates.**

## Files to change

- `database/db.py` — add `last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)` to the `User` model, immediately after `created_at`. `Optional` is already imported. Leave `seed_db()` untouched — the demo user stays `NULL` until first login.

- `database/schemas.py` — extend `LoginSchema` with `remember_me: bool = False`. Add a `validate_remember_me` field validator that accepts only an actual `bool`; the route is responsible for converting the checkbox string (`"on"`/missing) into a bool before constructing the schema. Keep the existing email/password validators unchanged. Keep the generic-error behavior — `ValidationError` here must still surface as the unified `"Invalid email or password."` flash from the route.

- `app.py` —
  - At the top of `create_app()`, import `timedelta` from `datetime` (already partially imported — extend the line).
  - Inside `app.config.update(...)`, after `WTF_CSRF_TIME_LIMIT`, add:
    - `REMEMBER_COOKIE_DURATION=timedelta(days=30)`
    - `REMEMBER_COOKIE_HTTPONLY=True`
    - `REMEMBER_COOKIE_SAMESITE="Lax"`
    - `SESSION_COOKIE_HTTPONLY=True`
    - `SESSION_COOKIE_SAMESITE="Lax"`
  - In `login()`:
    - Read `remember_me = request.form.get("remember_me") == "on"` alongside the existing `raw_email` / `raw_pass`.
    - Pass `remember_me=remember_me` into `LoginSchema(...)`.
    - On every `render_template("login.html", ...)` after a failure, pass `remember_me=remember_me` so the checkbox state is preserved (this includes the `ValidationError`, the credential-mismatch, and the `SQLAlchemyError` branches).
    - On successful credential check, call `login_user(user, remember=data.remember_me)` instead of the hardcoded `remember=False`.
    - Immediately after `login_user(...)`, set `user.last_login_at = datetime.now(timezone.utc)` and `db.session.commit()`. This commit goes inside the existing `try/except SQLAlchemyError` block so a failure rolls back and falls into the existing DB-error flash path.
  - In `register()`: after the existing `login_user(user, remember=False)` call, set `user.last_login_at = datetime.now(timezone.utc)` and `db.session.commit()`. Keep the `remember=False` here — registration intentionally creates a session-scoped login.
  - Change `@app.route("/logout")` to `@app.route("/logout", methods=["POST"])`. The function body (the existing `try/except` around `logout_user()`) is otherwise unchanged.

- `templates/login.html` — see *Templates* section above.

- `templates/base.html` — see *Templates* section above.

- `static/css/style.css` — append minimal rules only if existing tokens are not reusable:
  - `.nav-form` — `display: inline-flex; align-items: center; margin: 0;` so the inline logout form does not break navbar flex alignment.
  - `.nav-cta--button` — modifier that strips default `<button>` chrome (`border: none; background: inherit; font: inherit; cursor: pointer;`) so the submit button is visually identical to the previous `<a class="nav-cta">`. Reuse all colors and radii from existing `var(--…)` tokens — no new hex literals.
  - If the Step-2 `.form-checkbox` block already lays out compactly inside the login form, no new checkbox rules are needed.

## Files to create

- `migrations/versions/<hash>_add_last_login_at.py` — generated via `flask --app app db migrate -m "add last_login_at to users"`. Verify the autogenerated `op.add_column(...)` is nullable. Verify `downgrade()` drops the column. No backfill `op.execute(...)` is required.

## New dependencies

No new dependencies. `flask-login` already implements `remember=True` natively; the remember-cookie hardening is pure Flask config.

## Rules for implementation

- **Parameterised queries only** — keep using SQLAlchemy 2.0 `select(...)` / `db.session.execute(...)`. Never use raw f-string SQL.
- **Passwords hashed with werkzeug** — `user.check_password(...)` is unchanged. Never log raw passwords, password hashes, or remember tokens.
- **Use CSS variables — never hardcode hex values.** Any new color, radius, or font-family in `style.css` must reference an existing `var(--…)` defined in `:root`.
- **All templates extend `base.html`** — `login.html` already does. The logout form inside `base.html` uses `url_for('logout')` — never hardcode `/logout`.
- **CSRF on logout** — the new logout `<form>` MUST include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Flask-WTF will reject the POST without it. Do not exempt the logout view from CSRF.
- **Generic auth errors** — failed logins continue to flash the unified `"Invalid email or password."` message regardless of which check failed (Pydantic validation, missing email, wrong password). Do not leak account existence in flashes, logs, or HTTP status codes.
- **Open-redirect guard** — the existing `next_page.startswith("/") and not next_page.startswith("//")` check stays in place; do not relax it. The `next` parameter is consulted only after a successful credential check.
- **Remember-me cookie hardening** — `REMEMBER_COOKIE_HTTPONLY=True`, `REMEMBER_COOKIE_SAMESITE="Lax"`. Do **not** set `REMEMBER_COOKIE_SECURE=True` in this step — it would break local HTTP development. A production env-driven toggle is out of scope here and tracked for a later deployment-hardening step.
- **`last_login_at` update is best-effort within the auth path** — the stamp/commit sits inside the existing `try/except SQLAlchemyError` block. On commit failure, `db.session.rollback()`, log via `current_app.logger.error(...)`, and fall into the existing DB-error flash + re-render path. Never let a `last_login_at` write succeed silently while the session remains in an inconsistent state.
- **No promoting stub routes** — `/dashboard`, `/profile`, `/expenses/*` remain plain-string stubs in this step.
- **Migration safety** — the new column is nullable, so `flask db upgrade` against a database holding the Step 1 demo user must succeed without touching that row. Verify locally before merging.
- **Logout-method change is breaking** — every internal reference to the logout URL must move from `<a href>` to a POST form. Search `templates/` for `url_for('logout')` and confirm only the navbar reference exists; if any other template references it, update them too.

## Definition of done

- [ ] `flask --app app db upgrade` applies the new migration cleanly against a database holding the Step 1 demo user; `users.last_login_at` is added as nullable and the demo row's `last_login_at IS NULL` afterwards.
- [ ] `flask --app app db downgrade -1` removes the column without error.
- [ ] `GET /login` shows the form with: email, password (with the existing show/hide toggle from Step 2), a new **Remember me** checkbox (unchecked by default), and the submit button. No "Forgot password?" link is shown.
- [ ] Submitting **valid credentials with Remember me unchecked** logs the user in for the session only; restarting the browser process requires another login (no `remember_token` cookie is set).
- [ ] Submitting **valid credentials with Remember me checked** sets a `remember_token` cookie with `HttpOnly`, `SameSite=Lax`, and a 30-day expiry; closing and reopening the browser keeps the user signed in.
- [ ] On every successful `POST /login`, `users.last_login_at` for the signed-in account updates to the current UTC timestamp; verifiable via `SELECT last_login_at FROM users WHERE email = '<email>';`.
- [ ] Completing `POST /register` also stamps `last_login_at` for the new user as part of the auto-login.
- [ ] Submitting **invalid credentials** re-renders `/login` with the generic `"Invalid email or password."` flash, preserves the entered email, and preserves the **Remember me** checkbox state across the re-render.
- [ ] Clicking the navbar **Sign out** button issues a `POST /logout`, clears both the session cookie and any `remember_token` cookie, flashes the goodbye message, and redirects to `/`.
- [ ] A direct `GET /logout` returns HTTP 405 (Method Not Allowed).
- [ ] A `POST /logout` without a CSRF token returns HTTP 400 (CSRF failure) and does not clear the session.
- [ ] The navbar continues to render correctly for both authenticated and unauthenticated users — the sign-out button is visually indistinguishable from the previous `<a class="nav-cta">` link.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test, end-to-end: register a new user → confirm `last_login_at` set → sign out (POST) → sign back in with **Remember me** checked → close and reopen the browser → still signed in → `last_login_at` reflects the most recent sign-in.
