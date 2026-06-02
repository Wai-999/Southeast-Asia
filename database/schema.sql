-- ============================================================
-- Southeast Asia Economic & Political Change Dashboard
-- PostgreSQL Schema — Version 1
-- ============================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid() if needed later


-- ============================================================
-- TABLE 1: countries
-- The master list of all 14 countries tracked.
-- Every other table points back to this one.
-- ============================================================
CREATE TABLE countries (
    id           CHAR(3)      PRIMARY KEY,          -- ISO 3166-1 alpha-3 code (e.g. 'THA', 'VNM')
    name         TEXT         NOT NULL,
    region       TEXT         NOT NULL               -- 'ASEAN' or 'External Partner'
                              CHECK (region IN ('ASEAN', 'External Partner')),
    iso2         CHAR(2)      NOT NULL,              -- 2-letter code for flag emojis and APIs
    currency     CHAR(3)      NOT NULL,              -- ISO 4217 currency code (e.g. 'THB', 'USD')
    capital      TEXT,
    flag_emoji   TEXT                                -- e.g. '🇹🇭' — useful for UI
);


-- ============================================================
-- TABLE 2: indicators
-- The catalogue of 10 economic indicators tracked.
-- Stores metadata about each indicator, not the values.
-- ============================================================
CREATE TABLE indicators (
    id               SERIAL       PRIMARY KEY,
    code             TEXT         UNIQUE NOT NULL,   -- short machine key, e.g. 'gdp_growth'
    name             TEXT         NOT NULL,           -- human label, e.g. 'GDP Growth Rate'
    description      TEXT,
    unit             TEXT         NOT NULL,           -- '%', 'USD_millions', 'arrivals'
    cadence          TEXT         NOT NULL            -- how often it updates
                                  CHECK (cadence IN ('annual', 'quarterly', 'monthly', 'daily')),
    world_bank_code  TEXT,                            -- API indicator code, e.g. 'NY.GDP.MKTP.KD.ZG'
    imf_code         TEXT,                            -- IMF DataMapper field code
    source_name      TEXT         NOT NULL,           -- 'World Bank', 'IMF', 'UNWTO', etc.
    source_url       TEXT,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE
);


-- ============================================================
-- TABLE 3: indicator_values
-- The actual numbers. One row = one country + one indicator
-- + one time period (year / quarter / month).
-- This is the biggest table — it grows with every data fetch.
-- ============================================================
CREATE TABLE indicator_values (
    id           BIGSERIAL    PRIMARY KEY,
    country_id   CHAR(3)      NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    indicator_id INTEGER      NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
    year         SMALLINT     NOT NULL,
    quarter      SMALLINT     CHECK (quarter BETWEEN 1 AND 4),   -- NULL for annual/monthly rows
    month        SMALLINT     CHECK (month  BETWEEN 1 AND 12),   -- NULL for annual/quarterly rows
    value        NUMERIC(18, 4),
    source       TEXT,                                            -- override if differs from indicator default
    fetched_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- Prevents duplicate entries for the same country+indicator+period
    UNIQUE (country_id, indicator_id, year, quarter, month)
);

CREATE INDEX idx_iv_country   ON indicator_values (country_id);
CREATE INDEX idx_iv_indicator ON indicator_values (indicator_id);
CREATE INDEX idx_iv_year      ON indicator_values (year, quarter);


-- ============================================================
-- TABLE 4: trade_flows
-- Bilateral import/export values between any two countries.
-- reporter = the country doing the exporting or importing.
-- partner  = the other country in the transaction.
-- ============================================================
CREATE TABLE trade_flows (
    id             SERIAL       PRIMARY KEY,
    reporter_id    CHAR(3)      NOT NULL REFERENCES countries(id),
    partner_id     CHAR(3)      NOT NULL REFERENCES countries(id),
    year           SMALLINT     NOT NULL,
    quarter        SMALLINT     CHECK (quarter BETWEEN 1 AND 4),   -- NULL = annual
    direction      TEXT         NOT NULL
                                CHECK (direction IN ('export', 'import')),
    value_usd_m    NUMERIC(15, 2) NOT NULL,                        -- USD millions
    share_pct      NUMERIC(5, 2),                                  -- % of reporter's total trade
    source         TEXT         NOT NULL DEFAULT 'UN Comtrade',
    fetched_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (reporter_id, partner_id, year, quarter, direction),
    CHECK (reporter_id <> partner_id)                              -- a country can't trade with itself
);

CREATE INDEX idx_tf_reporter ON trade_flows (reporter_id);
CREATE INDEX idx_tf_partner  ON trade_flows (partner_id);


-- ============================================================
-- TABLE 5: event_categories
-- A small lookup table for news event types.
-- Keeps categories consistent across all news rows.
-- ============================================================
CREATE TABLE event_categories (
    id         SERIAL  PRIMARY KEY,
    code       TEXT    UNIQUE NOT NULL,   -- 'economy', 'politics', 'trade', 'security', 'disaster'
    name       TEXT    NOT NULL,
    color_hex  CHAR(7),                  -- '#E53E3E' — used for badge colors in the UI
    icon_name  TEXT                      -- icon identifier, e.g. 'trending-down', 'alert-triangle'
);


-- ============================================================
-- TABLE 6: news_events
-- One row per news headline fetched.
-- Linked to a country and a category.
-- Sentiment is rule-based in V1 (no ML needed).
-- ============================================================
CREATE TABLE news_events (
    id              BIGSERIAL    PRIMARY KEY,
    country_id      CHAR(3)      NOT NULL REFERENCES countries(id),
    category_id     INTEGER      REFERENCES event_categories(id),
    headline        TEXT         NOT NULL,
    summary         TEXT,
    source_name     TEXT,
    source_url      TEXT,
    published_at    TIMESTAMPTZ  NOT NULL,
    sentiment       TEXT         CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    sentiment_score NUMERIC(4, 3)                             -- -1.000 to 1.000
                                 CHECK (sentiment_score BETWEEN -1 AND 1),
    fetched_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ne_country      ON news_events (country_id);
CREATE INDEX idx_ne_published    ON news_events (published_at DESC);
CREATE INDEX idx_ne_sentiment    ON news_events (sentiment);


-- ============================================================
-- TABLE 7: impact_scores
-- Connects a news event to the economic indicators it affects.
-- One news event can impact multiple indicators across multiple
-- countries (e.g. a US tariff affects Vietnam's trade AND FDI).
-- ============================================================
CREATE TABLE impact_scores (
    id                SERIAL       PRIMARY KEY,
    news_event_id     BIGINT       NOT NULL REFERENCES news_events(id) ON DELETE CASCADE,
    country_id        CHAR(3)      NOT NULL REFERENCES countries(id),
    indicator_id      INTEGER      NOT NULL REFERENCES indicators(id),
    impact_level      SMALLINT     NOT NULL
                                   CHECK (impact_level BETWEEN 1 AND 5),  -- 1=minimal, 5=critical
    impact_direction  TEXT         NOT NULL
                                   CHECK (impact_direction IN ('positive', 'negative', 'neutral')),
    rationale         TEXT,         -- one sentence: why this event affects this indicator
    scored_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (news_event_id, country_id, indicator_id)
);


-- ============================================================
-- TABLE 8: alert_rules
-- The definitions of what triggers an alert.
-- V1 ships with 3 hardcoded rules but the table lets you add
-- more without code changes.
-- ============================================================
CREATE TABLE alert_rules (
    id            SERIAL       PRIMARY KEY,
    indicator_id  INTEGER      NOT NULL REFERENCES indicators(id),
    name          TEXT         NOT NULL,
    description   TEXT,
    condition     TEXT         NOT NULL
                               CHECK (condition IN ('above', 'below', 'change_pct', 'change_abs')),
    threshold     NUMERIC      NOT NULL,   -- the value to compare against
    period        TEXT         NOT NULL
                               CHECK (period IN ('annual', 'quarterly', 'monthly', 'rolling_30d')),
    severity      TEXT         NOT NULL
                               CHECK (severity IN ('info', 'warning', 'critical')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ============================================================
-- TABLE 9: pattern_alerts
-- One row per triggered alert instance.
-- Created by the alert engine when a rule fires.
-- resolved_at = NULL means the alert is still active.
-- ============================================================
CREATE TABLE pattern_alerts (
    id              BIGSERIAL    PRIMARY KEY,
    country_id      CHAR(3)      NOT NULL REFERENCES countries(id),
    alert_rule_id   INTEGER      NOT NULL REFERENCES alert_rules(id),
    indicator_id    INTEGER      NOT NULL REFERENCES indicators(id),
    trigger_value   NUMERIC      NOT NULL,   -- the actual value that crossed the threshold
    threshold       NUMERIC      NOT NULL,   -- snapshot of the rule's threshold at trigger time
    severity        TEXT         NOT NULL
                                 CHECK (severity IN ('info', 'warning', 'critical')),
    message         TEXT         NOT NULL,   -- human-readable alert message
    triggered_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,             -- NULL = still active
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_pa_country  ON pattern_alerts (country_id);
CREATE INDEX idx_pa_active   ON pattern_alerts (is_active, triggered_at DESC);


-- ============================================================
-- TABLE 10: ai_explanations
-- Stores Claude-generated explanations for indicator changes
-- or triggered alerts. One row per explanation generated.
-- Cached so the same explanation is not re-generated on every
-- page load.
-- ============================================================
CREATE TABLE ai_explanations (
    id                SERIAL       PRIMARY KEY,
    country_id        CHAR(3)      NOT NULL REFERENCES countries(id),
    indicator_id      INTEGER      REFERENCES indicators(id),    -- NULL if explaining an alert
    alert_id          BIGINT       REFERENCES pattern_alerts(id), -- NULL if explaining an indicator
    explanation_type  TEXT         NOT NULL
                                   CHECK (explanation_type IN (
                                       'indicator_change',
                                       'compound_alert',
                                       'country_summary'
                                   )),
    year              SMALLINT,
    quarter           SMALLINT     CHECK (quarter BETWEEN 1 AND 4),
    prompt_used       TEXT,                                       -- the prompt sent to Claude
    explanation_text  TEXT         NOT NULL,
    model_used        TEXT         NOT NULL DEFAULT 'claude-haiku-4-5',
    generated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ae_country   ON ai_explanations (country_id);
CREATE INDEX idx_ae_generated ON ai_explanations (generated_at DESC);
