"""
H1B/LCA source — DOL Foreign Labor Certification disclosure data.

The Department of Labor publishes every H1B/LCA application as a public record.
Each row contains: employer name, job title, SOC code, work location,
prevailing wage, and the actual offered wage. Free, no API key required.

Data: https://www.foreignlaborcert.doleta.gov/performancedata.cfm
Updated quarterly. Full-year Excel files (~100-300 MB each).

Workflow:
    frik h1b download          # download FY2025 Q4 + FY2026 Q2, cache as SQLite
    frik h1b search --title "AI Platform Engineer"
    frik h1b search --title "Software Engineer" --state CA --employer Google
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator

import requests

CACHE_DIR = Path.home() / ".frik_cache"

# Known quarterly release URLs. Add new quarters here as DOL publishes them.
KNOWN_FILES: list[dict] = [
    {
        "label": "FY2026 Q2",
        "url": "https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q2.xlsx",
        "fy": 2026, "quarter": 2,
    },
    {
        "label": "FY2025 Q4",
        "url": "https://www.foreignlaborcert.doleta.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx",
        "fy": 2025, "quarter": 4,
    },
    {
        "label": "FY2024 Q4",
        "url": "https://www.foreignlaborcert.doleta.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx",
        "fy": 2024, "quarter": 4,
    },
]

# LCA columns we care about — the full file has ~70 columns.
KEEP_COLUMNS = {
    "CASE_STATUS",
    "DECISION_DATE",
    "VISA_CLASS",
    "JOB_TITLE",
    "SOC_CODE",
    "SOC_TITLE",
    "EMPLOYER_NAME",
    "EMPLOYER_CITY",
    "EMPLOYER_STATE",
    "WORKSITE_CITY",
    "WORKSITE_STATE",
    "WAGE_RATE_OF_PAY_FROM",
    "WAGE_RATE_OF_PAY_TO",
    "WAGE_UNIT_OF_PAY",
    "PREVAILING_WAGE",
    "PW_UNIT_OF_PAY",
    "PW_WAGE_LEVEL",
}

# Wage unit multipliers → annual salary
UNIT_TO_ANNUAL: dict[str, float] = {
    "Year":       1.0,
    "Hour":       2080.0,
    "Week":       52.0,
    "Month":      12.0,
    "Bi-Weekly":  26.0,
}


def _cache_db_path(fy: int, quarter: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"h1b_FY{fy}_Q{quarter}.db"


def _xlsx_to_annual(wage: float | None, unit: str | None) -> float | None:
    if wage is None or not unit:
        return None
    mult = UNIT_TO_ANNUAL.get(unit.strip(), None)
    if mult is None:
        return None
    return round(wage * mult, 2)


def _download_xlsx(url: str, dest: Path, label: str, retries: int = 3) -> None:  # pragma: no cover
    """Stream-download an Excel file with progress display and retry logic."""
    print(f"Downloading {label}...", flush=True)
    headers = {"User-Agent": "frik/0.1 (salary research tool; github.com/beardfaceguy/frik)"}

    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=120, headers=headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            print(
                                f"\r  {pct:.0f}%  ({downloaded // 1_048_576} MB"
                                f" / {total // 1_048_576} MB)  ",
                                end="", flush=True,
                            )
            print(f"\r  Done — {downloaded // 1_048_576} MB saved to {dest}    ")
            return
        except requests.HTTPError as e:
            if attempt < retries and e.response is not None and e.response.status_code in (429, 503, 504):
                wait = 10 * attempt
                print(f"\r  HTTP {e.response.status_code} — retrying in {wait}s (attempt {attempt}/{retries})...")
                time.sleep(wait)
            else:
                dest.unlink(missing_ok=True)
                raise
        except requests.RequestException as e:
            if attempt < retries:
                wait = 10 * attempt
                print(f"\r  Network error: {e} — retrying in {wait}s (attempt {attempt}/{retries})...")
                time.sleep(wait)
            else:
                dest.unlink(missing_ok=True)
                raise


def _rows_from_xlsx(path: Path) -> Iterator[dict]:  # pragma: no cover
    """Yield rows as dicts from the LCA Excel file, keeping only KEEP_COLUMNS."""
    import openpyxl  # lazy import — only needed for download command

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(c).strip() if c else "" for c in row]
            continue
        yield {headers[j]: row[j] for j in range(len(headers)) if headers[j] in KEEP_COLUMNS}
    wb.close()


def _build_db(xlsx_path: Path, db_path: Path, label: str) -> int:  # pragma: no cover
    """Convert Excel → SQLite, returning number of certified H-1B rows stored."""
    print(f"Parsing {label} → {db_path.name} (this takes a few minutes for large files)...")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lca (
            id           INTEGER PRIMARY KEY,
            case_status  TEXT,
            decision_date TEXT,
            visa_class   TEXT,
            job_title    TEXT,
            soc_code     TEXT,
            soc_title    TEXT,
            employer     TEXT,
            employer_city TEXT,
            employer_state TEXT,
            worksite_city  TEXT,
            worksite_state TEXT,
            wage_from    REAL,
            wage_to      REAL,
            wage_unit    TEXT,
            annual_from  REAL,
            annual_to    REAL,
            pw_wage      REAL,
            pw_unit      TEXT,
            pw_level     TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS lca_fts USING fts5(
            job_title,
            employer,
            soc_code,
            soc_title,
            content='lca',
            content_rowid='id'
        )
    """)

    batch: list[tuple] = []
    total = 0
    skipped = 0
    t0 = time.time()

    for row in _rows_from_xlsx(xlsx_path):
        status = (row.get("CASE_STATUS") or "").strip().upper()
        visa = (row.get("VISA_CLASS") or "").strip()

        # Keep only certified H-1B / H-1B1 records
        if "CERTIFIED" not in status or "H-1B" not in visa:
            skipped += 1
            continue

        wage_from_raw = row.get("WAGE_RATE_OF_PAY_FROM")
        wage_to_raw   = row.get("WAGE_RATE_OF_PAY_TO")
        wage_unit     = row.get("WAGE_UNIT_OF_PAY")
        pw_raw        = row.get("PREVAILING_WAGE")
        pw_unit       = row.get("PW_UNIT_OF_PAY")

        try:
            wage_from = float(wage_from_raw) if wage_from_raw else None
        except (ValueError, TypeError):
            wage_from = None
        try:
            wage_to = float(wage_to_raw) if wage_to_raw else None
        except (ValueError, TypeError):
            wage_to = None
        try:
            pw_wage = float(pw_raw) if pw_raw else None
        except (ValueError, TypeError):
            pw_wage = None

        annual_from = _xlsx_to_annual(wage_from, wage_unit)
        annual_to   = _xlsx_to_annual(wage_to,   wage_unit)

        batch.append((
            status,
            str(row.get("DECISION_DATE") or ""),
            visa,
            (row.get("JOB_TITLE") or "").strip(),
            (row.get("SOC_CODE") or "").strip(),
            (row.get("SOC_TITLE") or "").strip(),
            (row.get("EMPLOYER_NAME") or "").strip(),
            (row.get("EMPLOYER_CITY") or "").strip(),
            (row.get("EMPLOYER_STATE") or "").strip(),
            (row.get("WORKSITE_CITY") or "").strip(),
            (row.get("WORKSITE_STATE") or "").strip(),
            wage_from, wage_to, wage_unit,
            annual_from, annual_to,
            pw_wage, pw_unit,
            (row.get("PW_WAGE_LEVEL") or "").strip(),
        ))
        total += 1

        if len(batch) >= 5000:
            conn.executemany("""
                INSERT INTO lca (
                    case_status, decision_date, visa_class, job_title, soc_code, soc_title,
                    employer, employer_city, employer_state,
                    worksite_city, worksite_state,
                    wage_from, wage_to, wage_unit, annual_from, annual_to,
                    pw_wage, pw_unit, pw_level
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            conn.commit()
            elapsed = time.time() - t0
            print(f"\r  {total:,} rows stored ({elapsed:.0f}s)...  ", end="", flush=True)
            batch.clear()

    if batch:
        conn.executemany("""
            INSERT INTO lca (
                case_status, decision_date, visa_class, job_title, soc_code, soc_title,
                employer, employer_city, employer_state,
                worksite_city, worksite_state,
                wage_from, wage_to, wage_unit, annual_from, annual_to,
                pw_wage, pw_unit, pw_level
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()

    # Populate FTS index
    print(f"\r  Indexing {total:,} rows for full-text search...     ", flush=True)
    conn.execute("INSERT INTO lca_fts(lca_fts) VALUES('rebuild')")
    conn.commit()

    # Basic indexes for filtered queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_state  ON lca(worksite_state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_soc    ON lca(soc_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_employer ON lca(employer)")
    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\n  Done — {total:,} certified H-1B rows, {skipped:,} skipped, {elapsed:.0f}s total")
    return total


def download(fy: int = 2025, quarter: int = 4, force: bool = False) -> Path:
    """
    Download and cache LCA disclosure data for the given fiscal year + quarter.
    Returns path to the SQLite database.
    Skips download if cache already exists (unless force=True).
    """
    db_path = _cache_db_path(fy, quarter)
    if db_path.exists() and not force:
        print(f"Cache already exists: {db_path}")
        return db_path

    entry = next((f for f in KNOWN_FILES if f["fy"] == fy and f["quarter"] == quarter), None)
    if not entry:
        raise ValueError(f"No known URL for FY{fy} Q{quarter}. Add it to KNOWN_FILES.")

    xlsx_path = CACHE_DIR / f"h1b_FY{fy}_Q{quarter}.xlsx"
    if not xlsx_path.exists() or force:
        _download_xlsx(entry["url"], xlsx_path, entry["label"])
    else:
        print(f"Using cached Excel: {xlsx_path}")

    _build_db(xlsx_path, db_path, entry["label"])

    # Remove xlsx after successful conversion to save disk space
    xlsx_path.unlink(missing_ok=True)

    return db_path


def _find_db() -> Path | None:
    """Return the most recent cached database, or None."""
    if not CACHE_DIR.exists():
        return None
    dbs = sorted(CACHE_DIR.glob("h1b_FY*.db"), reverse=True)
    return dbs[0] if dbs else None


def search(
    title: str | None = None,
    soc_code: str | None = None,
    state: str | None = None,
    employer: str | None = None,
    limit: int = 50,
    db_path: Path | None = None,
) -> list[dict]:
    """
    Search cached H1B data.

    Args:
        title:    Job title substring or FTS query (e.g. "AI Platform Engineer")
        soc_code: SOC code (e.g. "15-1252")
        state:    Two-letter state code (e.g. "CA")
        employer: Employer name substring (e.g. "Google")
        limit:    Max rows to return
        db_path:  Override cache path

    Returns:
        List of dicts with keys: job_title, employer, worksite_city,
        worksite_state, annual_from, annual_to, soc_code, pw_level, decision_date
    """
    path = db_path or _find_db()
    if path is None or not path.exists():
        raise FileNotFoundError(
            "No H1B cache found. Run `frik h1b download` first."
        )

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    if title:
        # Use FTS for title search, then apply additional filters
        sql = """
            SELECT l.job_title, l.employer, l.worksite_city, l.worksite_state,
                   l.annual_from, l.annual_to, l.soc_code, l.pw_level, l.decision_date
            FROM lca l
            JOIN lca_fts f ON l.id = f.rowid
            WHERE lca_fts MATCH ?
        """
        # Wrap in quotes for phrase search, add * for prefix matching
        fts_query = f'"{title}"'
        params: list = [fts_query]
    else:
        sql = """
            SELECT l.job_title, l.employer, l.worksite_city, l.worksite_state,
                   l.annual_from, l.annual_to, l.soc_code, l.pw_level, l.decision_date
            FROM lca l WHERE 1=1
        """
        params = []

    if soc_code:
        soc_norm = soc_code.replace("-", "").replace(".", "")
        sql += " AND replace(replace(l.soc_code, '-', ''), '.', '') LIKE ?"
        params.append(f"%{soc_norm}%")
    if state:
        sql += " AND l.worksite_state = ?"
        params.append(state.upper())
    if employer:
        sql += " AND l.employer LIKE ?"
        params.append(f"%{employer.upper()}%")

    sql += " ORDER BY l.annual_from DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def summarize(
    title: str | None = None,
    soc_code: str | None = None,
    state: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """
    Return wage statistics (p25, median, p75, p90, mean, n) for a query.
    Operates on annual_from (the offered wage floor).
    """
    path = db_path or _find_db()
    if path is None or not path.exists():
        raise FileNotFoundError(
            "No H1B cache found. Run `frik h1b download` first."
        )

    conn = sqlite3.connect(path)

    if title:
        sql = """
            SELECT l.annual_from
            FROM lca l
            JOIN lca_fts f ON l.id = f.rowid
            WHERE lca_fts MATCH ? AND l.annual_from IS NOT NULL
        """
        params: list = [f'"{title}"']
    else:
        sql = "SELECT l.annual_from FROM lca l WHERE l.annual_from IS NOT NULL"
        params = []

    if soc_code:
        sql += " AND l.soc_code LIKE ?"
        params.append(f"%{soc_code.replace('-','')}%")
    if state:
        sql += " AND l.worksite_state = ?"
        params.append(state.upper())

    wages = [r[0] for r in conn.execute(sql, params).fetchall() if r[0] and r[0] > 10000]
    conn.close()

    if not wages:
        return {"n": 0}

    wages.sort()
    n = len(wages)

    def pct(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return wages[lo] + (wages[hi] - wages[lo]) * (idx - lo)

    return {
        "n":      n,
        "mean":   round(sum(wages) / n),
        "median": round(pct(50)),
        "p25":    round(pct(25)),
        "p75":    round(pct(75)),
        "p90":    round(pct(90)),
        "min":    round(wages[0]),
        "max":    round(wages[-1]),
    }
