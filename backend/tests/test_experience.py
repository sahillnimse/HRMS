"""Unit tests for deterministic years_experience computation."""

from datetime import date

from app.services.experience import compute_years_experience, parse_resume_date


def test_single_interval_month_year():
    work = [{"start_date": "Jan 2020", "end_date": "Dec 2021"}]
    assert compute_years_experience(work, today=date(2025, 6, 1)) == 2.0


def test_overlapping_intervals_are_merged():
    work = [
        {"start_date": "Jan 2020", "end_date": "Dec 2022"},
        {"start_date": "Jun 2021", "end_date": "Jun 2023"},
    ]
    # Union Jan 2020 -> Jun 2023 inclusive = 42 months = 3.5 years
    assert compute_years_experience(work, today=date(2025, 6, 1)) == 3.5


def test_present_and_year_only_formats():
    work = [
        {"start_date": "2019", "end_date": "2019"},  # 12 months
        {"start_date": "01/2023", "end_date": "Present"},  # Jan 2023 -> Dec 2024 = 24 months
    ]
    assert compute_years_experience(work, today=date(2024, 12, 15)) == 3.0


def test_iso_and_quarter_formats():
    work = [
        {"start_date": "2021-01", "end_date": "2021-06"},  # 6 months
        {"start_date": "Q1 2022", "end_date": "Q4 2022"},  # 12 months
    ]
    assert compute_years_experience(work, today=date(2025, 1, 1)) == 1.5


def test_missing_end_date_counts_to_today():
    work = [{"start_date": "Jan 2024", "end_date": None}]
    assert compute_years_experience(work, today=date(2024, 12, 1)) == 1.0


def test_future_dates_are_clamped():
    work = [{"start_date": "Jan 2024", "end_date": "Dec 2030"}]
    assert compute_years_experience(work, today=date(2024, 12, 1)) == 1.0


def test_invalid_or_reversed_dates_return_zero():
    assert compute_years_experience([]) == 0.0
    assert compute_years_experience([{"start_date": "invalid", "end_date": "nope"}]) == 0.0
    assert compute_years_experience([{"start_date": "Dec 2022", "end_date": "Jan 2021"}]) == 0.0


def test_parse_month_name_variants():
    ref = date(2025, 1, 1)
    assert parse_resume_date("Sept. 2020", today=ref) == parse_resume_date("Sep 2020", today=ref)
    assert parse_resume_date("January, 2020", today=ref) == 2020 * 12
    assert parse_resume_date("current", is_end=True, today=ref) == 2025 * 12
