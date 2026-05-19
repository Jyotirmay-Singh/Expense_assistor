# 01 — Database Setup

## 1. Overview

Establish the PostgreSQL data layer foundation for the Spendly Flask application. This step replaces the SQLite placeholder with a robust SQLAlchemy 2.0 ORM setup against PostgreSQL, integrated with Alembic (via flask-migrate) for schema migrations. All future domains (profile, dashboard, expenses CRUD) depend on this schema and on the `db.session` request-scoped session being correctly wired.

## 2. Depends on

Local infrastructure running via Docker (`docker compose up -d` for the PostgreSQL service).

## 3. Routes

No new routes are implemented in this step. Existing routes in `app.py` (`/`, `/register`, `/login`, `/logout`, `/terms`, `/privacy`, plus stubs for dashboard/profile/expenses) remain unchanged.

## 4. Database schema (SQLAlchemy 2.0 typed mappings)

Models live in `database/db.py` (single-file layout). They use `Mapped` / `mapped_column` declarations on a shared `DeclarativeBase`.

### A. User (`users` table)

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | Primary key, autoincrement |
| `name` | String(120) | Not null |
| `email` | String(255) | Unique, not null, indexed |
| `password_hash` | String(255) | Not null |
| `created_at` | DateTime(timezone=True) | Default `datetime.now(timezone.utc)`, not null |

Relationship: `expenses` (one-to-many) with `cascade="all, delete-orphan"`.

`User` mixes in `flask_login.UserMixin`. Hashing uses `werkzeug.security.generate_password_hash` / `check_password_hash`.

### B. Expense (`expenses` table)

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | Primary key, autoincrement |
| `user_id` | Integer | Foreign key → `users.id`, `ON DELETE CASCADE`, not null, indexed |
| `title` | String(200) | Not null |
| `amount` | Numeric(10, 2) | Not null (**CRITICAL**: never use `Float`/`Real`) |
| `category` | String(50) | Not null |
| `date` | Date | Not null, default `date.today`, indexed |
| `notes` | Text | Nullable |
| `created_at` | DateTime(timezone=True) | Default `datetime.now(timezone.utc)`, not null |
| `updated_at` | DateTime(timezone=True) | Default + `onupdate` `datetime.now(timezone.utc)`, not null |

Table-level check constraints:
- `ck_expense_amount_positive` — `amount > 0`
- `ck_expense_category_valid` — `category` ∈ the fixed category list (see section 9)

## 5. Implementation targets

### A. Flask-SQLAlchemy setup (`database/db.py`)

- Define `class Base(DeclarativeBase): pass` and pass it to `SQLAlchemy(model_class=Base)`.
- Initialise the global extensions: `db`, `migrate = Migrate()`, `login_manager`, `csrf`.
- The session you use everywhere is `db.session` — request-scoped, owned by Flask. Do not construct a separate `Engine` or `sessionmaker`.

### B. Migrations (`migrations/` via flask-migrate)

- One-time: `flask --app app db init` scaffolds the `migrations/` directory.
- `flask --app app db migrate -m "initial_schema"` autogenerates the first revision (creates `users` and `expenses`). flask-migrate wires `target_metadata = db.metadata` automatically.
- `flask --app app db upgrade` applies the revision.

### C. Seed script (`seed_db()` in `database/db.py`)

- Use SQLAlchemy 2.0 syntax: `db.session.execute(select(User).limit(1)).scalar_one_or_none()` to detect existing data — return early if any user exists (idempotent).
- Insert one demo user:
  - Name: `Demo User`
  - Email: `demo@spendly.dev`
  - Password: hashed via `user.set_password("Demo@1234")`.
- Insert 8 sample expenses linked to the demo user covering multiple categories, dated across the current month. Amounts are constructed with `decimal.Decimal` literals — never floats.

## 6. Changes to `app.py`

- `SQLALCHEMY_DATABASE_URI` defaults to `postgresql+psycopg2://spendly:spendly@localhost:5544/spendly` (overridable via the `DATABASE_URL` env var). The host port is 5544 to avoid colliding with native PostgreSQL services the developer may have installed on 5432/5433.
- Remove the `os.makedirs(app.instance_path, ...)` SQLite scaffolding — no longer needed.
- `if __name__ == "__main__":` calls `seed_db(app)` only (not `init_db`). Schema is owned by Alembic; running `python app.py` against a freshly-migrated empty DB will populate demo data on first start.

## 7. Files to change / create

- `database/db.py` — refactor to SQLAlchemy 2.0 typed mappings; rewrite `seed_db()` with `select()` + `Decimal`; drop `init_db()`.
- `app.py` — switch DB URI default to Postgres; remove `init_db` call.
- `docker-compose.yml` — **create** (PostgreSQL 16 service with healthcheck and named volume).
- `.env.example` — **create** (documents `DATABASE_URL`, `SECRET_KEY`).
- `requirements.txt` — **modify** to add `psycopg2-binary==2.9.10`.
- `migrations/` — **create** via `flask db init`.
- `migrations/versions/<hash>_initial_schema.py` — **generate** via `flask db migrate`.
- `.gitignore` — ensure `.env`, `instance/`, `__pycache__/`, `venv/` are ignored.

## 8. Dependencies

Add: `psycopg2-binary` (sync PostgreSQL driver for SQLAlchemy).

Already managed (no change): `flask`, `flask-sqlalchemy`, `flask-migrate`, `flask-login`, `flask-wtf`, `email-validator`, `pydantic`, `werkzeug`, `pytest`, `pytest-flask`.

## 9. Categories (fixed list)

Use exactly these values for expense categorisation (8 entries):

- Bills
- Food
- Transport
- Health
- Entertainment
- Shopping
- Education
- Other

These are enforced by the `ck_expense_category_valid` table-level check constraint.

## 10. Rules for implementation

- **Architecture strictness**: Use SQLAlchemy 2.0 syntax exclusively (`select(...)`, `db.session.execute(...)`). Never use raw f-strings for SQL. Never use SQLite.
- **Data integrity**: Always use `Numeric(10, 2)` for currency in models and `decimal.Decimal` literals in Python.
- **Coding standards**: PEP 8 enforced via Ruff. Type hints required on every function signature.
- **Database sessions**: Use `db.session` from `flask_sqlalchemy`. Never construct a global engine, sessionmaker, or bypass Flask's app context.

## 11. Expected behaviour

- `flask --app app db upgrade` builds the `users` and `expenses` tables (and `alembic_version`) on an empty Postgres database without errors.
- `seed_db(app)` inserts the demo user and 8 expenses on a fresh DB; subsequent runs are a no-op (idempotent).
- PostgreSQL enforces the unique email and foreign key constraints natively.
- The existing `/register` and `/login` flows work against the new Postgres-backed DB.

## 12. Error handling expectations

- Unique constraint violations (e.g., duplicate emails) during commits raise `sqlalchemy.exc.IntegrityError`. The existing `try/except SQLAlchemyError` block in the `/register` route rolls back and flashes a user-friendly message.
- Invalid foreign key inserts raise the corresponding SQLAlchemy / psycopg2 error.

## 13. Definition of done

- [x] Docker compose service `spendly_postgres` is running and healthy.
- [x] `database/db.py` uses SQLAlchemy 2.0 typed mappings (`DeclarativeBase`, `Mapped`, `mapped_column`).
- [x] `Numeric(10, 2)` is used for `amount`; the seed uses `decimal.Decimal` literals.
- [x] Initial Alembic migration is generated and applies cleanly.
- [x] `seed_db()` inserts 1 hashed demo user + 8 expenses, and is a no-op on subsequent runs.
- [x] `ruff check .` passes with zero warnings.
- [x] No SQLite anywhere; `DATABASE_URL` points at Postgres.
- [x] Existing auth flow (register, login, logout) still works end-to-end.
