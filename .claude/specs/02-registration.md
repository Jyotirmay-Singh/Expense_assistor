# Spec: Registration Enhancements

## Overview

Step 1 delivered the database foundation. Step 2 already shipped a working `/register` flow with Pydantic-validated name/email/password and werkzeug-hashed credentials. This spec **revises** that flow to (a) relax the password rules to a length-only check so users aren't fighting symbol regexes, (b) add an explicit Terms of Service + Privacy Policy acceptance gate with an audit timestamp on the user row, and (c) collect two new fields at signup — a separate **display name** (short handle used in greetings) and a **default currency** (3-letter ISO 4217 code used as the per-user default when adding expenses). The goal is a friendlier signup with the legal acceptance and personalization data the rest of the app needs, captured once at creation.

## Depends on

Step 1 (Database Setup) — `users` table, Alembic migrations, `db.session`, `werkzeug.security` hashing, and the existing `RegisterSchema` / `/register` route must be in place. Templates `terms.html` and `privacy.html` must exist (they do) so the acceptance checkbox can link to them.

## Routes

No new routes. Existing routes change behavior only:

- `GET /register` — render the revised form (adds display name input, currency dropdown, terms checkbox).
- `POST /register` — accept and validate the new fields; persist `display_name`, `default_currency`, and `terms_accepted_at` on the created `User` row. Access remains **public**.

## Database changes

Modify the `users` table by adding three columns:

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `display_name` | `String(60)` | `NOT NULL` | Short handle shown in greetings / nav. Distinct from `name` (legal/full name). |
| `default_currency` | `String(3)` | `NOT NULL`, `server_default='INR'` | ISO 4217 code. Application-level allowlist enforced in `RegisterSchema`. |
| `terms_accepted_at` | `DateTime(timezone=True)` | `NOT NULL` | Timestamp of acceptance. Set at registration; never updated. |

Alembic migration must handle the existing demo user (`demo@fincheck.dev`) seeded in Step 1. Backfill pattern:

1. Add `display_name` as nullable, then `UPDATE users SET display_name = name WHERE display_name IS NULL`, then `ALTER COLUMN display_name SET NOT NULL`.
2. Add `default_currency` in one step with `server_default='INR'` and `nullable=False` (PostgreSQL applies the default to existing rows atomically).
3. Add `terms_accepted_at` as nullable, then `UPDATE users SET terms_accepted_at = NOW() WHERE terms_accepted_at IS NULL`, then `ALTER COLUMN terms_accepted_at SET NOT NULL`.

The `downgrade()` function must drop the three columns in reverse order.

No new tables. No new indexes. No new check constraints (currency validation lives in Pydantic, not the DB, because the allowlist is expected to evolve).

## Templates

- **Modify:** `templates/register.html`
  - Insert a `Display name` text input between `Full name` and `Email address`. Required, max 60 chars, autocomplete `nickname`.
  - Insert a `Default currency` `<select>` after `Email address`. Options listed in section *Rules for implementation*. Default selection: `INR`.
  - Replace the four-rule password checklist and four-segment strength bar with a single hint reading `At least 8 characters`. Update the input `placeholder` to `Min. 8 characters`.
  - Simplify the Alpine.js `x-data` on the password `form-group` so `score` and `colors` arrays are gone; keep only the show/hide toggle.
  - Add a `Terms of Service + Privacy Policy` checkbox immediately above the submit button. Label text: `I agree to the <a href="{{ url_for('terms') }}">Terms of Service</a> and <a href="{{ url_for('privacy') }}">Privacy Policy</a>.` Checkbox `name="accept_terms"`, `required` attribute on the input, and bind to Alpine via `x-model="accepted"` so the submit button can be disabled until checked (`:disabled="loading || !accepted"`).
  - On validation failure, re-render the template preserving prior `display_name`, `default_currency`, and `accepted` values (passed as template kwargs from the route).
- **No new templates.** `terms.html`, `privacy.html`, and `base.html` are untouched.

## Files to change

- `database/db.py` — add `display_name`, `default_currency`, `terms_accepted_at` to the `User` model using `Mapped[...] / mapped_column(...)`. Update `seed_db()` so the demo user is created with `display_name="Demo"`, `default_currency="INR"`, and `terms_accepted_at=_utcnow()`.
- `database/schemas.py` — extend `RegisterSchema` with `display_name: str`, `default_currency: str`, `accept_terms: bool`. Loosen `_PASSWORD_RE` to a length-only check (min 8, max 72). Add `validate_display_name` (strip, 2–60 chars), `validate_default_currency` (uppercase, membership in `ALLOWED_CURRENCIES`), and `validate_accept_terms` (must be `True`). Export an `ALLOWED_CURRENCIES` tuple module-level so the route and template can both reference it.
- `app.py` — in `register()`:
  - Read `display_name`, `default_currency`, `accept_terms` from `request.form`. Treat the checkbox value via `request.form.get("accept_terms") == "on"` (or `"1"` — whichever matches the template's `value`).
  - Pass the parsed values into `RegisterSchema(...)`.
  - On successful validation, construct the `User` with `display_name=data.display_name`, `default_currency=data.default_currency`, and `terms_accepted_at=datetime.now(timezone.utc)` before `set_password()`.
  - On any `ValidationError` or DB error re-render path, pass the entered `display_name`, `default_currency`, and the boolean `accepted` back to the template alongside the existing `name`, `email`.
  - Inject `ALLOWED_CURRENCIES` into the template context (either via `render_template(..., currencies=ALLOWED_CURRENCIES)` or a small context processor) so the dropdown options come from one source of truth.
- `templates/register.html` — see *Templates* section above.
- `static/css/style.css` — append minimal styles only if existing classes aren't reusable: a `.form-select` rule mirroring `.form-input`, a `.form-checkbox` rule for the acceptance row (flex layout, accent color via `var(--accent)`), and remove or unused `.strength-*` / `.pwd-hints` rules **only if** they have no other consumer. Use CSS variables exclusively — no new hex literals.

## Files to create

- `migrations/versions/<hash>_extend_registration.py` — generated via `flask --app app db migrate -m "extend registration with display_name, default_currency, terms_accepted_at"`. After autogeneration, hand-edit to insert the backfill `op.execute(...)` statements and the nullable→NOT NULL alters described in *Database changes*. Verify `downgrade()` drops columns in reverse order.

## New dependencies

No new dependencies. `requirements.txt` is unchanged.

## Rules for implementation

- **SQLAlchemy 2.0 only** — typed mappings (`Mapped`, `mapped_column`) and `select(...)` / `db.session.execute(...)` syntax. Never raw f-string SQL.
- **Pydantic v2 only** for input validation — extend `RegisterSchema`; do not validate by inspecting `request.form` in the route beyond reading raw strings.
- **Passwords hashed with werkzeug** — keep `user.set_password()` / `check_password_hash`. Loosening the regex must not weaken hashing.
- **No new currency formats** outside the `ALLOWED_CURRENCIES` allowlist. Initial set (alphabetical, 10 entries): `AED, AUD, CAD, CHF, EUR, GBP, INR, JPY, SGD, USD`. Default: `INR`. The dropdown must render this list verbatim from `database.schemas.ALLOWED_CURRENCIES`.
- **CSS variables only** — any new color, radius, or font-family in `style.css` must reference an existing `var(--…)` defined in `:root`. No new hex literals.
- **All templates extend `base.html`** — `register.html` already does. The acceptance-checkbox links use `url_for('terms')` and `url_for('privacy')` — never hardcoded `/terms` or `/privacy`.
- **CSRF** — the existing `csrf_token` hidden input must remain. New fields are inside the same `<form>`.
- **Migration safety** — the migration must complete cleanly against a database holding the Step 1 demo user. After `flask db upgrade`, the demo row must satisfy all three new NOT NULL constraints (`display_name='Demo User'` from the backfill is acceptable; the seed code change is for fresh databases only).
- **Error preservation** — re-rendering on validation failure must restore every entered value *except* the password. This includes the currency selection (selected `<option>` must reflect the prior choice) and the checkbox state.
- **Logging** — keep the existing `current_app.logger.error(...)` pattern for `SQLAlchemyError` and the generic `Exception` branches. Do not log the raw password or the password hash.
- **No promoting stub routes** — `/dashboard`, `/profile`, `/expenses/*` remain plain-string stubs. This spec touches only the registration flow.

## Definition of done

- [ ] `flask --app app db upgrade` applies the new migration cleanly against a database that already holds the Step 1 demo user; the demo user ends up with `display_name='Demo User'`, `default_currency='INR'`, and a non-null `terms_accepted_at`.
- [ ] `flask --app app db downgrade -1` removes the three new columns without error.
- [ ] `GET /register` shows: Full name, Display name, Email, Default currency dropdown (10 options, INR selected), Password (with a single "At least 8 characters" hint), Terms+Privacy checkbox with working links to `/terms` and `/privacy`.
- [ ] Submitting the form with `accept_terms` unchecked re-renders `/register` with a flashed error and **does not** create a user row.
- [ ] Submitting with a 7-character password re-renders with a length error and does not create a user row.
- [ ] Submitting with a `default_currency` not in `ALLOWED_CURRENCIES` (e.g. via a hand-crafted POST) re-renders with an error and does not create a user row.
- [ ] Submitting with all fields valid creates the `User` row, populates `display_name`, `default_currency`, and `terms_accepted_at`, logs the user in, and redirects to `/dashboard`.
- [ ] On any validation failure, the form reloads with the previously entered `name`, `display_name`, `email`, selected `default_currency`, and `accept_terms` state preserved — the password field is empty.
- [ ] The duplicate-email guard still works: registering twice with the same email returns the friendly flash and does not create a second row.
- [ ] `seed_db()` on a fresh empty database creates the demo user with all three new columns populated.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: register a brand-new user end-to-end in the browser, then log out and log in again with the same credentials.
