"""
CLI integration tests for frik.cli.

Tests the argument parser and command dispatch without real network calls.
"""

from __future__ import annotations

import json
import sys
from io import StringIO

import pytest
import responses as resp_lib

from frik.cli import _fmt_dollars, main


# ---------------------------------------------------------------------------
# _fmt_dollars
# ---------------------------------------------------------------------------

class TestFmtDollars:
    def test_none_returns_na(self):
        assert _fmt_dollars(None) == "N/A"

    def test_large_value_formatted_with_dollar_sign(self):
        assert _fmt_dollars(148_100) == "$148,100"

    def test_small_value_in_thousands_notation(self):
        result = _fmt_dollars(500)
        assert "k" in result

    def test_boundary_at_1000(self):
        assert "$" in _fmt_dollars(1000)
        assert "k" in _fmt_dollars(999)


# ---------------------------------------------------------------------------
# main() — argument parsing
# ---------------------------------------------------------------------------

class TestMainArgParsing:
    def test_no_args_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 0

    def test_unknown_command_exits_nonzero(self):
        with pytest.raises(SystemExit) as exc:
            main(["notacommand"])
        assert exc.value.code != 0

    def test_soc_command_runs_without_network(self, capsys):
        """frik soc should print the SOC table with no network access."""
        main(["soc"])
        out = capsys.readouterr().out
        assert "15-1252" in out
        assert "Software Developers" in out

    @resp_lib.activate
    def test_wages_command_json_output(self):
        """frik wages --json should output valid JSON."""
        payload = {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "OEUN000000000000015125204",
                        "data": [{"year": "2025", "period": "A01",
                                   "value": "148100", "footnotes": []}],
                    }
                ]
            },
        }
        resp_lib.add(resp_lib.POST,
                     "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                     json=payload, status=200)

        import os
        os.environ.setdefault("BLS_API_KEY", "test")

        output = StringIO()
        original_stdout = sys.stdout
        sys.stdout = output
        try:
            main(["wages", "--soc", "15-1252", "--json"])
        finally:
            sys.stdout = original_stdout

        result = json.loads(output.getvalue())
        assert isinstance(result, list)
        assert result[0]["soc"] == "15-1252"


# ---------------------------------------------------------------------------
# h1b subcommand error handling
# ---------------------------------------------------------------------------

class TestH1bCli:
    def test_h1b_no_subcommand_prints_help(self, capsys):
        """frik h1b with no subcommand should print help, not crash."""
        main(["h1b"])
        out = capsys.readouterr().out
        assert "download" in out or "search" in out or "subcommand" in out.lower()

    def test_h1b_search_no_db_no_title_exits_1(self, tmp_path, monkeypatch):
        """No DB and no title → scrape fallback unavailable → exit 1."""
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)

        with pytest.raises(SystemExit) as exc:
            main(["h1b", "search", "--state", "CA"])
        assert exc.value.code == 1

    def test_h1b_summary_no_db_no_title_exits_1(self, tmp_path, monkeypatch):
        """No DB and no title → scrape fallback unavailable → exit 1."""
        import frik.sources.h1b as h1b_mod
        monkeypatch.setattr(h1b_mod, "CACHE_DIR", tmp_path)

        with pytest.raises(SystemExit) as exc:
            main(["h1b", "summary", "--state", "CA"])
        assert exc.value.code == 1
