# Spec: Date Filter for Profile Page

## Overview

Steps 1–5 delivered the data layer, registration, login/logout, the profile page (account details + edit-profile + change-password), and the dashboard with its three named-period filter (`this_month` / `last_month` / `all_time`). Step 6 adds a **custom date-range filter** to the profile page so a signed-in user can browse *their own* expense history narrowed to an arbitrary `start`–`end` window. This is the complementary capability to the dashboard's fixed periods: the dashboard answers "how am I doing this month vs. last," while the profile activity view answers "show me exactly what I spent between these two dates." The feature reuses the existing date-bounded query infrastructure in `database/services.py` (`_where_user_and_period`, `_period_totals`) — it adds a render-time list, a forgiving query-string schema, and a new activity card on the profile template. No clock-dependent ("today") logic is involved: bounds come entirely from user input, which keeps the behaviour deterministic and testable against the seed data.

## Depends on

- **Step 1 (Database Setup)** — the `expenses` table with `user_id`, `amount` (`Numeric(10, 2)`), `category`, and an **indexed** `date` column (`database/db.py` line 107–109); the eight seed expenses for `demo@spendly.dev`, all dated across May 2026.
- **Step 3 (Login and Logout)** — `@login_required`, `current_user`, and CSRF wiring already present in `base.html`.
- **Step 4 (Profile Page Design)** — the `GET /profile` route, `templates/profile.html`, the `.profile-card` / `.form-group` / `.form-input` / `.btn-submit` CSS components, and the route → schema → service pattern this step extends.
- **Step 5 (Backend for Dashboard)** — the private helpers `_where_user_and_period(uid, lo, hi)` and `_period_totals(uid, lo, hi)` in `database/services.py`, and the `coerce_period(...)` graceful-coercion pattern in `database/schemas.py` that this step mirrors for date input.

## Routes

**No new routes.** The existing `GET /profile` route is *extended* to accept two optional query-string parameters:

- `GET /profile?start=<YYYY-MM-DD>&end=<YYYY-MM-DD>` — render the profile page with the activity list filtered to expenses whose `date` falls in the inclusive range. Either parameter may be omitted (that side is unbounded). Access — **logged-in**.

The two existing state-changing handlers — `POST /profile` (`profile_update`) and `POST /profile/change-password` (`change_password_route`) — are **unchanged**. The `/expenses/*` stub routes stay as plain-string stubs.

## Database changes

**No database changes.** Verified against `database/db.py`: `Expense.date` is a `Date` column with `index=True`, and `Expense.user_id` is an indexed FK. Both required filter columns already exist with appropriate types and indexes. No migration is needed.

## Templates

- **Modify:** `templates/profile.html`
  - Add **one** new `<article class="profile-card">` inside the existing `.profile-main` column (alongside "Edit profile" and "Change password"), titled "Spending activity" (use a Lucide icon consistent with the other card titles, e.g. `data-lucide="history"` or `"calendar-search"`).
  - **Filter form** — a `method="GET"` form whose `action` is `{{ url_for('profile') }}`, containing:
    - `<input type="date" name="start">` and `<input type="date" name="end">`, each in a `.form-group` with a `<label>`. Pre-populate each via `value="{{ range_start.isoformat() if range_start else '' }}"` (and likewise for `range_end`) so the active filter survives the round-trip.
    - An "Apply" submit button (reuse `.btn-submit`) and a "Clear" link pointing at `{{ url_for('profile') }}` (no query string) to reset the filter.
    - **No CSRF token** — this is a `GET` form; CSRF protects state-changing requests only. Do **not** convert it to POST.
  - **Summary line** — show `{{ activity_count }}` and the range total formatted as `{{ "{:,.2f}".format(activity_total) }} {{ currency }}`, plus a human-readable description of the active window (e.g. "All time", or "5 May 2026 → 12 May 2026") derived from `range_start` / `range_end`.
  - **Activity table** — columns `Date`, `Description`, `Category`, `Amount` over `activity_expenses` (newest first). Format the amount with `"{:,.2f}".format(...)` and suffix the `currency`. A category badge may reuse the dashboard's visual treatment, but **must not** introduce new hardcoded hex (see Rules).
  - **Empty states** — two distinct messages: when the user has expenses but none match the filter → "No expenses in this date range."; when the account has zero expenses at all → "No expenses recorded yet." (A simple way to distinguish: the filter is active when `range_start` or `range_end` is set.)
- **Create:** None.

## Files to change

- `app.py`
  - Extend the existing `GET /profile` handler (`profile()`), keeping it thin:
    ```python
    @app.route("/profile", methods=["GET"])
    @login_required
    def profile() -> ResponseReturnValue:
        date_range = coerce_date_range(
            request.args.get("start"), request.args.get("end")
        )
        try:
            activity = profile_activity(current_user, date_range)
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("DB error on /profile activity: %s", exc)
            flash("A database error occurred loading your activity.", "error")
            activity = empty_activity_payload(current_user, date_range)
        return render_template(
            "profile.html",
            user=current_user,
            currencies=ALLOWED_CURRENCIES,
            **activity,
        )
    ```
  - Add imports: `coerce_date_range` (and `DateRangeSchema` if referenced) from `database.schemas`; `profile_activity`, `empty_activity_payload` from `database.services`. Keep import groups sorted per the existing Ruff config.
  - **Do not touch** `profile_update()` or `change_password_route()`.

- `database/schemas.py`
  - Append a `DateRangeSchema(BaseModel)`:
    ```python
    class DateRangeSchema(BaseModel):
        start: date | None = None
        end: date | None = None

        @model_validator(mode="after")
        def order_bounds(self) -> "DateRangeSchema":
            if self.start and self.end and self.start > self.end:
                self.start, self.end = self.end, self.start
            return self
    ```
    (Add `from datetime import date` to the imports.)
  - Append a module-level helper `coerce_date_range(raw_start: str | None, raw_end: str | None) -> DateRangeSchema` that parses each value independently with a private `_parse_iso_date(raw: str | None) -> date | None` (returns `date.fromisoformat(raw.strip())`, or `None` on empty/`ValueError`), then constructs `DateRangeSchema(start=..., end=...)`. Passing pre-parsed `date | None` values means the schema can never raise — the view never 400s on a stray query string (mirrors `coerce_period`).

- `database/services.py`
  - Append `list_expenses_in_range(user_id: int, lo: date | None, hi: date | None) -> list[Expense]` that reuses `_where_user_and_period(user_id, lo, hi)` and runs `select(Expense).where(*clauses).order_by(Expense.date.desc(), Expense.id.desc())`, returning the scalars as a list. **No `LIMIT`** — the whole point of the filter is to return every match in the window (pagination is a future step).
  - Append an orchestrator `profile_activity(user: User, data: DateRangeSchema) -> dict[str, object]` returning the payload shape:
    ```python
    {
        "activity_expenses": list[Expense],   # all matches, newest first
        "activity_total": Decimal,            # sum over the range, quantised 0.01
        "activity_count": int,                # row count in the range
        "range_start": date | None,           # echo of the resolved lower bound
        "range_end": date | None,             # echo of the resolved upper bound
        "currency": str,                      # user.default_currency passthrough
    }
    ```
    It computes `total, count = _period_totals(user.id, data.start, data.end)` (reuse the existing private helper) and `list_expenses_in_range(...)`, quantising `total` to two places with `ROUND_HALF_UP`.
  - Append `empty_activity_payload(user: User, data: DateRangeSchema) -> dict[str, object]` (used on the `SQLAlchemyError` path) returning the same keys with `activity_expenses=[]`, `activity_total=Decimal("0.00")`, `activity_count=0`, and the echoed bounds + currency — so the page still renders on a DB error (mirrors `empty_dashboard_payload`).

- `templates/profile.html` — add the "Spending activity" card described in *Templates*.

- `static/css/style.css` — add any new rules needed for the activity filter row and table (suggested classes: `.activity-filter`, `.activity-table`). **Every** new declaration uses the existing `:root` tokens (`var(--accent)`, `var(--ink)`, `var(--ink-muted)`, `var(--border)`, `var(--paper-card)`, `var(--radius-md)`, etc.). No new hex literals.

## Files to create

None. The feature extends existing modules and templates only.

## New dependencies

No new dependencies. `datetime.date` / `date.fromisoformat` are stdlib, Pydantic v2 is already present, and `<input type="date">` is native HTML — no date-picker library, no new CDN script.

## Rules for implementation

- **Parameterised queries only** — the new list query and the reused `_period_totals` both go through SQLAlchemy 2.0 `select(...)` with parameterised `Expense.user_id == user.id`, `Expense.date >= lo`, `Expense.date <= hi` clauses. Never build SQL with f-strings.
- **Passwords hashed with werkzeug** — unchanged this step; no auth or password code is touched. The change-password form must keep working exactly as before.
- **Use CSS variables — never hardcode hex values** — all new styling in `static/css/style.css` references existing `var(--…)` tokens. Category badges in the activity table must not introduce new hardcoded colors.
- **All templates extend `base.html`** — `profile.html` already does; keep it that way and add the card inside the existing `{% block content %}`.
- **Always use `url_for()`** — the filter form `action` and the "Clear" link use `{{ url_for('profile') }}`; never hardcode `/profile`.
- **Filter is a GET, not a POST** — date filtering is idempotent and bookmarkable. Use `method="GET"`, no CSRF token on this form. Do not add a new route or a POST handler for it.
- **Service layer owns DB logic** — the `profile()` route body is limited to: coerce the query string, call `profile_activity(...)`, handle `SQLAlchemyError`, render. No `select(...)`, `func.*`, or `db.session.execute(...)` appears in the route.
- **Reuse, don't duplicate** — use the existing `_where_user_and_period` and `_period_totals` helpers rather than re-implementing range filtering. Keep the dashboard code untouched.
- **Graceful coercion** — an unparseable, partial, or out-of-order query string must never raise: a bad value on either side is treated as unbounded; `start > end` is swapped, not rejected. The view returns 200 for any input.
- **`Decimal` discipline** — `activity_total` is a `Decimal` quantised to two places (`Decimal("0.01")`, `ROUND_HALF_UP`) before it leaves the service. The template formats via `"{:,.2f}".format(...)` — never `float()`.
- **User isolation** — every query filters by `user_id = user.id`. A user's activity list must never include another user's expenses, regardless of the date range. This is part of the test plan.
- **No pagination / no `LIMIT`** — render every matching row. Pagination and infinite-scroll are explicitly out of scope for this step.
- **No promoting other stubs** — `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` stay as plain-string stubs; this spec touches only `GET /profile`.

## Definition of done

- [ ] `GET /profile` as a logged-out user redirects to `/login` (existing `@login_required` behaviour, unchanged).
- [ ] `GET /profile` with **no** query string as the seeded `demo@spendly.dev` user renders HTTP 200 and lists **all 8** seed expenses newest-first, with a summary count of `8` and total `8,299.50 INR`; the empty-state text does not appear.
- [ ] `GET /profile?start=2026-05-05&end=2026-05-12` shows exactly the **4** expenses in that inclusive window (Python books, Netflix, Doctor visit, Metro pass — newest first), with summary count `4` and total `2,699.00 INR`.
- [ ] `GET /profile?start=2026-05-10` (no `end`) shows every expense on/after 2026-05-10; `GET /profile?end=2026-05-03` (no `start`) shows every expense on/before 2026-05-03. Each returns 200.
- [ ] `GET /profile?start=2026-05-31&end=2026-05-01` (reversed) swaps the bounds, returns the same set as the normal-order range, and renders 200 with no error logged.
- [ ] `GET /profile?start=not-a-date&end=2026-13-99` ignores both bad values (treated as unbounded → all expenses), returns HTTP 200, and logs no exception (no 400, no 500).
- [ ] `GET /profile?start=2000-01-01&end=2000-12-31` matches nothing and shows the "No expenses in this date range." empty state at HTTP 200.
- [ ] A brand-new user with zero expenses lands on `/profile` and sees "No expenses recorded yet.", count `0`, total `0.00 <currency>`, all at HTTP 200.
- [ ] The two date inputs are pre-filled from the active filter (so reloading keeps the window), and the "Clear" link returns to an unfiltered `/profile`.
- [ ] The existing "Edit profile" form and "Change password" form still submit and behave exactly as before (regression check).
- [ ] Logging in as a second user with their own expenses shows **only** that user's rows in the activity list for every date range; the demo user's expenses never leak.
- [ ] Every amount displays with exactly two decimal places and the currency code matches the user's `default_currency`.
- [ ] The `profile()` route body contains no `select(...)`, `func.*`, or `db.session.execute(...)` — all query construction lives in `database/services.py`.
- [ ] No new hardcoded hex values were added to `static/css/style.css`; new rules use `var(--…)` tokens only. `profile.html` still extends `base.html` and uses `url_for()` for the form action and Clear link.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in as `demo@spendly.dev` → open `/profile` → confirm all 8 rows → apply a 5–12 May range → confirm 4 rows and the total → enter a reversed range and a garbage range → confirm graceful handling → click "Clear" → register a second account and confirm activity isolation → log out → confirm `/profile` redirects to `/login`.
