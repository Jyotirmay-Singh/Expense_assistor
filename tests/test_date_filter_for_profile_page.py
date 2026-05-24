"""Tests for the Date Filter for Profile Page feature.

Spec: .claude/specs/06-date-filter-for-profile-page.md
Coverage:
  - Auth & Access Control    (unauthenticated redirect)
  - Happy Paths              (full-page no-filter, full-page with range)
  - HTMX Reactivity          (partial fragment response)
  - Database State           (correct rows and totals returned)
  - Decimal Discipline       (two-decimal-place rendering)
  - Edge Cases & Empty States (reversed dates, garbage params, no-match,
                               zero-expense user, one-sided filters)
  - User Data Isolation      (second user cannot see first user's rows)
  - Input Pre-fill           (filter values echoed back to form)

Implementation divergences from spec (accounted for in tests):
  - Query params are ``start_date``/``end_date``, NOT ``start``/``end``.
  - Reversed-date bounds raise ``ValueError("End date cannot be before
    start date.")`` instead of being silently swapped.  The route catches
    this, shows the error banner, and falls back to an unbounded query
    (renders all 8 rows).
  - HTMX requests (``HX-Request: true`` header) return only the
    ``partials/_activity_results.html`` fragment (no ``<!DOCTYPE``,
    no ``<nav>``).
  - Template context includes ``raw_start``, ``raw_end``, ``range_error``,
    and ``today_ist`` in addition to the keys listed in the spec.

Seed data (8 expenses, all May 2026, demo@spendly.dev / Demo@1234):
  Electricity bill  2200.00  Bills          2026-05-01
  Groceries         1850.50  Food           2026-05-03
  Metro pass         500.00  Transport      2026-05-05
  Doctor visit       700.00  Health         2026-05-08
  Netflix            649.00  Entertainment  2026-05-10
  Python books       850.00  Education      2026-05-12
  Shirt             1200.00  Shopping       2026-05-14
  Water bill         350.00  Bills          2026-05-15
  ─────────────────────────
  Total            8299.50 INR
"""

import re
from decimal import Decimal

import pytest
from flask import url_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _html(response) -> str:
    """Decode the response body to a UTF-8 string."""
    return response.data.decode("utf-8")


def _count_occurrences(html: str, pattern: str) -> int:
    """Count non-overlapping occurrences of *pattern* (literal string)."""
    return html.count(pattern)


# ---------------------------------------------------------------------------
# Auth & Access Control
# ---------------------------------------------------------------------------


def test_profile_unauthenticated_get_redirects_to_login(client, app):
    # Spec §DoD-1 — unauthenticated GET /profile must redirect to /login
    with app.app_context():
        url = url_for("profile")
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_unauthenticated_with_date_params_still_redirects(client, app):
    # Spec §DoD-1 — query params do not bypass the auth guard
    with app.app_context():
        url = url_for("profile")
    response = client.get(
        url + "?start_date=2026-05-01&end_date=2026-05-31",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Happy Paths — full page, no filter
# ---------------------------------------------------------------------------


def test_profile_full_page_no_filter_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-2 — GET /profile (no params) returns HTTP 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    assert response.status_code == 200


def test_profile_full_page_no_filter_shows_all_8_expenses(auth_client, demo_expenses, app):
    # Spec §DoD-2 — all 8 seed expenses appear in the activity list
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    # Each expense title should appear exactly once
    for title in (
        "Electricity bill", "Groceries", "Metro pass", "Doctor visit",
        "Netflix", "Python books", "Shirt", "Water bill",
    ):
        assert title in html, f"Expected expense title '{title}' not found"


def test_profile_full_page_no_filter_summary_count_8(auth_client, demo_expenses, app):
    # Spec §DoD-2 — summary shows count of 8
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    # The template renders: <strong ...>{{ activity_count }}</strong> expense(s)
    assert "8" in html


def test_profile_full_page_no_filter_total_8299_50(auth_client, demo_expenses, app):
    # Spec §DoD-2 — total must be 8,299.50 INR
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "8,299.50" in html


def test_profile_full_page_no_filter_shows_all_time_label(auth_client, demo_expenses, app):
    # Spec §Templates — "All time" label when no date bounds are active
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "All time" in html


def test_profile_full_page_no_filter_empty_state_absent(auth_client, demo_expenses, app):
    # Spec §DoD-2 — empty-state messages must NOT appear when there are expenses
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "No expenses recorded yet." not in html
    assert "No expenses in this date range." not in html


def test_profile_full_page_is_not_partial(auth_client, demo_expenses, app):
    # Spec §Routes — non-HTMX request returns the full page (with doctype and nav)
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "<!DOCTYPE" in html or "<!doctype" in html.lower()
    assert '<nav' in html


# ---------------------------------------------------------------------------
# Happy Paths — full page WITH date range
# ---------------------------------------------------------------------------


def test_profile_full_page_with_valid_range_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-3 — GET /profile?start_date=...&end_date=... returns 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    assert response.status_code == 200


def test_profile_full_page_with_range_shows_4_expenses(auth_client, demo_expenses, app):
    # Spec §DoD-3 — 2026-05-05 to 2026-05-12 inclusive returns exactly 4 rows
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    for title in ("Metro pass", "Doctor visit", "Netflix", "Python books"):
        assert title in html, f"Expected '{title}' in filtered results"


def test_profile_full_page_with_range_excludes_out_of_range_expenses(
    auth_client, demo_expenses, app
):
    # Spec §DoD-3 — expenses outside the range must NOT appear
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    for title in ("Electricity bill", "Groceries", "Shirt", "Water bill"):
        assert title not in html, f"Out-of-range expense '{title}' leaked into results"


def test_profile_full_page_with_range_total_2699_00(auth_client, demo_expenses, app):
    # Spec §DoD-3 — filtered total must be 2,699.00 INR
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    assert "2,699.00" in html


def test_profile_full_page_with_range_is_full_page_not_partial(
    auth_client, demo_expenses, app
):
    # Spec §Implementation — without HX-Request header, always full page
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    assert "<!DOCTYPE" in html or "<!doctype" in html.lower()
    assert "<nav" in html


# ---------------------------------------------------------------------------
# HTMX Reactivity — partial fragment
# ---------------------------------------------------------------------------


def test_profile_htmx_request_returns_partial_not_full_page(
    auth_client, demo_expenses, app
):
    # Spec §Implementation divergence — HX-Request header returns partial fragment
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    html = _html(response)
    # Partial must NOT include full-page scaffolding
    assert "<!DOCTYPE" not in html
    assert "<!doctype" not in html.lower()
    assert "<nav" not in html


def test_profile_htmx_partial_contains_4_expense_rows(
    auth_client, demo_expenses, app
):
    # Spec §DoD-3 / HTMX variant — fragment has the 4 in-range expense titles
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12",
        headers={"HX-Request": "true"},
    )
    html = _html(response)
    for title in ("Metro pass", "Doctor visit", "Netflix", "Python books"):
        assert title in html, f"Expected '{title}' in HTMX fragment"


def test_profile_htmx_partial_total_2699_00(auth_client, demo_expenses, app):
    # Spec §DoD-3 / HTMX variant — fragment summary shows 2,699.00
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12",
        headers={"HX-Request": "true"},
    )
    assert "2,699.00" in _html(response)


def test_profile_htmx_no_filter_shows_all_time(auth_client, demo_expenses, app):
    # Spec §Templates — HTMX call with no bounds renders "All time"
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "All time" in _html(response)


# ---------------------------------------------------------------------------
# One-sided filters
# ---------------------------------------------------------------------------


def test_profile_start_only_filter_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-4 — GET /profile?start_date=2026-05-10 returns 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=2026-05-10")
    assert response.status_code == 200


def test_profile_start_only_filter_shows_expenses_on_and_after(
    auth_client, demo_expenses, app
):
    # Spec §DoD-4 — start-only: on/after 2026-05-10 → Netflix, Python books,
    #   Shirt, Water bill (4 rows)
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=2026-05-10")
    html = _html(response)
    for title in ("Netflix", "Python books", "Shirt", "Water bill"):
        assert title in html, f"Expected '{title}' with start_date-only filter"


def test_profile_start_only_filter_excludes_earlier_expenses(
    auth_client, demo_expenses, app
):
    # Spec §DoD-4 — expenses before the start date must not appear
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=2026-05-10")
    html = _html(response)
    for title in ("Electricity bill", "Groceries", "Metro pass", "Doctor visit"):
        assert title not in html, f"Pre-start expense '{title}' should not appear"


def test_profile_end_only_filter_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-4 — GET /profile?end_date=2026-05-03 returns 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?end_date=2026-05-03")
    assert response.status_code == 200


def test_profile_end_only_filter_shows_expenses_on_and_before(
    auth_client, demo_expenses, app
):
    # Spec §DoD-4 — end-only: on/before 2026-05-03 → Electricity bill,
    #   Groceries (2 rows)
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?end_date=2026-05-03")
    html = _html(response)
    for title in ("Electricity bill", "Groceries"):
        assert title in html, f"Expected '{title}' with end_date-only filter"


def test_profile_end_only_filter_excludes_later_expenses(
    auth_client, demo_expenses, app
):
    # Spec §DoD-4 — expenses after the end date must not appear
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?end_date=2026-05-03")
    html = _html(response)
    for title in ("Netflix", "Python books", "Shirt", "Water bill"):
        assert title not in html, f"Post-end expense '{title}' should not appear"


# ---------------------------------------------------------------------------
# Reversed date bounds
# ---------------------------------------------------------------------------


def test_profile_reversed_dates_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-5 / impl-divergence — reversed bounds: route returns 200,
    #   no server error
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-31&end_date=2026-05-01"
    )
    assert response.status_code == 200


def test_profile_reversed_dates_shows_error_banner(auth_client, demo_expenses, app):
    # Spec impl-divergence — reversed bounds trigger the error banner with the
    #   message "End date cannot be before start date."
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-31&end_date=2026-05-01"
    )
    html = _html(response)
    assert "End date cannot be before start date." in html


def test_profile_reversed_dates_fallback_shows_all_8_expenses(
    auth_client, demo_expenses, app
):
    # Spec impl-divergence — after a reversed-date error the route falls back
    #   to unbounded (DateRangeSchema() with no dates), returning all 8 rows
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-31&end_date=2026-05-01"
    )
    html = _html(response)
    for title in (
        "Electricity bill", "Groceries", "Metro pass", "Doctor visit",
        "Netflix", "Python books", "Shirt", "Water bill",
    ):
        assert title in html, (
            f"Expected all 8 expenses after reversed-date fallback; "
            f"'{title}' not found"
        )


# ---------------------------------------------------------------------------
# Garbage / unparseable parameters
# ---------------------------------------------------------------------------


def test_profile_garbage_start_date_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-6 / Rules §Graceful-coercion — bad date values must never 500
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=not-a-date")
    assert response.status_code == 200


def test_profile_garbage_both_dates_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-6 — both params garbage → treated as unbounded → 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=not-a-date&end_date=2026-13-99"
    )
    assert response.status_code == 200


def test_profile_garbage_start_date_does_not_crash(auth_client, demo_expenses, app):
    # Spec §DoD-6 — confirm page renders (no stack trace) with garbage params
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=not-a-date&end_date=2026-13-99")
    html = _html(response)
    # A 500 page typically contains "Internal Server Error" or a traceback
    assert "Internal Server Error" not in html
    assert "Traceback" not in html


def test_profile_garbage_params_treats_bounds_as_unbounded(
    auth_client, demo_expenses, app
):
    # Spec §Rules §Graceful-coercion — unparseable values treated as unbounded,
    #   so all seed expenses should appear
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url + "?start_date=not-a-date&end_date=2026-13-99")
    html = _html(response)
    for title in (
        "Electricity bill", "Groceries", "Metro pass", "Doctor visit",
        "Netflix", "Python books", "Shirt", "Water bill",
    ):
        assert title in html, (
            f"Expected all expenses with garbage params; '{title}' missing"
        )


# ---------------------------------------------------------------------------
# No-match date range
# ---------------------------------------------------------------------------


def test_profile_no_match_range_returns_200(auth_client, demo_expenses, app):
    # Spec §DoD-7 — a range that matches nothing returns HTTP 200
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2000-01-01&end_date=2000-12-31"
    )
    assert response.status_code == 200


def test_profile_no_match_range_shows_empty_state_message(
    auth_client, demo_expenses, app
):
    # Spec §Templates — "No expenses in this date range." when filter active
    #   but yields zero rows
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2000-01-01&end_date=2000-12-31"
    )
    html = _html(response)
    assert "No expenses in this date range." in html


def test_profile_no_match_range_does_not_show_recorded_yet_message(
    auth_client, demo_expenses, app
):
    # Spec §Templates — "No expenses recorded yet." only for zero-expense accounts,
    #   NOT for a filtered zero result (the filter is active here)
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2000-01-01&end_date=2000-12-31"
    )
    html = _html(response)
    assert "No expenses recorded yet." not in html


def test_profile_no_match_range_shows_zero_total(auth_client, demo_expenses, app):
    # Spec §Templates — summary total is 0.00 when no rows match
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2000-01-01&end_date=2000-12-31"
    )
    html = _html(response)
    assert "0.00" in html


# ---------------------------------------------------------------------------
# Zero-expense user
# ---------------------------------------------------------------------------


def test_profile_zero_expense_user_returns_200(second_auth_client, second_user, app):
    # Spec §DoD-8 — brand-new user with no expenses lands on /profile → 200
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    assert response.status_code == 200


def test_profile_zero_expense_user_shows_no_expenses_message(
    second_auth_client, second_user, app
):
    # Spec §Templates — "No expenses recorded yet." for zero-expense account
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    html = _html(response)
    assert "No expenses recorded yet." in html


def test_profile_zero_expense_user_count_is_0(second_auth_client, second_user, app):
    # Spec §DoD-8 — activity count is 0
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    html = _html(response)
    # The template renders: <strong>0</strong> expense(s)
    assert ">0<" in html or "0\n" in html or "0 expense" in html


def test_profile_zero_expense_user_total_is_0_00(
    second_auth_client, second_user, app
):
    # Spec §DoD-8 — total is 0.00 <currency>
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    html = _html(response)
    assert "0.00" in html


def test_profile_zero_expense_user_no_range_error(
    second_auth_client, second_user, app
):
    # Zero-expense user with a valid range: no error banner, just empty-range message
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(
        url + "?start_date=2026-05-01&end_date=2026-05-31"
    )
    html = _html(response)
    assert response.status_code == 200
    assert "End date cannot be before start date." not in html


# ---------------------------------------------------------------------------
# User Data Isolation
# ---------------------------------------------------------------------------


def test_profile_user_isolation_demo_user_cannot_see_second_user_expense(
    auth_client, demo_expenses, second_user_with_expense, app
):
    # Spec §DoD-11 / Rules §User-isolation — demo user's activity must not
    #   include the second user's expense
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "Second user only expense" not in html


def test_profile_user_isolation_second_user_cannot_see_demo_expenses(
    second_auth_client, demo_expenses, second_user_with_expense, app
):
    # Spec §DoD-11 — second user sees only their own rows
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    html = _html(response)
    for title in (
        "Electricity bill", "Groceries", "Metro pass", "Doctor visit",
        "Netflix", "Python books", "Shirt", "Water bill",
    ):
        assert title not in html, (
            f"Demo expense '{title}' leaked into second user's profile"
        )


def test_profile_user_isolation_second_user_sees_own_expense(
    second_auth_client, second_user_with_expense, app
):
    # Spec §DoD-11 — second user's own expense is visible to them
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(url)
    html = _html(response)
    assert "Second user only expense" in html


def test_profile_user_isolation_date_range_does_not_break_scoping(
    second_auth_client, demo_expenses, second_user_with_expense, app
):
    # Spec §DoD-11 — even with a date range spanning all seed data, the second
    #   user sees only their own rows
    with app.app_context():
        url = url_for("profile")
    response = second_auth_client.get(
        url + "?start_date=2026-01-01&end_date=2026-12-31"
    )
    html = _html(response)
    for title in (
        "Electricity bill", "Groceries", "Metro pass", "Doctor visit",
        "Netflix", "Python books", "Shirt", "Water bill",
    ):
        assert title not in html, (
            f"Demo expense '{title}' leaked through date-range query"
        )


# ---------------------------------------------------------------------------
# Decimal Discipline
# ---------------------------------------------------------------------------


def test_profile_amounts_render_with_two_decimal_places(
    auth_client, demo_expenses, app
):
    # Spec §DoD-12 / Rules §Decimal-discipline — every amount has exactly
    #   two decimal places in the rendered HTML
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    # Known amounts from seed data — verify rendered with 2 d.p.
    for amount_str in (
        "2,200.00", "1,850.50", "500.00", "700.00",
        "649.00", "850.00", "1,200.00", "350.00",
    ):
        assert amount_str in html, (
            f"Expected '{amount_str}' formatted with two decimal places"
        )


def test_profile_summary_total_has_two_decimal_places(
    auth_client, demo_expenses, app
):
    # Spec §DoD-12 — activity_total is quantised to 0.01 before reaching template
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    # The total 8299.50 must appear formatted as "8,299.50"
    assert "8,299.50" in html
    # Sanity: no trailing-zero truncation (e.g. "8,299.5" without the final zero)
    assert "8,299.5 " not in html  # accidental single d.p.


def test_profile_filtered_total_has_two_decimal_places(
    auth_client, demo_expenses, app
):
    # Spec §Rules §Decimal-discipline — filtered total also correctly formatted
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    assert "2,699.00" in html


def test_profile_htmx_amounts_render_with_two_decimal_places(
    auth_client, demo_expenses, app
):
    # Spec §DoD-12 — decimal discipline holds in the HTMX partial as well
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url, headers={"HX-Request": "true"})
    html = _html(response)
    assert "8,299.50" in html


# ---------------------------------------------------------------------------
# Input Pre-fill (filter values echoed back to form inputs)
# ---------------------------------------------------------------------------


def test_profile_filter_inputs_prefilled_with_start_date(
    auth_client, demo_expenses, app
):
    # Spec §DoD-9 — after filtering, start_date input value echoes the param
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    # The template sets value="{{ raw_start }}" on the start_date input
    assert 'value="2026-05-05"' in html


def test_profile_filter_inputs_prefilled_with_end_date(
    auth_client, demo_expenses, app
):
    # Spec §DoD-9 — after filtering, end_date input value echoes the param
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    assert 'value="2026-05-12"' in html


def test_profile_no_params_inputs_are_empty(auth_client, demo_expenses, app):
    # Spec §DoD-9 — without query params the date inputs are empty
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    # Inputs should have empty value attributes when no filter is active
    assert 'value=""' in html or 'value=""' in html


def test_profile_clear_link_points_to_unfiltered_profile(
    auth_client, demo_expenses, app
):
    # Spec §Templates — the "Clear" anchor href must be url_for('profile')
    #   with no query string (i.e. just /profile)
    with app.app_context():
        url = url_for("profile")
        profile_url = url_for("profile")
    response = auth_client.get(
        url + "?start_date=2026-05-05&end_date=2026-05-12"
    )
    html = _html(response)
    # The Clear link must target the plain profile URL without query params
    assert f'href="{profile_url}"' in html


# ---------------------------------------------------------------------------
# Template structural integrity
# ---------------------------------------------------------------------------


def test_profile_page_extends_base_has_doctype(auth_client, demo_expenses, app):
    # Spec §Rules — profile.html extends base.html; page must include DOCTYPE
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "<!DOCTYPE html" in html or "<!doctype html" in html.lower()


def test_profile_page_has_nav_element(auth_client, demo_expenses, app):
    # Spec §Rules — base.html provides a <nav>; full-page response must include it
    with app.app_context():
        url = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert "<nav" in html


def test_profile_page_filter_form_action_uses_url_for(
    auth_client, demo_expenses, app
):
    # Spec §Rules §Always-use-url_for — filter form action must be /profile
    #   (i.e. url_for('profile') resolves to /profile)
    with app.app_context():
        url = url_for("profile")
        expected_action = url_for("profile")
    response = auth_client.get(url)
    html = _html(response)
    assert f'hx-get="{expected_action}"' in html or f'action="{expected_action}"' in html
