"""
Shared pytest fixtures for frik tests.

Fixtures here are available to all test files without explicit import.
"""

import json
import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# BLS API fixtures
# ---------------------------------------------------------------------------

def _bls_series_response(series_id: str, value: str, year: str = "2025") -> dict:
    """Build a minimal BLS API v2 response for a single series."""
    return {
        "status": "REQUEST_SUCCEEDED",
        "responseDetails": None,
        "message": [],
        "Results": {
            "series": [
                {
                    "seriesID": series_id,
                    "data": [
                        {
                            "year": year,
                            "period": "A01",
                            "periodName": "Annual",
                            "latest": "true",
                            "value": value,
                            "footnotes": [{}],
                        }
                    ],
                }
            ]
        },
    }


@pytest.fixture
def bls_software_dev_response():
    """BLS response for Software Developers (15-1252), annual mean $148,100."""
    return _bls_series_response("OEUN000000000000015125204", "148100")


@pytest.fixture
def bls_multi_response():
    """BLS response covering several occupations at known values."""
    return {
        "status": "REQUEST_SUCCEEDED",
        "message": [],
        "Results": {
            "series": [
                {
                    "seriesID": "OEUN000000000000015125204",  # SW Dev mean
                    "data": [{"year": "2025", "period": "A01", "periodName": "Annual",
                               "latest": "true", "value": "148100", "footnotes": [{}]}],
                },
                {
                    "seriesID": "OEUN000000000000015125213",  # SW Dev median
                    "data": [{"year": "2025", "period": "A01", "periodName": "Annual",
                               "latest": "true", "value": "135980", "footnotes": [{}]}],
                },
                {
                    "seriesID": "OEUN000000000000015125214",  # SW Dev p75
                    "data": [{"year": "2025", "period": "A01", "periodName": "Annual",
                               "latest": "true", "value": "171980", "footnotes": [{}]}],
                },
                {
                    "seriesID": "OEUN000000000000015125215",  # SW Dev p90
                    "data": [],  # simulate missing data
                },
            ]
        },
    }


# ---------------------------------------------------------------------------
# H1B SQLite fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def h1b_db(tmp_path: Path) -> Path:
    """
    Create a minimal H1B SQLite database with known rows for testing.
    Returns path to the database file.
    """
    # Name matches the h1b_FY*.db glob so _find_db() locates it via CACHE_DIR monkeypatching
    db = tmp_path / "h1b_FY9999_Q1.db"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE lca (
            id            INTEGER PRIMARY KEY,
            case_status   TEXT,
            decision_date TEXT,
            visa_class    TEXT,
            job_title     TEXT,
            soc_code      TEXT,
            soc_title     TEXT,
            employer      TEXT,
            employer_city TEXT,
            employer_state TEXT,
            worksite_city  TEXT,
            worksite_state TEXT,
            wage_from     REAL,
            wage_to       REAL,
            wage_unit     TEXT,
            annual_from   REAL,
            annual_to     REAL,
            pw_wage       REAL,
            pw_unit       TEXT,
            pw_level      TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE lca_fts USING fts5(
            job_title, employer, soc_code, soc_title,
            content='lca', content_rowid='id'
        )
    """)

    rows = [
        # (case_status, decision_date, visa_class, job_title, soc_code, soc_title,
        #  employer, emp_city, emp_state, ws_city, ws_state,
        #  wage_from, wage_to, wage_unit, annual_from, annual_to,
        #  pw_wage, pw_unit, pw_level)
        ("CERTIFIED", "2024-06-01", "H-1B", "Software Engineer", "15-1252",
         "Software Developers", "GOOGLE LLC", "Mountain View", "CA",
         "Mountain View", "CA", 180000, 220000, "Year", 180000, 220000,
         175000, "Year", "Level III"),
        ("CERTIFIED", "2024-07-01", "H-1B", "AI Platform Engineer", "15-1299",
         "Computer Occupations", "ANTHROPIC PBC", "San Francisco", "CA",
         "San Francisco", "CA", 220000, 280000, "Year", 220000, 280000,
         210000, "Year", "Level IV"),
        ("CERTIFIED", "2024-05-15", "H-1B", "AI Platform Engineer", "15-1299",
         "Computer Occupations", "OPENAI LLC", "San Francisco", "CA",
         "San Francisco", "CA", 200000, 250000, "Year", 200000, 250000,
         195000, "Year", "Level III"),
        ("CERTIFIED", "2024-08-01", "H-1B", "Machine Learning Engineer", "15-1299",
         "Computer Occupations", "META PLATFORMS", "Menlo Park", "CA",
         "Menlo Park", "CA", 190000, 240000, "Year", 190000, 240000,
         185000, "Year", "Level III"),
        ("CERTIFIED", "2024-03-01", "H-1B", "Software Engineer", "15-1252",
         "Software Developers", "AMAZON WEB SERVICES", "Seattle", "WA",
         "Seattle", "WA", 160000, 195000, "Year", 160000, 195000,
         155000, "Year", "Level II"),
        # Hourly wage — should normalize to annual
        ("CERTIFIED", "2024-04-01", "H-1B", "Data Scientist", "15-2051",
         "Data Scientists", "STRIPE INC", "San Francisco", "CA",
         "San Francisco", "CA", 85, 110, "Hour", 176800, 228800,
         80, "Hour", "Level III"),
        # Denied — should be excluded from queries
        ("DENIED", "2024-05-01", "H-1B", "Software Engineer", "15-1252",
         "Software Developers", "SOME CORP", "Austin", "TX",
         "Austin", "TX", 90000, 90000, "Year", 90000, 90000,
         88000, "Year", "Level I"),
    ]

    conn.executemany("""
        INSERT INTO lca VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.execute("INSERT INTO lca_fts(lca_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return db
