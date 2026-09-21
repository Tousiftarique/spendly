from database.db import get_db


def test_get_register_renders_form(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"Create your account" in response.data


def test_valid_registration_creates_user_and_redirects(client):
    response = client.post(
        "/register",
        data={
            "name": "Anita Rao",
            "email": "anita.rao@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", ("anita.rao@example.com",)
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["name"] == "Anita Rao"


def test_password_is_hashed_not_plaintext(client):
    client.post(
        "/register",
        data={
            "name": "Hash Check",
            "email": "hash.check@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("hash.check@example.com",),
        ).fetchone()
    finally:
        conn.close()

    assert row["password_hash"] != "password123"
    assert row["password_hash"].startswith(("scrypt:", "pbkdf2:"))


def test_password_too_short_rejected(client):
    response = client.post(
        "/register",
        data={
            "name": "Short Pass",
            "email": "short.pass@example.com",
            "password": "short1",
            "confirm_password": "short1",
        },
    )
    assert response.status_code == 400
    assert b"at least 8 characters" in response.data

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("short.pass@example.com",)
        ).fetchone()
    finally:
        conn.close()
    assert row is None


def test_mismatched_passwords_rejected(client):
    response = client.post(
        "/register",
        data={
            "name": "Mismatch User",
            "email": "mismatch@example.com",
            "password": "password123",
            "confirm_password": "password456",
        },
    )
    assert response.status_code == 400
    assert b"do not match" in response.data


def test_missing_field_rejected(client):
    response = client.post(
        "/register",
        data={
            "name": "",
            "email": "missing.name@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    assert b"required" in response.data


def test_duplicate_email_rejected(client):
    response = client.post(
        "/register",
        data={
            "name": "Demo Duplicate",
            "email": "demo@spendly.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    assert b"already exists" in response.data

    conn = get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE email = ?",
            ("demo@spendly.com",),
        ).fetchone()["count"]
    finally:
        conn.close()
    assert count == 1


def test_email_case_insensitive_duplicate(client):
    client.post(
        "/register",
        data={
            "name": "Case Test",
            "email": "case.test@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    response = client.post(
        "/register",
        data={
            "name": "Case Test Again",
            "email": "Case.Test@Example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    assert b"already exists" in response.data


def test_repeated_valid_submission_no_duplicate(client):
    payload = {
        "name": "Repeat User",
        "email": "repeat.user@example.com",
        "password": "password123",
        "confirm_password": "password123",
    }
    first = client.post("/register", data=payload)
    second = client.post("/register", data=payload)

    assert first.status_code == 302
    assert second.status_code == 400

    conn = get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE email = ?",
            ("repeat.user@example.com",),
        ).fetchone()["count"]
    finally:
        conn.close()
    assert count == 1


def test_error_repopulates_name_and_email(client):
    response = client.post(
        "/register",
        data={
            "name": "Keep Me",
            "email": "keep.me@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert b'value="Keep Me"' in response.data
    assert b'value="keep.me@example.com"' in response.data
