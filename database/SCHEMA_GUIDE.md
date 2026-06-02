# Database Schema Guide
## Southeast Asia Economic & Political Change Dashboard — Version 1

---

## The 10 Tables at a Glance

| # | Table | What It Stores | Grows Over Time? |
|---|---|---|---|
| 1 | `countries` | The 14 countries tracked | No — fixed list |
| 2 | `indicators` | The 10 indicator definitions | Rarely — add new indicators |
| 3 | `indicator_values` | The actual numbers per country per period | Yes — every daily/weekly fetch |
| 4 | `trade_flows` | Bilateral import/export values | Yes — quarterly/annual updates |
| 5 | `event_categories` | 5 news category types (Economy, Politics, etc.) | No — fixed lookup |
| 6 | `news_events` | Headlines fetched from NewsAPI | Yes — every fetch cycle |
| 7 | `impact_scores` | Which indicator does each news event affect? | Yes — grows with news_events |
| 8 | `alert_rules` | The rules that define when to fire an alert | Rarely — add rules as needed |
| 9 | `pattern_alerts` | Each time an alert rule fires for a country | Yes — grows as data arrives |
| 10 | `ai_explanations` | Claude-generated explanations (cached) | Yes — on demand, then cached |

---

## How the Tables Connect (Relationships)

### The Central Hub: `countries`

`countries` is the spine of the entire database. Every other table — except `event_categories` and `alert_rules` — has a foreign key pointing to `countries.id`.

```
countries
    ├── indicator_values   (country_id → countries.id)
    ├── trade_flows        (reporter_id → countries.id)
    │                      (partner_id  → countries.id)  ← two FKs to same table
    ├── news_events        (country_id → countries.id)
    ├── impact_scores      (country_id → countries.id)
    ├── pattern_alerts     (country_id → countries.id)
    └── ai_explanations    (country_id → countries.id)
```

### The Indicator Catalogue: `indicators`

`indicators` is the second anchor. It defines what each measurement *means* — units, source API, update frequency. The actual numbers live in `indicator_values`.

```
indicators
    ├── indicator_values   (indicator_id → indicators.id)
    ├── impact_scores      (indicator_id → indicators.id)
    ├── alert_rules        (indicator_id → indicators.id)
    ├── pattern_alerts     (indicator_id → indicators.id)
    └── ai_explanations    (indicator_id → indicators.id)
```

### The News Chain: categories → events → impacts

News data flows through three tables:

```
event_categories
    └── news_events        (category_id → event_categories.id)
            └── impact_scores (news_event_id → news_events.id)
```

An `impact_score` is the bridge between a news event and the economic indicator it affects. One news event can have multiple impact scores (e.g., a coup hits `political_stability`, `exchange_rate`, and `fdi_inflows` all at once).

### The Alert Chain: rules → alerts → explanations

```
alert_rules
    └── pattern_alerts     (alert_rule_id → alert_rules.id)
            └── ai_explanations (alert_id → pattern_alerts.id)
```

---

## Beginner-Friendly ERD Description

Think of the schema as three clusters connected at `countries` and `indicators`:

```
┌──────────────────────────────────────────────────────────────────┐
│                         REFERENCE DATA                           │
│   countries (14 rows)        indicators (10 rows)                │
│   event_categories (5 rows)  alert_rules (3+ rows)               │
└──────────────────┬───────────────────────┬───────────────────────┘
                   │                       │
┌──────────────────▼───────────────────────▼───────────────────────┐
│                      ECONOMIC DATA                               │
│                                                                  │
│   indicator_values                                               │
│   (country + indicator + year/quarter/month + value)             │
│                                                                  │
│   trade_flows                                                    │
│   (reporter country ↔ partner country + direction + value)       │
└──────────────────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────┐
│                      NEWS & ALERTS                               │
│                                                                  │
│   news_events → impact_scores                                    │
│   (headline)     (which indicator does this event affect?)       │
│                                                                  │
│   pattern_alerts → ai_explanations                               │
│   (triggered rule)  (Claude explanation, cached)                 │
└──────────────────────────────────────────────────────────────────┘
```

### In plain English:

1. **`countries` and `indicators` are your dictionary.** They never change after setup.

2. **`indicator_values` is your spreadsheet.** Every row is one data point: Vietnam's GDP growth in 2024 = 7.1%. Thailand's inflation in Q1 2025 = 1.3%.

3. **`trade_flows` is your trade matrix.** Every row is one bilateral trade relationship in one direction: Vietnam exported $98bn to the USA in 2024.

4. **`news_events` is your news ticker.** Every row is one headline, tagged to a country and a category.

5. **`impact_scores` is the bridge between news and economics.** It answers: "This headline about a Laos currency crisis — which economic indicators does it affect, and how badly?"

6. **`alert_rules` is your rulebook.** "If inflation > 5%, fire a warning." "If GDP < 0%, fire a critical alert."

7. **`pattern_alerts` is your alert log.** Every row is one time a rule fired: "Myanmar GDP hit -2.1% on 2024-12-01 — Critical."

8. **`ai_explanations` is your analyst.** Every row is a Claude-generated paragraph explaining why a number changed or why an alert fired. Stored and reused so you don't pay the API twice.

---

## Primary and Foreign Key Summary

| Table | Primary Key | Foreign Keys |
|---|---|---|
| `countries` | `id` (CHAR 3) | — |
| `indicators` | `id` (SERIAL) | — |
| `indicator_values` | `id` (BIGSERIAL) | `country_id → countries`, `indicator_id → indicators` |
| `trade_flows` | `id` (SERIAL) | `reporter_id → countries`, `partner_id → countries` |
| `event_categories` | `id` (SERIAL) | — |
| `news_events` | `id` (BIGSERIAL) | `country_id → countries`, `category_id → event_categories` |
| `impact_scores` | `id` (SERIAL) | `news_event_id → news_events`, `country_id → countries`, `indicator_id → indicators` |
| `alert_rules` | `id` (SERIAL) | `indicator_id → indicators` |
| `pattern_alerts` | `id` (BIGSERIAL) | `country_id → countries`, `alert_rule_id → alert_rules`, `indicator_id → indicators` |
| `ai_explanations` | `id` (SERIAL) | `country_id → countries`, `indicator_id → indicators`, `alert_id → pattern_alerts` |

---

## Key Design Decisions for V1

**Why one `indicator_values` table instead of separate quarterly/monthly tables?**
Using `year`, `quarter` (nullable), and `month` (nullable) in a single table keeps queries simple — one `SELECT` covers all cadences. A `UNIQUE` constraint prevents duplicate rows.

**Why store `impact_scores` separately from `news_events`?**
One news event frequently affects multiple indicators across multiple countries. A US tariff announcement affects Vietnam's `trade_balance`, `fdi_inflows`, and `exchange_rate` simultaneously. A separate table models this cleanly without repeating the headline.

**Why cache `ai_explanations` in the database?**
Claude API calls cost money. Caching the explanation means a page load retrieves it from PostgreSQL instead of re-calling the API. The `generated_at` timestamp lets you refresh stale explanations (e.g., older than 30 days) on a schedule.

**Why BIGSERIAL for `news_events`, `indicator_values`, `pattern_alerts`?**
These three tables grow with every ingestion cycle. Over a year of daily fetches across 14 countries and 10 indicators, `indicator_values` could reach ~50,000 rows. BIGSERIAL (64-bit integer) avoids integer overflow far into the future.

---

## Running the Schema

```bash
# 1. Create your Supabase project (supabase.com) or local Postgres
# 2. Connect and run in order:
psql -h your-host -U postgres -d your-db -f database/schema.sql
psql -h your-host -U postgres -d your-db -f database/seed_data.sql

# With Supabase CLI:
supabase db reset   # applies all migrations
# or paste SQL directly into Supabase Studio → SQL Editor
```
