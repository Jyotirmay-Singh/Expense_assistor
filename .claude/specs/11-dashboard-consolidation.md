# Spec: Dashboard Consolidation

## Overview

Spendly currently spreads related "look at my spending" functionality across three pages: the Dashboard (period-based KPIs/charts), Profile (a custom date-range "Spending activity" table), and Analytics (a placeholder "Coming Soon" page with no real functionality). This step consolidates everything into a single, more useful Dashboard: the Analytics tab is removed entirely, the Profile page is trimmed back to personal account information only, and the custom date-range filtering that used to live on Profile becomes a fourth "Custom" option alongside the existing This Month / Last Month / All Time period selector on the Dashboard. The Dashboard also gains two new at-a-glance statistics — median expense amount and "busiest day" (the date with the most transactions in the selected period) — and drops the personalized "Hello, {name}" greeting in favor of a plain "Dashboard" heading. No routes are added beyond extending `/dashboard`'s existing query parameters, and no new database tables or columns are introduced.

## Depends on

- **Step 1 (Database Setup)** through **Step 10 (Easy Readable UI)** — this step restructures `base.html` navigation, the `/dashboard` and `/profile` routes and templates, and the shared aggregation helpers in `database/services.py` introduced in Step 5 and Step 6. All of those must already exist and work before this pass begins.

## Routes

- `GET /dashboard` — **modified**, logged-in. Now accepts `period` of `this_month` | `last_month` | `all_time` | `custom`. When `period=custom`, also accepts `start_date` and `end_date` (ISO `YYYY-MM-DD`) query params. Invalid/missing custom dates fall back to `this_month` (same fallback behavior `coerce_period` already uses for invalid `period` values).
- `GET /profile` — **modified**, logged-in. No longer accepts `start_date`/`end_date` query params, no longer returns the HTMX partial response, no longer computes activity totals. Renders only personal info + edit profile + change password.
- `GET /analytics` — **removed**. Visiting `/analytics` after this change returns 404 (route deleted entirely).

No other new routes.

## Database changes

No new tables, columns, or constraints. Two new **read-only aggregate queries** are added to `database/services.py` against the existing `expenses` table:

- **Median expense amount** for the selected period — use PostgreSQL's `percentile_cont(0.5) WITHIN GROUP (ORDER BY amount)` via SQLAlchemy's `func.percentile_cont(0.5).within_group(Expense.amount)`.
- **Busiest day** (mode of `Expense.date`) for the selected period — `GROUP BY date`, `ORDER BY COUNT(*) DESC, date DESC LIMIT 1`, returning the date and its transaction count. Ties broken by most recent date.

Both return `None`/zero-value defaults when the period has no expenses (mirroring `empty_dashboard_payload`).

## Templates

- **Create:** none.
- **Modify:**
  - `templates/base.html` — remove the "Analytics" nav link (and its `aria-current` block) entirely. Dashboard, Expenses, Profile, and Sign out remain unchanged.
  - `templates/dashboard.html`:
    - Remove the `<h1 class="db-greeting">Hello, {{ user.display_name.split()[0] }}</h1>` text and replace with a static `<h1 class="db-greeting">Dashboard</h1>` (keep the existing class/styling so the heading hierarchy from Step 10 — one `h1`, nested `h2`s — is preserved; only the text changes).
    - Extend the `db-period-nav` with a fourth "Custom" option. Selecting "Custom" reveals a small inline date-range form (two `<input type="date">` fields + submit), styled with the existing `.form-input`/`.form-group` classes — same visual language as the old Profile filter form, just relocated. Use Alpine.js (`x-data`/`x-show`) purely for show/hide of the date inputs; submission is a normal `GET` to `/dashboard?period=custom&start_date=...&end_date=...` (no HTMX needed, consistent with the existing period links).
    - Add two new stat cards to the KPI area (reusing `.db-kpi-card` styling): "Median expense" (formatted like the other currency KPIs) and "Busiest day" (date + "N expenses", or an empty/dash state when the period has no expenses).
    - Update the "Recent expenses" section: for `this_month`/`last_month`/`all_time` it keeps showing the 5 most recent expenses (unchanged). For `period=custom`, the heading changes to "Expenses in range" and the table shows **all** matching expenses for the selected range (no 5-row cap), reusing `list_expenses_in_range` (already implemented for the old Profile activity feature).
  - `templates/profile.html` — remove the entire "Spending activity" `<article>` (the date-range filter form, the `#activity-results` div, and the `{% include "partials/_activity_results.html" %}`). The page keeps: avatar/header, "Account details" info card, "Edit profile" form, and "Change password" form — i.e. personal information only.
- **Delete:**
  - `templates/analytics.html`
  - `templates/partials/_activity_results.html` (its functionality is folded into `dashboard.html`'s expense table for `period=custom`)

## Files to change

- `app.py` — remove the `/analytics` route handler; update the `/dashboard` route to read/validate `start_date`/`end_date` when `period=custom` and pass them to `compute_dashboard`; simplify the `/profile` GET route to drop date-range handling, the HTMX partial branch, and the `profile_activity` call.
- `database/schemas.py` — extend `DASHBOARD_PERIODS` and `DashboardPeriodSchema.period` to include `"custom"`; add validation so `period=custom` requires valid `start_date`/`end_date` with `end_date >= start_date` (falling back to `this_month` on failure, matching existing `coerce_period` behavior). `DateRangeSchema` can be reused for the custom-range validation.
- `database/services.py` — add `_median_amount(uid, lo, hi)` and `_busiest_day(uid, lo, hi)` helper functions; update `_period_bounds`/`compute_dashboard`/`empty_dashboard_payload` to accept explicit `lo`/`hi` for the `custom` case and to include `median_amount`, `busiest_day_date`, and `busiest_day_count` in the payload; update the "recent expenses" logic so `period=custom` returns the full `list_expenses_in_range` result instead of the 5-row `_recent_expenses` result; remove `profile_activity` and `empty_activity_payload` (no longer used once `/profile` is simplified) — keep `list_expenses_in_range` since the dashboard now uses it.
- `templates/base.html`, `templates/dashboard.html`, `templates/profile.html` — as described above.
- `static/css/style.css` — only if the new "Custom" period inputs or the two extra KPI cards need minor layout tweaks (e.g. `.db-kpi-grid` may need `grid-template-columns` adjusted to fit 5 cards, or wrap responsively). Reuse existing `--space-*`/`--fs-*` tokens from Step 10 — no new hardcoded values.

## Files to create

No new files.

## New dependencies

No new dependencies.

## Rules for implementation

- Parameterised queries only.
- Passwords hashed with werkzeug.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- **Preserve heading hierarchy** — `dashboard.html` keeps exactly one `<h1>` (now reading "Dashboard") followed by `<h2>`s for each card section, as established in Step 10's accessibility pass.
- **No HTMX/JS for the new "Custom" period** — it must work as a plain `GET` request with query params, exactly like the existing This Month/Last Month/All Time links, so the page is fully functional without JavaScript (Alpine.js may still be used for purely cosmetic show/hide of the date inputs).
- **Keep the UI visually intact** — reuse existing CSS classes (`.db-kpi-card`, `.db-card`, `.db-period-nav`, `.db-period-btn`, `.form-input`, `.form-group`) for all new elements; do not introduce a new visual style system.
- Do not remove or rename `list_expenses_in_range` — it is reused by the new `period=custom` table.
- Do not touch `static/js/main.js` beyond what's strictly necessary (none expected).

## Definition of done

- [ ] `GET /analytics` returns 404, and the "Analytics" link no longer appears in the navbar for any page.
- [ ] `/profile` shows only the avatar/header, "Account details", "Edit profile", and "Change password" sections — no date-range filter or activity table.
- [ ] `/dashboard` period nav shows four options: This Month, Last Month, All Time, Custom.
- [ ] Selecting "Custom" reveals two date inputs; submitting a valid range reloads `/dashboard?period=custom&start_date=...&end_date=...` and all KPIs/charts/breakdown reflect that range.
- [ ] An invalid custom range (e.g. end before start, or missing dates) falls back to `this_month` without raising an error.
- [ ] For `this_month`/`last_month`/`all_time`, the expenses table is titled "Recent expenses" and shows at most 5 rows (unchanged from before). For `period=custom`, it is titled "Expenses in range" and shows every matching expense.
- [ ] Dashboard shows "Median expense" and "Busiest day" stat cards, both showing sensible empty states (e.g. "—") when the selected period has zero expenses, and correct values when expenses exist — verified against the seeded demo user's data for at least one period.
- [ ] The dashboard heading reads "Dashboard" (not "Hello, &lt;name&gt;") on every period.
- [ ] All existing functional flows continue to work unchanged: login, add/edit/delete expense, profile update, change password, and the three original period switches.
- [ ] `ruff check .` and `ruff format --check .` pass with zero warnings.
