"""
conftest.py — shared pytest fixtures for Spendly tests.

Database strategy: tests run against the real Postgres instance
(same connection used by the app: localhost:5544). Each fixture that
creates rows is responsible for cleaning them up in teardown so that
tests remain independent and do not pollute production seed data.
"""

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Make sure the project root is importable regardless of how pytest is invoked
# ---------------------------------------------------------------------------
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app import create_app  # noqa: E402 — must come after sys.path fix
from database.db import Expense, User, db as _db  # noqa: E402


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create a Flask application configured for testing.

    Points at the real Postgres container (port 5544) — identical to the
    development connection.  CSRF and TESTING flags are adjusted so the
    test client can submit forms without a real CSRF token.
    """
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,          # disable CSRF for form-POST tests
        WTF_CSRF_CHECK_DEFAULT=False,
        # Keep the same DB URI; override only if env var is set for CI
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "TEST_DATABASE_URL",
            flask_app.config.get(
                "SQLALCHEMY_DATABASE_URI",
                "postgresql+psycopg2://spendly:spendly@localhost:5544/spendly",
            ),
        ),
    )
    return flask_app


# ---------------------------------------------------------------------------
# Database session fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db(app):
    """Return the SQLAlchemy db extension bound to the test app."""
    with app.app_context():
        yield _db


# ---------------------------------------------------------------------------
# Request-scoped DB session helper
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(app):
    """Yield the SQLAlchemy session inside an active app context.

    Each test that uses this fixture gets a fresh app-context push/pop.
    """
    with app.app_context():
        yield _db.session


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(app):
    """Unauthenticated Flask test client."""
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Demo user fixture
# ---------------------------------------------------------------------------

_DEMO_EMAIL = "demo@spendly.dev"
_DEMO_PASSWORD = "Demo@1234"


@pytest.fixture()
def demo_user(app, db_session):
    """Ensure the seeded demo user exists and return it.

    If the user already exists (from seed_db or a previous test run) it is
    reused.  The fixture does NOT delete the demo user on teardown because it
    is shared seed data that other parts of the app rely on.
    """
    user = db_session.execute(
        select(User).filter_by(email=_DEMO_EMAIL)
    ).scalar_one_or_none()

    if user is None:
        user = User(
            name="Demo User",
            display_name="Demo",
            email=_DEMO_EMAIL,
            default_currency="INR",
            terms_accepted_at=datetime.now(timezone.utc),
        )
        user.set_password(_DEMO_PASSWORD)
        db_session.add(user)
        db_session.commit()

    return user


# ---------------------------------------------------------------------------
# Demo user expenses fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def demo_expenses(app, db_session, demo_user):
    """Ensure the 8 canonical May-2026 seed expenses exist for demo_user.

    If any of the expected expenses are missing they are inserted.  All rows
    are removed on teardown so subsequent test runs start clean.
    Yields the list of created (or found) Expense objects.
    """
    seed_rows = [
        dict(title="Electricity bill", amount=Decimal("2200.00"), category="Bills",         date=date(2026, 5, 1)),
        dict(title="Groceries",        amount=Decimal("1850.50"), category="Food",          date=date(2026, 5, 3)),
        dict(title="Metro pass",       amount=Decimal("500.00"),  category="Transport",     date=date(2026, 5, 5)),
        dict(title="Doctor visit",     amount=Decimal("700.00"),  category="Health",        date=date(2026, 5, 8)),
        dict(title="Netflix",          amount=Decimal("649.00"),  category="Entertainment", date=date(2026, 5, 10)),
        dict(title="Python books",     amount=Decimal("850.00"),  category="Education",     date=date(2026, 5, 12)),
        dict(title="Shirt",            amount=Decimal("1200.00"), category="Shopping",      date=date(2026, 5, 14)),
        dict(title="Water bill",       amount=Decimal("350.00"),  category="Bills",         date=date(2026, 5, 15)),
    ]

    # Wipe any pre-existing expenses for demo_user to guarantee a clean slate
    existing = db_session.execute(
        select(Expense).filter_by(user_id=demo_user.id)
    ).scalars().all()
    for exp in existing:
        db_session.delete(exp)
    db_session.commit()

    expenses: list[Expense] = []
    for row in seed_rows:
        exp = Expense(user_id=demo_user.id, **row)
        db_session.add(exp)
        expenses.append(exp)
    db_session.commit()

    yield expenses

    # Teardown: remove the expenses inserted by this fixture
    for exp in expenses:
        obj = db_session.get(Expense, exp.id)
        if obj is not None:
            db_session.delete(obj)
    db_session.commit()


# ---------------------------------------------------------------------------
# Authenticated client (demo user)
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_client(app, demo_user):
    """Test client that is already logged in as the demo user.

    Uses the /login form POST so Flask-Login session cookies are set
    correctly — identical to the real user login flow.
    """
    with app.test_client() as c:
        response = c.post(
            "/login",
            data={"email": _DEMO_EMAIL, "password": _DEMO_PASSWORD},
            follow_redirects=False,
        )
        # A successful login redirects to /dashboard (302)
        assert response.status_code == 302, (
            f"Demo user login failed — got {response.status_code}. "
            "Ensure the demo user exists in the DB and the password is correct."
        )
        yield c


# ---------------------------------------------------------------------------
# Second (isolated) user fixture
# ---------------------------------------------------------------------------

_SECOND_EMAIL = "second_tester_unique@spendly-tests.io"
_SECOND_PASSWORD = "Test@5678"


@pytest.fixture()
def second_user(app, db_session):
    """Create a brand-new user with no expenses.  Deleted on teardown."""
    # Clean up any leftover from a previous run
    old = db_session.execute(
        select(User).filter_by(email=_SECOND_EMAIL)
    ).scalar_one_or_none()
    if old is not None:
        # cascade delete removes expenses too
        db_session.delete(old)
        db_session.commit()

    user = User(
        name="Second Tester",
        display_name="Tester",
        email=_SECOND_EMAIL,
        default_currency="INR",
        terms_accepted_at=datetime.now(timezone.utc),
    )
    user.set_password(_SECOND_PASSWORD)
    db_session.add(user)
    db_session.commit()

    yield user

    obj = db_session.get(User, user.id)
    if obj is not None:
        db_session.delete(obj)
        db_session.commit()


@pytest.fixture()
def second_user_with_expense(app, db_session, second_user):
    """Second user with one expense; lets isolation tests verify no cross-leak."""
    exp = Expense(
        user_id=second_user.id,
        title="Second user only expense",
        amount=Decimal("99.99"),
        category="Other",
        date=date(2026, 5, 7),
    )
    db_session.add(exp)
    db_session.commit()

    yield second_user, exp

    obj = db_session.get(Expense, exp.id)
    if obj is not None:
        db_session.delete(obj)
        db_session.commit()


@pytest.fixture()
def second_auth_client(app, second_user):
    """Test client logged in as the second user."""
    with app.test_client() as c:
        resp = c.post(
            "/login",
            data={"email": _SECOND_EMAIL, "password": _SECOND_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"Second user login failed — got {resp.status_code}."
        )
        yield c
