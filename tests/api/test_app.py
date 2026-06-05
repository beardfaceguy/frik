"""
API integration tests using FastAPI's TestClient (synchronous httpx transport).

All BLS HTTP calls are mocked via `responses`. H1B tests reuse the h1b_db
fixture from conftest.py and monkeypatch the h1b source's CACHE_DIR.
"""

from __future__ import annotations

import pytest
import responses as resp_lib
from fastapi.testclient import TestClient

from frik.api.app import app
from frik.sources.h1b import H1BDATA_URL

# Minimal HTML that scrape_h1bdata() can parse — used to mock h1bdata.info in CI
_MOCK_H1BDATA_HTML = (
    "<html><body><table>"
    "<tr><th>Employer</th><th>Job Title</th><th>Base Salary</th>"
    "<th>Location</th><th>Submit Date</th><th>Start Date</th></tr>"
    "<tr><td>ACME CORP</td><td>SOFTWARE ENGINEER</td><td>180,000</td>"
    "<td>SAN JOSE, CA</td><td>01/01/2025</td><td>02/01/2025</td></tr>"
    "</table></body></html>"
)

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self):
        r = client.get("/health")
        assert r.status_code == 200

    def test_body(self):
        r = client.get("/health")
        assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /soc
# ---------------------------------------------------------------------------

class TestSoc:
    def test_returns_200(self):
        r = client.get("/soc")
        assert r.status_code == 200

    def test_returns_list(self):
        r = client.get("/soc")
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_contains_software_developers(self):
        r = client.get("/soc")
        socs = {entry["soc"] for entry in r.json()}
        assert "15-1252" in socs

    def test_each_entry_has_required_fields(self):
        r = client.get("/soc")
        for entry in r.json():
            assert "soc" in entry
            assert "title" in entry
            assert "category" in entry
            assert "notes" in entry


# ---------------------------------------------------------------------------
# /wages
# ---------------------------------------------------------------------------

_BLS_PAYLOAD = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {
        "series": [
            {
                "seriesID": "OEUN000000000000015125204",
                "data": [{"year": "2025", "period": "A01",
                           "value": "148100", "footnotes": []}],
            },
            {
                "seriesID": "OEUN000000000000015125213",
                "data": [{"year": "2025", "period": "A01",
                           "value": "135980", "footnotes": []}],
            },
            {
                "seriesID": "OEUN000000000000015125214",
                "data": [{"year": "2025", "period": "A01",
                           "value": "171980", "footnotes": []}],
            },
            {
                "seriesID": "OEUN000000000000015125215",
                "data": [],
            },
            {
                "seriesID": "OEUN000000000000015125201",
                "data": [{"year": "2025", "period": "A01",
                           "value": "1820.4", "footnotes": []}],
            },
        ]
    },
}


class TestWages:
    @resp_lib.activate
    def test_returns_200(self):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=_BLS_PAYLOAD, status=200)
        r = client.get("/wages?soc=15-1252")
        assert r.status_code == 200

    @resp_lib.activate
    def test_returns_list(self):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=_BLS_PAYLOAD, status=200)
        data = client.get("/wages?soc=15-1252").json()
        assert isinstance(data, list)
        assert len(data) == 1

    @resp_lib.activate
    def test_response_shape(self):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=_BLS_PAYLOAD, status=200)
        entry = client.get("/wages?soc=15-1252").json()[0]
        assert entry["soc"] == "15-1252"
        assert "wages" in entry
        wages = entry["wages"]
        assert "annual_mean" in wages
        assert "annual_median" in wages
        assert "annual_p75" in wages
        assert "annual_p90" in wages

    @resp_lib.activate
    def test_known_wage_value_parsed_correctly(self):
        """Regression: $148,100 annual_mean for 15-1252 must survive the round-trip."""
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=_BLS_PAYLOAD, status=200)
        wages = client.get("/wages?soc=15-1252").json()[0]["wages"]
        assert wages["annual_mean"] == 148100.0

    @resp_lib.activate
    def test_null_for_missing_series_data(self):
        """p90 has empty data in mock — should return null, not error."""
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=_BLS_PAYLOAD, status=200)
        wages = client.get("/wages?soc=15-1252").json()[0]["wages"]
        assert wages["annual_p90"] is None

    @resp_lib.activate
    def test_multiple_soc_params(self):
        """?soc=A&soc=B — FastAPI repeats query params as a list."""
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json={"status": "REQUEST_SUCCEEDED", "Results": {"series": []}},
                     status=200)
        r = client.get("/wages?soc=15-1252&soc=15-1299")
        assert r.status_code == 200
        assert len(r.json()) == 2

    @resp_lib.activate
    def test_bls_api_failure_returns_502(self):
        resp_lib.add(resp_lib.POST, "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     status=500)
        r = client.get("/wages?soc=15-1252")
        assert r.status_code == 502
        assert "detail" in r.json()


# ---------------------------------------------------------------------------
# /h1b/search
# ---------------------------------------------------------------------------

class TestH1BSearch:
    def test_no_filters_returns_422(self):
        r = client.get("/h1b/search")
        assert r.status_code == 422
        assert "filter" in r.json()["detail"].lower()

    @resp_lib.activate
    def test_no_db_with_title_falls_back_to_scrape(self, tmp_path, monkeypatch):
        """With a title but no local DB, /h1b/search falls back to h1bdata.info scrape."""
        resp_lib.add(resp_lib.GET, H1BDATA_URL, body=_MOCK_H1BDATA_HTML, status=200)
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        r = client.get("/h1b/search?title=Software+Engineer")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["annual_from"] == 180_000

    def test_no_db_no_title_returns_404(self, tmp_path, monkeypatch):
        """Without a title the scrape fallback can't run; expect 404."""
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        r = client.get("/h1b/search?state=CA")
        assert r.status_code == 404

    def test_returns_results_from_cache(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/search?title=Software+Engineer")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_result_shape(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/search?state=CA")
        assert r.status_code == 200
        for row in r.json():
            assert "job_title" in row
            assert "employer" in row
            assert "annual_from" in row

    def test_limit_param_respected(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/search?state=CA&limit=2")
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_limit_above_500_rejected(self):
        r = client.get("/h1b/search?state=CA&limit=501")
        assert r.status_code == 422

    def test_state_filter(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/search?state=CA")
        assert r.status_code == 200
        for row in r.json():
            assert row["worksite_state"] == "CA"


# ---------------------------------------------------------------------------
# /h1b/summary
# ---------------------------------------------------------------------------

class TestH1BSummary:
    def test_no_filters_returns_422(self):
        r = client.get("/h1b/summary")
        assert r.status_code == 422

    @resp_lib.activate
    def test_no_db_with_title_falls_back_to_scrape(self, tmp_path, monkeypatch):
        """With a title but no local DB, /h1b/summary falls back to h1bdata.info scrape."""
        resp_lib.add(resp_lib.GET, H1BDATA_URL, body=_MOCK_H1BDATA_HTML, status=200)
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        r = client.get("/h1b/summary?title=Software+Engineer")
        assert r.status_code == 200
        data = r.json()
        assert data["n"] == 1
        assert data["median"] == 180_000

    def test_no_db_no_title_returns_404(self, tmp_path, monkeypatch):
        """Without a title the scrape fallback can't run; expect 404."""
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)
        r = client.get("/h1b/summary?state=CA")
        assert r.status_code == 404

    def test_returns_stats(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/summary?state=CA")
        assert r.status_code == 200
        data = r.json()
        assert data["n"] > 0
        assert "median" in data
        assert "p75" in data

    def test_no_matches_returns_n_zero(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/summary?title=Underwater+Basket+Weaver")
        assert r.status_code == 200
        assert r.json()["n"] == 0

    def test_percentile_ordering(self, h1b_db, monkeypatch):
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", h1b_db.parent)
        r = client.get("/h1b/summary?state=CA")
        d = r.json()
        if d["n"] > 1:
            assert d["p25"] <= d["median"] <= d["p75"]


# ---------------------------------------------------------------------------
# OpenAPI schema sanity
# ---------------------------------------------------------------------------

class TestOpenAPI:
    def test_openapi_json_available(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200

    def test_openapi_has_expected_paths(self):
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health" in paths
        assert "/soc" in paths
        assert "/wages" in paths
        assert "/h1b/search" in paths
        assert "/h1b/summary" in paths

    def test_docs_available(self):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_redoc_available(self):
        r = client.get("/redoc")
        assert r.status_code == 200
