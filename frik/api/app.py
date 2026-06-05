"""
FRIK API — Fair Remuneration Intelligence Kit

Run locally:
    frik serve                         # defaults: host=127.0.0.1 port=8000
    frik serve --host 0.0.0.0 --port 9000

Or directly via uvicorn:
    uvicorn frik.api.app:app --reload

Interactive docs (once running):
    http://localhost:8000/docs          # Swagger UI
    http://localhost:8000/redoc         # ReDoc
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from frik.api.models import (
    ErrorResponse,
    H1BRow,
    H1BSummary,
    OccupationWages,
    SocEntry,
    WageData,
)
from frik.sources.bls import DEFAULT_OCCUPATIONS, fetch_wages

app = FastAPI(
    title="FRIK — Fair Remuneration Intelligence Kit",
    description=(
        "Multi-source compensation data API. Pulls from BLS OEWS and DOL H1B/LCA "
        "disclosure filings. Designed to support California SB 1162 pay range generation."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow web front-ends on any origin during development.
# Tighten this to specific origins before any public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"], summary="Health check")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SOC catalog
# ---------------------------------------------------------------------------

@app.get(
    "/soc",
    response_model=list[SocEntry],
    tags=["reference"],
    summary="List built-in SOC code definitions",
)
def list_soc() -> list[SocEntry]:
    """Returns the built-in list of SOC codes frik knows about."""
    return [SocEntry(**o) for o in DEFAULT_OCCUPATIONS]


# ---------------------------------------------------------------------------
# BLS OEWS wages
# ---------------------------------------------------------------------------

@app.get(
    "/wages",
    response_model=list[OccupationWages],
    responses={502: {"model": ErrorResponse}},
    tags=["bls"],
    summary="BLS OEWS wages by SOC code",
)
def get_wages(
    soc: Annotated[
        list[str] | None,
        Query(
            description="One or more SOC codes to look up (e.g. `15-1252`). "
                        "Omit to return all built-in occupations.",
        ),
    ] = None,
) -> list[OccupationWages]:
    """
    Fetches national annual wage percentiles from the BLS Occupational
    Employment and Wage Statistics (OEWS) survey.

    - **soc**: repeat the parameter to query multiple codes, e.g.
      `?soc=15-1252&soc=15-1299`
    - Data is released annually; figures reflect the most recent survey year.
    - Does **not** include equity, bonus, or geographic adjustments.
    """
    try:
        results = fetch_wages(soc_codes=soc or None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BLS API error: {e}") from e

    return [
        OccupationWages(
            soc=r["soc"],
            title=r["title"],
            category=r["category"],
            notes=r["notes"],
            wages=WageData(**r["wages"]),
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# H1B / LCA
# ---------------------------------------------------------------------------

def _h1b_source(db_path_override: str | None = None):
    """Import h1b lazily — only required when H1B cache is present."""
    from frik.sources import h1b
    return h1b


@app.get(
    "/h1b/search",
    response_model=list[H1BRow],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["h1b"],
    summary="Search H1B/LCA disclosure records",
)
def h1b_search(
    title: Annotated[str | None, Query(description="Job title (full-text search)")] = None,
    soc:   Annotated[str | None, Query(description="SOC code, e.g. `15-1252`")] = None,
    state: Annotated[str | None, Query(description="Two-letter state code, e.g. `CA`")] = None,
    employer: Annotated[str | None, Query(description="Employer name substring")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return")] = 50,
) -> list[H1BRow]:
    """
    Search certified H-1B LCA filings from the DOL disclosure database.

    At least one of `title`, `soc`, `state`, or `employer` is recommended;
    an unfiltered query may be slow against large datasets.

    Results are ordered by offered wage (highest first).
    Requires the H1B cache to be populated — run `frik h1b download` first.
    """
    if not any([title, soc, state, employer]):
        raise HTTPException(
            status_code=422,
            detail="Provide at least one filter: title, soc, state, or employer.",
        )

    h1b = _h1b_source()
    try:
        rows = h1b.search(title=title, soc_code=soc, state=state, employer=employer, limit=limit)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return [H1BRow(**r) for r in rows]


@app.get(
    "/h1b/summary",
    response_model=H1BSummary,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["h1b"],
    summary="Wage statistics for a H1B query",
)
def h1b_summary(
    title: Annotated[str | None, Query(description="Job title (full-text search)")] = None,
    soc:   Annotated[str | None, Query(description="SOC code, e.g. `15-1252`")] = None,
    state: Annotated[str | None, Query(description="Two-letter state code, e.g. `CA`")] = None,
) -> H1BSummary:
    """
    Returns wage statistics (p25, median, mean, p75, p90, min, max) computed
    from certified H-1B filings matching the query.

    Based on the **offered wage floor** (`annual_from`) — a reasonable proxy
    for market floor compensation at each employer.

    Requires the H1B cache — run `frik h1b download` first.
    """
    if not any([title, soc, state]):
        raise HTTPException(
            status_code=422,
            detail="Provide at least one filter: title, soc, or state.",
        )

    h1b = _h1b_source()
    try:
        stats = h1b.summarize(title=title, soc_code=soc, state=state)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if stats.get("n", 0) == 0:
        return H1BSummary(n=0)

    return H1BSummary(**stats)
