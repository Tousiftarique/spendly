"""
Spec-based tests for Step 6: Date Filter for Profile Page.

Reference: .claude/specs/06-profile-date-filter.md

These tests treat `GET /profile` as a black box driven purely by the
`date_from` / `date_to` query-string contract described in the spec. They do
not assume any internal helper names, HTML class names, or exact date-math
algorithms beyond what the spec itself states explicitly (e.g. "This Month"
starts on the first day of the current month).

Seed data (per task brief): user demo@spendly.com / demo123 has expenses on
days 1, 3, 5, 8, 10, 14, 18, 22 of the *current* month. Dates are computed
relative to `date.today()` so the suite stays correct on any run date.
"""

import html as html_lib
import re
from datetime import date, timedelta

import pytest

from app import _date_presets, _months_ago, _resolve_active_preset, _resolve_date_filter
from database.db import get_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# --------------------------------------------------------------------- #
# Shared constants / helpers
# --------------------------------------------------------------------- #

SEED_DAYS = [1, 3, 5, 8, 10, 14, 18, 22]
SEED_TOTAL = round(45.50 + 20.00 + 120.00 + 60.00 + 15.75 + 89.99 + 12.00 + 30.25, 2)

PRESET_LABELS = ("This Month", "Last 3 Months", "Last 6 Months", "All Time")


def _seed_date(day):
    """Return the ISO date string for a seeded expense's calendar day
    in the current month (matches how seed_db() builds its dates)."""
    return date.today().replace(day=day).isoformat()


def _login(client):
    return client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
    )


def _expenses_row_count():
    """Read the expenses table directly to confirm filtering never
    mutates data (spec: filtering is read-only)."""
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
        return row["n"]
    finally:
        conn.close()


def _extract_href_for_label(html_body, label):
    """Find the <a ...>label</a> preset link and return its href,
    HTML-unescaped (Jinja auto-escapes `&` to `&amp;` in query strings)."""
    marker = f">{label}<"
    idx = html_body.index(marker)
    anchor_start = html_body.rindex("<a ", 0, idx)
    tag = html_body[anchor_start:idx]
    match = re.search(r'href="([^"]*)"', tag)
    assert match, f"Expected an href on the {label!r} preset link"
    return html_lib.unescape(match.group(1))


def _input_tag(html_body, field_name):
    """Return the full <input ...> tag whose name attribute matches
    field_name, regardless of attribute ordering."""
    marker = f'name="{field_name}"'
    idx = html_body.index(marker)
    tag_start = html_body.rindex("<input", 0, idx)
    tag_end = html_body.index(">", idx)
    return html_body[tag_start:tag_end]


def _rupee_total(user_id=1):
    """Baseline unfiltered total, formatted like a 2-decimal currency
    amount, used only to sanity-check that unaffected requests return
    the same figures as the true unfiltered view."""
    stats = get_summary_stats(user_id)
    return f"{stats['total_spent']:.2f}"


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestAuthGuard:
    def test_filtered_request_redirects_to_login_when_unauthenticated(self, client):
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_unfiltered_request_redirects_to_login_when_unauthenticated(self, client):
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# No params => identical to unfiltered (Step 5) behaviour
# --------------------------------------------------------------------- #

class TestNoParamsIsUnfiltered:
    def test_no_params_returns_200(self, client):
        _login(client)
        response = client.get("/profile")
        assert response.status_code == 200

    def test_no_params_shows_currency_symbol(self, client):
        _login(client)
        response = client.get("/profile")
        assert "₹".encode() in response.data, "Expected the ₹ symbol on the profile page"

    def test_no_params_does_not_flash_any_filter_error(self, client):
        _login(client)
        response = client.get("/profile")
        assert b"Start date must be before end date." not in response.data

    def test_no_params_does_not_modify_expenses_table(self, client):
        _login(client)
        before = _expenses_row_count()
        client.get("/profile")
        after = _expenses_row_count()
        assert before == after == len(SEED_DAYS)


# --------------------------------------------------------------------- #
# Preset links are present and well-formed
# --------------------------------------------------------------------- #

class TestPresetLinksPresent:
    @pytest.mark.parametrize("label", PRESET_LABELS)
    def test_preset_label_rendered(self, client, label):
        _login(client)
        response = client.get("/profile")
        assert label.encode() in response.data, f"Expected preset label {label!r} on the page"

    def test_all_time_preset_points_to_clean_profile_url(self, client):
        _login(client)
        response = client.get("/profile")
        href = _extract_href_for_label(response.data.decode(), "All Time")
        assert href in ("/profile", "/profile?"), (
            "'All Time' must link to a clean /profile URL with no query params"
        )

    def test_this_month_preset_starts_on_first_of_current_month(self, client):
        _login(client)
        response = client.get("/profile")
        href = _extract_href_for_label(response.data.decode(), "This Month")
        assert "date_from=" in href and "date_to=" in href
        expected_from = date.today().replace(day=1).isoformat()
        assert f"date_from={expected_from}" in href

    def test_last_3_months_ends_today_and_starts_no_later_than_this_month(self, client):
        _login(client)
        response = client.get("/profile")
        page = response.data.decode()
        this_month_href = _extract_href_for_label(page, "This Month")
        last_3_href = _extract_href_for_label(page, "Last 3 Months")

        this_month_from = re.search(r"date_from=([\d-]+)", this_month_href).group(1)
        last_3_from = re.search(r"date_from=([\d-]+)", last_3_href).group(1)
        last_3_to = re.search(r"date_to=([\d-]+)", last_3_href).group(1)

        assert last_3_to == date.today().isoformat(), "'Last 3 Months' must end today"
        assert last_3_from <= this_month_from, (
            "'Last 3 Months' must start no later than 'This Month' (a wider window)"
        )

    def test_last_6_months_starts_no_later_than_last_3_months(self, client):
        _login(client)
        response = client.get("/profile")
        page = response.data.decode()
        last_3_href = _extract_href_for_label(page, "Last 3 Months")
        last_6_href = _extract_href_for_label(page, "Last 6 Months")

        last_3_from = re.search(r"date_from=([\d-]+)", last_3_href).group(1)
        last_6_from = re.search(r"date_from=([\d-]+)", last_6_href).group(1)
        last_6_to = re.search(r"date_to=([\d-]+)", last_6_href).group(1)

        assert last_6_to == date.today().isoformat(), "'Last 6 Months' must end today"
        assert last_6_from <= last_3_from, (
            "'Last 6 Months' must start no later than 'Last 3 Months' (a wider window)"
        )


# --------------------------------------------------------------------- #
# Following each preset link works and never mutates data
# --------------------------------------------------------------------- #

class TestFollowingPresetLinks:
    @pytest.mark.parametrize("label", PRESET_LABELS)
    def test_following_preset_link_returns_200(self, client, label):
        _login(client)
        page = client.get("/profile").data.decode()
        href = _extract_href_for_label(page, label)
        response = client.get(href)
        assert response.status_code == 200

    @pytest.mark.parametrize("label", PRESET_LABELS)
    def test_following_preset_link_does_not_mutate_expenses_table(self, client, label):
        _login(client)
        page = client.get("/profile").data.decode()
        href = _extract_href_for_label(page, label)
        before = _expenses_row_count()
        client.get(href)
        after = _expenses_row_count()
        assert before == after == len(SEED_DAYS)

    def test_this_month_never_shows_more_transactions_than_all_time(self, client):
        _login(client)
        page = client.get("/profile").data.decode()
        this_month_href = _extract_href_for_label(page, "This Month")
        all_time_total = get_summary_stats(1)["transaction_count"]

        this_month_from = re.search(r"date_from=([\d-]+)", this_month_href).group(1)
        this_month_to = re.search(r"date_to=([\d-]+)", this_month_href).group(1)
        this_month_total = get_summary_stats(
            1, date_from=this_month_from, date_to=this_month_to
        )["transaction_count"]

        assert this_month_total <= all_time_total


# --------------------------------------------------------------------- #
# Pure helper: _months_ago
# --------------------------------------------------------------------- #

class TestMonthsAgo:
    def test_simple_month_subtraction(self):
        result = _months_ago(date(2026, 5, 15), 3)
        assert result == date(2026, 2, 15)

    def test_clamps_day_to_shorter_month(self):
        result = _months_ago(date(2026, 5, 31), 3)
        assert result == date(2026, 2, 28), "Feb 2026 has 28 days, should clamp"

    def test_handles_year_boundary(self):
        result = _months_ago(date(2026, 1, 15), 3)
        assert result == date(2025, 10, 15)

    def test_zero_months_returns_same_date(self):
        today = date(2026, 6, 10)
        assert _months_ago(today, 0) == today

    def test_clamps_on_leap_year_february(self):
        # 2024 is a leap year: Feb has 29 days
        result = _months_ago(date(2024, 3, 31), 1)
        assert result == date(2024, 2, 29)

    def test_clamps_on_non_leap_year_february(self):
        # 2025 is not a leap year: Feb has 28 days
        result = _months_ago(date(2025, 3, 31), 1)
        assert result == date(2025, 2, 28)

    def test_six_months_crosses_year_boundary(self):
        result = _months_ago(date(2026, 3, 1), 6)
        assert result == date(2025, 9, 1)


# --------------------------------------------------------------------- #
# Pure helper: _date_presets
# --------------------------------------------------------------------- #

class TestDatePresets:
    def test_returns_all_four_expected_keys(self):
        presets = _date_presets(date(2026, 6, 15))
        assert set(presets.keys()) == {"this_month", "last_3", "last_6", "all"}

    def test_this_month_starts_on_first_of_month(self):
        today = date(2026, 6, 15)
        label, p_from, p_to = _date_presets(today)["this_month"]
        assert label == "This Month"
        assert p_from == "2026-06-01"
        assert p_to == "2026-06-15"

    def test_last_3_spans_three_months_ending_today(self):
        today = date(2026, 6, 15)
        label, p_from, p_to = _date_presets(today)["last_3"]
        assert label == "Last 3 Months"
        assert p_from == "2026-03-15"
        assert p_to == "2026-06-15"

    def test_last_6_spans_six_months_ending_today(self):
        today = date(2026, 6, 15)
        label, p_from, p_to = _date_presets(today)["last_6"]
        assert label == "Last 6 Months"
        assert p_from == "2025-12-15"
        assert p_to == "2026-06-15"

    def test_all_time_has_no_bounds(self):
        label, p_from, p_to = _date_presets(date(2026, 6, 15))["all"]
        assert label == "All Time"
        assert p_from is None
        assert p_to is None


# --------------------------------------------------------------------- #
# Pure helper: _resolve_date_filter
# --------------------------------------------------------------------- #

class TestResolveDateFilter:
    def test_valid_range_returns_iso_bounds_and_no_error(self):
        d_from, d_to, error = _resolve_date_filter("2026-01-01", "2026-01-31")
        assert (d_from, d_to, error) == ("2026-01-01", "2026-01-31", None)

    def test_missing_from_falls_back_to_unfiltered(self):
        d_from, d_to, error = _resolve_date_filter(None, "2026-01-31")
        assert (d_from, d_to, error) == (None, None, None)

    def test_missing_to_falls_back_to_unfiltered(self):
        d_from, d_to, error = _resolve_date_filter("2026-01-01", None)
        assert (d_from, d_to, error) == (None, None, None)

    def test_both_missing_falls_back_to_unfiltered(self):
        d_from, d_to, error = _resolve_date_filter(None, None)
        assert (d_from, d_to, error) == (None, None, None)

    def test_malformed_from_falls_back_to_unfiltered(self):
        d_from, d_to, error = _resolve_date_filter("not-a-date", "2026-01-31")
        assert (d_from, d_to, error) == (None, None, None)

    def test_malformed_to_falls_back_to_unfiltered(self):
        d_from, d_to, error = _resolve_date_filter("2026-01-01", "not-a-date")
        assert (d_from, d_to, error) == (None, None, None)

    def test_from_after_to_returns_error_and_no_bounds(self):
        d_from, d_to, error = _resolve_date_filter("2026-02-01", "2026-01-01")
        assert d_from is None
        assert d_to is None
        assert error == "Start date must be before end date."

    def test_from_equal_to_is_valid_inclusive_range(self):
        d_from, d_to, error = _resolve_date_filter("2026-01-15", "2026-01-15")
        assert (d_from, d_to, error) == ("2026-01-15", "2026-01-15", None)


# --------------------------------------------------------------------- #
# database/queries.py — filtering behaviour
# --------------------------------------------------------------------- #

class TestQueryHelpersUnfiltered:
    def test_get_summary_stats_unfiltered_matches_all_seed_expenses(self, app):
        with app.app_context():
            stats = get_summary_stats(1)
        assert stats["transaction_count"] == 8
        assert stats["total_spent"] == pytest.approx(SEED_TOTAL, abs=0.01)

    def test_get_recent_transactions_unfiltered_returns_all_within_limit(self, app):
        with app.app_context():
            transactions = get_recent_transactions(1, limit=20)
        assert len(transactions) == 8

    def test_get_category_breakdown_unfiltered_covers_all_categories(self, app):
        with app.app_context():
            categories = get_category_breakdown(1)
        names = {c["name"] for c in categories}
        assert names == {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}


class TestQueryHelpersOneSidedBoundsAreUnfiltered:
    def test_summary_stats_only_from_given_is_unfiltered(self, app):
        with app.app_context():
            filtered = get_summary_stats(1, date_from=_seed_date(SEED_DAYS[0]))
            unfiltered = get_summary_stats(1)
        assert filtered == unfiltered

    def test_summary_stats_only_to_given_is_unfiltered(self, app):
        with app.app_context():
            filtered = get_summary_stats(1, date_to=_seed_date(SEED_DAYS[-1]))
            unfiltered = get_summary_stats(1)
        assert filtered == unfiltered


class TestQueryHelpersFiltered:
    def test_get_summary_stats_filters_inclusive_bounds(self, app):
        d_from = _seed_date(3)
        d_to = _seed_date(8)
        with app.app_context():
            stats = get_summary_stats(1, date_from=d_from, date_to=d_to)
        # days 3, 5, 8 fall within [3, 8]
        expected_total = round(20.00 + 120.00 + 60.00, 2)
        assert stats["transaction_count"] == 3
        assert stats["total_spent"] == pytest.approx(expected_total, abs=0.01)

    def test_get_summary_stats_inclusive_on_exact_boundary_dates(self, app):
        d_from = _seed_date(1)
        d_to = _seed_date(1)
        with app.app_context():
            stats = get_summary_stats(1, date_from=d_from, date_to=d_to)
        assert stats["transaction_count"] == 1
        assert stats["total_spent"] == pytest.approx(45.50, abs=0.01)

    def test_get_recent_transactions_filters_to_range(self, app):
        d_from = _seed_date(5)
        d_to = _seed_date(14)
        with app.app_context():
            transactions = get_recent_transactions(1, date_from=d_from, date_to=d_to)
        # days 5, 8, 10, 14 fall within range
        assert len(transactions) == 4

    def test_get_recent_transactions_respects_limit_within_filtered_range(self, app):
        d_from = _seed_date(1)
        d_to = _seed_date(22)
        with app.app_context():
            transactions = get_recent_transactions(1, limit=2, date_from=d_from, date_to=d_to)
        assert len(transactions) == 2

    def test_get_category_breakdown_filters_to_range(self, app):
        d_from = _seed_date(1)
        d_to = _seed_date(5)
        with app.app_context():
            categories = get_category_breakdown(1, date_from=d_from, date_to=d_to)
        names = {c["name"] for c in categories}
        # days 1 (Food), 3 (Transport), 5 (Bills)
        assert names == {"Food", "Transport", "Bills"}

    def test_get_category_breakdown_percentages_sum_to_100(self, app):
        d_from = _seed_date(1)
        d_to = _seed_date(22)
        with app.app_context():
            categories = get_category_breakdown(1, date_from=d_from, date_to=d_to)
        assert sum(c["pct"] for c in categories) == 100

    def test_empty_range_returns_zero_totals_and_no_categories(self, app):
        # A range strictly before the earliest seed expense and after none.
        far_past_from = (date.fromisoformat(_seed_date(1)) - timedelta(days=60)).isoformat()
        far_past_to = (date.fromisoformat(_seed_date(1)) - timedelta(days=30)).isoformat()
        with app.app_context():
            stats = get_summary_stats(1, date_from=far_past_from, date_to=far_past_to)
            transactions = get_recent_transactions(1, date_from=far_past_from, date_to=far_past_to)
            categories = get_category_breakdown(1, date_from=far_past_from, date_to=far_past_to)
        assert stats["total_spent"] == 0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—"
        assert transactions == []
        assert categories == []


# --------------------------------------------------------------------- #

class TestResolveActivePreset:
    PRESETS = _date_presets(date(2026, 6, 15))

    def test_unfiltered_is_all_time(self):
        assert _resolve_active_preset(self.PRESETS, None, None) == "all"

    def test_matching_range_returns_preset_key(self):
        assert _resolve_active_preset(self.PRESETS, "2026-06-01", "2026-06-15") == "this_month"

    def test_non_matching_range_is_custom(self):
        assert _resolve_active_preset(self.PRESETS, "2026-06-02", "2026-06-10") == "custom"


# --------------------------------------------------------------------- #
# Custom range filtering — happy path
# --------------------------------------------------------------------- #

class TestCustomRangeHappyPath:
    def test_valid_custom_range_returns_200(self, client):
        _login(client)
        d_from, d_to = _seed_date(3), _seed_date(8)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        assert response.status_code == 200

    def test_valid_custom_range_excludes_transactions_outside_bounds(self, client):
        _login(client)
        d_from, d_to = _seed_date(3), _seed_date(8)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        page = response.data.decode()
        # Day 1 and day 22 fall outside [day 3, day 8]. Only inspect the data
        # sections — preset links (e.g. "This Month") legitimately contain
        # the 1st of the month in their hrefs.
        table = re.search(r'<table class="profile-table">.*?</table>', page, re.S).group(0)
        cat_list = re.search(r'<div class="profile-cat-list">.*?</section>', page, re.S).group(0)
        data_sections = table + cat_list
        for day in (1, 22):
            seeded = date.fromisoformat(_seed_date(day))
            assert _seed_date(day) not in data_sections
            assert f"{seeded.strftime('%b')} {seeded.day}, {seeded.year}" not in data_sections
        # Day 1 (Groceries) and day 22 (Restaurant) are the only Food rows.
        assert "Groceries" not in table
        assert "Restaurant" not in table

    def test_valid_custom_range_includes_boundary_dates(self, client):
        _login(client)
        d_from, d_to = _seed_date(3), _seed_date(8)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        page = response.data.decode()
        # Inclusive bounds: day 3 and day 8 themselves must be represented
        # in the query used to build the page (checked at the DB layer,
        # since exact date rendering format is not part of the spec).
        stats = get_summary_stats(1, date_from=d_from, date_to=d_to)
        assert stats["transaction_count"] == 3  # days 3, 5, 8
        assert response.status_code == 200
        assert page  # page rendered without error

    def test_custom_range_prefills_date_input_values(self, client):
        _login(client)
        d_from, d_to = _seed_date(3), _seed_date(14)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        page = response.data.decode()
        from_tag = _input_tag(page, "date_from")
        to_tag = _input_tag(page, "date_to")
        assert f'value="{d_from}"' in from_tag
        assert f'value="{d_to}"' in to_tag

    def test_valid_custom_range_does_not_mutate_expenses_table(self, client):
        _login(client)
        d_from, d_to = _seed_date(1), _seed_date(22)
        before = _expenses_row_count()
        client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        after = _expenses_row_count()
        assert before == after == len(SEED_DAYS)

    def test_from_equal_to_is_a_valid_single_day_range(self, client):
        _login(client)
        d = _seed_date(5)
        response = client.get(f"/profile?date_from={d}&date_to={d}")
        assert response.status_code == 200
        assert b"Start date must be before end date." not in response.data


# --------------------------------------------------------------------- #
# Malformed / partial params fall back silently to unfiltered
# --------------------------------------------------------------------- #

class TestMalformedAndPartialParamsFallBack:
    def test_malformed_date_from_does_not_crash(self, client):
        _login(client)
        response = client.get("/profile?date_from=not-a-date&date_to=2026-01-31")
        assert response.status_code == 200

    def test_malformed_date_to_does_not_crash(self, client):
        _login(client)
        response = client.get("/profile?date_from=2026-01-01&date_to=not-a-date")
        assert response.status_code == 200

    def test_malformed_dates_fall_back_to_all_time_totals(self, client):
        _login(client)
        expected_total = _rupee_total()
        response = client.get("/profile?date_from=nope&date_to=nope")
        assert response.status_code == 200
        assert expected_total.encode() in response.data

    def test_only_date_from_given_falls_back_to_all_time_totals(self, client):
        _login(client)
        expected_total = _rupee_total()
        response = client.get(f"/profile?date_from={_seed_date(3)}")
        assert response.status_code == 200
        assert expected_total.encode() in response.data

    def test_only_date_to_given_falls_back_to_all_time_totals(self, client):
        _login(client)
        expected_total = _rupee_total()
        response = client.get(f"/profile?date_to={_seed_date(8)}")
        assert response.status_code == 200
        assert expected_total.encode() in response.data

    def test_empty_string_params_fall_back_to_all_time_totals(self, client):
        _login(client)
        expected_total = _rupee_total()
        response = client.get("/profile?date_from=&date_to=")
        assert response.status_code == 200
        assert expected_total.encode() in response.data

    def test_sql_injection_attempt_in_date_from_does_not_crash_or_error(self, client):
        _login(client)
        response = client.get(
            "/profile?date_from=' OR '1'='1&date_to=2026-01-31"
        )
        assert response.status_code == 200
        assert _expenses_row_count() == len(SEED_DAYS), (
            "An injection attempt must never alter the expenses table"
        )

    def test_excessively_long_date_from_does_not_crash(self, client):
        _login(client)
        long_value = "9" * 5000
        response = client.get(f"/profile?date_from={long_value}&date_to=2026-01-31")
        assert response.status_code == 200

    def test_malformed_params_do_not_mutate_expenses_table(self, client):
        _login(client)
        before = _expenses_row_count()
        client.get("/profile?date_from=garbage&date_to=garbage")
        after = _expenses_row_count()
        assert before == after == len(SEED_DAYS)


# --------------------------------------------------------------------- #
# date_from > date_to => flash error + fall back to unfiltered
# --------------------------------------------------------------------- #

class TestInvertedRangeValidationError:
    def test_inverted_range_returns_200_not_400(self, client):
        _login(client)
        d_from, d_to = _seed_date(22), _seed_date(1)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        assert response.status_code == 200

    def test_inverted_range_flashes_exact_error_message(self, client):
        _login(client)
        d_from, d_to = _seed_date(22), _seed_date(1)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        assert b"Start date must be before end date." in response.data

    def test_inverted_range_falls_back_to_all_time_totals(self, client):
        _login(client)
        expected_total = _rupee_total()
        d_from, d_to = _seed_date(22), _seed_date(1)
        response = client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        assert expected_total.encode() in response.data

    def test_inverted_range_does_not_mutate_expenses_table(self, client):
        _login(client)
        d_from, d_to = _seed_date(22), _seed_date(1)
        before = _expenses_row_count()
        client.get(f"/profile?date_from={d_from}&date_to={d_to}")
        after = _expenses_row_count()
        assert before == after == len(SEED_DAYS)


# --------------------------------------------------------------------- #
# Empty result range => zero-state, no errors
# --------------------------------------------------------------------- #

class TestEmptyResultRange:
    def test_range_with_no_matching_expenses_returns_200(self, client):
        _login(client)
        far_from = "1999-01-01"
        far_to = "1999-01-31"
        response = client.get(f"/profile?date_from={far_from}&date_to={far_to}")
        assert response.status_code == 200

    def test_range_with_no_matching_expenses_shows_zero_total(self, client):
        _login(client)
        far_from = "1999-01-01"
        far_to = "1999-01-31"
        response = client.get(f"/profile?date_from={far_from}&date_to={far_to}")
        assert "₹0.00".encode() in response.data, (
            "Expected a ₹0.00 total for a range with no matching expenses"
        )

    def test_range_with_no_matching_expenses_does_not_crash_or_mutate_data(self, client):
        _login(client)
        before = _expenses_row_count()
        far_from, far_to = "1999-01-01", "1999-01-31"
        response = client.get(f"/profile?date_from={far_from}&date_to={far_to}")
        after = _expenses_row_count()
        assert response.status_code == 200
        assert before == after == len(SEED_DAYS)


# --------------------------------------------------------------------- #
# Currency formatting is preserved regardless of filter state
# --------------------------------------------------------------------- #

class TestCurrencySymbolAlwaysPresent:
    @pytest.mark.parametrize(
        "query_string",
        [
            "",
            f"?date_from={_seed_date(3)}&date_to={_seed_date(8)}",
            "?date_from=bad&date_to=bad",
            f"?date_from={_seed_date(22)}&date_to={_seed_date(1)}",  # inverted
            "?date_from=1999-01-01&date_to=1999-01-31",  # empty range
        ],
    )
    def test_rupee_symbol_present_for_every_filter_state(self, client, query_string):
        _login(client)
        response = client.get(f"/profile{query_string}")
        assert response.status_code == 200
        assert "₹".encode() in response.data
