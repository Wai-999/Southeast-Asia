-- ============================================================
-- Seed Data — Version 1
-- Run AFTER schema.sql
-- Populates: countries, indicators, event_categories, alert_rules
-- ============================================================


-- ============================================================
-- SEED: countries (14 total)
-- ============================================================
INSERT INTO countries (id, name, region, iso2, currency, capital, flag_emoji) VALUES
  -- ASEAN members
  ('MMR', 'Myanmar',     'ASEAN', 'MM', 'MMK', 'Naypyidaw',    '🇲🇲'),
  ('THA', 'Thailand',    'ASEAN', 'TH', 'THB', 'Bangkok',      '🇹🇭'),
  ('VNM', 'Vietnam',     'ASEAN', 'VN', 'VND', 'Hanoi',        '🇻🇳'),
  ('KHM', 'Cambodia',    'ASEAN', 'KH', 'KHR', 'Phnom Penh',   '🇰🇭'),
  ('LAO', 'Laos',        'ASEAN', 'LA', 'LAK', 'Vientiane',    '🇱🇦'),
  ('MYS', 'Malaysia',    'ASEAN', 'MY', 'MYR', 'Kuala Lumpur', '🇲🇾'),
  ('SGP', 'Singapore',   'ASEAN', 'SG', 'SGD', 'Singapore',    '🇸🇬'),
  ('IDN', 'Indonesia',   'ASEAN', 'ID', 'IDR', 'Jakarta',      '🇮🇩'),
  ('PHL', 'Philippines', 'ASEAN', 'PH', 'PHP', 'Manila',       '🇵🇭'),
  ('BRN', 'Brunei',      'ASEAN', 'BN', 'BND', 'Bandar Seri Begawan', '🇧🇳'),
  -- External partners
  ('CHN', 'China',         'External Partner', 'CN', 'CNY', 'Beijing',      '🇨🇳'),
  ('IND', 'India',         'External Partner', 'IN', 'INR', 'New Delhi',    '🇮🇳'),
  ('JPN', 'Japan',         'External Partner', 'JP', 'JPY', 'Tokyo',        '🇯🇵'),
  ('USA', 'United States', 'External Partner', 'US', 'USD', 'Washington DC','🇺🇸');


-- ============================================================
-- SEED: indicators (10 core indicators)
-- ============================================================
INSERT INTO indicators (code, name, description, unit, cadence, world_bank_code, imf_code, source_name, source_url) VALUES
  (
    'gdp_growth',
    'GDP Growth Rate',
    'Annual percentage growth rate of GDP at market prices based on constant local currency.',
    '%',
    'annual',
    'NY.GDP.MKTP.KD.ZG',
    'NGDP_RPCH',
    'World Bank',
    'https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.KD.ZG'
  ),
  (
    'inflation',
    'Inflation Rate (CPI)',
    'Annual change in Consumer Price Index, reflecting cost of living pressure.',
    '%',
    'annual',
    'FP.CPI.TOTL.ZG',
    'PCPIPCH',
    'World Bank',
    'https://api.worldbank.org/v2/indicator/FP.CPI.TOTL.ZG'
  ),
  (
    'unemployment',
    'Unemployment Rate',
    'Share of the labor force that is jobless, looking for a job, and available for work.',
    '%',
    'annual',
    'SL.UEM.TOTL.ZS',
    NULL,
    'World Bank / ILO',
    'https://api.worldbank.org/v2/indicator/SL.UEM.TOTL.ZS'
  ),
  (
    'trade_balance',
    'Trade Balance',
    'Value of exports minus imports of goods and services, in USD billions.',
    'USD_billions',
    'annual',
    'NE.EXP.GNFS.ZS',
    NULL,
    'World Bank / UN Comtrade',
    'https://api.worldbank.org/v2/indicator/NE.EXP.GNFS.ZS'
  ),
  (
    'fdi_inflows',
    'FDI Net Inflows',
    'Foreign direct investment net inflows in current USD millions.',
    'USD_millions',
    'annual',
    'BX.KLT.DINV.CD.WD',
    NULL,
    'World Bank / UNCTAD',
    'https://api.worldbank.org/v2/indicator/BX.KLT.DINV.CD.WD'
  ),
  (
    'exchange_rate',
    'Exchange Rate vs USD',
    'Official exchange rate — local currency units per one US dollar, period average.',
    'LCU_per_USD',
    'daily',
    'PA.NUS.FCRF',
    NULL,
    'ExchangeRate-API',
    'https://www.exchangerate-api.com'
  ),
  (
    'govt_debt',
    'Government Debt (% of GDP)',
    'Central government debt as a percentage of GDP.',
    '%_of_GDP',
    'annual',
    'GC.DOD.TOTL.GD.ZS',
    'GGXWDG_NGDP',
    'IMF / World Bank',
    'https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO'
  ),
  (
    'tourism_arrivals',
    'International Tourism Arrivals',
    'Number of international tourist arrivals, in thousands.',
    'arrivals_thousands',
    'annual',
    'ST.INT.ARVL',
    NULL,
    'World Bank / UNWTO',
    'https://api.worldbank.org/v2/indicator/ST.INT.ARVL'
  ),
  (
    'political_stability',
    'Political Stability Index',
    'World Bank Governance Indicator: likelihood of political instability or violence. Scale: -2.5 (worst) to +2.5 (best).',
    'index_score',
    'annual',
    NULL,
    NULL,
    'World Bank WGI',
    'https://info.worldbank.org/governance/wgi/'
  ),
  (
    'current_account',
    'Current Account Balance (% of GDP)',
    'Current account balance as a percentage of GDP. Negative = deficit (reliant on foreign capital).',
    '%_of_GDP',
    'annual',
    'BN.CAB.XOKA.GD.ZS',
    'BCA_NGDPD',
    'IMF / World Bank',
    'https://www.imf.org/external/datamapper/BCA_NGDPD@WEO'
  );


-- ============================================================
-- SEED: event_categories (5 types)
-- ============================================================
INSERT INTO event_categories (code, name, color_hex, icon_name) VALUES
  ('economy',   'Economy',            '#3182CE', 'trending-up'),
  ('politics',  'Politics',           '#805AD5', 'landmark'),
  ('trade',     'Trade & Investment', '#D69E2E', 'package'),
  ('security',  'Security & Conflict','#E53E3E', 'alert-triangle'),
  ('disaster',  'Natural Disaster',   '#DD6B20', 'cloud-lightning');


-- ============================================================
-- SEED: alert_rules (3 V1 hardcoded rules)
-- ============================================================
INSERT INTO alert_rules (indicator_id, name, description, condition, threshold, period, severity) VALUES
  (
    (SELECT id FROM indicators WHERE code = 'inflation'),
    'High Inflation Warning',
    'Fires when a country''s annual inflation rate exceeds 5%.',
    'above',
    5.0,
    'annual',
    'warning'
  ),
  (
    (SELECT id FROM indicators WHERE code = 'gdp_growth'),
    'Negative GDP Growth',
    'Fires when a country records negative GDP growth for the year — recession signal.',
    'below',
    0.0,
    'annual',
    'critical'
  ),
  (
    (SELECT id FROM indicators WHERE code = 'current_account'),
    'Current Account Vulnerability',
    'Fires when a country''s current account deficit exceeds 5% of GDP — external vulnerability signal.',
    'below',
    -5.0,
    'annual',
    'warning'
  );


-- ============================================================
-- EXAMPLE ROWS — indicator_values
-- A small sample to show the data shape. Real data is
-- fetched by the ingestion script (scripts/ingest.ts).
-- ============================================================
INSERT INTO indicator_values (country_id, indicator_id, year, quarter, month, value, source) VALUES
  -- GDP Growth (annual, no quarter/month)
  ('THA', (SELECT id FROM indicators WHERE code = 'gdp_growth'), 2024, NULL, NULL,  2.5,  'World Bank'),
  ('VNM', (SELECT id FROM indicators WHERE code = 'gdp_growth'), 2024, NULL, NULL,  7.1,  'World Bank'),
  ('MMR', (SELECT id FROM indicators WHERE code = 'gdp_growth'), 2024, NULL, NULL, -2.1,  'World Bank'),
  ('SGP', (SELECT id FROM indicators WHERE code = 'gdp_growth'), 2024, NULL, NULL,  3.6,  'World Bank'),
  ('IDN', (SELECT id FROM indicators WHERE code = 'gdp_growth'), 2024, NULL, NULL,  5.0,  'World Bank'),
  -- Inflation (annual)
  ('THA', (SELECT id FROM indicators WHERE code = 'inflation'),  2024, NULL, NULL,  1.0,  'World Bank'),
  ('VNM', (SELECT id FROM indicators WHERE code = 'inflation'),  2024, NULL, NULL,  3.6,  'World Bank'),
  ('LAO', (SELECT id FROM indicators WHERE code = 'inflation'),  2024, NULL, NULL, 21.1,  'World Bank'),  -- triggers alert
  ('MMR', (SELECT id FROM indicators WHERE code = 'inflation'),  2024, NULL, NULL, 26.8,  'World Bank'),  -- triggers alert
  -- Exchange Rate (daily — one sample row per country)
  ('THA', (SELECT id FROM indicators WHERE code = 'exchange_rate'), 2025, NULL, NULL, 34.85, 'ExchangeRate-API'),
  ('VNM', (SELECT id FROM indicators WHERE code = 'exchange_rate'), 2025, NULL, NULL, 25450, 'ExchangeRate-API'),
  ('MMR', (SELECT id FROM indicators WHERE code = 'exchange_rate'), 2025, NULL, NULL, 2098,  'ExchangeRate-API');


-- ============================================================
-- EXAMPLE ROWS — trade_flows
-- ============================================================
INSERT INTO trade_flows (reporter_id, partner_id, year, quarter, direction, value_usd_m, share_pct, source) VALUES
  ('VNM', 'CHN', 2024, NULL, 'import', 118000, 38.5, 'UN Comtrade'),
  ('VNM', 'USA', 2024, NULL, 'export',  98000, 28.7, 'UN Comtrade'),
  ('THA', 'CHN', 2024, NULL, 'import',  52000, 22.4, 'UN Comtrade'),
  ('THA', 'USA', 2024, NULL, 'export',  35000, 15.1, 'UN Comtrade'),
  ('SGP', 'CHN', 2024, NULL, 'export',  72000, 14.8, 'UN Comtrade'),
  ('IDN', 'CHN', 2024, NULL, 'export',  58000, 22.0, 'UN Comtrade');


-- ============================================================
-- EXAMPLE ROWS — news_events + impact_scores
-- ============================================================
INSERT INTO news_events (country_id, category_id, headline, summary, source_name, published_at, sentiment, sentiment_score)
VALUES
  (
    'LAO',
    (SELECT id FROM event_categories WHERE code = 'economy'),
    'Laos Faces Currency Crisis as Kip Hits Record Low Against Dollar',
    'The Lao kip has depreciated over 30% this year as public debt reaches critical levels and foreign reserves fall to under two months of import cover.',
    'Reuters',
    '2024-10-15 09:30:00+00',
    'negative',
    -0.82
  ),
  (
    'VNM',
    (SELECT id FROM event_categories WHERE code = 'trade'),
    'Vietnam Attracts $18bn in FDI in First Half of 2024, Samsung Leads',
    'Vietnam continued to draw foreign investment away from China, with electronics and semiconductor sectors driving a 13% year-over-year increase.',
    'Bloomberg',
    '2024-07-02 06:00:00+00',
    'positive',
    0.75
  ),
  (
    'MMR',
    (SELECT id FROM event_categories WHERE code = 'security'),
    'Myanmar Junta Loses Control of Key Trade Corridor to Resistance Forces',
    'Armed resistance groups have taken control of border crossings with China and Thailand, disrupting billions in annual cross-border trade.',
    'The Irrawaddy',
    '2024-11-20 11:00:00+00',
    'negative',
    -0.91
  );

-- Link news events to affected indicators via impact_scores
INSERT INTO impact_scores (news_event_id, country_id, indicator_id, impact_level, impact_direction, rationale)
VALUES
  -- Laos currency crisis → affects exchange_rate (5/critical) and current_account (4/negative)
  (1, 'LAO', (SELECT id FROM indicators WHERE code = 'exchange_rate'),   5, 'negative', 'Kip depreciation is the primary subject of the event.'),
  (1, 'LAO', (SELECT id FROM indicators WHERE code = 'current_account'), 4, 'negative', 'Reserve depletion indicates worsening external balance.'),
  -- Vietnam FDI news → affects fdi_inflows (5/positive) and gdp_growth (3/positive)
  (2, 'VNM', (SELECT id FROM indicators WHERE code = 'fdi_inflows'),     5, 'positive', 'FDI figure is directly cited in the headline.'),
  (2, 'VNM', (SELECT id FROM indicators WHERE code = 'gdp_growth'),      3, 'positive', 'High FDI is a leading indicator of future GDP expansion.'),
  -- Myanmar conflict → affects trade_balance (4/negative) and fdi_inflows (4/negative)
  (3, 'MMR', (SELECT id FROM indicators WHERE code = 'trade_balance'),   4, 'negative', 'Trade corridor disruption will reduce export and import volumes.'),
  (3, 'MMR', (SELECT id FROM indicators WHERE code = 'fdi_inflows'),     4, 'negative', 'Security instability deters foreign investment.');


-- ============================================================
-- EXAMPLE ROWS — pattern_alerts (triggered by alert engine)
-- ============================================================
INSERT INTO pattern_alerts (country_id, alert_rule_id, indicator_id, trigger_value, threshold, severity, message, is_active)
VALUES
  (
    'LAO',
    (SELECT id FROM alert_rules WHERE name = 'High Inflation Warning'),
    (SELECT id FROM indicators WHERE code = 'inflation'),
    21.1,
    5.0,
    'warning',
    'Laos: Inflation reached 21.1% in 2024 — threshold of 5% exceeded.',
    TRUE
  ),
  (
    'MMR',
    (SELECT id FROM alert_rules WHERE name = 'Negative GDP Growth'),
    (SELECT id FROM indicators WHERE code = 'gdp_growth'),
    -2.1,
    0.0,
    'critical',
    'Myanmar: GDP contracted -2.1% in 2024 — recession confirmed.',
    TRUE
  );


-- ============================================================
-- EXAMPLE ROWS — ai_explanations (cached Claude responses)
-- ============================================================
INSERT INTO ai_explanations (country_id, indicator_id, alert_id, explanation_type, year, quarter, explanation_text, model_used)
VALUES
  (
    'MMR',
    (SELECT id FROM indicators WHERE code = 'gdp_growth'),
    2,
    'indicator_change',
    2024,
    NULL,
    'Myanmar''s economy contracted by 2.1% in 2024, continuing a multi-year decline that began with the February 2021 military coup. The contraction reflects three compounding forces: ongoing armed conflict that has disrupted agriculture and cross-border trade routes; Western sanctions that cut off foreign investment and banking access; and currency collapse (the kyat has lost over 60% of its value since 2021) which has driven inflation above 25% and crushed domestic purchasing power. This is not a cyclical slowdown — it is a structural deterioration driven by political crisis.',
    'claude-haiku-4-5'
  ),
  (
    'VNM',
    (SELECT id FROM indicators WHERE code = 'fdi_inflows'),
    NULL,
    'indicator_change',
    2024,
    NULL,
    'Vietnam attracted approximately $18 billion in FDI in the first half of 2024, a 13% increase year-over-year and one of the strongest performances in Southeast Asia. This surge reflects Vietnam''s position as the primary beneficiary of the "China+1" diversification strategy — global manufacturers, particularly in electronics (Samsung, Intel, LG) and semiconductors, are relocating production capacity to Vietnam to reduce concentration risk in China. Vietnam''s young workforce, improving infrastructure, and preferential trade agreements (including EVFTA with the EU and CPTPP) make it structurally attractive for export-oriented FDI.',
    'claude-haiku-4-5'
  );
