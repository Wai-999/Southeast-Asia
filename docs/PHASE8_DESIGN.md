# Phase 8 Design — Quarterly & Monthly Data Integration

**Date:** 2026-06-02  
**Countries in scope:** Thailand (THA), Vietnam (VNM), Singapore (SGP), Indonesia (IDN), Malaysia (MYS)  
**Indicators in scope:** Quarterly GDP growth, monthly CPI, monthly exchange rate, monthly exports/imports, quarterly FDI  

---

## 1. Source List by Country

### Thailand
| Indicator | Primary Source | Authority | URL |
|-----------|---------------|-----------|-----|
| Quarterly GDP growth | NESDC (National Economic and Social Development Council) | Official national accounts | https://www.nesdc.go.th/ewt_w3c/main.php?filename=national_account |
| Monthly CPI / inflation | Ministry of Commerce → IMF IFS | Official CPI data | https://price.moc.go.th |
| Monthly exchange rate | Bank of Thailand (BOT) | Central bank | https://www.bot.or.th/en/financial-statistics/financial-markets/exchange-rate-statistics.html |
| Monthly exports / imports | Bank of Thailand (BOT) / Thai Customs | Official trade | https://www.bot.or.th/en/financial-statistics/trade-and-payment-statistics.html |
| Quarterly FDI | Bank of Thailand (BOT) — BOP data | Central bank | https://www.bot.or.th/en/financial-statistics/economic-and-financial-statistics/direct-investment.html |
| **IMF IFS fallback** | IMF International Financial Statistics | International agency | https://data.imf.org/?sk=4C514D48-B6BA-49ED-8AB9-52B0C1A0179B |

### Vietnam
| Indicator | Primary Source | Authority | URL |
|-----------|---------------|-----------|-----|
| Quarterly GDP growth | GSO (General Statistics Office) | Official national accounts | https://www.gso.gov.vn/en/ |
| Monthly CPI / inflation | GSO → IMF IFS | Official CPI | https://www.gso.gov.vn/en/ |
| Monthly exchange rate | State Bank of Vietnam (SBV) | Central bank | https://www.sbv.gov.vn |
| Monthly exports / imports | GSO / General Dept of Customs | Official trade | https://www.customs.gov.vn |
| Quarterly FDI | Ministry of Planning and Investment (MPI) | Official FDI registrations | https://mpi.gov.vn/en |
| **IMF IFS fallback** | IMF IFS | International agency | https://data.imf.org |

> **Note on Vietnam quarterly GDP:** GSO releases quarterly GDP estimates ~30–45 days after quarter end. The data is available as press releases and CSV on the GSO website but has **no public API**. Requires scheduled CSV download or web scraping.

### Singapore
| Indicator | Primary Source | Authority | URL |
|-----------|---------------|-----------|-----|
| Quarterly GDP growth | SingStat (Dept of Statistics Singapore) | Official national accounts | https://www.singstat.gov.sg/find-data/search-by-theme/economy/national-accounts/latest-data |
| Monthly CPI / inflation | SingStat → IMF IFS | Official CPI | https://www.singstat.gov.sg/find-data/search-by-theme/economy/prices-and-price-indices/latest-data |
| Monthly exchange rate | Monetary Authority of Singapore (MAS) | Central bank | https://eservices.mas.gov.sg/statistics/msb-xml/Report.aspx?tableSetID=I&tableID=I.1 |
| Monthly exports / imports | SingStat | Official trade | https://www.singstat.gov.sg/find-data/search-by-theme/trade/external-trade |
| Quarterly FDI | EDB / SingStat BOP | Official BOP | https://www.singstat.gov.sg/find-data/search-by-theme/trade/investment/latest-data |
| **SingStat API** | SingStat TableBuilder API | Official | https://tablebuilder.singstat.gov.sg/publicapi/resourceId |

> **Best API in Phase 8:** Singapore's SingStat TableBuilder REST API (no key required for most tables) is the most developer-friendly source in this set.

### Indonesia
| Indicator | Primary Source | Authority | URL |
|-----------|---------------|-----------|-----|
| Quarterly GDP growth | BPS (Badan Pusat Statistik) | Official national accounts | https://www.bps.go.id/en/statistics-table/2/MjE4IzI=/gross-domestic-product.html |
| Monthly CPI / inflation | BPS → IMF IFS | Official CPI | https://www.bps.go.id/en/statistics-table/2/NTgwIzI=/consumer-price-index.html |
| Monthly exchange rate | Bank Indonesia (BI) | Central bank | https://www.bi.go.id/en/statistik/informasi-kurs/transaksi-bi/Default.aspx |
| Monthly exports / imports | BPS | Official trade | https://www.bps.go.id/en/statistics-table/2/MTgzMyMy/value-of-exports.html |
| Quarterly FDI | BKPM / Bank Indonesia BOP | Investment board + central bank | https://bkpm.go.id/en/statistics |
| **BPS API** | BPS Web API | Official | https://webapi.bps.go.id/v1/ |

> **BPS API:** Requires a free API key (`keyToken`) from https://webapi.bps.go.id/. Key registration is open. Table IDs must be discovered via the BPS table browser. Most useful for CPI and trade series.

### Malaysia
| Indicator | Primary Source | Authority | URL |
|-----------|---------------|-----------|-----|
| Quarterly GDP growth | DOSM (Dept of Statistics Malaysia) | Official national accounts | https://www.dosm.gov.my/v2/dashboard/national-accounts |
| Monthly CPI / inflation | DOSM → IMF IFS | Official CPI | https://www.dosm.gov.my/v2/dashboard/consumer-price-index |
| Monthly exchange rate | Bank Negara Malaysia (BNM) | Central bank | https://www.bnm.gov.my/exchange-rates |
| Monthly exports / imports | DOSM | Official trade | https://www.dosm.gov.my/v2/dashboard/external-trade |
| Quarterly FDI | BNM (BOP data) | Central bank | https://www.bnm.gov.my/publications/mab |
| **DOSM OpenDOSM** | OpenDOSM platform | Official | https://open.dosm.gov.my |

> **Best regional source:** Malaysia's **OpenDOSM** platform (https://open.dosm.gov.my) launched in 2023 and offers machine-readable JSON/CSV downloads for many national series, including quarterly GDP and monthly CPI. No API key required.

---

## 2. Indicator Availability Table

A `✓` means real quarterly/monthly data is available from an official source. `⚠` means data exists but access is inconvenient (no API, manual CSV, or significant lag). `✗` means not available at quarterly/monthly frequency.

| Indicator | Frequency | THA | VNM | SGP | IDN | MYS | Notes |
|-----------|-----------|-----|-----|-----|-----|-----|-------|
| **GDP growth** | Quarterly | ✓ | ✓ | ✓ | ✓ | ✓ | All 5 publish official Q-GDP. Lag: 4–8 weeks |
| **CPI inflation** | Monthly | ✓ | ✓ | ✓ | ✓ | ✓ | All via IMF IFS. Lag: 3–4 weeks |
| **Exchange rate vs USD** | Monthly | ✓ | ✓ | ✓ | ✓ | ✓ | All via IMF IFS ENDA series. Lag: same month |
| **Exports (goods)** | Monthly | ✓ | ✓ | ✓ | ✓ | ✓ | All via IMF IFS TXG series. Lag: 4–6 weeks |
| **Imports (goods)** | Monthly | ✓ | ✓ | ✓ | ✓ | ✓ | All via IMF IFS TMG series. Lag: 4–6 weeks |
| **FDI inflows** | Quarterly | ⚠ | ⚠ | ✓ | ⚠ | ⚠ | SGP best; others: IMF BOP, annual more reliable |
| **FDI inflows** | Annual | ✓ | ✓ | ✓ | ✓ | ✓ | Already in worldbank_indicators.json |

### Quarterly GDP source detail

| Country | Release name | Lag after quarter end | API? |
|---------|-------------|----------------------|------|
| Thailand | NESDC QNA Flash Estimate | ~8 weeks | No — CSV download |
| Vietnam | GSO Quarterly GDP | ~4–6 weeks | No — CSV / press release |
| Singapore | MTI Advance GDP Estimate | ~4 weeks (advance); ~8 weeks (full) | Yes — SingStat API |
| Indonesia | BPS Quarterly GDP | ~8 weeks | Yes — BPS API |
| Malaysia | DOSM Quarterly GDP | ~5–6 weeks | Yes — OpenDOSM JSON |

### Quarterly FDI availability detail

| Country | Source | Quarterly available? | Gaps |
|---------|--------|---------------------|------|
| Thailand | BOT BOP table | Yes, via web/CSV | Revisions common |
| Vietnam | MPI press releases | Monthly registered FDI (not disbursed) | Not standard quarterly BOP |
| Singapore | SingStat BOP | Yes, via API | Best coverage |
| Indonesia | BKPM reports | Yes, but inconsistent | Some quarters missing |
| Malaysia | BNM BOP | Yes, via CSV | 1–2 quarter lag |
| **All (fallback)** | IMF IFS / BOP | Yes, via IFS API | 3–4 month lag |

**Recommendation:** For FDI, use IMF IFS BOP data as the primary source for consistency. National sources serve as supplemental real-time data only.

---

## 3. API / Download Methods

### 3A — IMF IFS REST API (Primary for monthly data)

**Base URL:** `http://dataservices.imf.org/REST/SDMX_JSON.svc/`  
**Auth:** None required.  
**Rate limit:** ~10 requests/min; use 1.5s delay between calls.

**Endpoint pattern:**
```
GET /CompactData/{dataset}/{frequency}.{country}.{indicator}?startPeriod={YYYY-MM}&endPeriod={YYYY-MM}
```

**Key parameters for Phase 8:**

| Series | Frequency code | Country codes | Indicator code | Unit |
|--------|---------------|---------------|----------------|------|
| CPI inflation (YoY%) | M (monthly) | TH, VN, SG, ID, MY | PCPI_PC_PP_PT | % |
| Exchange rate vs USD | M (monthly) | TH, VN, SG, ID, MY | ENDA_XDC_USD_RATE | LCU/USD |
| Exports of goods (FOB) | M (monthly) | TH, VN, SG, ID, MY | TXG_FOB_USD | USD millions |
| Imports of goods (CIF) | M (monthly) | TH, VN, SG, ID, MY | TMG_CIF_USD | USD millions |
| GDP volume index | Q (quarterly) | TH, VN, SG, ID, MY | NGDP_R_K_IX | Index |
| FDI inflows (BOP) | Q (quarterly) | TH, VN, SG, ID, MY | BF_KA_FI_D_T_USD | USD millions |

**Example call (Thailand monthly CPI, last 2 years):**
```
http://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/M.TH.PCPI_PC_PP_PT?startPeriod=2022-01&endPeriod=2024-12
```

**Parse path in JSON response:**
```python
data["CompactData"]["DataSet"]["Series"]["Obs"]  # list of {"@TIME_PERIOD": "2024-01", "@OBS_VALUE": "1.27"}
```

### 3B — SingStat TableBuilder API (Singapore only)

**Base URL:** `https://tablebuilder.singstat.gov.sg/publicapi/`  
**Auth:** None required.  
**Key table IDs:**

| Series | Table ID |
|--------|----------|
| Quarterly GDP at 2015 prices (% change) | 15002 |
| Monthly CPI (2019=100) | 17001 |
| Monthly non-oil domestic exports | 16001 |

**Example (GDP quarterly table):**
```
GET https://tablebuilder.singstat.gov.sg/publicapi/tableBuilder/15002?
    variableCode=&timeFilter=5Y&sortBy=period&sortOrder=desc
```

### 3C — OpenDOSM (Malaysia)

**Base URL:** `https://api.data.gov.my/data-catalogue/`  
**Auth:** None required.  
**Key datasets:**

| Series | Dataset ID |
|--------|-----------|
| Quarterly GDP (% change) | gdp_qoq |
| Monthly CPI | cpi_core |
| Monthly trade | trade_monthly |

**Example:**
```
GET https://api.data.gov.my/data-catalogue?id=gdp_qoq&limit=20&sort=-date
```

### 3D — BPS API (Indonesia)

**Base URL:** `https://webapi.bps.go.id/v1/api/`  
**Auth:** Requires free `key` parameter (register at webapi.bps.go.id)  
**Key variables:**

| Series | Table/Variable ID |
|--------|-----------------|
| Quarterly GDP growth (%) | var: 1975 |
| Monthly CPI (% change) | var: 1755 |
| Monthly exports (USD) | var: 1756 |

**Note:** Store BPS key as `BPS_API_KEY` in `.env`.

### 3E — FRED API (Supplemental)

**Base URL:** `https://api.stlouisfed.org/fred/series/observations`  
**Auth:** Free API key (`FRED_API_KEY` in `.env`).  
**Useful for:**  
- USD/THB, USD/VND, USD/SGD, USD/IDR, USD/MYR monthly exchange rates (cross-check with IMF)
- Cross-validation only — IMF IFS is preferred primary source for consistency

---

## 4. Data Model — `quarterly_values.json`

**Location:** `pipeline/data/processed/quarterly_values.json`  
**Frontend reads:** `frontend/data/quarterly-data.ts`

### Full schema

```json
{
  "_meta": {
    "generated": "2026-06-02T00:00:00Z",
    "version": "1",
    "phase": "8",
    "description": "Quarterly and monthly economic data for 5 SEA countries",
    "phase8_countries": ["THA", "VNM", "SGP", "IDN", "MYS"],
    "primary_source": "IMF_IFS",
    "supplemental_sources": ["SINGSTAT", "OPENDOSM", "BPS", "NESDC", "GSO"],
    "monthly_range": "2022-01 to 2024-12",
    "quarterly_range": "2022-Q1 to 2024-Q4",
    "quality_levels": {
      "official":     "Real data from official source, not revised",
      "preliminary":  "Flash/advance estimate — subject to revision",
      "interpolated": "Linearly interpolated between two official values. NOT real quarterly data.",
      "unavailable":  "No data available at this frequency. Value is null."
    },
    "important_note": "Quarterly GDP is NEVER interpolated from annual data. If quarterly GDP is unavailable for a country-period, value is null and availability is unavailable.",
    "total_monthly_records": 0,
    "total_quarterly_records": 0,
    "last_fetch_duration_s": 0
  },
  "countries": {
    "THA": {
      "name": "Thailand",
      "flag": "🇹🇭",
      "imf_code": "TH",
      "quarterly": {
        "gdp_growth_yoy_pct": {
          "label": "GDP Growth (% YoY)",
          "source": "NESDC",
          "source_url": "https://www.nesdc.go.th",
          "imf_series": "IFS/Q.TH.NGDP_R_K_IX",
          "unit": "percent_yoy",
          "frequency": "quarterly",
          "availability": "available",
          "values": [
            {
              "period": "2023-Q1",
              "value": 2.7,
              "quality": "official",
              "release_date": "2023-05-15"
            },
            {
              "period": "2023-Q2",
              "value": 1.8,
              "quality": "official",
              "release_date": "2023-08-21"
            }
          ],
          "latest_period": "2024-Q3",
          "last_updated": "2026-06-02"
        },
        "fdi_inflows_usd_mn": {
          "label": "FDI Inflows (USD million)",
          "source": "IMF_IFS_BOP",
          "source_url": "https://data.imf.org",
          "imf_series": "IFS/Q.TH.BF_KA_FI_D_T_USD",
          "unit": "usd_millions",
          "frequency": "quarterly",
          "availability": "partial",
          "values": [],
          "latest_period": "2024-Q2",
          "last_updated": "2026-06-02"
        }
      },
      "monthly": {
        "inflation_cpi_yoy_pct": {
          "label": "CPI Inflation (% YoY)",
          "source": "IMF_IFS",
          "source_url": "https://data.imf.org",
          "imf_series": "IFS/M.TH.PCPI_PC_PP_PT",
          "unit": "percent_yoy",
          "frequency": "monthly",
          "availability": "available",
          "values": [
            {
              "period": "2024-01",
              "value": 1.27,
              "quality": "official"
            }
          ],
          "latest_period": "2024-12",
          "last_updated": "2026-06-02"
        },
        "exchange_rate_usd": {
          "label": "Exchange Rate (THB per USD)",
          "source": "IMF_IFS",
          "imf_series": "IFS/M.TH.ENDA_XDC_USD_RATE",
          "unit": "lcu_per_usd",
          "frequency": "monthly",
          "availability": "available",
          "values": [],
          "latest_period": "2024-12",
          "last_updated": "2026-06-02"
        },
        "exports_usd_mn": {
          "label": "Exports of Goods FOB (USD million)",
          "source": "IMF_IFS",
          "imf_series": "IFS/M.TH.TXG_FOB_USD",
          "unit": "usd_millions",
          "frequency": "monthly",
          "availability": "available",
          "values": [],
          "latest_period": "2024-12",
          "last_updated": "2026-06-02"
        },
        "imports_usd_mn": {
          "label": "Imports of Goods CIF (USD million)",
          "source": "IMF_IFS",
          "imf_series": "IFS/M.TH.TMG_CIF_USD",
          "unit": "usd_millions",
          "frequency": "monthly",
          "availability": "available",
          "values": [],
          "latest_period": "2024-12",
          "last_updated": "2026-06-02"
        }
      }
    }
  }
}
```

### Value object fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `period` | string | ✓ | `"YYYY-Qn"` for quarterly, `"YYYY-MM"` for monthly |
| `value` | number \| null | ✓ | `null` when `quality` is `"unavailable"` |
| `quality` | string | ✓ | See quality levels table below |
| `release_date` | string | optional | `"YYYY-MM-DD"` when advance estimate released |
| `revision_flag` | boolean | optional | `true` if this value has been revised from a prior release |

### Quality level values

| Level | Meaning | Display in UI |
|-------|---------|---------------|
| `"official"` | Confirmed, finalized data from official source | — (no badge) |
| `"preliminary"` | Flash/advance estimate, subject to revision | 🔵 `Preliminary` chip |
| `"interpolated"` | Linearly interpolated between two known values | 🟡 `Estimated` chip + tooltip |
| `"unavailable"` | No data at this frequency. Value is `null`. | 🔴 `No data` placeholder |

---

## 5. Fallback Strategy

### Rule 1 — Quarterly GDP: never interpolate from annual

```
IF quarterly GDP source is unavailable:
    value = null
    quality = "unavailable"
    availability = "unavailable"
    # DO NOT divide annual GDP by 4, DO NOT linear-interpolate between annual points
```

**Rationale:** Quarterly GDP has genuine seasonality and economic variance. Dividing annual by 4 would be misleading for a dashboard claiming to show quarterly trends.

### Rule 2 — Monthly CPI: short gaps may be interpolated, labeled

```
IF monthly CPI missing for ≤ 2 consecutive months (e.g., data delay):
    interpolate linearly between surrounding official values
    quality = "interpolated"
    # Show "Estimated" chip in UI
ELSE (gap > 2 months):
    value = null
    quality = "unavailable"
```

**Rationale:** CPI typically has only publication delays, not true data gaps. A 1–2 month delay (e.g., for Vietnam or Indonesia) can be bridged with a linear estimate while the official number is awaited.

### Rule 3 — Exchange rate: interpolate freely, label clearly

```
IF monthly exchange rate missing for ≤ 1 month:
    interpolate (average of adjacent months)
    quality = "interpolated"
ELSE:
    value = null
    quality = "unavailable"
```

**Rationale:** Exchange rates are continuous. A single-month gap is almost certainly a publication gap, not a genuine missing value.

### Rule 4 — Monthly trade (exports/imports): no interpolation

```
IF monthly trade figure missing:
    value = null
    quality = "unavailable"
    # DO NOT interpolate — monthly trade is volatile and directionally meaningful
```

**Rationale:** Monthly trade swings ±15–30% around events (holidays, supply shocks, elections). Interpolation would mask exactly the signals the dashboard is designed to catch.

### Rule 5 — Quarterly FDI: use IMF IFS as fallback, annual as last resort

```
IF national source unavailable:
    → try IMF IFS BOP quarterly
IF IMF IFS also unavailable for that quarter:
    value = null
    quality = "unavailable"
    # DO NOT use annual FDI / 4 as quarterly estimate
```

### Fallback cascade

```
National stats office API/CSV
    → IMF IFS REST API
        → null + "unavailable" (never fabricate)
```

The World Bank (current `worldbank_indicators.json`) is **never** used as a quarterly fallback — it's annual only.

---

## 6. Warning Labels for Estimated / Interpolated Values

### Frontend label specs

| Condition | Badge label | Badge color | Tooltip text |
|-----------|------------|-------------|-------------|
| `quality === "preliminary"` | Preliminary | Blue (`bg-blue-100 text-blue-700`) | "Advance estimate released [date]. Subject to revision." |
| `quality === "interpolated"` | Estimated | Amber (`bg-amber-100 text-amber-700`) | "Linearly interpolated from surrounding official values. Not a measured data point." |
| `quality === "unavailable"` | No data | Red slate (`bg-slate-100 text-slate-500`) | "Quarterly data not available for this country. Annual data may be available in Overview." |
| `revision_flag === true` | Revised | Gray (`bg-gray-100 text-gray-600`) | "This value was revised from the initial release." |

### Chart-level annotations

When a chart series contains interpolated points:
- Render interpolated points as **open circles** or **dashed line segment** (not filled dot)
- Add footnote below chart: `"⚠ Estimated values (⊙) are interpolated from official data. Not directly measured."`

When a quarterly GDP chart has unavailable periods:
- Show gap in line chart (no line connecting across the gap)
- Show gray `—` placeholder in the data table
- Do NOT show "0" or carry forward last value

### Dashboard availability indicator (new component)

Each quarterly/monthly chart card should show a small source + availability footer:

```
Source: IMF IFS · Last updated: Nov 2024 · Coverage: 2022–2024
```

When data is partial:

```
Source: NESDC (via IMF IFS) · Coverage: Q1 2022–Q2 2024 · [2 gaps]
```

---

## Implementation Plan

### Phase 8A — IMF IFS fetcher (all 5 countries, monthly)
**New file:** `pipeline/fetch_imf_quarterly.py`  
**Output:** `pipeline/data/processed/quarterly_values.json`  
**What it fetches:** CPI, exchange rate, exports, imports via IMF IFS REST API (no key required)  
**Fallback:** Per Rule 1–4 above

### Phase 8B — National source fetchers (quarterly GDP)
**New files (one each):**
- `pipeline/fetch_singstat_gdp.py` — SingStat API, quarterly GDP
- `pipeline/fetch_opendosm_gdp.py` — OpenDOSM API, quarterly GDP  
- `pipeline/fetch_bps_gdp.py` — BPS API, quarterly GDP (requires `BPS_API_KEY`)
- `pipeline/fetch_nesdc_gdp.py` — NESDC CSV download + parse, quarterly GDP
- `pipeline/fetch_gso_gdp.py` — GSO CSV download + parse, quarterly GDP (Vietnam)

Or consolidated: `pipeline/fetch_national_gdp.py` with per-country handlers.

### Phase 8C — Frontend quarterly chart
**New file:** `frontend/data/quarterly-data.ts`  
**New component:** `frontend/components/charts/QuarterlyChart.tsx`  
**Updated page:** `frontend/app/country/[code]/page.tsx` — add quarterly section

### Phase 8D — integrate into run_pipeline.py
Add Step 5 (IMF quarterly) and Step 6 (national GDP) to `scripts/run_pipeline.py`.

---

## Environment Variables to Add to `.env.example`

```bash
# Phase 8 — Quarterly/Monthly Data
BPS_API_KEY=your_bps_api_key_here          # Indonesia BPS (free, register at webapi.bps.go.id)
FRED_API_KEY=your_fred_api_key_here        # St. Louis FRED (free, register at fred.stlouisfed.org)
# IMF IFS: no key required
# SingStat: no key required
# OpenDOSM: no key required
```

---

## Open Questions / Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| IMF IFS has gaps for Vietnam quarterly GDP | High — Vietnam's IFS coverage is inconsistent | Use GSO directly; mark unavailable if GSO fails |
| BPS API key not configured | Medium | Graceful fallback: fetch BPS via CSV scrape |
| NESDC CSV format changes | Low-medium | Pin to current download URL; add format version check |
| IMF IFS rate limiting | Low | 1.5s delay; retry with exponential backoff |
| OpenDOSM API in beta | Low | Verified stable as of 2024; pin API version |
| Vietnam FDI quarterly not standard BOP | Medium | Use MPI registered FDI as proxy; label as "registered, not disbursed" |

---

*Generated as part of Phase 8 design. Implementation starts with Phase 8A (fetch_imf_quarterly.py).*
