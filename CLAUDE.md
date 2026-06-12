# CLAUDE.md

## Project overview

FinCheck is a personal expense tracking application built on Flask. It uses Flask-SQLAlchemy 3.x (with SQLAlchemy 2.0 typed mappings) against PostgreSQL for the data layer, server-rendered Jinja2 templates for the UI, and Pydantic v2 for input validation. The goal is a small, secure, maintainable codebase — no Single Page Application bloat.

---

## Architecture

```text
fincheck/
├── app.py                # Flask application factory + route registrations
├── database/
│   ├── db.py             # SQLAlchemy models, Flask extensions (db, migrate, login_manager, csrf), seed_db
│   └── schemas.py        # Pydantic v2 schemas (RegisterSchema, LoginSchema)
├── templates/            # Jinja2 templates (landing, register, login, terms, privacy, ...)
├── static/               # CSS, JS, images
├── migrations/           # Alembic migrations managed by flask-migrate
├── instance/             # Local-only secrets / files (gitignored)
├── docker-compose.yml    # Local PostgreSQL service
├── .env.example          # Documented environment variables
└── requirements.txt      # Managed dependencies
```

**Where things belong:**
- New routes → register inside `_register_auth_routes()` / `_register_main_routes()` in `app.py` (or a new `_register_*_routes()` helper for a new domain). Promote to Flask blueprints once route count justifies it.
- DB logic & calculations → service functions in `database/` (or a new `services/` module). Never inline non-trivial queries in route bodies.
- Schema validation → `database/schemas.py` using Pydantic v2.
- New pages/components → `templates/` (`.html` files), referenced via `render_template(...)`.
- Page-specific behavior → progressive enhancement with vanilla JS or HTMX attributes on HTML elements.

---

## Code style

- Python: PEP 8 enforced via Ruff. Use snake_case for variables/functions, PascalCase for classes. Type hints required on every function signature.
- Templates: Jinja2. Always use `flask.url_for()` (or `{{ url_for(...) }}` in templates) for every internal link or form action — never hardcode URLs.
- Route functions: One responsibility only — parse request, call service / DB code, render template, done. Keep routes thin.
- DB queries: Use SQLAlchemy 2.0 syntax (`select(...)`, `db.session.execute(...)`, `.scalar_one_or_none()`). Never use raw f-strings for SQL.
- Error handling: Catch `sqlalchemy.exc.SQLAlchemyError` in routes, `db.session.rollback()`, log the error, then `flash(...)` a safe user-facing message and re-render the template. For programmer/auth errors, use `flask.abort(...)` or raise `werkzeug.exceptions.HTTPException`.

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks.
- **PostgreSQL only** — accessed via `psycopg2-binary` and SQLAlchemy 2.0. No SQLite.
- **Server-rendered HTML + vanilla JS / HTMX** — no React, no Vue, no jQuery, no npm build steps for JS.
- **Python 3.12+** — use modern syntax (`match`, `list[int]`, `str | None`, etc.).

---

## Subagent policy

- Use a built-in Explore subagent for open-ended codebase exploration before implementing any new feature.
- Use a subagent to verify test results after any implementation.
- When asked to plan, delegate codebase research to a subagent before presenting the plan.
- Always use the built-in Plan subagent in plan mode.

---

## Commands

```bash
# Infrastructure (PostgreSQL)
docker compose up -d
docker compose ps          # verify fincheck_postgres is healthy

# Install dependencies
pip install -r requirements.txt

# Run dev server (port 8000)
python app.py
# or
flask --app app run --port 8000 --debug

# Database migrations (flask-migrate wraps Alembic)
flask --app app db init                      # first time only
flask --app app db migrate -m "description"
flask --app app db upgrade
flask --app app db downgrade -1              # roll back one revision

# Code quality (run before marking task complete)
ruff check . --fix
ruff format .

# Tests
pytest -v
pytest tests/test_auth.py
pytest -k "test_register"
```

---

## Implemented vs stub routes

| Route | Methods | Status |
|---|---|---|
| `/` | GET | Implemented — renders `landing.html` |
| `/register` | GET, POST | Implemented — Pydantic validation + user creation |
| `/login` | GET, POST | Implemented — credential check, session login |
| `/logout` | GET | Implemented — clears session, redirects to landing |
| `/dashboard` | GET | **Stub** — returns plain string; real view planned |
| `/profile` | GET | **Stub** |
| `/expenses/add` | GET | **Stub** |
| `/expenses/<int:id>/edit` | GET | **Stub** |
| `/expenses/<int:id>/delete` | GET | **Stub** |
| `/terms` | GET | Implemented — renders `terms.html` |
| `/privacy` | GET | Implemented — renders `privacy.html` |

**Do not promote a stub route to a full implementation unless the active task explicitly targets it.** Stubs currently return plain strings — that is intentional until their dedicated step lands.

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes once they are implemented** — always render a Jinja2 template.
- **Never hardcode URLs** in templates or views — always use `flask.url_for()` / `{{ url_for(...) }}`.
- **Never put DB logic in route functions** beyond a single call — push transactions and complex queries into `database/` (or a future `services/` module).
- **Never install new packages mid-feature without flagging it** — keep `requirements.txt` in sync.
- **Never use heavy JS frameworks** — server-rendered HTML + vanilla JS / HTMX is the model.
- **Never instantiate a global DB Session or Engine** — use `db.session` from `flask_sqlalchemy` inside the app context or a request.
- **Never store currency as floats** — amounts represent whole currency units (no fractional sub-units): use `Integer` in models and `int` in Python, validated as positive whole numbers in `ExpenseSchema`.
- **Never use SQLite, not even for local dev** — point `DATABASE_URL` at the Dockerised Postgres.
