"""
BLS OEWS source — Occupational Employment and Wage Statistics.

Pulls national annual wage percentiles by SOC code from the
BLS Public Data API v2 (https://api.bls.gov/publicAPI/v2).

Series ID format (OEWS national, all industries):
    OEUN + 0000000000000 (13-char padding) + SOC6 (no dash) + data_type_code

Data type codes:
    01  employment
    04  annual mean wage
    13  annual median wage
    14  annual 75th percentile wage
    15  annual 90th percentile wage

API key is optional but raises daily query limit from 25 to 500.
Read from env var BLS_API_KEY or ~/.blue_rose/bls_api_key.env.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import requests

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# SOC codes commonly relevant to tech / software roles.
# 'category' is used to group output; 'notes' explains the classification.
DEFAULT_OCCUPATIONS: list[dict] = [
    {
        "soc": "15-1252",
        "title": "Software Developers",
        "category": "engineering",
        "notes": "Baseline for individual contributor engineering roles",
    },
    {
        "soc": "15-1299",
        "title": "Computer Occupations, All Other",
        "category": "engineering",
        "notes": "BLS catch-all; AI Engineer / ML Engineer / Platform Engineer "
                 "roles often land here until a dedicated SOC is assigned",
    },
    {
        "soc": "15-2051",
        "title": "Data Scientists",
        "category": "engineering",
        "notes": "Relevant when ML/data work dominates the role description",
    },
    {
        "soc": "11-3021",
        "title": "Computer and Information Systems Managers",
        "category": "management",
        "notes": "Staff / Principal / Director / VP Engineering track",
    },
    {
        "soc": "15-1211",
        "title": "Computer Systems Analysts",
        "category": "engineering",
        "notes": "Systems / infrastructure design angle",
    },
    {
        "soc": "15-1244",
        "title": "Network and Computer Systems Administrators",
        "category": "infrastructure",
        "notes": "Cloud operations / infrastructure angle",
    },
    {
        "soc": "15-1253",
        "title": "Software Quality Assurance Analysts and Testers",
        "category": "engineering",
        "notes": "QA / SDET baseline for comparison",
    },
]

DATA_TYPES: dict[str, str] = {
    "04": "annual_mean",
    "13": "annual_median",
    "14": "annual_p75",
    "15": "annual_p90",
    "01": "employment",
}


def _load_api_key() -> str:
    if key := os.environ.get("BLS_API_KEY"):
        return key
    key_file = Path.home() / ".blue_rose" / "bls_api_key.env"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            if m := re.match(r"BLS_API_KEY=(.+)", line):
                return m.group(1).strip()
    return ""


def _series_id(soc: str, data_type_code: str) -> str:
    return f"OEUN0000000000000{soc.replace('-', '')}{data_type_code}"


def _fetch(series_ids: list[str], api_key: str) -> dict:
    payload: dict = {"seriesid": series_ids}
    if api_key:
        payload["registrationkey"] = api_key
    resp = requests.post(BLS_API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _latest_annual(series_data: dict) -> dict[str, str | None]:
    """Return {seriesID: value_str} for the most recent annual data point."""
    out: dict[str, str | None] = {}
    for s in series_data.get("Results", {}).get("series", []):
        annual = [v for v in s.get("data", []) if v.get("period") == "A01"]
        out[s["seriesID"]] = annual[0]["value"] if annual else None
    return out


def fetch_wages(
    soc_codes: list[str] | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """
    Fetch BLS OEWS wage data for the given SOC codes.

    Args:
        soc_codes: List of SOC codes (e.g. ["15-1252", "15-1299"]).
                   Defaults to DEFAULT_OCCUPATIONS.
        api_key:   BLS API key. Auto-detected from env/file if not provided.

    Returns:
        List of dicts, one per occupation:
        {
            "soc": "15-1252",
            "title": "Software Developers",
            "category": "engineering",
            "notes": "...",
            "wages": {
                "annual_mean":   148100,
                "annual_median": 135980,
                "annual_p75":    171980,
                "annual_p90":    214670,
                "employment":    1820.4,   # in thousands
            }
        }
    """
    key = api_key or _load_api_key()

    occs = DEFAULT_OCCUPATIONS
    if soc_codes:
        occs = [o for o in DEFAULT_OCCUPATIONS if o["soc"] in soc_codes]
        unknown = set(soc_codes) - {o["soc"] for o in DEFAULT_OCCUPATIONS}
        for soc in unknown:
            occs.append({"soc": soc, "title": soc, "category": "unknown", "notes": ""})

    all_series = [
        _series_id(o["soc"], dt)
        for o in occs
        for dt in DATA_TYPES
    ]

    raw: dict[str, str | None] = {}
    for i in range(0, len(all_series), 50):
        resp = _fetch(all_series[i:i + 50], key)
        raw.update(_latest_annual(resp))

    results = []
    for occ in occs:
        wages: dict[str, float | None] = {}
        for dt_code, dt_name in DATA_TYPES.items():
            sid = _series_id(occ["soc"], dt_code)
            val = raw.get(sid)
            wages[dt_name] = float(val) if val else None
        results.append({**occ, "wages": wages})

    return results
