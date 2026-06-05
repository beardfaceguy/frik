"""
Job postings source — live salary ranges from active job listings.

Several US states require employers to disclose salary ranges in job postings:
  - California (SB 1162, effective Jan 2023)
  - New York (effective Nov 2022)
  - Washington (effective Jan 2023)
  - Colorado (EPEWA, effective Jan 2021)

This makes job postings from these states a real-time market signal —
the range a company publishes is the range they've approved for the role.

Planned implementation via JobSpy:
  pip install jobspy
  from jobspy import scrape_jobs
  jobs = scrape_jobs(
      site_name=["linkedin", "indeed", "glassdoor", "zip_recruiter"],
      search_term="AI Platform Engineer",
      location="San Francisco, CA",
      results_wanted=50,
  )

Alternatively via the jobspy-mcp server (andrijdavid/jobspy-mcp) if running
as part of an MCP-enabled agent workflow.

TODO: Implement scrape_jobs wrapper that:
  1. Filters to postings with disclosed salary ranges only
  2. Normalizes hourly/annual/monthly to annual
  3. Deduplicates cross-platform postings for the same role
  4. Returns structured {title, employer, location, salary_min, salary_max, posted_date}
"""

from __future__ import annotations


class PostingsSource:
    """Placeholder — not yet implemented."""

    def fetch_ranges(
        self,
        job_title: str,
        location: str | None = None,
        results: int = 50,
    ) -> list[dict]:
        raise NotImplementedError(
            "Postings source not yet implemented. "
            "See frik/sources/postings.py for planned approach."
        )
