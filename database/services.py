from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import delete, func, select
from werkzeug.security import check_password_hash

from database.db import Expense, PasswordHistory, User, db
from database.schemas import (
    ChangePasswordSchema,
    ExpenseSchema,
    ProfileUpdateSchema,
)

PASSWORD_HISTORY_LIMIT = 5

# Soft-delete tuning: how long "Undo" works, and how long a soft-deleted row
# survives before being purged. PURGE_AFTER_SECONDS must stay well above
# UNDO_WINDOW_SECONDS so a row can never be purged mid-undo.
UNDO_WINDOW_SECONDS = 8
PURGE_AFTER_SECONDS = 60


def update_profile(user: User, data: ProfileUpdateSchema) -> None:
    user.display_name = data.display_name
    user.default_currency = data.default_currency
    db.session.commit()
    current_app.logger.info("Profile updated for user_id=%s", user.id)


def update_avatar(user: User, filename: str) -> None:
    user.avatar_filename = filename
    db.session.commit()
    current_app.logger.info("Avatar updated for user_id=%s", user.id)


def remove_avatar(user: User) -> str | None:
    old_filename = user.avatar_filename
    user.avatar_filename = None
    db.session.commit()
    current_app.logger.info("Avatar removed for user_id=%s", user.id)
    return old_filename


class PasswordChangeResult(Enum):
    WRONG_CURRENT_PASSWORD = "wrong_current_password"
    PASSWORD_REUSED = "password_reused"
    SUCCESS = "success"


def _is_password_reused(user: User, new_password: str) -> bool:
    if user.check_password(new_password):
        return True

    recent = (
        db.session.execute(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(PASSWORD_HISTORY_LIMIT)
        )
        .scalars()
        .all()
    )
    return any(check_password_hash(h.password_hash, new_password) for h in recent)


def _prune_password_history(user_id: int) -> None:
    keep_ids = (
        select(PasswordHistory.id)
        .where(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
        .limit(PASSWORD_HISTORY_LIMIT)
    )
    db.session.execute(
        delete(PasswordHistory).where(
            PasswordHistory.user_id == user_id,
            PasswordHistory.id.notin_(keep_ids),
        )
    )


def change_password(user: User, data: ChangePasswordSchema) -> PasswordChangeResult:
    if not user.check_password(data.current_password):
        return PasswordChangeResult.WRONG_CURRENT_PASSWORD

    if _is_password_reused(user, data.new_password):
        return PasswordChangeResult.PASSWORD_REUSED

    db.session.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    user.set_password(data.new_password)
    db.session.flush()
    _prune_password_history(user.id)
    db.session.commit()
    current_app.logger.info("Password changed for user_id=%s", user.id)
    return PasswordChangeResult.SUCCESS


# ------------------------------------------------------------------ #
# Dashboard aggregations                                               #
# ------------------------------------------------------------------ #

_IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> date:
    return datetime.now(tz=_IST).date()


def _period_bounds(
    period: str, start_date: date | None = None, end_date: date | None = None
) -> tuple[date | None, date | None]:
    if period == "custom":
        return (start_date, end_date)

    if period == "all_time":
        return (None, None)

    today = _today_ist()

    if period == "last_month":
        first_of_this = date(today.year, today.month, 1)
        last_of_prev = first_of_this - timedelta(days=1)
        _, last_day = monthrange(last_of_prev.year, last_of_prev.month)
        return (
            date(last_of_prev.year, last_of_prev.month, 1),
            date(last_of_prev.year, last_of_prev.month, last_day),
        )

    return (date(today.year, today.month, 1), today)


def _where_user_and_period(uid: int, lo: date | None, hi: date | None) -> list:
    clauses: list = [Expense.user_id == uid, Expense.deleted_at.is_(None)]
    if lo is not None:
        clauses.append(Expense.date >= lo)
    if hi is not None:
        clauses.append(Expense.date <= hi)
    return clauses


def _period_totals(uid: int, lo: date | None, hi: date | None) -> tuple[int, int]:
    total_raw, count = db.session.execute(
        select(
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        ).where(*_where_user_and_period(uid, lo, hi))
    ).one()
    return int(total_raw), int(count)


def _category_breakdown(
    uid: int,
    lo: date | None,
    hi: date | None,
    total_amount: int,
) -> list[dict[str, object]]:
    rows = db.session.execute(
        select(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), 0).label("cat_total"),
        )
        .where(*_where_user_and_period(uid, lo, hi))
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc(), Expense.category.asc())
    ).all()

    breakdown: list[dict[str, object]] = []
    for category, raw_total in rows:
        cat_total = int(raw_total)
        percent = round(cat_total / total_amount * 100) if total_amount > 0 else 0
        breakdown.append({"category": category, "total": cat_total, "percent": percent})
    return breakdown


def _recent_expenses(uid: int, lo: date | None, hi: date | None) -> list[Expense]:
    return list(
        db.session.execute(
            select(Expense)
            .where(*_where_user_and_period(uid, lo, hi))
            .order_by(Expense.date.desc(), Expense.id.desc())
            .limit(5)
        ).scalars()
    )


def _daily_series(
    uid: int, lo: date | None, hi: date | None
) -> list[dict[str, object]]:
    rows = db.session.execute(
        select(
            Expense.date,
            func.coalesce(func.sum(Expense.amount), 0).label("day_total"),
        )
        .where(*_where_user_and_period(uid, lo, hi))
        .group_by(Expense.date)
        .order_by(Expense.date.asc())
    ).all()
    return [
        {
            "date": d,
            "total": int(t),
        }
        for d, t in rows
    ]


def _median_amount(uid: int, lo: date | None, hi: date | None) -> int | None:
    result = db.session.execute(
        select(func.percentile_cont(0.5).within_group(Expense.amount)).where(
            *_where_user_and_period(uid, lo, hi)
        )
    ).scalar_one_or_none()
    if result is None:
        return None
    return int(Decimal(str(result)).to_integral_value(rounding=ROUND_HALF_UP))


def _busiest_day(uid: int, lo: date | None, hi: date | None) -> tuple[date, int] | None:
    row = db.session.execute(
        select(Expense.date, func.count(Expense.id).label("cnt"))
        .where(*_where_user_and_period(uid, lo, hi))
        .group_by(Expense.date)
        .order_by(func.count(Expense.id).desc(), Expense.date.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return (row[0], row[1])


def list_expenses_in_range(
    user_id: int, lo: date | None, hi: date | None
) -> list[Expense]:
    return list(
        db.session.execute(
            select(Expense)
            .where(*_where_user_and_period(user_id, lo, hi))
            .order_by(Expense.date.desc(), Expense.id.desc())
        ).scalars()
    )


def empty_dashboard_payload(
    user: User,
    period: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    lo, hi = _period_bounds(period, start_date, end_date)
    return {
        "total_amount": 0,
        "expense_count": 0,
        "average_amount": 0,
        "median_amount": None,
        "busiest_day_date": None,
        "busiest_day_count": 0,
        "category_breakdown": [],
        "recent_expenses": [],
        "daily_series": [],
        "currency": user.default_currency,
        "period_start": lo,
        "period_end": hi,
        "today_ist": _today_ist(),
    }


def compute_dashboard(
    user: User,
    period: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    lo, hi = _period_bounds(period, start_date, end_date)
    payload: dict[str, object] = empty_dashboard_payload(
        user, period, start_date, end_date
    )

    total, count = _period_totals(user.id, lo, hi)
    if count == 0:
        return payload

    total_q = total
    avg_q = int((Decimal(total) / count).to_integral_value(rounding=ROUND_HALF_UP))

    busiest = _busiest_day(user.id, lo, hi)
    recent = (
        list_expenses_in_range(user.id, lo, hi)
        if period == "custom"
        else _recent_expenses(user.id, lo, hi)
    )

    payload.update(
        total_amount=total_q,
        expense_count=count,
        average_amount=avg_q,
        median_amount=_median_amount(user.id, lo, hi),
        busiest_day_date=busiest[0] if busiest else None,
        busiest_day_count=busiest[1] if busiest else 0,
        category_breakdown=_category_breakdown(user.id, lo, hi, total),
        recent_expenses=recent,
        daily_series=_daily_series(user.id, lo, hi),
    )
    return payload


# ------------------------------------------------------------------ #
# Expense CRUD                                                         #
# ------------------------------------------------------------------ #


def list_user_expenses(user: User) -> list[Expense]:
    purge_expired_soft_deletes(user.id)
    return list(
        db.session.execute(
            select(Expense)
            .where(
                Expense.user_id == user.id,
                Expense.deleted_at.is_(None),
            )
            .order_by(Expense.date.desc(), Expense.id.desc())
        ).scalars()
    )


def get_expense_for_user(expense_id: int, user_id: int) -> Expense | None:
    return db.session.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def create_expense(user: User, data: ExpenseSchema) -> Expense:
    expense = Expense(
        user_id=user.id,
        title=data.title,
        amount=data.amount,
        category=data.category,
        date=data.date,
        notes=data.notes,
    )
    db.session.add(expense)
    db.session.commit()
    return expense


def update_expense(expense: Expense, data: ExpenseSchema) -> Expense:
    expense.title = data.title
    expense.amount = data.amount
    expense.category = data.category
    expense.date = data.date
    expense.notes = data.notes
    db.session.commit()
    return expense


def destroy_expense(expense_id: int, user_id: int) -> bool:
    expense = get_expense_for_user(expense_id, user_id)
    if expense is None:
        return False
    expense.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    return True


def restore_expense(expense_id: int, user_id: int) -> bool:
    expense = db.session.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
            Expense.deleted_at.is_not(None),
        )
    ).scalar_one_or_none()

    if expense is None:
        return False

    if datetime.now(timezone.utc) - expense.deleted_at > timedelta(
        seconds=UNDO_WINDOW_SECONDS
    ):
        return False

    expense.deleted_at = None
    db.session.commit()
    return True


def purge_expired_soft_deletes(user_id: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=PURGE_AFTER_SECONDS)
    result = db.session.execute(
        delete(Expense).where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_not(None),
            Expense.deleted_at < cutoff,
        )
    )
    db.session.commit()
    if result.rowcount:
        current_app.logger.info(
            "Purged %d soft-deleted expense(s) for user_id=%s",
            result.rowcount,
            user_id,
        )
    return result.rowcount
