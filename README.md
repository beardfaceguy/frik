# frik

**Fair Remuneration Intelligence Kit** — multi-source salary intelligence for compensation research and California-compliant pay range generation.

> Named in honor of Henry Clay Frick, the 19th-century industrialist who pioneered the tradition of paying workers exactly as little as the market would tolerate. We are correcting that.

## What it does

Two use cases:

1. **Individual salary negotiation** — pull market data from BLS OEWS, H1B/LCA filings, and disclosed job postings to understand what your role is actually worth before walking into a negotiation.

2. **California SB 1162 pay range generation** — give hiring managers and HR accurate, defensible salary bands for job postings. California law requires posted ranges to reflect the *genuine* expected range, not a placeholder wide band.

## Status

| Source | CLI | API |
|--------|-----|-----|
| BLS OEWS (national wage percentiles by SOC code) | ✅ `frik wages` | ✅ `GET /wages` |
| H1B/LCA filings (exact salaries by employer + title) | ✅ `frik h1b` | ✅ `GET /h1b/search`, `GET /h1b/summary` |
| Job postings with disclosed ranges (CA/NY/WA/CO) | 🔲 Planned | 🔲 Planned |
| CA SB 1162 pay range generator (unified output) | 🔲 Planned | 🔲 Planned |

**Note on H1B download:** The DOL servers at `foreignlaborcert.doleta.gov` occasionally return 503s. The download command implements retry logic with backoff — if it fails, wait a few minutes and try again. The parsing and caching logic is fully implemented.

## Installation

```bash
git clone https://github.com/beardfaceguy/frik
cd frik
pip install -e .
```

To also run the API server:

```bash
pip install -e ".[api]"
```

Optionally set a [free BLS API key](https://data.bls.gov/registrationEngine/) to raise the daily query limit from 25 to 500:

```bash
# add to ~/.blue_rose/bls_api_key.env
BLS_API_KEY=your_key_here

# or export directly
export BLS_API_KEY=your_key_here
```

## CLI Usage

### Wages by SOC code (BLS OEWS)

```bash
# All built-in occupations
frik wages

# Specific SOC codes
frik wages --soc 15-1252 15-1299

# JSON output
frik wages --json
frik wages --out wages.json
```

**Example output:**
```
Occupation                                         Mean       Median          P75          P90
-----------------------------------------------------------------------------------------------
Software Developers                            $148,100     $135,980     $171,980     $214,670
Computer Occupations, All Other                $122,230     $116,580     $157,500     $188,470
Data Scientists                                $126,800     $120,230     $158,880     $199,130
Computer and Information Systems Managers      $192,160     $175,140     $220,730     $297,510

Source: BLS OEWS (latest annual release) — national, all industries.
Does not include equity, bonus, or geographic cost-of-living adjustment.
```

### H1B/LCA filings (DOL disclosure data)

```bash
# Download and cache FY2025 Q4 data (~200 MB Excel → local SQLite)
frik h1b download

# Search by job title
frik h1b search --title "AI Platform Engineer"

# Filter by title + state + employer
frik h1b search --title "Software Engineer" --state CA --employer Google

# Wage statistics (p25/median/p75/p90) for a query
frik h1b summary --title "Software Engineer" --state CA

# Download a different quarter
frik h1b download --fy 2026 --quarter 2
```

### List available SOC codes

```bash
frik soc
```

### Start the API server

```bash
# Localhost only (default)
frik serve

# Accessible on your network
frik serve --host 0.0.0.0 --port 8000

# With auto-reload for development
frik serve --reload
```

## API

Once running, interactive docs are available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/soc` | List built-in SOC codes |
| `GET` | `/wages` | BLS OEWS wages (`?soc=15-1252&soc=15-1299`) |
| `GET` | `/h1b/search` | Search H1B filings (`?title=...&state=CA&employer=...&limit=50`) |
| `GET` | `/h1b/summary` | Wage stats for a query (`?title=...&soc=...&state=...`) |

All responses are JSON. The OpenAPI schema is available at `/openapi.json`.

**Note:** `/h1b/*` endpoints require the local cache to be populated first (`frik h1b download`).

## Data sources

### BLS OEWS
The Bureau of Labor Statistics [Occupational Employment and Wage Statistics](https://www.bls.gov/oes/) program publishes annual median and mean wages for ~800 occupations at national, state, and metro levels. Free, authoritative, updated annually (~May). Lags market by 12–18 months but is the standard reference cited in salary disputes and legal contexts.

**Caveat for AI/agentic roles:** BLS has no dedicated SOC code for "AI Engineer," "AI Platform Engineer," or similar emerging titles. These roles currently land under `15-1299` (Computer Occupations, All Other) or `15-1252` (Software Developers). Supplement with H1B filings for current market signal on AI-specific compensation.

### H1B/LCA filings
The DOL [Foreign Labor Certification](https://www.foreignlaborcert.doleta.gov/performancedata.cfm) database contains every H1B application filed — employer name, job title, SOC code, work location, and exact offered wage. Public record, updated quarterly, no API key required. The most accurate free source for what named companies actually pay for specific titles.

Data is downloaded once, converted to a local SQLite database with full-text search, and cached at `~/.frik_cache/`. Subsequent queries run locally with no network access.

### Job postings *(planned)*
California (SB 1162), New York, Washington, and Colorado require employers to disclose salary ranges in job postings. These disclosed ranges are a real-time market signal. Implementation planned via [JobSpy](https://github.com/Bunsly/JobSpy).

## California SB 1162

California law requires employers with 15+ employees to include the expected salary or hourly wage range in all job postings. The range must be the *genuine* range the employer reasonably expects to pay — posting `$1 – $1,000,000` is non-compliant.

`frik range` *(planned)* will generate a defensible range for a given title and level by triangulating BLS percentiles, H1B filings for comparable roles, and current job postings with disclosed ranges.

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest

# Fast TDD loop (no coverage overhead)
pytest --no-cov -x -q

# Lint
ruff check . --fix && ruff format .
```

See `AGENTS.md` for contributor conventions and the TDD workflow expected in this repo.

## Roadmap

- [ ] Job postings scraper with salary filter (`frik/sources/postings.py`)
- [ ] `frik range` — CA SB 1162 pay range generator
- [ ] Metro/state-level BLS data (national only today)
- [ ] Level mapping (IC1–IC5, M1–M3 → percentile bands)
- [ ] API authentication (before any non-internal deployment)
- [ ] CORS lockdown to company domain

## License

MIT
