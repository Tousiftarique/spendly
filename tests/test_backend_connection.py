import pytest

from database.db import create_user, get_user_by_email
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


@pytest.fixture
def demo_user_id(app):
    return get_user_by_email("demo@spendly.com")["id"]


@pytest.fixture
def empty_user_id(app):
    return create_user("Empty User", "empty@spendly.com", "password123")


def _login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


# ------------------------------------------------------------------ #
# User info                                                           #
# ------------------------------------------------------------------ #

def test_get_user_by_id_returns_user(demo_user_id):
    user = get_user_by_id(demo_user_id)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["initials"] == "DU"
    assert len(user["member_since"].split()) == 2


def test_get_user_by_id_missing_returns_none(app):
    assert get_user_by_id(99999) is None


def test_profile_redirects_when_logged_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_renders_user_info_and_rupee(client):
    _login(client)
    response = client.get("/profile")
    assert response.status_code == 200
    assert b"Demo User" in response.data
    assert b"demo@spendly.com" in response.data
    assert "₹".encode() in response.data


def test_profile_empty_user_renders(client, empty_user_id):
    _login(client, "empty@spendly.com", "password123")
    response = client.get("/profile")
    assert response.status_code == 200
    assert "₹0.00".encode() in response.data


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def test_get_summary_stats_demo_user(demo_user_id):
    stats = get_summary_stats(demo_user_id)
    assert stats["total_spent"] == pytest.approx(393.49)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_empty_user(empty_user_id):
    assert get_summary_stats(empty_user_id) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_get_summary_stats_isolated_per_user(demo_user_id, empty_user_id):
    from database.db import get_db

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (empty_user_id, 999.00, "Shopping", "2026-01-01", "Isolation"),
        )
        conn.commit()
    finally:
        conn.close()

    stats = get_summary_stats(demo_user_id)
    assert stats["total_spent"] == pytest.approx(393.49)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_profile_renders_summary_stats(client):
    _login(client)
    response = client.get("/profile")
    assert response.status_code == 200
    assert b"393.49" in response.data
    assert b">8<" in response.data
    assert b"Bills" in response.data


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_returns_all_demo_items(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)
    assert len(transactions) == 8
    for tx in transactions:
        assert set(tx.keys()) == {"date", "description", "category", "amount"}
        assert isinstance(tx["amount"], float)


def test_get_recent_transactions_newest_first(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)
    assert transactions[0]["description"] == "Restaurant"
    assert transactions[-1]["description"] == "Groceries"


def test_get_recent_transactions_date_formatted(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)
    month, day, year = transactions[-1]["date"].replace(",", "").split()
    assert len(month) == 3
    assert day == "1"
    assert len(year) == 4


def test_get_recent_transactions_respects_limit(demo_user_id):
    assert len(get_recent_transactions(demo_user_id, limit=3)) == 3


def test_get_recent_transactions_empty_user(empty_user_id):
    assert get_recent_transactions(empty_user_id) == []


def test_profile_transactions_ordered_newest_first(client):
    _login(client)
    response = client.get("/profile")
    assert response.status_code == 200
    assert response.data.index(b"Restaurant") < response.data.index(b"Groceries")



# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def test_category_breakdown_demo_user(demo_user_id):
    categories = get_category_breakdown(demo_user_id)
    assert len(categories) == 7
    amounts = [cat["amount"] for cat in categories]
    assert amounts == sorted(amounts, reverse=True)
    assert categories[0] == {"name": "Bills", "amount": 120.0,
                             "pct": categories[0]["pct"]}
    assert categories[1]["name"] == "Shopping"
    assert categories[1]["amount"] == 89.99
    assert categories[2]["name"] == "Food"
    assert categories[2]["amount"] == 75.75
    assert all(isinstance(cat["pct"], int) for cat in categories)
    assert sum(cat["pct"] for cat in categories) == 100


def test_category_breakdown_empty_user(empty_user_id):
    assert get_category_breakdown(empty_user_id) == []


def test_category_breakdown_pct_rounding_sums_to_100(app):
    from database.db import get_db

    user_id = create_user("Round User", "round@spendly.com", "password123")
    conn = get_db()
    try:
        for category in ("Food", "Bills", "Health"):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                (user_id, 10.0, category, "2026-01-01", "Equal split"),
            )
        conn.commit()
    finally:
        conn.close()

    categories = get_category_breakdown(user_id)
    pcts = [cat["pct"] for cat in categories]
    assert pcts == [34, 33, 33]
    assert sum(pcts) == 100


def test_profile_renders_category_rows(client):
    _login(client)
    response = client.get("/profile")
    assert response.status_code == 200
    assert response.data.count(b"profile-cat-row") == 7
