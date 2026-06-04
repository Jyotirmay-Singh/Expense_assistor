from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import func, select

from database.db import Expense, User, db
from database.schemas import (
    ChangePasswordSchema,
    DateRangeSchema,
    ExpenseSchema,
    ProfileUpdateSchema,
)


def update_profile(user: User, data: ProfileUpdateSchema) -> None:
    user.display_name = data.display_name
    user.default_currency = data.default_currency
    db.session.commit()
    current_app.logger.info("Profile updated for user_id=%s", user.id)


def change_password(user: User, data: ChangePasswordSchema) -> bool:
    if not user.check_password(data.current_password):
        return False

    user.set_password(data.new_password)
    db.session.commit()
    current_app.logger.info("Password changed for user_id=%s", user.id)
    return True


# ------------------------------------------------------------------ #
# Dashboard aggregations                                               #
# ------------------------------------------------------------------ #

_IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> date:
    return datetime.now(tz=_IST).date()


def _period_bounds(period: str) -> tuple[date | None, date | None]:
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
    clauses: list = [Expense.user_id == uid]
    if lo is not None:
        clauses.append(Expense.date >= lo)
    if hi is not None:
        clauses.append(Expense.date <= hi)
    return clauses


def _period_totals(uid: int, lo: date | None, hi: date | None) -> tuple[Decimal, int]:
    total_raw, count = db.session.execute(
        select(
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        ).where(*_where_user_and_period(uid, lo, hi))
    ).one()
    return Decimal(str(total_raw)), int(count)


def _category_breakdown(
    uid: int,
    lo: date | None,
    hi: date | None,
    total_amount: Decimal,
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
        cat_total = Decimal(str(raw_total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        percent = (
            (cat_total / total_amount * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if total_amount > 0
            else Decimal("0.00")
        )
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
            "total": Decimal(str(t)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
        for d, t in rows
    ]


def empty_dashboard_payload(user: User, period: str) -> dict[str, object]:
    lo, hi = _period_bounds(period)
    return {
        "total_amount": Decimal("0.00"),
        "expense_count": 0,
        "average_amount": Decimal("0.00"),
        "category_breakdown": [],
        "recent_expenses": [],
        "daily_series": [],
        "currency": user.default_currency,
        "period_start": lo,
        "period_end": hi,
    }


def compute_dashboard(user: User, period: str) -> dict[str, object]:
    lo, hi = _period_bounds(period)
    payload: dict[str, object] = empty_dashboard_payload(user, period)

    total, count = _period_totals(user.id, lo, hi)
    if count == 0:
        return payload

    total_q = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    avg_q = (total / count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    payload.update(
        total_amount=total_q,
        expense_count=count,
        average_amount=avg_q,
        category_breakdown=_category_breakdown(user.id, lo, hi, total),
        recent_expenses=_recent_expenses(user.id, lo, hi),
        daily_series=_daily_series(user.id, lo, hi),
    )
    return payload


# ------------------------------------------------------------------ #
# Profile activity (custom date range)                                 #
# ------------------------------------------------------------------ #


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


def empty_activity_payload(user: User, data: DateRangeSchema) -> dict[str, object]:
    return {
        "activity_expenses": [],
        "activity_total": Decimal("0.00"),
        "activity_count": 0,
        "range_start": data.start_date,
        "range_end": data.end_date,
        "currency": user.default_currency,
        "today_ist": _today_ist(),
    }


def profile_activity(user: User, data: DateRangeSchema) -> dict[str, object]:
    payload = empty_activity_payload(user, data)

    total, count = _period_totals(user.id, data.start_date, data.end_date)
    if count == 0:
        return payload

    payload.update(
        activity_expenses=list_expenses_in_range(
            user.id, data.start_date, data.end_date
        ),
        activity_total=total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        activity_count=count,
    )
    return payload


# ------------------------------------------------------------------ #
# Expense CRUD                                                         #
# ------------------------------------------------------------------ #


def list_user_expenses(user: User) -> list[Expense]:
    return list(
        db.session.execute(
            select(Expense)
            .where(Expense.user_id == user.id)
            .order_by(Expense.date.desc(), Expense.id.desc())
        ).scalars()
    )


def get_expense_for_user(expense_id: int, user_id: int) -> Expense | None:
    return db.session.execute(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
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
    db.session.delete(expense)
    db.session.commit()
    return True
