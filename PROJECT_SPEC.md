# Southeast Asia Economic & Political Change Dashboard
## Version 1 — Project Specification

---

## Project Objective

Build a web dashboard that aggregates official economic indicators and real-time news signals for Southeast Asian countries and their major external partners — enabling analysts, researchers, and curious users to detect economic shifts, political changes, and trade relationship movements in one unified view.

---

## User Problem

Southeast Asia is one of the world's fastest-changing economic regions, yet monitoring it requires juggling the World Bank portal, IMF datasets, ASEAN statistical tables, and dozens of news sources simultaneously. There is no single lightweight tool that:

- Shows quarterly economic trends across all 10 ASEAN countries side by side
- Connects trade relationship data with current news signals
- Flags anomalies or threshold breaches automatically
- Explains what the numbers mean in plain language

Target users: economics students, regional policy researchers, journalists, and business analysts who track Southeast Asia but lack enterprise data tools.

---

## Research Questions

1. Which ASEAN economies showed the strongest GDP growth in each quarter this year, and what drove it?
2. How are import/export balances shifting between ASEAN members and China, India, Japan, and the US?
3. When a political event occurs (election, coup, sanctions), how quickly do economic indicators follow?
4. Which countries are showing early warning signals — inflation spikes, currency pressure, or trade deficit widening?
5. How correlated are ASEAN economies with each other versus with China and the US?

---

## Countries Covered

| Group | Countries |
|---|---|
| ASEAN Core | Myanmar, Thailand, Vietnam, Cambodia, Laos, Malaysia, Singapore, Indonesia, Philippines, Brunei |
| External Partners | China, India, Japan, United States |

---

## Dashboard Pages

### Page 1 — Regional Overview (Home)
- Regional map with color-coded GDP growth rate per country (current quarter)
- Top-line summary cards: fastest growing, highest inflation, biggest trade surplus/deficit
- Recent alerts ticker
- Latest news headlines (5 items per country, filterable)

### Page 2 — Country Profile
- Selected country deep-dive (dropdown selector)
- Key indicator cards: GDP growth %, inflation %, unemployment %, trade balance, currency vs USD
- Quarterly trend chart: 4 quarters, all key indicators on one chart
- Recent news feed for that country
- Trade partner breakdown: top 5 import and export partners with values
- Active alerts for that country

### Page 3 — Quarterly Comparison
- Side-by-side bar chart: all 10 ASEAN countries, one metric at a time (GDP / inflation / trade balance)
- Quarter selector: Q1 / Q2 / Q3 / Q4 toggle
- Metric selector: choose which indicator to compare
- Sortable data table below the chart

### Page 4 — Trade & Relations Map
- Import/export flow visualization (chord diagram or sankey diagram)
- Country pair selector: pick any two countries to see bilateral trade value
- Top 3 trade partners per ASEAN country (cards)
- Year-over-year trade change % (positive/negative badge)

### Page 5 — News & Event Signal Feed
- Filterable news feed: by country, by category (economy / politics / trade / security)
- Sentiment label per headline: Positive / Neutral / Negative (rule-based, not AI in V1)
- Source and timestamp for each item
- Link to original article

### Page 6 — Alerts & Pattern Detection
- List of active threshold alerts (e.g. "Vietnam inflation exceeded 4%")
- Alert rule display: what triggered it and when
- Historical alert log per country
- Alert severity: Info / Warning / Critical

---

## Data Sources

### Economic Indicators (Free APIs)

| Source | Data | API |
|---|---|---|
| World Bank Open Data | GDP growth, inflation, unemployment, trade balance, FDI | `api.worldbank.org/v2` — free, no key required |
| IMF Data API | Current account, exchange rates, government debt | `datahelp.imf.org` — free |
| ASEAN Stats | ASEAN-specific trade and economic data | Manual download (CSV), updated quarterly |

### Trade Data (Free)

| Source | Data | Access |
|---|---|---|
| UN Comtrade API | Bilateral import/export values by country pair | Free tier: 100 requests/hour |
| World Bank WITS | Trade statistics by commodity | Free API |

### News & Events (Free Tier)

| Source | Data | API |
|---|---|---|
| NewsAPI.org | English-language news headlines by country/keyword | Free tier: 100 requests/day |
| GDELT Project | Global event database, political events, conflict signals | Free, bulk download |

### Reference Data

- ISO country codes and metadata: `restcountries.com` (free)
- Currency exchange rates: `exchangerate-api.com` (free tier)

---

## Data Model

### `countries`
```
id          TEXT PRIMARY KEY  -- ISO 3166-1 alpha-3 (e.g. "MMR", "THA")
name        TEXT
region      TEXT              -- "ASEAN" or "External Partner"
iso2        TEXT
currency    TEXT
capital     TEXT
```

### `economic_indicators`
```
id          SERIAL PRIMARY KEY
country_id  TEXT REFERENCES countries(id)
year        INTEGER
quarter     INTEGER           -- 1, 2, 3, 4
metric      TEXT              -- "gdp_growth", "inflation", "unemployment", "trade_balance", "fdi_net"
value       NUMERIC
unit        TEXT              -- "%", "USD_billions", etc.
source      TEXT              -- "worldbank", "imf", "aseanstats"
fetched_at  TIMESTAMPTZ
```

### `trade_flows`
```
id              SERIAL PRIMARY KEY
reporter_id     TEXT REFERENCES countries(id)
partner_id      TEXT REFERENCES countries(id)
year            INTEGER
quarter         INTEGER
direction       TEXT          -- "export" or "import"
value_usd_m     NUMERIC       -- value in millions USD
commodity_group TEXT          -- "total" for V1
source          TEXT
fetched_at      TIMESTAMPTZ
```

### `news_events`
```
id              SERIAL PRIMARY KEY
country_id      TEXT REFERENCES countries(id)
headline        TEXT
summary         TEXT
source_name     TEXT
source_url      TEXT
published_at    TIMESTAMPTZ
category        TEXT          -- "economy", "politics", "trade", "security"
sentiment       TEXT          -- "positive", "neutral", "negative"
fetched_at      TIMESTAMPTZ
```

### `alerts`
```
id              SERIAL PRIMARY KEY
country_id      TEXT REFERENCES countries(id)
metric          TEXT
trigger_value   NUMERIC
threshold       NUMERIC
condition       TEXT          -- "above", "below", "change_pct"
severity        TEXT          -- "info", "warning", "critical"
message         TEXT
triggered_at    TIMESTAMPTZ
resolved_at     TIMESTAMPTZ
```

---

## Tech Stack (V1)

| Layer | Choice | Reason |
|---|---|---|
| Framework | Next.js 14 (App Router) | Full-stack in one repo, API routes built-in |
| Language | TypeScript | Type safety for data models |
| Styling | Tailwind CSS | Fast, consistent, no custom CSS files |
| Charts | Recharts | React-native, simple, good enough for V1 |
| Database | Supabase (PostgreSQL) | Free tier, hosted, REST + realtime |
| ORM | Prisma | Type-safe queries, easy migrations |
| State | Zustand | Lightweight, no boilerplate |
| Data fetch | SWR | Caching and revalidation for API data |
| AI explanations | Anthropic Claude API (claude-haiku-4-5) | Cheap, fast, explain indicator changes in plain language |

---

## MVP Features (Version 1)

These 6 features ship in V1 — no more, no less.

- [x] **Country selector** — click any country and see its profile page
- [x] **Quarterly indicators** — GDP, inflation, trade balance for Q1–Q4, pulled from World Bank API
- [x] **News feed** — latest 20 headlines per country via NewsAPI, filtered by country
- [x] **Trade overview** — top 5 import and top 5 export partners per country (annual data, UN Comtrade)
- [x] **Threshold alerts** — 3 hardcoded rules: inflation > 5%, GDP growth < 0%, trade deficit > 10B USD
- [x] **AI explanation** — one-paragraph Claude-generated explanation when a user clicks "Explain this" on any indicator card

---

## What V1 Deliberately Excludes

- Real-time data (all data is fetched once daily via a cron job)
- User accounts or saved dashboards
- Commodity-level trade breakdown
- Political risk scoring
- Mobile-optimized layout (desktop first)
- Multilingual support

---

## Future Advanced Features (V2+)

| Feature | Description |
|---|---|
| Real-time event stream | GDELT webhook integration for live political event signals |
| Correlation matrix | Show GDP/trade correlation heatmap across all 14 countries |
| Political risk index | Composite score from Freedom House + news sentiment + GDELT conflict signals |
| Commodity breakdown | Trade flows by product category (SITC codes from UN Comtrade) |
| Regime change detector | Pattern: news sentiment drops + currency pressure + FDI outflow in same quarter |
| Custom alert rules | User-defined thresholds with email/Slack notification |
| Historical backtesting | Scroll back to any year since 2000 and replay indicator history |
| Bayesian trend model | Dynamic Factor Model for shared regional growth factor (see DFM-ESV extension) |
| PDF export | One-click country report export |
| Mobile layout | Responsive design pass |

---

## Build Sequence (Recommended Order)

```
Week 1  — Database schema + Supabase setup + World Bank data ingestion script
Week 2  — Country profile page + quarterly indicator charts
Week 3  — News feed integration + sentiment labels
Week 4  — Trade flow visualization + bilateral trade cards
Week 5  — Alert engine + alert list page
Week 6  — AI explanation integration + regional overview map
Week 7  — Polish, loading states, error handling, deploy to Vercel
```

---

## Project Directory Structure

```
/
├── app/
│   ├── page.tsx                  # Regional overview
│   ├── country/[id]/page.tsx     # Country profile
│   ├── compare/page.tsx          # Quarterly comparison
│   ├── trade/page.tsx            # Trade & relations
│   ├── news/page.tsx             # News feed
│   └── alerts/page.tsx           # Alerts
├── components/
│   ├── charts/                   # Recharts wrappers
│   ├── cards/                    # Indicator, news, alert cards
│   ├── map/                      # Regional map component
│   └── layout/                   # Sidebar, navbar
├── lib/
│   ├── worldbank.ts              # World Bank API client
│   ├── newsapi.ts                # NewsAPI client
│   ├── comtrade.ts               # UN Comtrade client
│   ├── claude.ts                 # Anthropic API client
│   └── alerts.ts                 # Alert rule engine
├── prisma/
│   └── schema.prisma             # Data model
├── scripts/
│   └── ingest.ts                 # Daily data fetch script
└── types/
    └── index.ts                  # Shared TypeScript types
```

---

*Version 1 specification — 2026-06-01*
