"""
Pydantic request/response models for the FRIK API.

Keeping models in their own file avoids circular imports and makes it easy
to generate client SDKs or export the OpenAPI schema later.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# BLS / wages
# ---------------------------------------------------------------------------

class WageData(BaseModel):
    annual_mean:   Optional[float] = Field(None, description="Annual mean wage (USD)")
    annual_median: Optional[float] = Field(None, description="Annual median wage (USD)")
    annual_p75:    Optional[float] = Field(None, description="Annual 75th-percentile wage (USD)")
    annual_p90:    Optional[float] = Field(None, description="Annual 90th-percentile wage (USD)")
    employment:    Optional[float] = Field(None, description="Total employment in thousands")


class OccupationWages(BaseModel):
    soc:      str = Field(..., description="SOC code, e.g. '15-1252'")
    title:    str = Field(..., description="BLS occupational title")
    category: str = Field(..., description="Grouping label, e.g. 'engineering'")
    notes:    str = Field("",  description="Notes on how this SOC relates to the role")
    wages:    WageData


# ---------------------------------------------------------------------------
# SOC catalog
# ---------------------------------------------------------------------------

class SocEntry(BaseModel):
    soc:      str
    title:    str
    category: str
    notes:    str


# ---------------------------------------------------------------------------
# H1B / LCA
# ---------------------------------------------------------------------------

class H1BRow(BaseModel):
    job_title:      Optional[str]   = None
    employer:       Optional[str]   = None
    worksite_city:  Optional[str]   = None
    worksite_state: Optional[str]   = None
    annual_from:    Optional[float] = Field(None, description="Offered wage floor, annualized (USD)")
    annual_to:      Optional[float] = Field(None, description="Offered wage ceiling, annualized (USD)")
    soc_code:       Optional[str]   = None
    pw_level:       Optional[str]   = Field(None, description="Prevailing wage level (I-IV)")
    decision_date:  Optional[str]   = None


class H1BSummary(BaseModel):
    n:      int   = Field(..., description="Number of matching certified filings")
    mean:   Optional[float] = None
    median: Optional[float] = None
    p25:    Optional[float] = None
    p75:    Optional[float] = None
    p90:    Optional[float] = None
    min:    Optional[float] = None
    max:    Optional[float] = None


# ---------------------------------------------------------------------------
# Common error response
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str
