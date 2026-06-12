# Spec: Backend for Dashboard

## Overview

Steps 1–4 delivered the data layer, registration, hardened login/logout, and the profile page. Step 5 builds the **backend** that the upcoming dashboard view will consume: a set of pure-Python aggregation service functions over the `expenses` table (period totals, category breakdown, recent activity, per-day time series) plus a small Pydantic schema for the period filter accepted on the `/dashboard` URL. The `/dashboard` route is promoted from its current plain-string stub to a real `render_template(...)` call backed by a deliberately **minimal** data-display template — the visual design of the dashboard is reserved for the next step (`dashboard-page-design`). Splitting backend from UI keeps query design and visual iteration on independent change cycles and gives the design step a stable data contract to bind to.

## Depends on

- **Step 1 (Database Setup)** — `expenses` table with `user_id`, `amount` (`Numeric(10, 2)`), `category`, `date`; `Decimal` discipline; `db.session`; the eight seed expenses for the demo user (all dated in May 2026, which is the current month per the project's frozen "today").
- **Step 2 (Registration Enhancements)** — `User.default_currency` used as the display currency on the dashboard.
- **Step 3 (Login and Logout)** — `@login_required` decorator; `current_user`; CSRF token already wired in `base.html`.
- **Step 4 (Profile Page Design)** — established the `database/services.py` module and the route → schema → service pattern reused here.
- Frontend Stack — Tailwind CSS initialized via base.html as defined in the global SKILL document.

## Routes

- `GET /dashboard` — render the dashboard data view for the signed-in user. Accepts an optional `?period=` query string with values `this_month` (default), `last_month`, or `all_time`. Access — **logged-in**.

No other routes change. `/profile`, `/expenses/*`, and the public routes remain exactly as they are.

## Database changes

No database changes. Every aggregation reads from the existing `expenses` table. Confirmed against `database/db.py`: the columns required (`user_id`, `amount`, `category`, `date`) all exist and have appropriate types and indexes.

## Templates

- **Create:** `templates/dashboard.html`
  - `{% extends "base.html" %}`.
  - **Period selector** at the top — three `<a>` links to `url_for('dashboard', period='this_month' | 'last_month' | 'all_time')`. The current period gets a visible "active" marker (a small `[selected]` text or a class — design polish is deferred).
  - **Summary tiles** — three plain `<div>`s showing: total spent (formatted `Decimal` with the user's `default_currency` code as suffix), expense count (integer), and average per expense (`Decimal`, two decimal places).
  - **Category breakdown** — a `<table>` with rows `(category, total, percent of period total)`. Sorted by total descending. Empty state: a single row reading "No spending in this period."
  - **Recent expenses** — a `<table>` with columns `(date, title, category, amount)`, limited to the most recent 5 expenses in the selected period. Empty state: a single row reading "No expenses yet."
  - **Daily series** — a `<table>` with columns `(date, total)` for every day in the period that has at least one expense, sorted by date ascending. This is the data the future chart step will bind to; for now it is rendered as a plain table so it is verifiable. Empty state: a single row reading "No daily activity in this period."
  - **No CSS work in this step beyond what is required to keep the page legible.** A short `<style>` block scoped to `.dashboard-debug` is acceptable for tabular spacing if existing utility classes do not cover it. No new color tokens, no new layout primitives.
- **Modify:** None.

## Files to change

- `app.py`
  - Inside `_register_main_routes()`, replace the existing `/dashboard` stub:
    ```python
    @app.route("/dashboard")
    @login_required
    def dashboard() -> ResponseReturnValue:
        return f"Dashboard — welcome, {current_user.name} (coming in Step 5)"
    ```
    with a real handler that:
    1. Parses the `period` query parameter via `coerce_period(request.args.get("period"))`.
    2. Calls `compute_dashboard(current_user, period_schema.period)`.
    3. Renders `dashboard.html` with `user=current_user`, `period=period_schema.period`, and the dashboard payload spread as template kwargs.
    4. Catches `SQLAlchemyError`, calls `db.session.rollback()`, logs via `current_app.logger.error(...)`, flashes a generic message, and re-renders the dashboard with an empty payload so the page still loads.
  - Add imports for `DashboardPeriodSchema`, `coerce_period` from `database.schemas` and `compute_dashboard` from `database.services`. Keep import groups sorted per existing Ruff configuration.

- `database/schemas.py`
  - Append a `DashboardPeriodSchema(BaseModel)` with a single field `period: Literal["this_month", "last_month", "all_time"] = "this_month"`. Use `typing.Literal` for the type-level allowlist — no field validator needed.
  - Append a module-level helper `coerce_period(raw: str | None) -> DashboardPeriodSchema` that returns `DashboardPeriodSchema(period=raw)` on a valid value and falls back to `DashboardPeriodSchema()` (the default) on any `ValidationError` or `None`. The view never 400s on a stray query string.
  - Export the literal tuple of valid period values (e.g. `DASHBOARD_PERIODS: tuple[str, ...] = ("this_month", "last_month", "all_time")`) so the template can iterate the selector options from one source of truth.

- `database/services.py`
  - Append a top-level `compute_dashboard(user: User, period: str) -> dict[str, object]` orchestrator returning a payload of the shape:
    ```python
    {
        "total_amount": Decimal,                # sum of expenses in period
        "expense_count": int,                   # row count in period
        "average_amount": Decimal,              # total / count, Decimal("0.00") when count == 0
        "category_breakdown": list[dict],       # [{ "category": str, "total": Decimal, "percent": Decimal }]
        "recent_expenses": list[Expense],       # up to 5 most recent in period
        "daily_series": list[dict],             # [{ "date": date, "total": Decimal }]
        "currency": str,                        # passthrough of user.default_currency
        "period_start": date | None,            # inclusive lower bound, None for all_time
        "period_end": date | None,              # inclusive upper bound, None for all_time
    }
    ```
  - Add module-private helpers (`_period_bounds`, `_period_totals`, `_category_breakdown`, `_recent_expenses`, `_daily_series`). Each helper accepts the resolved `(user_id, start, end)` triple plus `db.session` and returns a typed primitive. All aggregations use SQLAlchemy 2.0 `select(...)` with `func.sum`, `func.count`, and `func.coalesce(..., 0)` to convert empty-table results from `None` into `0`.
  - Currency math stays in `Decimal` everywhere. Percent computation uses `Decimal` division with explicit quantisation to two decimal places (`Decimal("0.01")`, `ROUND_HALF_UP`). Never cast to `float`.

## Files to create

- `templates/dashboard.html` — see *Templates* section above.

## New dependencies

No new dependencies. `typing.Literal` is stdlib; `decimal.Decimal` and `datetime.date` are already in use.

## Rules for implementation

- **Parameterised queries only** — every aggregation issues SQLAlchemy 2.0 `select(...)` with `.filter_by(user_id=user.id)` (or `.where(Expense.user_id == user.id)`) and parameterised `Expense.date >= start`/`<= end` conditions. Never use raw f-string SQL.
- **Passwords hashed with werkzeug** — unchanged in this step; no auth-related code is touched.
- **Use CSS variables — never hardcode hex values.** Any inline `<style>` in `dashboard.html` (used only for minimal table spacing) must reference existing `var(--…)` tokens defined in `:root` inside `static/css/style.css`. No new color tokens are introduced in this step.
- **All templates extend `base.html`** — `dashboard.html` must start with `{% extends "base.html" %}`.
- **Always use `url_for()`** — period selector links and any internal navigation use `url_for('dashboard', period=...)`. Never hardcode `/dashboard`.
- **Service layer owns DB logic** — the route function body is limited to: parse the query string, call `compute_dashboard(...)`, handle `SQLAlchemyError`, render. No `select(...)`, `func.*`, or `db.session.execute(...)` calls live inside the route.
- **`Decimal` discipline** — `total_amount`, `average_amount`, `category_breakdown[*].total`, `category_breakdown[*].percent`, and `daily_series[*].total` are all `Decimal` values quantised to two decimal places before they leave the service module. The template formats them via `"{:,.2f}".format(...)` or Jinja's built-in `|round(2)` — never via `float()` or Python's `%f`.
- **User isolation** — every aggregation **must** filter by `user_id = user.id`. There is no admin/overview mode in this step. Cross-user data must never appear on a user's dashboard even when the period filter falls back to its default. This is part of the test plan.
- **Period semantics:**
  - `this_month` — `date(today.year, today.month, 1)` → `today` (inclusive both ends).
  - `last_month` — first day of the previous month → last day of the previous month (use `calendar.monthrange` or `dateutil.relativedelta` from stdlib alternatives; do **not** add `python-dateutil` as a dependency — the stdlib `calendar` module suffices).
  - `all_time` — `(None, None)`. The query helpers must conditionally skip the `date` filter clauses when bounds are `None`; never compare against `None` in SQL.
- **Empty-state safety** — `compute_dashboard` must return a fully populated payload for a user with zero expenses: `total_amount = Decimal("0.00")`, `expense_count = 0`, `average_amount = Decimal("0.00")`, `category_breakdown = []`, `recent_expenses = []`, `daily_series = []`. The template renders the explicit empty-state strings listed in *Templates*. No Jinja `None` checks should be needed beyond the empty-list checks.
- **`func.coalesce(func.sum(...), 0)`** — every `SUM` aggregation is wrapped in `coalesce` so a zero-row query returns `0` rather than `None`. The Python-side conversion to `Decimal` happens once at the boundary (e.g. `Decimal(str(value))` to preserve precision).
- **Ordering rules** — category breakdown sorted by `total` descending (ties broken by `category` ascending for determinism); recent expenses sorted by `date` descending then `id` descending and limited to `5`; daily series sorted by `date` ascending.
- **No promoting other stub routes** — `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` stay as plain-string stubs. This spec touches only `/dashboard`.
- **No visual polish** — `dashboard.html` is the minimum required to display the computed payload. Do not introduce charting libraries, icons, animation, layout grids, or new CSS components. That work is owned by the next step.
- **Logging** — `compute_dashboard` does not log on the happy path (these are read-only queries that run on every dashboard load). The route logs `SQLAlchemyError` via `current_app.logger.error(...)` consistent with the existing pattern in `app.py`.

## Definition of done

- [ ] `GET /dashboard` as a logged-out user redirects to `/login` (existing `@login_required` behaviour, unchanged).
- [ ] `GET /dashboard` (no query string) as the seeded `demo@fincheck.dev` user renders `dashboard.html` with HTTP 200 and shows: total spent for May 2026, expense count `8`, average computed correctly, a category breakdown that sums to the same total, the 5 most recent demo expenses, and a daily series with one row per distinct seed-expense date.
- [ ] `GET /dashboard?period=last_month` renders the previous calendar month's data; for the demo user against the frozen 2026-05-22 "today", that means April 2026 with all zeros and the empty-state rows.
- [ ] `GET /dashboard?period=all_time` renders aggregations over every expense the user has (no date filter applied) — verifiable by cross-checking against `SELECT SUM(amount), COUNT(*) FROM expenses WHERE user_id=<id>;` in `psql`.
- [ ] `GET /dashboard?period=garbage` falls back to `this_month` and returns HTTP 200 (no 400, no 500, no exception in the logs).
- [ ] A brand-new user with zero expenses lands on `/dashboard` and sees: total `0.00 <currency>`, count `0`, average `0.00 <currency>`, "No spending in this period.", "No expenses yet.", "No daily activity in this period." All on a single HTTP 200 render.
- [ ] Every numeric total displayed has exactly two decimal places (`1850.50`, not `1850.5` or `1850.4999999`). The currency code suffix matches the user's `default_currency`.
- [ ] Creating a second user with their own expenses and logging in as them shows **only** that user's data on `/dashboard`; the demo user's totals never leak. Verifiable by registering a second account, adding a row directly via `psql` (or letting it remain empty), and comparing dashboards.
- [ ] `compute_dashboard` issues only parameterised queries — verifiable by setting `SQLALCHEMY_ECHO=True` locally and confirming every emitted SQL statement uses `%(param)s`-style bind parameters, never inlined literals from f-strings.
- [ ] The `/dashboard` route function body contains no `select(...)`, `func.*`, or `db.session.execute(...)` — all query construction lives in `database/services.py`.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
- [ ] Manual smoke test: log in as `demo@fincheck.dev` → land on `/dashboard` → cycle through all three period values via the selector → verify the numbers match expectations against the seed data → register a second user → confirm dashboard isolation → log out → confirm `/dashboard` redirects to `/login`.
