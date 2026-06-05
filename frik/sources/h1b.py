"""
H1B/LCA source — DOL Foreign Labor Certification data.

The Department of Labor publishes every H1B/LCA application as a public record:
exact employer name, job title, SOC code, work location, prevailing wage,
and offered wage. This is the most accurate public source for what named
companies actually pay for specific titles.

Data: https://www.foreignlaborcert.doleta.gov/performancedata.cfm
Updated quarterly. Raw Excel/CSV bulk download, no API key required.

Wrapper sites that make this queryable:
  - h1bdata.info     — free, searchable by employer + title
  - h1bdata.net      — 4M+ records, trend data
  - h1bgrader.com    — approval rates per employer

TODO: Implement one of:
  a) Direct bulk CSV download + local SQLite for offline querying
  b) Scrape h1bdata.info for quick title/employer lookups
  c) Use the DOL OFLC Performance Data API if one becomes available
"""

from __future__ import annotations


class H1BSource:
    """Placeholder — not yet implemented."""

    def fetch_wages(
        self,
        job_title: str,
        location: str | None = None,
        employer: str | None = None,
        year: int | None = None,
    ) -> list[dict]:
        raise NotImplementedError(
            "H1B source not yet implemented. "
            "See frik/sources/h1b.py for planned approach."
        )
