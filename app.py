import os
from datetime import datetime, timedelta, timezone

from flask import Flask, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database.db import User, csrf, db, login_manager, migrate, seed_db
from database.schemas import (
    ALLOWED_CURRENCIES,
    DASHBOARD_PERIODS,
    ChangePasswordSchema,
    DateRangeSchema,
    LoginSchema,
    ProfileUpdateSchema,
    RegisterSchema,
    coerce_period,
    extract_messages,
)
from database.services import (
    change_password,
    compute_dashboard,
    empty_activity_payload,
    empty_dashboard_payload,
    profile_activity,
    update_profile,
)


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-in-production"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg2://spendly:spendly@localhost:5544/spendly",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        WTF_CSRF_TIME_LIMIT=3600,
        REMEMBER_COOKIE_DURATION=timedelta(days=30),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    @app.template_filter("strftime")
    def _strftime_filter(value: datetime | None, fmt: str = "%B %d, %Y") -> str:
        return value.strftime(fmt) if value else ""

    _register_auth_routes(app)
    _register_main_routes(app)

    return app


# ------------------------------------------------------------------ #
# Auth routes                                                          #
# ------------------------------------------------------------------ #


def _register_auth_routes(app: Flask) -> None:

    @app.route("/register", methods=["GET", "POST"])
    def register() -> ResponseReturnValue:
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            raw_name = request.form.get("name", "")
            raw_display_name = request.form.get("display_name", "")
            raw_email = request.form.get("email", "")
            raw_currency = request.form.get("default_currency", "INR")
            raw_pass = request.form.get("password", "")
            accepted = request.form.get("accept_terms") == "on"

            ctx: dict[str, object] = {
                "name": raw_name,
                "display_name": raw_display_name,
                "email": raw_email,
                "default_currency": raw_currency or "INR",
                "accepted": accepted,
                "currencies": ALLOWED_CURRENCIES,
            }

            # --- Pydantic validation ---
            try:
                data = RegisterSchema(
                    name=raw_name,
                    display_name=raw_display_name,
                    email=raw_email,
                    default_currency=raw_currency,
                    password=raw_pass,
                    accept_terms=accepted,
                )
            except ValidationError as exc:
                for msg in extract_messages(exc):
                    flash(msg, "error")
                return render_template("register.html", **ctx)

            # Schema succeeded — use normalised values for subsequent re-renders.
            ctx["name"] = data.name
            ctx["display_name"] = data.display_name
            ctx["email"] = data.email
            ctx["default_currency"] = data.default_currency

            # --- DB operations ---
            try:
                existing = db.session.execute(
                    select(User).filter_by(email=data.email)
                ).scalar_one_or_none()

                if existing is not None:
                    flash("An account with this email already exists.", "error")
                    return render_template("register.html", **ctx)

                user = User(
                    name=data.name,
                    display_name=data.display_name,
                    email=data.email,
                    default_currency=data.default_currency,
                    terms_accepted_at=datetime.now(timezone.utc),
                )
                user.set_password(data.password)
                db.session.add(user)
                db.session.commit()

                login_user(user, remember=False)
                user.last_login_at = datetime.now(timezone.utc)
                db.session.commit()
                flash(f"Welcome to Spendly, {user.display_name}!", "success")
                return redirect(url_for("dashboard"))

            except SQLAlchemyError as exc:
                db.session.rollback()
                current_app.logger.error("DB error during register: %s", exc)
                flash("A database error occurred. Please try again.", "error")
                return render_template("register.html", **ctx)
            except Exception as exc:
                current_app.logger.error("Unexpected register error: %s", exc)
                flash("An unexpected error occurred. Please try again.", "error")
                return render_template("register.html", **ctx)

        return render_template(
            "register.html",
            name="",
            display_name="",
            email="",
            default_currency="INR",
            accepted=False,
            currencies=ALLOWED_CURRENCIES,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login() -> ResponseReturnValue:
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            raw_email = request.form.get("email", "")
            raw_pass = request.form.get("password", "")
            remember_me = request.form.get("remember_me") == "on"

            # --- Pydantic validation ---
            try:
                data = LoginSchema(
                    email=raw_email, password=raw_pass, remember_me=remember_me
                )
            except ValidationError:
                # Generic message — don't reveal whether the email exists
                flash("Invalid email or password.", "error")
                return render_template(
                    "login.html", email=raw_email, remember_me=remember_me
                )

            # --- DB operations ---
            try:
                user = db.session.execute(
                    select(User).filter_by(email=data.email)
                ).scalar_one_or_none()

                if user is None or not user.check_password(data.password):
                    flash("Invalid email or password.", "error")
                    return render_template(
                        "login.html", email=raw_email, remember_me=remember_me
                    )

                login_user(user, remember=data.remember_me)
                user.last_login_at = datetime.now(timezone.utc)
                db.session.commit()
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
                return render_template(
                    "login.html", email=raw_email, remember_me=remember_me
                )
            except Exception as exc:
                current_app.logger.error("Unexpected login error: %s", exc)
                flash("An unexpected error occurred. Please try again.", "error")
                return render_template("login.html", remember_me=remember_me)

        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout() -> ResponseReturnValue:
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
    def landing() -> ResponseReturnValue:
        return render_template("landing.html")

    @app.route("/dashboard")
    @login_required
    def dashboard() -> ResponseReturnValue:
        period = coerce_period(request.args.get("period")).period
        try:
            payload = compute_dashboard(current_user, period)
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("DB error on /dashboard: %s", exc)
            flash("A database error occurred loading your dashboard.", "error")
            payload = empty_dashboard_payload(current_user, period)
        return render_template(
            "dashboard.html",
            user=current_user,
            period=period,
            periods=DASHBOARD_PERIODS,
            **payload,
        )

    @app.route("/profile", methods=["GET"])
    @login_required
    def profile() -> ResponseReturnValue:
        raw_start = request.args.get("start_date") or None
        raw_end = request.args.get("end_date") or None

        range_error: str | None = None
        try:
            date_range = DateRangeSchema(start_date=raw_start, end_date=raw_end)
        except ValidationError as exc:
            range_error = extract_messages(exc)[0]
            date_range = DateRangeSchema()

        try:
            activity = profile_activity(current_user, date_range)
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("DB error on /profile activity: %s", exc)
            flash("A database error occurred loading your activity.", "error")
            activity = empty_activity_payload(current_user, date_range)

        activity["range_error"] = range_error
        activity["raw_start"] = raw_start or ""
        activity["raw_end"] = raw_end or ""

        if request.headers.get("HX-Request"):
            return render_template("partials/_activity_results.html", **activity)
        return render_template(
            "profile.html",
            user=current_user,
            currencies=ALLOWED_CURRENCIES,
            **activity,
        )

    @app.route("/profile", methods=["POST"])
    @login_required
    def profile_update() -> ResponseReturnValue:
        raw_display_name = request.form.get("display_name", "")
        raw_currency = request.form.get("default_currency", "")

        try:
            data = ProfileUpdateSchema(
                display_name=raw_display_name,
                default_currency=raw_currency,
            )
        except ValidationError as exc:
            for msg in extract_messages(exc):
                flash(msg, "error")
            return redirect(url_for("profile"))

        try:
            update_profile(current_user, data)
            flash("Profile updated.", "success")
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("DB error during profile update: %s", exc)
            flash("A database error occurred. Please try again.", "error")
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error("Unexpected profile update error: %s", exc)
            flash("An unexpected error occurred. Please try again.", "error")

        return redirect(url_for("profile"))

    @app.route("/profile/change-password", methods=["POST"])
    @login_required
    def change_password_route() -> ResponseReturnValue:
        raw_current = request.form.get("current_password", "")
        raw_new = request.form.get("new_password", "")
        raw_confirm = request.form.get("confirm_password", "")

        try:
            data = ChangePasswordSchema(
                current_password=raw_current,
                new_password=raw_new,
                confirm_password=raw_confirm,
            )
        except ValidationError as exc:
            for msg in extract_messages(exc):
                flash(msg, "error")
            return redirect(url_for("profile"))

        try:
            ok = change_password(current_user, data)
            if not ok:
                flash("Current password is incorrect.", "error")
            else:
                flash("Password updated.", "success")
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error("DB error during password change: %s", exc)
            flash("A database error occurred. Please try again.", "error")
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error("Unexpected password change error: %s", exc)
            flash("An unexpected error occurred. Please try again.", "error")

        return redirect(url_for("profile"))

    @app.route("/analytics")
    @login_required
    def analytics() -> ResponseReturnValue:
        return render_template("analytics.html", user=current_user)

    @app.route("/expenses/add")
    @login_required
    def add_expense() -> ResponseReturnValue:
        return "Add expense — coming in Step 7"

    @app.route("/expenses/<int:id>/edit")
    @login_required
    def edit_expense(id: int) -> ResponseReturnValue:
        return "Edit expense — coming in Step 8"

    @app.route("/expenses/<int:id>/delete")
    @login_required
    def delete_expense(id: int) -> ResponseReturnValue:
        return "Delete expense — coming in Step 9"

    @app.route("/terms")
    def terms() -> ResponseReturnValue:
        return render_template("terms.html")

    @app.route("/privacy")
    def privacy() -> ResponseReturnValue:
        return render_template("privacy.html")


app = create_app()

if __name__ == "__main__":
    seed_db(app)
    app.run(debug=True, port=8000)
