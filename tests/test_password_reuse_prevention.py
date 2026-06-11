"""Tests for password reuse prevention on /profile/change-password.

Coverage:
  - New password identical to the current password is rejected (schema-level)
  - New password matching a password from history is rejected
  - History is pruned to the last 5 entries; older passwords become reusable
  - A successful change records the previous password hash in password_history
  - Wrong current password still produces the existing error message
"""

from flask import url_for
from sqlalchemy import delete, select
from werkzeug.security import check_password_hash

from database.db import PasswordHistory, User
from database.db import db as _db

_DEMO_PASSWORD = "Demo@1234"


def _change_password_url(app) -> str:
    with app.app_context():
        return url_for("change_password_route")


def _change_password(auth_client, post_url, current, new, confirm=None):
    return auth_client.post(
        post_url,
        data={
            "current_password": current,
            "new_password": new,
            "confirm_password": new if confirm is None else confirm,
        },
        follow_redirects=True,
    )


def _restore_demo_user(app, demo_user) -> None:
    """Reset demo_user's password to the seed password and clear its history."""
    with app.app_context():
        user = _db.session.get(User, demo_user.id)
        user.set_password(_DEMO_PASSWORD)
        _db.session.execute(
            delete(PasswordHistory).where(PasswordHistory.user_id == demo_user.id)
        )
        _db.session.commit()


def test_change_password_to_same_password_rejected(auth_client, app, demo_user):
    # Schema-level check: new password identical to current password is rejected.
    post_url = _change_password_url(app)
    response = _change_password(auth_client, post_url, _DEMO_PASSWORD, _DEMO_PASSWORD)
    assert response.status_code == 200
    assert (
        b"New password must be different from your current password." in response.data
    )
    _restore_demo_user(app, demo_user)


def test_change_password_success_records_history(auth_client, app, demo_user):
    post_url = _change_password_url(app)
    try:
        response = _change_password(
            auth_client, post_url, _DEMO_PASSWORD, "NewPass@001"
        )
        assert response.status_code == 200
        assert b"Password updated." in response.data

        with app.app_context():
            history = (
                _db.session.execute(
                    select(PasswordHistory).where(
                        PasswordHistory.user_id == demo_user.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(history) == 1
            assert check_password_hash(history[0].password_hash, _DEMO_PASSWORD)
    finally:
        _restore_demo_user(app, demo_user)


def test_change_password_reuse_from_history_rejected(auth_client, app, demo_user):
    post_url = _change_password_url(app)
    try:
        response = _change_password(
            auth_client, post_url, _DEMO_PASSWORD, "NewPass@001"
        )
        assert b"Password updated." in response.data

        # Changing back to the original password should be rejected — it's
        # still in the history.
        response = _change_password(
            auth_client, post_url, "NewPass@001", _DEMO_PASSWORD
        )
        assert response.status_code == 200
        assert b"You cannot reuse a previous password." in response.data
    finally:
        _restore_demo_user(app, demo_user)


def test_change_password_history_pruned_allows_reuse_after_limit(
    auth_client, app, demo_user
):
    post_url = _change_password_url(app)
    # passwords[0] is the seeded password; passwords[1..6] are 6 rotations.
    passwords = [_DEMO_PASSWORD] + [f"RotatePass@{i:03d}" for i in range(1, 7)]
    try:
        for i in range(1, len(passwords)):
            response = _change_password(
                auth_client, post_url, passwords[i - 1], passwords[i]
            )
            assert b"Password updated." in response.data, f"change {i} failed"

        with app.app_context():
            history = (
                _db.session.execute(
                    select(PasswordHistory).where(
                        PasswordHistory.user_id == demo_user.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(history) == 5

        # The original password has been pruned out of history, so it can be
        # reused now.
        response = _change_password(auth_client, post_url, passwords[-1], passwords[0])
        assert b"Password updated." in response.data
    finally:
        _restore_demo_user(app, demo_user)


def test_change_password_wrong_current_password(auth_client, app, demo_user):
    post_url = _change_password_url(app)
    response = _change_password(auth_client, post_url, "WrongPassword@1", "NewPass@002")
    assert response.status_code == 200
    assert b"Current password is incorrect." in response.data
    _restore_demo_user(app, demo_user)
