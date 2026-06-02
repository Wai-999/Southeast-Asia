# SEA Change Intelligence Dashboard — Data Pipeline

This folder contains all the Python scripts that fetch, process, and generate
alerts for the dashboard. You only need to run **one command** to update
everything:

```bash
cd pipeline
python run_pipeline.py
```

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [How the Pipeline Works](#2-how-the-pipeline-works)
3. [Script Reference](#3-script-reference)
4. [Output Files](#4-output-files)
5. [Common Tasks](#5-common-tasks)
6. [Troubleshooting](#6-troubleshooting)
7. [Scheduling a Daily Refresh](#7-scheduling-a-daily-refresh)
8. [API Keys](#8-api-keys)
9. [Data Sources](#9-data-sources)

---

## 1. Quick Start

### Prerequisites

- Python 3.11 or later
- The project's Python dependencies

```bash
# Install dependencies
cd pipeline
pip install -r requirements.txt
```

### Run the full pipeline

```bash
cd pipeline
python run_pipeline.py
```

This runs all 6 scripts in order and prints a summary at the end.

### Run only the processing steps (fast, no API calls)

If you already ran the fetch scripts recently and just need to reprocess:

```bash
python run_pipeline.py --skip-fetch
```

This takes about 5–10 seconds.

### See what would run without actually running it

```bash
python run_pipeline.py --dry-run
```

---

## 2. How the Pipeline Works

The pipeline has two phases:

**Phase 1 — Fetch** (steps 1–3): Download data from external APIs and save
raw JSON files to `data/raw/`.

**Phase 2 — Process** (steps 4–6): Read the raw files, clean and reshape
the data, compute alerts, and save dashboard-ready JSON files to
`data/processed/`.

```
External APIs                    Raw Data               Dashboard Data
─────────────────────────────────────────────────────────────────────────

World Bank API  ──→  fetch_worldbank.py  ──→  worldbank_indicators.json ─┐
                                                                          │
GDELT API  ──────→  fetch_gdelt_news.py  ──→  news_signals.json ─────────┼──→  process_indicators.py  ──→  indicators_dashboard.json
                                                                          │
UN Comtrade  ────→  fetch_comtrade.py    ──→  trade_flows.json ──────────┘──→  process_news.py          ──→  news_dashboard.json
                                                                              →  generate_alerts.py       ──→  alerts.json
```

The **Next.js frontend** reads from `data/processed/` at build time.
After running the pipeline, restart (or rebuild) the frontend to see updates.

---

## 3. Script Reference

### Step 1 — `fetch_worldbank.py`

Downloads annual economic indicators from the [World Bank Open Data API](https://data.worldbank.org/).
No API key needed. Free.

**Countries**: 11 Southeast Asian countries + 6 partners (China, US, Japan, India, South Korea, Australia)

**Indicators**:
| Code | Name |
|---|---|
| NY.GDP.MKTP.KD.ZG | GDP Growth Rate |
| NY.GDP.MKTP.CD | GDP Nominal (USD) |
| FP.CPI.TOTL.ZG | Inflation (CPI) |
| SL.UEM.TOTL.ZS | Unemployment Rate |
| BX.KLT.DINV.WD.GD.ZS | FDI (% of GDP) |
| NE.EXP.GNFS.CD | Exports (USD) |
| NE.IMP.GNFS.CD | Imports (USD) |
| SP.POP.TOTL | Population |

```bash
python fetch_worldbank.py          # use today's cached raw files
python fetch_worldbank.py --refresh  # force re-download from API
```

**Note**: World Bank data is **annual only** with a 1–2 year lag. In 2026,
the most recent confirmed year for most countries is 2023.

---

### Step 2 — `fetch_gdelt_news.py`

Downloads recent news articles from the [GDELT 2.0 Document API](https://www.gdeltproject.org/).
No API key needed. Free. Covers the last 7 days by default.

**Classifies each article** into one of 12 categories:
`tariff`, `conflict`, `disaster`, `border`, `protest`, `election`,
`policy`, `trade`, `technology`, `infrastructure`, `economy`, `politics`

**Scores each article** on impact 1–5 based on keywords and category.

```bash
python fetch_gdelt_news.py             # last 7 days, use cache
python fetch_gdelt_news.py --days 14   # extend to 14-day window
python fetch_gdelt_news.py --refresh   # force re-fetch
python fetch_gdelt_news.py --country THA  # test one country
```

**Important**: GDELT rate-limits aggressively. If you see 429 errors,
wait 10–15 minutes before retrying. The script will preserve existing
data and exit cleanly if it's rate-limited.

---

### Step 3 — `fetch_comtrade.py`

Downloads bilateral trade data from the [UN Comtrade API](https://comtradeplus.un.org/).

**Reporter countries** (10 SEA): Thailand, Vietnam, Myanmar, Cambodia, Laos,
Malaysia, Singapore, Indonesia, Philippines, Brunei

**Partner entities** (7): China, USA, Japan, India, South Korea, Australia,
European Union

**Computes dependency risk** per bilateral pair:
- `partner_share = (exports_to + imports_from) / total_trade`
- `>40%` = **high** dependency
- `20–40%` = **medium** dependency  
- `<20%` = **low** dependency

```bash
python fetch_comtrade.py           # free preview mode (no key needed)
python fetch_comtrade.py --refresh # force re-fetch
```

**For live data**: Register at [comtradeplus.un.org](https://comtradeplus.un.org)
(free), get a subscription key, and add it to `.env`:
```
COMTRADE_SUBSCRIPTION_KEY=your_key_here
```

---

### Step 4 — `process_indicators.py`

Reads the World Bank and Comtrade raw files, combines them, and produces
a clean per-country summary for the dashboard.

**What it adds that the raw files don't have**:
- Latest value + previous year value per indicator
- Trend direction: `up` / `down` / `flat` / `unknown`
- Full history array for sparkline charts
- Trade dependency data merged per country
- Data completeness percentage per country

```bash
python process_indicators.py
```

---

### Step 5 — `process_news.py`

Reads the GDELT news signal file and reshapes it into useful views
for the dashboard's news feed and alert widgets.

**What it adds**:
- Articles sorted newest-first, then by impact score
- `critical` list — articles with impact 4 or 5
- Grouped by country and by category
- Risk signal per country: `low` / `medium` / `high`
- Aggregate counts by impact level, category, and sentiment

```bash
python process_news.py
```

---

### Step 6 — `generate_alerts.py`

Reads the processed indicator and news files, builds a snapshot for each
SEA country, and runs the 8-type pattern alert engine.

**The 8 alert types** (from `pattern_engine.py`):

| Type | What it detects |
|---|---|
| `export_stress` | Exports falling + trade balance worsening |
| `inflation_pressure` | CPI high or accelerating |
| `political_instability` | Conflict/protest news spike |
| `currency_pressure` | Exchange rate depreciating |
| `investment_slowdown` | FDI declining + political uncertainty |
| `trade_dependency_risk` | Over-concentrated trading partner |
| `tourism_recovery` | Arrivals still below 2019 level |
| `regional_spillover` | Multiple neighbours under stress |

Each alert gets a score from 0–100 and a severity: `info` / `warning` / `critical`.

```bash
python generate_alerts.py                   # all countries, min score 20
python generate_alerts.py --min-score 40    # higher threshold
python generate_alerts.py --country MMR     # single country (for testing)
```

---

## 4. Output Files

All output files live in `pipeline/data/processed/`.

| File | Created by | Used by |
|---|---|---|
| `worldbank_indicators.json` | `fetch_worldbank.py` | `process_indicators.py` |
| `news_signals.json` | `fetch_gdelt_news.py` | `process_news.py` |
| `trade_flows.json` | `fetch_comtrade.py` | `process_indicators.py` |
| `indicators_dashboard.json` | `process_indicators.py` | Frontend, `generate_alerts.py` |
| `news_dashboard.json` | `process_news.py` | Frontend, `generate_alerts.py` |
| `alerts.json` | `generate_alerts.py` | Frontend |

### Raw data (audit trail)

Raw API responses are saved in `pipeline/data/raw/`:
- `worldbank/` — one JSON file per indicator per day
- `gdelt/` — one JSON file per country per day
- `comtrade/` — one JSON file per trade flow type per year

These files are cached: if you run a script twice on the same day, it
reads the cached file instead of calling the API again.  
Use `--refresh` to bypass the cache and force a new API call.

---

## 5. Common Tasks

### Refresh only the news feed (fastest)

```bash
python fetch_gdelt_news.py && python process_news.py
```

### Refresh indicators only

```bash
python fetch_worldbank.py && python process_indicators.py
```

### Regenerate alerts without re-fetching anything

```bash
python generate_alerts.py
```

### Test a single country

```bash
python fetch_gdelt_news.py --country THA
python generate_alerts.py --country MMR
```

### Full pipeline, processing only (no API calls)

```bash
python run_pipeline.py --skip-fetch
```

---

## 6. Troubleshooting

### "File not found" errors

Scripts must be run in order. If `process_indicators.py` fails with
"worldbank_indicators.json not found", run `fetch_worldbank.py` first.

The full order is always: fetch → process → generate.

### GDELT 429 rate limit

GDELT blocks IP addresses that make too many requests.

**What to do**:
1. Wait 10–15 minutes
2. Run: `python fetch_gdelt_news.py`
3. If still blocked, wait 1 hour and use `--refresh`

The script will keep your existing `news_signals.json` intact
if it gets rate-limited — your dashboard continues to work.

### World Bank data seems old

World Bank publishes **annual** data only, usually with a 1–2 year lag.
In 2026, the most recent year for most countries is 2023 or 2024.
This is normal and expected — it's not a bug.

### UN Comtrade returns $0 for some flows

The free Comtrade API has a 500-record cap per request. When batching
many countries, the cap is hit and some bilateral pairs show $0.
Use single-pair queries or get a free Plus API key from
[comtradeplus.un.org](https://comtradeplus.un.org).

### Import errors (`cannot import 'pattern_engine'`)

Make sure you are running scripts from the `pipeline/` directory:
```bash
cd pipeline
python generate_alerts.py    ✓  correct
python pipeline/generate_alerts.py    ✗  wrong directory
```

---

## 7. Scheduling a Daily Refresh

### Using cron (macOS / Linux)

Open the crontab editor:
```bash
crontab -e
```

Add a line to run the processing steps every day at 6:00 AM:
```cron
0 6 * * *  cd /path/to/project/pipeline && python run_pipeline.py --skip-fetch >> /tmp/sea-pipeline.log 2>&1
```

To also refresh the fetched data (slower, calls APIs):
```cron
0 4 * * *  cd /path/to/project/pipeline && python run_pipeline.py >> /tmp/sea-pipeline.log 2>&1
```

### Using GitHub Actions

A workflow file is already set up at `.github/workflows/`. It can be
triggered manually or on a schedule.

---

## 8. API Keys

| API | Key needed? | Where to get it |
|---|---|---|
| World Bank | **No** | Free, open access |
| GDELT | **No** | Free, open access |
| UN Comtrade (free preview) | **No** | Free, but 500-record cap |
| UN Comtrade Plus | Optional | [comtradeplus.un.org](https://comtradeplus.un.org) — free registration |

If you have a UN Comtrade Plus key, add it to `.env` in the project root:
```
COMTRADE_SUBSCRIPTION_KEY=your_key_here
```

The `fetch_comtrade.py` script automatically detects and uses the key.

---

## 9. Data Sources

| Source | Data | Frequency | Lag |
|---|---|---|---|
| [World Bank Open Data](https://data.worldbank.org/) | GDP, inflation, unemployment, FDI, trade, population | Annual | 1–2 years |
| [GDELT Project](https://www.gdeltproject.org/) | News articles, sentiment, event categories | Near real-time | Minutes |
| [UN Comtrade](https://comtradeplus.un.org/) | Bilateral trade flows | Annual / Monthly | 6–12 months |

---

## File Structure

```
pipeline/
├── run_pipeline.py          ← start here: runs everything in order
│
├── fetch_worldbank.py       step 1: download World Bank indicators
├── fetch_gdelt_news.py      step 2: download GDELT news articles
├── fetch_comtrade.py        step 3: download UN Comtrade trade data
├── process_indicators.py    step 4: combine and reshape indicators
├── process_news.py          step 5: reshape news feed + risk signals
├── generate_alerts.py       step 6: run pattern engine → alerts
│
├── pattern_engine.py        alert engine (8 alert types, reusable)
├── requirements.txt         Python dependencies
│
├── utils/
│   └── logger.py            shared terminal output helpers
│
└── data/
    ├── raw/
    │   ├── worldbank/       raw API responses (one file per indicator/day)
    │   ├── gdelt/           raw article responses (one file per country/day)
    │   └── comtrade/        raw trade responses
    └── processed/
        ├── worldbank_indicators.json    ← step 1 output
        ├── news_signals.json            ← step 2 output
        ├── trade_flows.json             ← step 3 output
        ├── indicators_dashboard.json    ← step 4 output
        ├── news_dashboard.json          ← step 5 output
        └── alerts.json                  ← step 6 output
```
