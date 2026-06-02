# Southeast Asia Economic & Political Change Dashboard

Track economic indicators, news signals, pattern alerts, and AI-generated explanations
for 10 ASEAN countries across 5 dashboard views.

---

## Quick Start

Three terminal tabs. Five minutes.

```bash
# Tab 1 — Backend (MVP — no database needed)
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-mvp.txt
uvicorn server:app --reload --port 8000

# Tab 2 — Frontend
cd frontend
npm install
npm run dev

# Tab 3 — open browser
open http://localhost:3000
```

Runs immediately on sample data. No database required. No API keys required.

> **Note:** `requirements-mvp.txt` is for the single-file MVP server (`server.py`).
> The full `requirements.txt` includes PostgreSQL/SQLAlchemy — only needed for
> the complete backend under `backend/app/`.

---

## Prerequisites

| Tool    | Version | Check              |
|---------|---------|--------------------|
| Node.js | 18+     | `node --version`   |
| Python  | 3.11+   | `python --version` |
| npm     | 9+      | `npm --version`    |

---

## What You'll See

| Page           | URL                | What it shows                                       |
|----------------|--------------------|-----------------------------------------------------|
| Overview       | `localhost:3000`   | Risk grid, alert ticker, GDP chart, recent news     |
| Country        | `/country/MMR`     | Indicators, trend charts, trade partners, alerts    |
| Comparison     | `/compare`         | Side-by-side metric comparison across all countries |
| News Feed      | `/news`            | News items filtered by country and category         |
| Pattern Alerts | `/alerts`          | Rule-based alerts with AI explanation button        |

---

## AI Explanation Feature

Click **✦ AI Explanation** on any alert card on the `/alerts` page.

- **Demo mode** (default — no key needed): returns a pre-written contextual explanation.
- **Live mode** (with API key): calls Claude and generates a real explanation in 2-3 seconds.

To enable live AI:

```bash
# create backend/.env
echo "ANTHROPIC_API_KEY=your_key_here" > backend/.env
# restart the backend — button shows ✦ Claude badge
```

Get a key at: https://console.anthropic.com

---

## Project Structure

```
├── frontend/                  Next.js 14 App Router
│   ├── app/
│   │   ├── page.tsx           Overview / home
│   │   ├── country/[id]/      Country profile
│   │   ├── compare/           Comparison tool
│   │   ├── news/              News feed
│   │   └── alerts/            Pattern alerts
│   ├── components/
│   │   ├── cards/             AlertCard, CountryRiskCard, NewsCard, IndicatorCard
│   │   ├── charts/            TrendLineChart, CompareBarChart, MiniSparkline
│   │   └── layout/            Sidebar
│   ├── data/
│   │   └── sample-data.ts     All sample data (countries, indicators, news, alerts)
│   └── lib/
│       ├── api.ts             Backend API client
│       └── utils.ts           Helpers and color maps
│
├── backend/
│   ├── server.py              MVP server — single file, no database (START HERE)
│   └── app/                   Full backend (V2, requires PostgreSQL)
│
├── pipeline/                  Data pipeline scripts
│   ├── fetch_worldbank.py     World Bank economic indicators (free, no key)
│   ├── fetch_gdelt.py         GDELT news signals (free, no key)
│   ├── fetch_comtrade.py      IMF DOTS trade data (free, no key)
│   └── pattern_engine.py      Rule-based alert detection (8 alert types)
│
└── database/
    ├── schema.sql             PostgreSQL schema
    └── seed_data.sql          Seed data for 14 countries
```

---

## Tech Stack

| Layer    | Technology                               |
|----------|------------------------------------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS     |
| Charts   | Recharts 2.x                             |
| Backend  | FastAPI, Python 3.11+                    |
| AI       | Anthropic Claude (claude-haiku-4-5)      |
| Database | PostgreSQL / Supabase (V2, optional)     |
| Data     | World Bank API, GDELT 2.0, IMF DOTS      |

---

## Environment Variables

### `backend/.env`

```env
ANTHROPIC_API_KEY=your_key_here     # enables live AI explanations
CLAUDE_MODEL=claude-haiku-4-5       # model to use
DATABASE_URL=postgresql://...        # V2 only (full backend)
```

### `frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000   # backend URL (default)
```

---

## Data Pipeline (Optional)

Not required for MVP. These scripts fetch real data and save CSV files.

```bash
cd pipeline
pip install httpx python-dotenv

python fetch_worldbank.py          # World Bank indicators
python fetch_gdelt.py --days 7     # GDELT news signals
python fetch_comtrade.py           # IMF DOTS trade data
python pattern_engine.py           # run alert detection
```

---

## Countries Tracked

**ASEAN (10):**
Myanmar 🇲🇲 · Thailand 🇹🇭 · Vietnam 🇻🇳 · Cambodia 🇰🇭 · Laos 🇱🇦 ·
Malaysia 🇲🇾 · Singapore 🇸🇬 · Indonesia 🇮🇩 · Philippines 🇵🇭 · Brunei 🇧🇳

**External Partners (4):**
China 🇨🇳 · United States 🇺🇸 · Japan 🇯🇵 · India 🇮🇳

---

## Alert Types

| Alert                 | Trigger                                       |
|-----------------------|-----------------------------------------------|
| Export Stress         | Exports fell > 3% YoY                        |
| Inflation Pressure    | CPI > 5% or accelerating                     |
| Political Instability | Conflict news > 1.3× country baseline         |
| Currency Pressure     | Depreciation > 5% from 2020 reference         |
| Investment Slowdown   | FDI fell > 5% YoY                            |
| Trade Dependency Risk | Single partner > 30% of exports or imports    |
| Tourism Recovery      | Arrivals below 90% of 2019 baseline           |
| Regional Spillover    | Multiple stressed neighbours simultaneously   |

---

## Troubleshooting

**Frontend blank or unstyled**
```bash
cd frontend && rm -rf .next && npm run dev
```

**AI button shows "Could not reach backend"**
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok","ai_enabled":false}
# If it fails, start the backend first
```

**Port 3000 already in use**
```bash
lsof -ti:3000 | xargs kill && npm run dev
```

**Python module not found**
```bash
source backend/venv/bin/activate
pip install fastapi uvicorn python-dotenv anthropic
```

---

## Next Steps After MVP

1. **Real data** — run `pipeline/fetch_worldbank.py`, replace sample-data.ts
2. **Live AI** — add `ANTHROPIC_API_KEY` to `backend/.env`
3. **Database** — set up PostgreSQL, run `database/schema.sql`, switch to full backend
4. **Deploy** — Vercel (frontend) + Railway (backend) + Supabase (database)

---

## Project Structure

```
sea-change-dashboard/
│
├── frontend/                   Next.js 14 (TypeScript + Tailwind + ECharts + Leaflet)
│   ├── app/                    Pages (App Router)
│   │   ├── page.tsx            Regional overview (home)
│   │   ├── country/[id]/       Country profile — /country/THA
│   │   ├── compare/            Quarterly comparison across countries
│   │   ├── trade/              Import/export flow visualization
│   │   ├── news/               News feed with sentiment filter
│   │   └── alerts/             Active threshold alerts
│   ├── components/
│   │   ├── charts/             ECharts wrappers (bar, line, radar)
│   │   ├── cards/              Indicator, news, and alert card components
│   │   ├── map/                Leaflet regional map
│   │   ├── layout/             Sidebar and top navigation
│   │   └── ui/                 Shared UI: Badge, Spinner, Button
│   ├── lib/
│   │   ├── api.ts              Axios client — all calls to FastAPI backend
│   │   └── types.ts            TypeScript types matching the DB schema
│   └── store/index.ts          Zustand global state
│
├── backend/                    Python FastAPI
│   └── app/
│       ├── main.py             App entry point — registers all routers
│       ├── config.py           Reads .env into a typed Settings object
│       ├── database.py         SQLAlchemy engine + session dependency
│       ├── models/             SQLAlchemy ORM models (one file per table)
│       ├── routers/            Route handlers
│       │   ├── countries.py    GET /countries, GET /countries/{id}
│       │   ├── indicators.py   GET /indicators/{country_id}
│       │   ├── trade.py        GET /trade/{country_id}
│       │   ├── news.py         GET /news
│       │   ├── alerts.py       GET /alerts
│       │   └── explanations.py POST /explain
│       └── services/
│           ├── claude_service.py  Anthropic API calls + prompt templates
│           └── alert_engine.py    Threshold checking logic
│
├── pipeline/                   Python data ingestion scripts
│   ├── sources/
│   │   ├── worldbank.py        World Bank API — 7 indicators, no key needed
│   │   ├── newsapi.py          NewsAPI — headlines per country
│   │   └── exchangerate.py     Exchange rates vs USD (free, no key)
│   ├── loaders/
│   │   └── db_loader.py        Upserts data into PostgreSQL
│   └── run_daily.py            Main script — run once a day
│
├── database/
│   ├── schema.sql              PostgreSQL table definitions
│   ├── seed_data.sql           Countries, indicators, categories, example rows
│   └── SCHEMA_GUIDE.md         Full schema documentation with ERD
│
├── docs/
│   └── PROJECT_SPEC.md         Full project specification
│
├── docker-compose.yml          Local dev: Postgres + FastAPI + Next.js
├── .env.example                Template for your .env file
├── .gitignore
└── README.md                   This file
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend framework | Next.js 14 (App Router) | Full-stack routing + server components |
| Language | TypeScript | Type safety across the whole frontend |
| Styling | Tailwind CSS | Utility-first, fast to iterate |
| Charts | ECharts via echarts-for-react | Rich chart types, performant |
| Map | Leaflet + react-leaflet | Free, lightweight, good ASEAN tile support |
| State | Zustand | Minimal boilerplate |
| Data fetching | SWR + Axios | Caching + simple API calls |
| Backend | Python FastAPI | Fast, typed, automatic /docs |
| ORM | SQLAlchemy 2.0 | Pythonic, supports async |
| Database | PostgreSQL 16 | Robust, free, JSONB if needed later |
| Pipeline | Python + httpx | Simple scripts, easy to schedule |
| AI | Anthropic Claude API | Plain-language economic explanations |

---

## Development Setup

### Prerequisites
- Node.js 20+
- Python 3.11+
- PostgreSQL 16 (or Docker)

---

### Option A — Manual Setup (Recommended for Learning)

**Step 1 — Clone and configure**
```bash
git clone <your-repo-url> sea-change-dashboard
cd sea-change-dashboard
cp .env.example .env
# Edit .env and fill in your API keys
```

**Step 2 — Set up the database**
```bash
# Start PostgreSQL (if not running)
brew services start postgresql@16   # macOS
# or: sudo systemctl start postgresql  # Linux

# Create the database
createdb sea_dashboard

# Apply schema and seed data
psql -d sea_dashboard -f database/schema.sql
psql -d sea_dashboard -f database/seed_data.sql
```

**Step 3 — Start the backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# API docs now at: http://localhost:8000/docs
```

**Step 4 — Start the frontend**
```bash
cd frontend
npm install
npm run dev
# App now at: http://localhost:3000
```

**Step 5 — Run the data pipeline (first time)**
```bash
cd ..                              # back to project root
source backend/.venv/bin/activate
pip install -r pipeline/requirements.txt
python pipeline/run_daily.py
# Fetches World Bank indicators, exchange rates, and news headlines
```

---

### Option B — Docker Compose (Quick Start)

```bash
cp .env.example .env
# Edit .env and fill in NEWSAPI_KEY and ANTHROPIC_API_KEY

docker-compose up --build
# Database + backend + frontend all start together
# App: http://localhost:3000
# API docs: http://localhost:8000/docs
```

---

## API Endpoints

Once the backend is running, visit `http://localhost:8000/docs` for the interactive Swagger UI.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/countries` | List all 14 countries |
| GET | `/countries/{id}` | Single country (e.g. `/countries/THA`) |
| GET | `/indicators/{country_id}` | All indicator values for a country |
| GET | `/trade/{country_id}` | Import/export flows |
| GET | `/news` | News feed (filter by country, category, sentiment) |
| GET | `/alerts` | Active pattern alerts |
| POST | `/explain` | Generate/fetch AI explanation for an indicator |
| GET | `/health` | Health check |

---

## Running the Daily Pipeline

Add a cron job to run the pipeline automatically:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 6am daily):
0 6 * * * cd /path/to/sea-change-dashboard && /path/to/.venv/bin/python pipeline/run_daily.py >> logs/pipeline.log 2>&1
```

Or run it manually any time:
```bash
python pipeline/run_daily.py
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `NEXT_PUBLIC_API_URL` | Yes | FastAPI backend URL (for frontend) |
| `NEWSAPI_KEY` | For news | Free at newsapi.org/register |
| `ANTHROPIC_API_KEY` | For AI | From console.anthropic.com |
| `COMTRADE_SUBSCRIPTION_KEY` | Optional | For detailed trade data |
| `CLAUDE_MODEL` | Optional | Default: claude-haiku-4-5 |

---

## First Tasks (What to Build Next)

1. **Verify the backend starts** — run `uvicorn app.main:app --reload` and open `/docs`
2. **Run the pipeline** — `python pipeline/run_daily.py` to load real World Bank data
3. **Build the CountryCard component** — `frontend/components/cards/CountryCard.tsx`
4. **Build the IndicatorChart component** — bar chart using echarts-for-react
5. **Wire up the Country Profile page** — fetch from `/indicators/{id}` via SWR
6. **Add the regional map** — Leaflet with choropleth coloring by GDP growth
7. **Build the news feed component** — with sentiment badge and category filter
8. **Test the alert engine** — `python -c "from backend.app.services.alert_engine import run_alert_check; ..."`
9. **Add the AI explanation button** — calls POST `/explain`, shows text in a modal
10. **Deploy to Vercel (frontend) + Railway (backend)**

---

## Countries Tracked

| Code | Country | Region |
|---|---|---|
| MMR | Myanmar | ASEAN |
| THA | Thailand | ASEAN |
| VNM | Vietnam | ASEAN |
| KHM | Cambodia | ASEAN |
| LAO | Laos | ASEAN |
| MYS | Malaysia | ASEAN |
| SGP | Singapore | ASEAN |
| IDN | Indonesia | ASEAN |
| PHL | Philippines | ASEAN |
| BRN | Brunei | ASEAN |
| CHN | China | External Partner |
| IND | India | External Partner |
| JPN | Japan | External Partner |
| USA | United States | External Partner |

---

*Version 1 — 2026-06-01*
