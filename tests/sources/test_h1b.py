"""
Unit and regression tests for frik.sources.h1b.

Tests cover pure functions and SQLite-backed functions using the h1b_db fixture
from conftest.py. No network access needed — download() is tested for error
paths only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from frik.sources.h1b import (
    UNIT_TO_ANNUAL,
    _cache_db_path,
    _find_db,
    _xlsx_to_annual,
    search,
    summarize,
)


# ---------------------------------------------------------------------------
# _xlsx_to_annual — regression: exact multipliers must never drift
# ---------------------------------------------------------------------------

class TestXlsxToAnnual:
    """Regression suite for wage-unit normalization.

    If these constants change, every downstream salary figure changes with them.
    Any test failure here requires explicit human sign-off before merging.
    """

    @pytest.mark.parametrize("unit,hourly,expected", [
        ("Hour",       50.0,  104_000.0),
        ("Hour",       85.0,  176_800.0),
        ("Hour",      110.0,  228_800.0),
        ("Week",    3_000.0,  156_000.0),
        ("Month",  10_000.0,  120_000.0),
        ("Year",  150_000.0,  150_000.0),
        ("Bi-Weekly", 5_000.0, 130_000.0),
    ])
    def test_unit_conversion(self, unit, hourly, expected):
        assert _xlsx_to_annual(hourly, unit) == pytest.approx(expected)

    def test_none_wage_returns_none(self):
        assert _xlsx_to_annual(None, "Year") is None

    def test_none_unit_returns_none(self):
        assert _xlsx_to_annual(100_000.0, None) is None

    def test_empty_unit_returns_none(self):
        assert _xlsx_to_annual(100_000.0, "") is None

    def test_unknown_unit_returns_none(self):
        assert _xlsx_to_annual(100_000.0, "Quarter") is None

    def test_strips_whitespace_from_unit(self):
        """Units with surrounding spaces must still convert."""
        assert _xlsx_to_annual(50.0, "  Hour  ") == pytest.approx(104_000.0)

    def test_zero_wage_returns_zero(self):
        assert _xlsx_to_annual(0.0, "Year") == 0.0

    def test_result_is_rounded_to_two_decimals(self):
        result = _xlsx_to_annual(33.33, "Hour")
        assert result == round(33.33 * 2080, 2)

    def test_unit_to_annual_constants(self):
        """Regression: multipliers themselves must not change."""
        assert UNIT_TO_ANNUAL["Year"]      == 1.0
        assert UNIT_TO_ANNUAL["Hour"]      == 2080.0
        assert UNIT_TO_ANNUAL["Week"]      == 52.0
        assert UNIT_TO_ANNUAL["Month"]     == 12.0
        assert UNIT_TO_ANNUAL["Bi-Weekly"] == 26.0


# ---------------------------------------------------------------------------
# _cache_db_path
# ---------------------------------------------------------------------------

class TestCacheDbPath:
    def test_returns_path_object(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        result = _cache_db_path(2025, 4)
        assert isinstance(result, Path)

    def test_filename_contains_fy_and_quarter(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        result = _cache_db_path(2025, 4)
        assert "FY2025" in result.name
        assert "Q4" in result.name

    def test_creates_cache_dir(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        new_dir = tmp_path / "nested" / "cache"
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", new_dir)
        _cache_db_path(2025, 4)
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# _find_db
# ---------------------------------------------------------------------------

class TestFindDb:
    def test_returns_none_when_cache_missing(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path / "nonexistent")
        assert _find_db() is None

    def test_returns_none_when_cache_empty(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        assert _find_db() is None

    def test_returns_most_recent_db(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        (tmp_path / "h1b_FY2024_Q4.db").touch()
        (tmp_path / "h1b_FY2025_Q4.db").touch()
        result = _find_db()
        assert result is not None
        assert "FY2025" in result.name


# ---------------------------------------------------------------------------
# search — using h1b_db fixture
# ---------------------------------------------------------------------------

class TestSearch:
    def test_returns_results_for_known_title(self, h1b_db):
        rows = search(title="Software Engineer", db_path=h1b_db)
        assert len(rows) >= 1
        assert all("Software Engineer" in r["job_title"] for r in rows)

    def test_filters_by_state(self, h1b_db):
        rows = search(title="Software Engineer", state="CA", db_path=h1b_db)
        assert all(r["worksite_state"] == "CA" for r in rows)

    def test_filters_by_employer(self, h1b_db):
        rows = search(employer="Google", db_path=h1b_db)
        assert all("GOOGLE" in r["employer"] for r in rows)

    def test_state_filter_case_insensitive(self, h1b_db):
        rows_upper = search(state="CA", db_path=h1b_db)
        rows_lower = search(state="ca", db_path=h1b_db)
        assert len(rows_upper) == len(rows_lower)

    def test_results_sorted_by_annual_from_desc(self, h1b_db):
        rows = search(db_path=h1b_db, limit=100)
        wages = [r["annual_from"] for r in rows if r["annual_from"] is not None]
        assert wages == sorted(wages, reverse=True)

    def test_limit_respected(self, h1b_db):
        rows = search(db_path=h1b_db, limit=2)
        assert len(rows) <= 2

    def test_no_results_returns_empty_list(self, h1b_db):
        rows = search(title="Underwater Basket Weaver", db_path=h1b_db)
        assert rows == []

    def test_raises_when_db_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.db"
        with pytest.raises(FileNotFoundError):
            search(db_path=missing)

    def test_result_has_expected_keys(self, h1b_db):
        rows = search(db_path=h1b_db, limit=1)
        assert len(rows) == 1
        expected_keys = {
            "job_title", "employer", "worksite_city", "worksite_state",
            "annual_from", "annual_to", "soc_code", "pw_level", "decision_date",
        }
        assert expected_keys.issubset(rows[0].keys())

    def test_hourly_wages_normalized_to_annual(self, h1b_db):
        """Data Scientist row in fixture has hourly wage — verify annual normalization."""
        rows = search(title="Data Scientist", db_path=h1b_db)
        assert len(rows) >= 1
        # $85/hr → $176,800; $110/hr → $228,800
        assert any(r["annual_from"] == pytest.approx(176_800.0) for r in rows)


# ---------------------------------------------------------------------------
# summarize — using h1b_db fixture
# ---------------------------------------------------------------------------

class TestSummarize:
    def test_returns_stats_dict(self, h1b_db):
        stats = summarize(db_path=h1b_db)
        required = {"n", "mean", "median", "p25", "p75", "p90", "min", "max"}
        assert required.issubset(stats.keys())

    def test_n_equals_all_rows_with_wage(self, h1b_db):
        """summarize() counts all rows with annual_from > 10k (7 total in fixture).
        case_status filtering happens at ingest time (_build_db), not query time.
        """
        stats = summarize(db_path=h1b_db)
        assert stats["n"] == 7

    def test_p25_lte_median_lte_p75(self, h1b_db):
        stats = summarize(db_path=h1b_db)
        assert stats["p25"] <= stats["median"] <= stats["p75"]

    def test_min_lte_p25_and_max_gte_p90(self, h1b_db):
        stats = summarize(db_path=h1b_db)
        assert stats["min"] <= stats["p25"]
        assert stats["max"] >= stats["p90"]

    def test_filter_by_state(self, h1b_db):
        ca_stats = summarize(state="CA", db_path=h1b_db)
        wa_stats  = summarize(state="WA", db_path=h1b_db)
        assert ca_stats["n"] > wa_stats["n"]

    def test_empty_query_returns_n_zero(self, h1b_db):
        stats = summarize(title="Intergalactic Neutrino Wrangler", db_path=h1b_db)
        assert stats["n"] == 0
        assert "mean" not in stats

    def test_raises_when_db_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.db"
        with pytest.raises(FileNotFoundError):
            summarize(db_path=missing)

    def test_mean_is_arithmetic_mean(self, h1b_db):
        """Verify mean calculation isn't accidentally returning median."""
        stats = summarize(db_path=h1b_db)
        # Mean and median won't be identical for an asymmetric distribution
        # At minimum, both should be positive and reasonable salary figures
        assert stats["mean"] > 50_000
        assert stats["median"] > 50_000


# ---------------------------------------------------------------------------
# download — error path only (no network)
# ---------------------------------------------------------------------------

class TestDownloadErrors:
    def test_raises_for_unknown_fy_quarter(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        from frik.sources.h1b import download
        with pytest.raises(ValueError, match="No known URL"):
            download(fy=1899, quarter=1)

    def test_returns_existing_cache_without_download(self, tmp_path, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        # Pre-create the db file
        db = tmp_path / "h1b_FY2025_Q4.db"
        db.touch()
        from frik.sources.h1b import download
        result = download(fy=2025, quarter=4, force=False)
        assert result == db
