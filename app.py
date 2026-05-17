import os

from flask import Flask, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from database.db import db, migrate, login_manager, csrf, init_db, seed_db, User
from database.schemas import RegisterSchema, LoginSchema, extract_messages


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-in-production"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///{}".format(os.path.join(app.instance_path, "spendly.db")),
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        WTF_CSRF_TIME_LIMIT=3600,
    )

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    _register_auth_routes(app)
    _register_main_routes(app)

    return app


# ------------------------------------------------------------------ #
# Auth routes                                                          #
# ------------------------------------------------------------------ #

def _register_auth_routes(app: Flask) -> None:

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            raw_name  = request.form.get("name", "")
            raw_email = request.form.get("email", "")
            raw_pass  = request.form.get("password", "")

            # --- Pydantic validation ---
            try:
                data = RegisterSchema(name=raw_name, email=raw_email, password=raw_pass)
            except ValidationError as exc:
                for msg in extract_messages(exc):
                    flash(msg, "error")
                return render_template("register.html", name=raw_name, email=raw_email)

            # --- DB operations ---
            try:
                if User.query.filter_by(email=data.email).first():
                    flash("An account with this email already exists.", "error")
                    return render_template("register.html", name=data.name, email=data.email)

                user = User(name=data.name, email=data.email)
                user.set_password(data.password)
                db.session.add(user)
                db.session.commit()

                login_user(user, remember=False)
                flash(f"Welcome to Spendly, {user.name}!", "success")
                return redirect(url_for("dashboard"))

            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.error("DB error during register: %s", exc)
                flash("A database error occurred. Please try again.", "error")
                return render_template("register.html", name=data.name, email=data.email)
            except Exception as exc:
                current_app.logger.error("Unexpected register error: %s", exc)
                flash("An unexpected error occurred. Please try again.", "error")
                return render_template("register.html")

        return render_template("register.html")


    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            raw_email = request.form.get("email", "")
            raw_pass  = request.form.get("password", "")

            # --- Pydantic validation ---
            try:
                data = LoginSchema(email=raw_email, password=raw_pass)
            except ValidationError:
                # Generic message — don't reveal whether the email exists
                flash("Invalid email or password.", "error")
                return render_template("login.html", email=raw_email)

            # --- DB operations ---
            try:
                user = User.query.filter_by(email=data.email).first()

                if user is None or not user.check_password(data.password):
                    flash("Invalid email or password.", "error")
                    return render_template("login.html", email=raw_email)

                login_user(user, remember=False)
                flash(f"Welcome back, {user.name}!", "success")

                # Safe open-redirect guard
                next_page = request.args.get("next", "")
                if next_page.startswith("/") and not next_page.startswith("//"):
                    return redirect(next_page)
                return redirect(url_for("dashboard"))

            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.error("DB error during login: %s", exc)
                flash("A database error occurred. Please try again.", "error")
                return render_template("login.html", email=raw_email)
            except Exception as exc:
                current_app.logger.error("Unexpected login error: %s", exc)
                flash("An unexpected error occurred. Please try again.", "error")
                return render_template("login.html")

        return render_template("login.html")


    @app.route("/logout")
    @login_required
    def logout():
        try:
            name = current_user.name
            logout_user()
            flash(f"Goodbye, {name}. You have been signed out.", "info")
        except Exception as exc:
            current_app.logger.error("Logout error: %s", exc)
            flash("An error occurred during sign out.", "error")
        return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Main / protected routes                                              #
# ------------------------------------------------------------------ #

def _register_main_routes(app: Flask) -> None:

    @app.route("/")
    def landing():
        return render_template("landing.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return f"Dashboard — welcome, {current_user.name} (coming in Step 5)"

    @app.route("/profile")
    @login_required
    def profile():
        return "Profile page — coming in Step 4"

    @app.route("/expenses/add")
    @login_required
    def add_expense():
        return "Add expense — coming in Step 7"

    @app.route("/expenses/<int:id>/edit")
    @login_required
    def edit_expense(id):
        return "Edit expense — coming in Step 8"

    @app.route("/expenses/<int:id>/delete")
    @login_required
    def delete_expense(id):
        return "Delete expense — coming in Step 9"


app = create_app()

if __name__ == "__main__":
    init_db(app)
    seed_db(app)
    app.run(debug=True, port=8000)
