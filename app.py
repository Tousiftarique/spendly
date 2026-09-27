import calendar
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    email_exists,
    get_user_by_email,
    init_db,
    seed_db,
)
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
app.secret_key = "dev-only-secret-key"  # dev only — replace before any real deployment


# ------------------------------------------------------------------ #
# Date filter helpers                                                 #
# ------------------------------------------------------------------ #

def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _months_ago(day, months):
    total = day.year * 12 + (day.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def _date_presets(today):
    today_iso = today.isoformat()
    return {
        "this_month": ("This Month", today.replace(day=1).isoformat(), today_iso),
        "last_3": ("Last 3 Months", _months_ago(today, 3).isoformat(), today_iso),
        "last_6": ("Last 6 Months", _months_ago(today, 6).isoformat(), today_iso),
        "all": ("All Time", None, None),
    }


def _resolve_date_filter(raw_from, raw_to):
    parsed_from = _parse_iso_date(raw_from)
    parsed_to = _parse_iso_date(raw_to)
    if parsed_from is None or parsed_to is None:
        return None, None, None
    if parsed_from > parsed_to:
        return None, None, "Start date must be before end date."
    return parsed_from.isoformat(), parsed_to.isoformat(), None


def _resolve_active_preset(presets, date_from, date_to):
    if date_from is None:
        return "all"
    return next(
        (key for key, (_, p_from, p_to) in presets.items()
         if (p_from, p_to) == (date_from, date_to)),
        "custom",
    )


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template(
            "register.html",
            error="All fields are required.",
            name=name,
            email=email,
        ), 400

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        ), 400

    if password != confirm_password:
        return render_template(
            "register.html",
            error="Passwords do not match.",
            name=name,
            email=email,
        ), 400

    if email_exists(email):
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        ), 400

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        ), 400

    flash("Account created — please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password"), 400

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    flash("Logged in successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    # --- Date filter (section: date-filter) ---
    date_from, date_to, filter_error = _resolve_date_filter(
        request.args.get("date_from"), request.args.get("date_to")
    )
    if filter_error:
        flash(filter_error, "error")

    presets = _date_presets(date.today())
    active_preset = _resolve_active_preset(presets, date_from, date_to)
    # --- end date-filter ---

    # --- Summary stats (section: summary-stats) ---
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    # --- end summary-stats ---

    # --- Transaction history (section: transaction-history) ---
    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    # --- end transaction-history ---

    # --- Category breakdown (section: category-breakdown) ---
    categories = get_category_breakdown(
        user_id, date_from=date_from, date_to=date_to
    )
    # --- end category-breakdown ---

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        presets=presets,
        active_preset=active_preset,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


# ------------------------------------------------------------------ #
# Database initialization                                             #
# ------------------------------------------------------------------ #

with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)