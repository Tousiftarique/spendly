from datetime import datetime

from database.db import get_db


# ------------------------------------------------------------------ #
# User info                                                           #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    created_at = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    initials = "".join(word[0] for word in row["name"].split()[:2]).upper()
    return {
        "name": row["name"],
        "email": row["email"],
        "initials": initials,
        "member_since": created_at.strftime("%B %Y"),
    }


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def get_summary_stats(user_id):
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if totals["count"] == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    return {
        "total_spent": round(float(totals["total"]), 2),
        "transaction_count": int(totals["count"]),
        "top_category": top_row["category"],
    }


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    transactions = []
    for row in rows:
        spent_on = datetime.strptime(row["date"][:10], "%Y-%m-%d")
        transactions.append({
            "date": f"{spent_on.strftime('%b')} {spent_on.day}, {spent_on.year}",
            "description": row["description"],
            "category": row["category"],
            "amount": float(row["amount"]),
        })
    return transactions


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY amount DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    grand_total = sum(row["amount"] for row in rows)
    if not rows or grand_total <= 0:
        return []

    categories = [
        {
            "name": row["category"],
            "amount": round(row["amount"], 2),
            "pct": round(row["amount"] / grand_total * 100),
        }
        for row in rows
    ]
    categories[0]["pct"] += 100 - sum(cat["pct"] for cat in categories)
    return categories
