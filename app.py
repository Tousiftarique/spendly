import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    email_exists,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = "dev-only-secret-key"  # dev only — replace before any real deployment


# ------------------------------------------------------------------ #
# Hardcoded profile data (Step 4 — replaced with real queries in      #
# Step 5)                                                             #
# ------------------------------------------------------------------ #

PROFILE_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "initials": "DU",
    "member_since": "September 2026",
}

PROFILE_STATS = {
    "total_spent": 393.49,
    "transaction_count": 8,
    "top_category": "Bills",
}

PROFILE_TRANSACTIONS = [
    {"date": "Sep 22, 2026", "description": "Restaurant", "category": "Food", "amount": 30.25},
    {"date": "Sep 18, 2026", "description": "Miscellaneous", "category": "Other", "amount": 12.00},
    {"date": "Sep 14, 2026", "description": "New shoes", "category": "Shopping", "amount": 89.99},
    {"date": "Sep 10, 2026", "description": "Movie ticket", "category": "Entertainment", "amount": 15.75},
    {"date": "Sep 8, 2026", "description": "Pharmacy", "category": "Health", "amount": 60.00},
    {"date": "Sep 5, 2026", "description": "Electricity bill", "category": "Bills", "amount": 120.00},
    {"date": "Sep 3, 2026", "description": "Bus pass top-up", "category": "Transport", "amount": 20.00},
    {"date": "Sep 1, 2026", "description": "Groceries", "category": "Food", "amount": 45.50},
]

PROFILE_CATEGORIES = [
    {"name": "Bills", "total": 120.00, "percent": 30.5},
    {"name": "Shopping", "total": 89.99, "percent": 22.9},
    {"name": "Food", "total": 75.75, "percent": 19.3},
    {"name": "Health", "total": 60.00, "percent": 15.3},
    {"name": "Transport", "total": 20.00, "percent": 5.1},
    {"name": "Entertainment", "total": 15.75, "percent": 4.0},
    {"name": "Other", "total": 12.00, "percent": 3.0},
]


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
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=PROFILE_USER,
        stats=PROFILE_STATS,
        transactions=PROFILE_TRANSACTIONS,
        categories=PROFILE_CATEGORIES,
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