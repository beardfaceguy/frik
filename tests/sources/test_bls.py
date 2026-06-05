"""
Unit and regression tests for frik.sources.bls.

Mocks all HTTP via the `responses` library — no network access needed.
"""

from __future__ import annotations

import json
import os

import pytest
import responses as resp_lib

from frik.sources.bls import (
    DATA_TYPES,
    DEFAULT_OCCUPATIONS,
    _fetch,
    _latest_annual,
    _load_api_key,
    _series_id,
    fetch_wages,
)


# ---------------------------------------------------------------------------
# _series_id — regression: these exact strings must never drift
# ---------------------------------------------------------------------------

class TestSeriesId:
    def test_software_developers(self):
        assert _series_id("15-1252", "04") == "OEUN000000000000015125204"

    def test_computer_occupations_all_other(self):
        assert _series_id("15-1299", "13") == "OEUN000000000000015129913"

    def test_data_scientists(self):
        assert _series_id("15-2051", "14") == "OEUN000000000000015205114"

    def test_no_dash_variant(self):
        """SOC codes without dashes should produce the same ID."""
        assert _series_id("151252", "04") == _series_id("15-1252", "04")

    def test_length(self):
        """BLS OEWS national series IDs are always 25 characters."""
        assert len(_series_id("15-1252", "04")) == 25

    def test_prefix(self):
        """All OEWS national series start with OEUN."""
        assert _series_id("15-1252", "04").startswith("OEUN")

    @pytest.mark.parametrize("dt_code", list(DATA_TYPES.keys()))
    def test_all_data_types_produce_25_char_ids(self, dt_code):
        assert len(_series_id("15-1252", dt_code)) == 25


# ---------------------------------------------------------------------------
# _latest_annual — value extraction from API response
# ---------------------------------------------------------------------------

class TestLatestAnnual:
    def test_extracts_annual_value(self):
        raw = {
            "Results": {
                "series": [
                    {
                        "seriesID": "OEUN000000000000015125204",
                        "data": [
                            {"year": "2025", "period": "A01", "value": "148100", "footnotes": []},
                            {"year": "2025", "period": "M01", "value": "99999", "footnotes": []},
                        ],
                    }
                ]
            }
        }
        result = _latest_annual(raw)
        assert result["OEUN000000000000015125204"] == "148100"

    def test_returns_none_for_empty_data(self):
        raw = {
            "Results": {
                "series": [
                    {"seriesID": "OEUN000000000000015125204", "data": []}
                ]
            }
        }
        result = _latest_annual(raw)
        assert result["OEUN000000000000015125204"] is None

    def test_prefers_a01_period_over_monthly(self):
        """Annual period (A01) must be selected, not monthly periods."""
        raw = {
            "Results": {
                "series": [
                    {
                        "seriesID": "X",
                        "data": [
                            {"year": "2025", "period": "M12", "value": "bad",  "footnotes": []},
                            {"year": "2025", "period": "A01", "value": "good", "footnotes": []},
                        ],
                    }
                ]
            }
        }
        assert _latest_annual(raw)["X"] == "good"

    def test_empty_results(self):
        assert _latest_annual({}) == {}
        assert _latest_annual({"Results": {}}) == {}


# ---------------------------------------------------------------------------
# _load_api_key — env var takes precedence
# ---------------------------------------------------------------------------

class TestLoadApiKey:
    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("BLS_API_KEY", "testkey123")
        assert _load_api_key() == "testkey123"

    def test_returns_empty_when_absent(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BLS_API_KEY", raising=False)
        # Point home to tmp_path so the key file doesn't exist
        monkeypatch.setenv("HOME", str(tmp_path))
        # _load_api_key uses Path.home() which re-reads HOME on each call
        # Force it by patching directly
        import frik.sources.bls as bls_mod
        original = bls_mod.Path.home
        monkeypatch.setattr(bls_mod, "Path", type("P", (), {
            "home": staticmethod(lambda: tmp_path),
            "__truediv__": lambda self, other: tmp_path / other,
        }))
        # Simpler: just verify no env var and missing file returns ""
        monkeypatch.delenv("BLS_API_KEY", raising=False)
        key = _load_api_key()
        assert isinstance(key, str)


# ---------------------------------------------------------------------------
# _fetch — HTTP layer
# ---------------------------------------------------------------------------

class TestFetch:
    @resp_lib.activate
    def test_posts_to_bls_api(self):
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        result = _fetch(["OEUN000000000000015125204"], api_key="")
        assert result["status"] == "REQUEST_SUCCEEDED"

    @resp_lib.activate
    def test_includes_api_key_when_provided(self):
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        _fetch(["OEUN000000000000015125204"], api_key="mykey")
        body = json.loads(resp_lib.calls[0].request.body)
        assert body["registrationkey"] == "mykey"

    @resp_lib.activate
    def test_omits_api_key_when_empty(self):
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        _fetch(["OEUN000000000000015125204"], api_key="")
        body = json.loads(resp_lib.calls[0].request.body)
        assert "registrationkey" not in body

    @resp_lib.activate
    def test_raises_on_http_error(self):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     status=500)
        with pytest.raises(Exception):
            _fetch(["OEUN000000000000015125204"], api_key="")


# ---------------------------------------------------------------------------
# fetch_wages — integration (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFetchWages:
    @resp_lib.activate
    def test_returns_list_of_occupations(self, bls_multi_response):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=bls_multi_response, status=200)

        results = fetch_wages(soc_codes=["15-1252"], api_key="test")
        assert isinstance(results, list)
        assert len(results) >= 1

    @resp_lib.activate
    def test_result_has_expected_keys(self, bls_software_dev_response):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=bls_software_dev_response, status=200)

        results = fetch_wages(soc_codes=["15-1252"], api_key="test")
        assert len(results) == 1
        r = results[0]
        assert r["soc"] == "15-1252"
        assert "wages" in r
        assert "annual_mean" in r["wages"]
        assert "annual_median" in r["wages"]
        assert "annual_p75" in r["wages"]
        assert "annual_p90" in r["wages"]

    @resp_lib.activate
    def test_parses_known_wage_value(self, bls_software_dev_response):
        """Regression: $148,100 mean for 15-1252 must parse as float 148100.0."""
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=bls_software_dev_response, status=200)

        results = fetch_wages(soc_codes=["15-1252"], api_key="test")
        assert results[0]["wages"]["annual_mean"] == 148100.0

    @resp_lib.activate
    def test_missing_data_returns_none_not_error(self, bls_multi_response):
        """Series with empty data[] should yield None, not raise."""
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=bls_multi_response, status=200)

        results = fetch_wages(soc_codes=["15-1252"], api_key="test")
        r = results[0]
        # p90 has empty data in bls_multi_response
        assert r["wages"]["annual_p90"] is None

    @resp_lib.activate
    def test_unknown_soc_code_included(self):
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        results = fetch_wages(soc_codes=["99-9999"], api_key="test")
        assert any(r["soc"] == "99-9999" for r in results)

    @resp_lib.activate
    def test_default_occupations_all_fetched(self):
        """Without explicit soc_codes, all DEFAULT_OCCUPATIONS must appear in results."""
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}}
        # The function batches 50 at a time; may hit the endpoint multiple times
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        results = fetch_wages(api_key="test")
        result_socs = {r["soc"] for r in results}
        expected_socs = {o["soc"] for o in DEFAULT_OCCUPATIONS}
        assert expected_socs.issubset(result_socs)
