import re

from pathlib import Path


def _login(client):
    return client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )


def _nav_links(html_bytes):
    html = html_bytes.decode()
    start = html.index('class="nav-links"')
    end = html.index("</div>", start)
    return html[start:end]


def test_profile_redirects_when_logged_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_profile_renders_when_logged_in(client):
    _login(client)

    response = client.get("/profile")
    assert response.status_code == 200
    assert b"Demo User" in response.data
    assert b"demo@spendly.com" in response.data


def test_profile_shows_summary_stats(client):
    _login(client)

    response = client.get("/profile")
    assert b"393.49" in response.data
    assert b">8<" in response.data
    assert b"Bills" in response.data


def test_profile_shows_transaction_rows(client):
    _login(client)

    response = client.get("/profile")
    row_count = response.data.count(b'class="profile-badge ')
    assert row_count >= 3


def test_profile_shows_category_breakdown(client):
    _login(client)

    response = client.get("/profile")
    cat_count = response.data.count(b"profile-cat-row")
    assert cat_count >= 3


def test_profile_nav_shows_username_and_logout(client):
    _login(client)

    response = client.get("/profile")
    nav = _nav_links(response.data)
    assert "Demo User" in nav
    assert "Logout" in nav
    assert "Sign in" not in nav


def test_profile_template_has_no_hex_colors():
    template = Path("templates/profile.html").read_text(encoding="utf-8")
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", template) is None


def test_profile_template_has_no_inline_styles():
    template = Path("templates/profile.html").read_text(encoding="utf-8")
    assert "style=" not in template
