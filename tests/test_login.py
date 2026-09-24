def test_get_login_renders_form(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Welcome back" in response.data


def test_valid_login_sets_session_and_redirects(client):
    response = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"

    with client.session_transaction() as session:
        assert session["user_id"] is not None


def test_wrong_password_rejected(client):
    response = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "wrong-password"},
    )
    assert response.status_code == 400
    assert b"Invalid email or password" in response.data

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_unknown_email_rejected(client):
    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert response.status_code == 400
    assert b"Invalid email or password" in response.data

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_logout_clears_session_and_redirects(client):
    client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )

    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    with client.session_transaction() as session:
        assert "user_id" not in session


def _nav_links(html_bytes):
    html = html_bytes.decode()
    start = html.index('class="nav-links"')
    end = html.index("</div>", start)
    return html[start:end]


def test_nav_shows_logout_when_logged_in(client):
    client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )

    response = client.get("/")
    nav = _nav_links(response.data)
    assert "Logout" in nav
    assert "Sign in" not in nav


def test_nav_shows_sign_in_when_logged_out(client):
    response = client.get("/")
    nav = _nav_links(response.data)
    assert "Sign in" in nav
    assert "Logout" not in nav


def test_logged_in_user_redirected_away_from_login(client):
    client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )

    response = client.get("/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"


def test_logged_in_user_redirected_away_from_register(client):
    client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )

    response = client.get("/register")
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
