# frik

**Fair Remuneration Intelligence Kit** — multi-source salary intelligence for compensation research and California-compliant pay range generation.

## What it does

Two use cases:

1. **Individual salary negotiation** — pull market data from BLS OEWS, H1B/LCA filings, and disclosed job postings to understand what your role is actually worth before walking into a negotiation.

2. **California SB 1162 pay range generation** — give hiring managers and HR accurate, defensible salary bands for job postings. California law requires posted ranges to reflect the *genuine* expected range, not a placeholder wide band.

## Status

| Source | Status |
|--------|--------|
| BLS OEWS (national wage percentiles by SOC code) | ✅ Working |
| H1B/LCA filings (exact salaries by employer + title) | 🔲 Planned |
| Job postings with disclosed ranges (CA/NY/WA/CO) | 🔲 Planned |
| CA SB 1162 pay range generator (unified output) | 🔲 Planned |

## Installation

```bash
git clone https://github.com/beardfaceguy/frik
cd frik
pip install -e .
```

Optionally set a [free BLS API key](https://data.bls.gov/registrationEngine/) to raise the daily query limit from 25 to 500:

```bash
# add to ~/.blue_rose/bls_api_key.env
BLS_API_KEY=your_key_here

# or export directly
export BLS_API_KEY=your_key_here
```

## Usage

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

### List available SOC codes

```bash
frik soc
```

## Data sources

### BLS OEWS (implemented)
The Bureau of Labor Statistics [Occupational Employment and Wage Statistics](https://www.bls.gov/oes/) program publishes annual median and mean wages for ~800 occupations at national, state, and metro levels. Free, authoritative, updated annually (~May). Lags market by 12–18 months but is the standard reference cited in salary disputes and legal contexts.

**Caveat for AI/agentic roles:** BLS has no dedicated SOC code for "AI Engineer," "AI Platform Engineer," or similar emerging titles. These roles are currently classified under `15-1299` (Computer Occupations, All Other) or `15-1252` (Software Developers) depending on the employer. The BLS figures for these codes understate actual market comp for AI-specialized roles — supplement with H1B filings and job postings for current market signal.

### H1B/LCA filings (planned)
The DOL [Foreign Labor Certification](https://www.foreignlaborcert.doleta.gov/performancedata.cfm) database contains every H1B application filed — employer name, job title, SOC code, work location, and exact offered wage. Public record, updated quarterly, no API key required. The most accurate source for what named companies actually pay for specific titles.

### Job postings (planned)
California (SB 1162), New York, Washington, and Colorado require employers to disclose salary ranges in job postings. These disclosed ranges are a real-time market signal. Implementation planned via [JobSpy](https://github.com/Bunsly/JobSpy) to scrape LinkedIn, Indeed, Glassdoor, and ZipRecruiter.

## California SB 1162

California law requires employers with 15+ employees to include the expected salary or hourly wage range in all job postings. The range must be the *genuine* range the employer reasonably expects to pay — posting `$1 – $1,000,000` is non-compliant.

`frik range` (planned) will generate a defensible range for a given title and level by triangulating BLS percentiles, H1B filings for comparable roles, and current job postings with disclosed ranges.

## Roadmap

- [ ] H1B/LCA integration (`frik/sources/h1b.py`)
- [ ] Job postings scraper with salary filter (`frik/sources/postings.py`)
- [ ] `frik range` command — CA SB 1162 pay range generator
- [ ] Metro-area adjustment (BLS state/MSA data)
- [ ] Level mapping (IC1–IC5, M1–M3) to percentile bands
- [ ] Output formats: Markdown table, CSV, JSON

## License

MIT
