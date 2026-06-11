from datetime import datetime, date, timezone
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access this page."
login_manager.login_message_category = "error"

CATEGORIES: tuple[str, ...] = (
    "Bills",
    "Food",
    "Transport",
    "Health",
    "Entertainment",
    "Shopping",
    "Education",
    "Other",
)

_CATEGORY_CHECK = "category IN ({})".format(", ".join(f"'{c}'" for c in CATEGORIES))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="INR"
    )
    avatar_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    terms_accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    password_history: Mapped[list["PasswordHistory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.email!r}>"


class PasswordHistory(db.Model):
    __tablename__ = "password_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="password_history")

    def __repr__(self) -> str:
        return f"<PasswordHistory user_id={self.user_id}>"


class Expense(db.Model):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    user: Mapped["User"] = relationship(back_populates="expenses")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        CheckConstraint(_CATEGORY_CHECK, name="ck_expense_category_valid"),
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "amount": str(self.amount),
            "category": self.category,
            "date": self.date.isoformat(),
            "notes": self.notes,
        }

    def __repr__(self) -> str:
        return f"<Expense {self.title!r} ₹{self.amount}>"


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None


def seed_db(app: Flask) -> None:
    """Insert demo data. No-op if any user already exists."""
    with app.app_context():
        existing = db.session.execute(select(User).limit(1)).scalar_one_or_none()
        if existing is not None:
            return

        demo = User(
            name="Demo User",
            display_name="Demo",
            email="demo@spendly.dev",
            default_currency="INR",
            terms_accepted_at=_utcnow(),
        )
        demo.set_password("Demo@1234")
        db.session.add(demo)
        db.session.flush()

        sample: list[Expense] = [
            Expense(
                user_id=demo.id,
                title="Electricity bill",
                amount=2200,
                category="Bills",
                date=date(2026, 5, 1),
            ),
            Expense(
                user_id=demo.id,
                title="Groceries",
                amount=1851,
                category="Food",
                date=date(2026, 5, 3),
            ),
            Expense(
                user_id=demo.id,
                title="Metro pass",
                amount=500,
                category="Transport",
                date=date(2026, 5, 5),
            ),
            Expense(
                user_id=demo.id,
                title="Doctor visit",
                amount=700,
                category="Health",
                date=date(2026, 5, 8),
            ),
            Expense(
                user_id=demo.id,
                title="Netflix",
                amount=649,
                category="Entertainment",
                date=date(2026, 5, 10),
            ),
            Expense(
                user_id=demo.id,
                title="Python books",
                amount=850,
                category="Education",
                date=date(2026, 5, 12),
            ),
            Expense(
                user_id=demo.id,
                title="Shirt",
                amount=1200,
                category="Shopping",
                date=date(2026, 5, 14),
            ),
            Expense(
                user_id=demo.id,
                title="Water bill",
                amount=350,
                category="Bills",
                date=date(2026, 5, 15),
            ),
        ]
        db.session.add_all(sample)
        db.session.commit()
