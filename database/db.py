from datetime import datetime, date, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access this page."
login_manager.login_message_category = "error"

CATEGORIES = (
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


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    expenses = db.relationship(
        "Expense",
        backref="user",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.email!r}>"


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        db.CheckConstraint(_CATEGORY_CHECK, name="ck_expense_category_valid"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "amount": float(self.amount),
            "category": self.category,
            "date": self.date.isoformat(),
            "notes": self.notes,
        }

    def __repr__(self) -> str:
        return f"<Expense {self.title!r} ₹{self.amount}>"


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None


def init_db(app) -> None:
    """Create all tables. Safe to call on every startup — uses IF NOT EXISTS."""
    with app.app_context():
        db.create_all()


def seed_db(app) -> None:
    """Insert demo data. No-op if any user already exists."""
    with app.app_context():
        if User.query.first():
            return

        demo = User(name="Demo User", email="demo@spendly.dev")
        demo.set_password("Demo@1234")
        db.session.add(demo)
        db.session.flush()

        sample = [
            Expense(user_id=demo.id, title="Electricity bill", amount=2200.00, category="Bills",         date=date(2026, 5,  1)),
            Expense(user_id=demo.id, title="Groceries",        amount=1850.50, category="Food",          date=date(2026, 5,  3)),
            Expense(user_id=demo.id, title="Metro pass",       amount=500.00,  category="Transport",     date=date(2026, 5,  5)),
            Expense(user_id=demo.id, title="Doctor visit",     amount=700.00,  category="Health",        date=date(2026, 5,  8)),
            Expense(user_id=demo.id, title="Netflix",          amount=649.00,  category="Entertainment", date=date(2026, 5, 10)),
            Expense(user_id=demo.id, title="Python books",     amount=850.00,  category="Education",     date=date(2026, 5, 12)),
            Expense(user_id=demo.id, title="Shirt",            amount=1200.00, category="Shopping",      date=date(2026, 5, 14)),
            Expense(user_id=demo.id, title="Water bill",       amount=350.00,  category="Bills",         date=date(2026, 5, 15)),
        ]
        db.session.add_all(sample)
        db.session.commit()
