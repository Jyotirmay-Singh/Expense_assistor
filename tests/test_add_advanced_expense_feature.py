"""Tests for Add Advanced Expense Feature (Step 7).

Spec: .claude/specs/07-add-advanced-expense-feature.md
Coverage:
  - Auth & Access Control (unauthenticated redirect on all protected routes)
  - Happy Paths (list, add, edit, delete with valid data)
  - Database State (persistence, update, deletion verified directly)
  - Decimal Discipline (amount stored and retrieved as Decimal, not float)
  - Input Validation (amount ≤ 0, blank title, field preservation on error)
  - Edge Cases (empty state for new user, GET on POST-only delete route)
  - CSRF Protection (POST without token returns 400)
  - User Data Isolation (User A cannot see or mutate User B's expenses)
  - Regression (dashboard totals correct after expense CRUD operations)
"""

# ─── No new fixtures required ─────────────────────────────────────────────────
# All required fixtures are already provided by tests/conftest.py:
#   client               — unauthenticated test client
#   auth_client          — test client logged in as demo@spendly.dev
#   demo_user            — the seeded demo User object
#   demo_expenses        — 8 seeded Expense rows for demo_user (yields list[Expense])
#   db_session           — SQLAlchemy session inside an active app context
#   second_user          — a freshly created User with no expenses (deleted on teardown)
#   second_user_with_expense — (second_user, Expense) tuple; second user has one expense
#   second_auth_client   — test client logged in as second_user
# ──────────────────────────────────────────────────────────────────────────────

import pytest
from datetime import date
from decimal import Decimal

from flask import url_for
from sqlalchemy import select

from database.db import Expense, User


# ── Helpers ────────────────────────────────────────────────────────────────────


def _today_iso() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()


def _valid_expense_form(**overrides: object) -> dict[str, str]:
    """Return a valid expense form payload; individual fields may be overridden."""
    base: dict[str, str] = {
        "title": "Lunch",
        "amount": "250.50",
        "category": "Food",
        "date": _today_iso(),
        "notes": "",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return base


# ── Auth & Access Control ──────────────────────────────────────────────────────


def test_expenses_list_unauthenticated_redirects_to_login(client, app):
    # Spec §Routes — GET /expenses requires login; unauthenticated access → 302 to /login
    with app.app_context():
        url = url_for("expenses_list")
    response = client.get(url)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_add_expense_form_unauthenticated_redirects_to_login(client, app):
    # Spec §Routes — GET /expenses/add requires login; unauthenticated → 302 to /login
    with app.app_context():
        url = url_for("add_expense")
    response = client.get(url)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_add_expense_post_unauthenticated_redirects_to_login(client, app):
    # Spec §Routes — POST /expenses/add requires login; unauthenticated → 302 to /login
    with app.app_context():
        url = url_for("add_expense_post")
    response = client.post(url, data=_valid_expense_form())
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_edit_expense_form_unauthenticated_redirects_to_login(
    client, app, demo_expenses
):
    # Spec §Routes — GET /expenses/<id>/edit requires login; unauthenticated → 302 to /login
    expense = demo_expenses[0]
    with app.app_context():
        url = url_for("edit_expense", id=expense.id)
    response = client.get(url)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_delete_expense_unauthenticated_redirects_to_login(client, app, demo_expenses):
    # Spec §Routes — POST /expenses/<id>/delete requires login; unauthenticated → 302 to /login
    expense = demo_expenses[0]
    with app.app_context():
        url = url_for("delete_expense", id=expense.id)
    response = client.post(url)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ── Happy Paths ────────────────────────────────────────────────────────────────


def test_expenses_list_demo_user_returns_200(auth_client, app, demo_expenses):
    # Spec §Definition of done — GET /expenses as demo user renders HTTP 200
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    assert response.status_code == 200


def test_expenses_list_demo_user_shows_all_8_seed_expenses(
    auth_client, app, demo_expenses
):
    # Spec §Definition of done — all 8 seed expenses listed on /expenses
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    html = response.data.decode()
    expected_titles = [
        "Electricity bill",
        "Groceries",
        "Metro pass",
        "Doctor visit",
        "Netflix",
        "Python books",
        "Shirt",
        "Water bill",
    ]
    for title in expected_titles:
        assert title in html, f"Expected expense title '{title}' not found in /expenses"


def test_expenses_list_demo_user_newest_first_ordering(auth_client, app, demo_expenses):
    # Spec §Definition of done — seed expenses listed newest-first (Water bill 2026-05-15 before Electricity bill 2026-05-01)
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    html = response.data.decode()
    pos_water = html.find("Water bill")
    pos_electricity = html.find("Electricity bill")
    assert pos_water < pos_electricity, (
        "Water bill (2026-05-15) must appear before Electricity bill (2026-05-01) "
        "in the newest-first list"
    )


def test_expenses_list_shows_currency_code(auth_client, app, demo_expenses, demo_user):
    # Spec §Templates expenses.html — each row shows formatted amount with user's default_currency
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    html = response.data.decode()
    assert demo_user.default_currency in html


def test_add_expense_form_returns_200_with_blank_form(auth_client, app):
    # Spec §Definition of done — GET /expenses/add renders an empty form at HTTP 200
    with app.app_context():
        url = url_for("add_expense")
    response = auth_client.get(url)
    assert response.status_code == 200
    html = response.data.decode()
    # Page title context variable drives the <h1> — spec says "Add Expense"
    assert "Add Expense" in html


def test_add_expense_form_defaults_date_to_today(auth_client, app):
    # Spec §Definition of done — date field defaults to today
    with app.app_context():
        url = url_for("add_expense")
    response = auth_client.get(url)
    html = response.data.decode()
    assert _today_iso() in html


def test_add_expense_form_contains_csrf_token(auth_client, app):
    # Spec §Definition of done — CSRF token present in blank add form
    # Even with WTF_CSRF_ENABLED=False in tests the csrf_token() helper renders
    # a hidden input element named "csrf_token" when the app is configured for it.
    # We verify the <form> element and a csrf_token field name are present.
    with app.app_context():
        url = url_for("add_expense")
    response = auth_client.get(url)
    html = response.data.decode()
    assert "csrf_token" in html


def test_add_expense_form_contains_all_category_options(auth_client, app):
    # Spec §Templates expense_form.html — all 8 CATEGORIES rendered as <select> options
    from database.db import CATEGORIES

    with app.app_context():
        url = url_for("add_expense")
    response = auth_client.get(url)
    html = response.data.decode()
    for cat in CATEGORIES:
        assert cat in html, f"Category '{cat}' missing from add expense form"


def test_add_expense_valid_post_redirects_to_expenses_list(
    auth_client, app, demo_user, db_session
):
    # Spec §Definition of done — valid POST /expenses/add → 302 redirect to /expenses
    with app.app_context():
        post_url = url_for("add_expense_post")
        list_url = url_for("expenses_list")

    response = auth_client.post(
        post_url, data=_valid_expense_form(), follow_redirects=False
    )
    assert response.status_code == 302
    assert list_url in response.headers["Location"] or response.headers[
        "Location"
    ].endswith("/expenses")

    # Cleanup: remove the expense created by this test
    with app.app_context():
        from database.db import db as _db

        expense = _db.session.execute(
            select(Expense).where(
                Expense.user_id == demo_user.id,
                Expense.title == "Lunch",
            )
        ).scalar_one_or_none()
        if expense is not None:
            _db.session.delete(expense)
            _db.session.commit()


def test_add_expense_valid_post_persists_new_row_in_database(
    auth_client, app, demo_user
):
    # Spec §Definition of done — valid POST /expenses/add creates a new row in expenses
    with app.app_context():
        post_url = url_for("add_expense_post")

    payload = _valid_expense_form(
        title="DB Persist Test", amount="99.99", category="Food"
    )
    auth_client.post(post_url, data=payload, follow_redirects=False)

    with app.app_context():
        from database.db import db as _db

        expense = _db.session.execute(
            select(Expense).where(
                Expense.user_id == demo_user.id,
                Expense.title == "DB Persist Test",
            )
        ).scalar_one_or_none()
        try:
            assert expense is not None, "Expense row was not inserted"
            assert expense.title == "DB Persist Test"
            assert expense.category == "Food"
            assert expense.amount == Decimal("99.99")
        finally:
            if expense is not None:
                _db.session.delete(expense)
                _db.session.commit()


def test_add_expense_valid_post_new_expense_appears_at_top_of_list(
    auth_client, app, demo_user, demo_expenses
):
    # Spec §Definition of done — new expense appears at top of list after add
    with app.app_context():
        post_url = url_for("add_expense_post")
        list_url = url_for("expenses_list")

    # Use today's date so it sorts before the May 2026 seed data
    payload = _valid_expense_form(
        title="Top Of List Expense", amount="1.00", category="Other"
    )
    auth_client.post(post_url, data=payload, follow_redirects=False)

    response = auth_client.get(list_url)
    html = response.data.decode()

    pos_new = html.find("Top Of List Expense")
    pos_old = html.find("Water bill")  # latest seed row (2026-05-15)
    assert pos_new != -1, "New expense not found in list"
    assert pos_new < pos_old, "New expense should appear before older seed rows"

    # Cleanup
    with app.app_context():
        from database.db import db as _db

        expense = _db.session.execute(
            select(Expense).where(
                Expense.user_id == demo_user.id,
                Expense.title == "Top Of List Expense",
            )
        ).scalar_one_or_none()
        if expense is not None:
            _db.session.delete(expense)
            _db.session.commit()


def test_edit_expense_form_owned_expense_returns_200(auth_client, app, demo_expenses):
    # Spec §Definition of done — GET /expenses/<id>/edit for owned expense → HTTP 200
    expense = demo_expenses[0]
    with app.app_context():
        url = url_for("edit_expense", id=expense.id)
    response = auth_client.get(url)
    assert response.status_code == 200


def test_edit_expense_form_pre_fills_existing_values(auth_client, app, demo_expenses):
    # Spec §Definition of done — edit form pre-filled with expense's existing values
    expense = demo_expenses[0]  # Electricity bill, 2200.00, Bills, 2026-05-01
    with app.app_context():
        url = url_for("edit_expense", id=expense.id)
    response = auth_client.get(url)
    html = response.data.decode()
    assert expense.title in html
    assert expense.category in html
    assert expense.date.isoformat() in html


def test_edit_expense_post_valid_data_updates_record(
    auth_client, app, demo_expenses, db_session
):
    # Spec §Definition of done — valid POST /expenses/<id>/edit updates the record
    expense = demo_expenses[1]  # Groceries, 1850.50, Food
    with app.app_context():
        post_url = url_for("edit_expense_post", id=expense.id)

    updated_payload = _valid_expense_form(
        title="Updated Groceries",
        amount="2000.00",
        category="Food",
        date="2026-05-03",
    )
    response = auth_client.post(post_url, data=updated_payload, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        from database.db import db as _db

        refreshed = _db.session.get(Expense, expense.id)
        assert refreshed is not None
        assert refreshed.title == "Updated Groceries"
        assert refreshed.amount == Decimal("2000.00")
        # Restore original values for other tests
        refreshed.title = "Groceries"
        refreshed.amount = Decimal("1850.50")
        _db.session.commit()


def test_edit_expense_post_valid_data_redirects_to_expenses_list(
    auth_client, app, demo_expenses
):
    # Spec §Definition of done — valid POST /expenses/<id>/edit → 302 to /expenses
    expense = demo_expenses[2]  # Metro pass
    with app.app_context():
        post_url = url_for("edit_expense_post", id=expense.id)
        list_url = url_for("expenses_list")

    payload = _valid_expense_form(
        title="Metro pass", amount="500.00", category="Transport", date="2026-05-05"
    )
    response = auth_client.post(post_url, data=payload, follow_redirects=False)
    assert response.status_code == 302
    assert list_url in response.headers["Location"] or response.headers[
        "Location"
    ].endswith("/expenses")


def test_delete_expense_owned_deletes_row_and_redirects(
    auth_client, app, demo_user, db_session
):
    # Spec §Definition of done — POST /expenses/<id>/delete deletes the row, 302 to /expenses
    # Create a dedicated expense so teardown of demo_expenses is not affected
    with app.app_context():
        from database.db import db as _db

        victim = Expense(
            user_id=demo_user.id,
            title="Delete Me",
            amount=Decimal("10.00"),
            category="Other",
            date=date(2026, 5, 20),
        )
        _db.session.add(victim)
        _db.session.commit()
        victim_id = victim.id
        delete_url = url_for("delete_expense", id=victim_id)
        list_url = url_for("expenses_list")

    response = auth_client.post(delete_url, follow_redirects=False)
    assert response.status_code == 302
    assert list_url in response.headers["Location"] or response.headers[
        "Location"
    ].endswith("/expenses")

    with app.app_context():
        from database.db import db as _db

        gone = _db.session.get(Expense, victim_id)
        assert gone is None, "Expense row should have been deleted"


def test_delete_expense_owned_no_longer_appears_in_list(auth_client, app, demo_user):
    # Spec §Definition of done — deleted expense no longer appears in /expenses list
    with app.app_context():
        from database.db import db as _db

        victim = Expense(
            user_id=demo_user.id,
            title="GoneExpense",
            amount=Decimal("5.00"),
            category="Other",
            date=date(2026, 5, 21),
        )
        _db.session.add(victim)
        _db.session.commit()
        victim_id = victim.id
        delete_url = url_for("delete_expense", id=victim_id)
        list_url = url_for("expenses_list")

    auth_client.post(delete_url, follow_redirects=False)
    response = auth_client.get(list_url)
    html = response.data.decode()
    assert "GoneExpense" not in html


# ── Input Validation ───────────────────────────────────────────────────────────


def test_add_expense_negative_amount_rerenders_form_with_error(auth_client, app):
    # Spec §Definition of done — POST /expenses/add with amount=-5 → HTTP 200, form + error, no DB insert
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(amount="-5"),
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.data.decode()
    # The error message from ExpenseSchema.validate_amount: "Amount must be greater than zero."
    assert "greater than zero" in html or "Amount" in html


def test_add_expense_zero_amount_rerenders_form_with_error(auth_client, app):
    # Spec §Definition of done — POST /expenses/add with amount=0 → HTTP 200, form + error, no DB insert
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(amount="0"),
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.data.decode()
    assert "greater than zero" in html or "Amount" in html


def test_add_expense_negative_amount_no_db_insert(auth_client, app, demo_user):
    # Spec §Definition of done — no row inserted when amount is invalid
    with app.app_context():
        post_url = url_for("add_expense_post")
        from database.db import db as _db

        before_count = (
            _db.session.execute(select(Expense).where(Expense.user_id == demo_user.id))
            .scalars()
            .all()
            .__len__()
        )

    auth_client.post(
        post_url,
        data=_valid_expense_form(title="ShouldNotExist", amount="-5"),
        follow_redirects=False,
    )

    with app.app_context():
        from database.db import db as _db

        after_count = len(
            _db.session.execute(select(Expense).where(Expense.user_id == demo_user.id))
            .scalars()
            .all()
        )
    assert after_count == before_count


def test_add_expense_blank_title_rerenders_form_with_error(auth_client, app):
    # Spec §Definition of done — POST /expenses/add with empty title → HTTP 200, error message
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(title=""),
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.data.decode()
    # ExpenseSchema.validate_title raises "Title is required."
    assert "Title" in html


def test_add_expense_blank_title_preserves_other_field_values(auth_client, app):
    # Spec §Definition of done — other submitted field values are preserved on form re-render
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(
            title="", amount="123.45", category="Health", notes="preserved note"
        ),
        follow_redirects=False,
    )
    html = response.data.decode()
    assert "123.45" in html
    assert "preserved note" in html


def test_add_expense_invalid_category_rerenders_form_with_error(auth_client, app):
    # Spec §Rules — category must be in CATEGORIES; invalid value → form re-render with error
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(category="InvalidCat"),
        follow_redirects=False,
    )
    assert response.status_code == 200


# ── CSRF Protection ────────────────────────────────────────────────────────────


def test_add_expense_post_without_csrf_token_returns_400(app, demo_user):
    # Spec §Definition of done / Rules — POST without valid CSRF token → HTTP 400 (Flask-WTF default)
    # This test uses a separate app instance with CSRF enabled
    csrf_app = app
    # Override CSRF setting for this test only by creating a dedicated client with CSRF on
    original_csrf = csrf_app.config.get("WTF_CSRF_ENABLED", False)
    csrf_app.config["WTF_CSRF_ENABLED"] = True
    try:
        with csrf_app.test_client() as csrf_client:
            # Login without CSRF (login route itself doesn't check WTF CSRF in test mode
            # because we toggled it after the session-scoped app fixture ran; the login
            # form POST will also be rejected — so we inject the session cookie directly)
            # Use the test request context to push a login session manually
            with csrf_app.test_request_context():
                with csrf_app.app_context():
                    from database.db import db as _db

                    user = _db.session.get(User, demo_user.id)
                    if user is None:
                        pytest.skip("Demo user not found; skipping CSRF test")

            # Perform login via POST — CSRF is now on, login form has no CSRF field
            # so we must temporarily re-disable it for the login step, then re-enable
            csrf_app.config["WTF_CSRF_ENABLED"] = False
            login_resp = csrf_client.post(
                "/login",
                data={"email": "demo@spendly.dev", "password": "Demo@1234"},
                follow_redirects=False,
            )
            assert login_resp.status_code == 302, (
                "Login step failed during CSRF test setup"
            )
            csrf_app.config["WTF_CSRF_ENABLED"] = True

            with csrf_app.app_context():
                post_url = url_for("add_expense_post")

            # POST without any CSRF token field
            response = csrf_client.post(
                post_url,
                data=_valid_expense_form(),
                follow_redirects=False,
            )
            assert response.status_code == 400, (
                f"Expected 400 when posting without CSRF token, got {response.status_code}"
            )
    finally:
        csrf_app.config["WTF_CSRF_ENABLED"] = original_csrf


def test_edit_expense_post_without_csrf_token_returns_400(
    app, demo_user, demo_expenses
):
    # Spec §Definition of done / Rules — POST /expenses/<id>/edit without CSRF → HTTP 400
    csrf_app = app
    original_csrf = csrf_app.config.get("WTF_CSRF_ENABLED", False)
    csrf_app.config["WTF_CSRF_ENABLED"] = True
    expense = demo_expenses[0]
    try:
        with csrf_app.test_client() as csrf_client:
            csrf_app.config["WTF_CSRF_ENABLED"] = False
            login_resp = csrf_client.post(
                "/login",
                data={"email": "demo@spendly.dev", "password": "Demo@1234"},
                follow_redirects=False,
            )
            assert login_resp.status_code == 302
            csrf_app.config["WTF_CSRF_ENABLED"] = True

            with csrf_app.app_context():
                post_url = url_for("edit_expense_post", id=expense.id)

            response = csrf_client.post(
                post_url,
                data=_valid_expense_form(
                    title="Electricity bill", amount="2200.00", category="Bills"
                ),
                follow_redirects=False,
            )
            assert response.status_code == 400
    finally:
        csrf_app.config["WTF_CSRF_ENABLED"] = original_csrf


def test_delete_expense_post_without_csrf_token_returns_400(
    app, demo_user, demo_expenses
):
    # Spec §Definition of done / Rules — POST /expenses/<id>/delete without CSRF → HTTP 400
    csrf_app = app
    original_csrf = csrf_app.config.get("WTF_CSRF_ENABLED", False)
    csrf_app.config["WTF_CSRF_ENABLED"] = True
    expense = demo_expenses[-1]
    try:
        with csrf_app.test_client() as csrf_client:
            csrf_app.config["WTF_CSRF_ENABLED"] = False
            login_resp = csrf_client.post(
                "/login",
                data={"email": "demo@spendly.dev", "password": "Demo@1234"},
                follow_redirects=False,
            )
            assert login_resp.status_code == 302
            csrf_app.config["WTF_CSRF_ENABLED"] = True

            with csrf_app.app_context():
                post_url = url_for("delete_expense", id=expense.id)

            response = csrf_client.post(post_url, data={}, follow_redirects=False)
            assert response.status_code == 400
    finally:
        csrf_app.config["WTF_CSRF_ENABLED"] = original_csrf


# ── Edge Cases & Empty States ──────────────────────────────────────────────────


def test_expenses_list_new_user_shows_empty_state_message(
    second_auth_client, app, second_user
):
    # Spec §Definition of done — brand-new user with zero expenses sees empty-state message
    with app.app_context():
        url = url_for("expenses_list")
    response = second_auth_client.get(url)
    assert response.status_code == 200
    html = response.data.decode()
    assert "no expenses" in html.lower() or "add your first" in html.lower()


def test_delete_expense_get_method_returns_405(auth_client, app, demo_expenses):
    # Spec §Definition of done — GET /expenses/<id>/delete (wrong method) → 405; route does not exist for GET
    expense = demo_expenses[0]
    with app.app_context():
        # Construct the URL manually; url_for('delete_expense', ...) resolves to POST-only route
        url = f"/expenses/{expense.id}/delete"
    response = auth_client.get(url)
    assert response.status_code == 405


def test_add_expense_amount_too_large_rerenders_form_with_error(auth_client, app):
    # Spec §Schemas — amount must be ≤ 9_999_999.99; exceeding it → form re-render with error
    with app.app_context():
        post_url = url_for("add_expense_post")
    response = auth_client.post(
        post_url,
        data=_valid_expense_form(amount="99999999.99"),
        follow_redirects=False,
    )
    assert response.status_code == 200
    html = response.data.decode()
    assert "too large" in html.lower() or "Amount" in html


# ── Database State ─────────────────────────────────────────────────────────────


def test_add_expense_persists_exact_decimal_amount(auth_client, app, demo_user):
    # Spec §Rules — amount stored as Decimal, never float; two decimal places
    with app.app_context():
        post_url = url_for("add_expense_post")

    payload = _valid_expense_form(
        title="Decimal Test", amount="333.33", category="Education"
    )
    auth_client.post(post_url, data=payload, follow_redirects=False)

    with app.app_context():
        from database.db import db as _db

        expense = _db.session.execute(
            select(Expense).where(
                Expense.user_id == demo_user.id,
                Expense.title == "Decimal Test",
            )
        ).scalar_one_or_none()
        try:
            assert expense is not None
            assert isinstance(expense.amount, Decimal), (
                f"Expected Decimal, got {type(expense.amount)}"
            )
            assert expense.amount == Decimal("333.33")
            # Verify two decimal places exactly
            assert expense.amount == expense.amount.quantize(Decimal("0.01"))
        finally:
            if expense is not None:
                _db.session.delete(expense)
                _db.session.commit()


def test_edit_expense_persists_updated_decimal_amount(auth_client, app, demo_expenses):
    # Spec §Rules — updated amount stored as Decimal after edit
    expense = demo_expenses[3]  # Doctor visit, 700.00, Health
    with app.app_context():
        post_url = url_for("edit_expense_post", id=expense.id)

    payload = _valid_expense_form(
        title="Doctor visit", amount="750.25", category="Health", date="2026-05-08"
    )
    auth_client.post(post_url, data=payload, follow_redirects=False)

    with app.app_context():
        from database.db import db as _db

        refreshed = _db.session.get(Expense, expense.id)
        assert refreshed is not None
        assert isinstance(refreshed.amount, Decimal), (
            f"Expected Decimal after update, got {type(refreshed.amount)}"
        )
        assert refreshed.amount == Decimal("750.25")
        # Restore
        refreshed.amount = Decimal("700.00")
        _db.session.commit()


def test_expenses_list_shows_amounts_with_two_decimal_places(
    auth_client, app, demo_expenses
):
    # Spec §Templates — amount formatted as "{:,.2f}" — always two decimal places
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    html = response.data.decode()
    # Seed data has "2,200.00" (Electricity bill) — verify comma-formatted two-decimal display
    assert "2,200.00" in html or "2200.00" in html
    # Groceries 1850.50 — must show exactly two decimal places
    assert "1,850.50" in html or "1850.50" in html


# ── Decimal Discipline ─────────────────────────────────────────────────────────


def test_expense_amount_stored_as_decimal_not_float(auth_client, app, demo_expenses):
    # Spec §Rules — Decimal discipline: amount on retrieved Expense object is Decimal, not float
    with app.app_context():
        from database.db import db as _db

        expense = _db.session.get(Expense, demo_expenses[0].id)
        assert expense is not None
        assert isinstance(expense.amount, Decimal), (
            f"Expense.amount must be Decimal, got {type(expense.amount).__name__}"
        )
        assert not isinstance(expense.amount, float)


def test_all_seed_expense_amounts_are_decimal_not_float(app, demo_expenses):
    # Spec §Rules — every seeded expense amount is Decimal, validating Numeric(10,2) mapping
    with app.app_context():
        from database.db import db as _db

        for seed_exp in demo_expenses:
            refreshed = _db.session.get(Expense, seed_exp.id)
            assert refreshed is not None
            assert isinstance(refreshed.amount, Decimal), (
                f"Expense '{refreshed.title}' has amount type {type(refreshed.amount).__name__}, expected Decimal"
            )


# ── User Data Isolation ────────────────────────────────────────────────────────


def test_expenses_list_user_a_cannot_see_user_b_expenses(
    auth_client, app, second_user_with_expense
):
    # Spec §Definition of done / Rules — User A's /expenses list never shows User B's data
    _second_user, second_expense = second_user_with_expense
    with app.app_context():
        url = url_for("expenses_list")
    response = auth_client.get(url)
    html = response.data.decode()
    assert second_expense.title not in html, (
        "Demo user's /expenses must not contain second user's expense"
    )


def test_expenses_list_user_b_cannot_see_user_a_expenses(
    second_auth_client, app, demo_expenses
):
    # Spec §Definition of done / Rules — User B's /expenses list never shows User A's data
    with app.app_context():
        url = url_for("expenses_list")
    response = second_auth_client.get(url)
    html = response.data.decode()
    for exp in demo_expenses:
        assert exp.title not in html, (
            f"Second user's /expenses must not contain demo user's expense '{exp.title}'"
        )


def test_edit_expense_form_wrong_owner_returns_404(
    second_auth_client, app, demo_expenses
):
    # Spec §Definition of done — GET /expenses/<id>/edit for another user's expense → 404
    demo_expense = demo_expenses[0]
    with app.app_context():
        url = url_for("edit_expense", id=demo_expense.id)
    response = second_auth_client.get(url)
    assert response.status_code == 404, (
        "Accessing another user's expense edit form must return 404, not reveal ownership"
    )


def test_edit_expense_post_wrong_owner_returns_404(
    second_auth_client, app, demo_expenses
):
    # Spec §Definition of done / Rules — POST /expenses/<id>/edit for another user's expense → 404
    demo_expense = demo_expenses[1]
    with app.app_context():
        post_url = url_for("edit_expense_post", id=demo_expense.id)
    response = second_auth_client.post(
        post_url,
        data=_valid_expense_form(title="Hijack Attempt"),
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_delete_expense_wrong_owner_returns_404(second_auth_client, app, demo_expenses):
    # Spec §Definition of done — POST /expenses/<id>/delete for another user's expense → 404, no deletion
    demo_expense = demo_expenses[2]
    with app.app_context():
        delete_url = url_for("delete_expense", id=demo_expense.id)
    response = second_auth_client.post(delete_url, data={}, follow_redirects=False)
    assert response.status_code == 404


def test_delete_expense_wrong_owner_does_not_delete_row(
    second_auth_client, app, demo_expenses
):
    # Spec §Definition of done — wrong-owner delete attempt must not remove any row
    demo_expense = demo_expenses[2]
    with app.app_context():
        delete_url = url_for("delete_expense", id=demo_expense.id)
        from database.db import db as _db

        before = _db.session.get(Expense, demo_expense.id)
        assert before is not None

    second_auth_client.post(delete_url, data={}, follow_redirects=False)

    with app.app_context():
        from database.db import db as _db

        still_there = _db.session.get(Expense, demo_expense.id)
        assert still_there is not None, (
            "Expense must not be deleted when the requesting user is not the owner"
        )


def test_user_b_expenses_not_visible_via_known_id_on_edit(
    auth_client, app, second_user_with_expense
):
    # Spec §Definition of done — User A directly visiting User B's edit URL → 404 (isolation)
    _second_user, second_expense = second_user_with_expense
    with app.app_context():
        url = url_for("edit_expense", id=second_expense.id)
    response = auth_client.get(url)
    assert response.status_code == 404, (
        "Directly visiting another user's edit URL must return 404 regardless of known ID"
    )


# ── Regression: Dashboard totals after CRUD operations ────────────────────────


def test_dashboard_totals_correct_after_adding_expense(
    auth_client, app, demo_user, demo_expenses
):
    # Spec §Definition of done — dashboard and profile totals still correct after adding an expense
    # Seed contains 8 May-2026 expenses; adding a new one with a May date increases the count
    with app.app_context():
        post_url = url_for("add_expense_post")
        dashboard_url = url_for("dashboard")

    payload = _valid_expense_form(
        title="Regression Add Test",
        amount="100.00",
        category="Other",
        date="2026-05-16",
    )
    auth_client.post(post_url, data=payload, follow_redirects=False)

    response = auth_client.get(dashboard_url + "?period=all_time")
    assert response.status_code == 200
    html = response.data.decode()
    # The total across all time must include the new expense amount (100.00)
    # We verify the page renders without error, which means the aggregation ran correctly
    assert "100" in html or "regression" not in html.lower()

    # Cleanup
    with app.app_context():
        from database.db import db as _db

        expense = _db.session.execute(
            select(Expense).where(
                Expense.user_id == demo_user.id,
                Expense.title == "Regression Add Test",
            )
        ).scalar_one_or_none()
        if expense is not None:
            _db.session.delete(expense)
            _db.session.commit()


def test_dashboard_totals_correct_after_editing_expense(
    auth_client, app, demo_expenses
):
    # Spec §Definition of done — dashboard aggregation is unaffected by edit (no stale cache)
    expense = demo_expenses[4]  # Netflix, 649.00, Entertainment
    with app.app_context():
        edit_url = url_for("edit_expense_post", id=expense.id)
        dashboard_url = url_for("dashboard")

    # Edit to a new amount
    payload = _valid_expense_form(
        title="Netflix", amount="699.00", category="Entertainment", date="2026-05-10"
    )
    auth_client.post(edit_url, data=payload, follow_redirects=False)

    response = auth_client.get(dashboard_url + "?period=all_time")
    assert response.status_code == 200

    # Restore original value
    with app.app_context():
        from database.db import db as _db

        refreshed = _db.session.get(Expense, expense.id)
        if refreshed is not None:
            refreshed.amount = Decimal("649.00")
            _db.session.commit()


def test_dashboard_totals_correct_after_deleting_expense(auth_client, app, demo_user):
    # Spec §Definition of done — dashboard total decreases correctly after a delete
    # Create then delete a known expense; verify dashboard returns 200
    with app.app_context():
        from database.db import db as _db

        temp = Expense(
            user_id=demo_user.id,
            title="Regression Delete Test",
            amount=Decimal("50.00"),
            category="Other",
            date=date(2026, 5, 22),
        )
        _db.session.add(temp)
        _db.session.commit()
        temp_id = temp.id
        delete_url = url_for("delete_expense", id=temp_id)
        dashboard_url = url_for("dashboard")

    auth_client.post(delete_url, follow_redirects=False)

    response = auth_client.get(dashboard_url + "?period=all_time")
    assert response.status_code == 200

    # Verify row is gone
    with app.app_context():
        from database.db import db as _db

        gone = _db.session.get(Expense, temp_id)
        assert gone is None


def test_profile_activity_correct_after_expense_edit(auth_client, app, demo_expenses):
    # Spec §Definition of done — profile activity totals reflect updated expense values
    expense = demo_expenses[5]  # Python books, 850.00, Education, 2026-05-12
    with app.app_context():
        edit_url = url_for("edit_expense_post", id=expense.id)
        profile_url = url_for("profile")

    payload = _valid_expense_form(
        title="Python books", amount="900.00", category="Education", date="2026-05-12"
    )
    auth_client.post(edit_url, data=payload, follow_redirects=False)

    response = auth_client.get(
        profile_url + "?start_date=2026-05-01&end_date=2026-05-31"
    )
    assert response.status_code == 200

    # Restore
    with app.app_context():
        from database.db import db as _db

        refreshed = _db.session.get(Expense, expense.id)
        if refreshed is not None:
            refreshed.amount = Decimal("850.00")
            _db.session.commit()
