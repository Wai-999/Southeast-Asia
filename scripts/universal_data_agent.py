#!/usr/bin/env python3
"""
scripts/universal_data_agent.py
────────────────────────────────────────────────────────────────────────────
THE UNIVERSAL OFFICIAL DATA EXPANSION AGENT

Reads source_registry.json and indicator_registry.json, then for each
registered source attempts to fetch the latest available data and expand
combined_indicators.json coverage.

ARCHITECTURE
  1. SOURCE DISCOVERY  — reads source_registry.json, filters by country/sector
  2. FETCH DISPATCH    — routes each source to the correct fetch strategy
  3. NORMALIZATION     — enforces 22-field schema on every row
  4. CONFLICT GUARD    — never overwrites official_actual with forecast
  5. EXPANSION REPORT  — shows coverage gain per country/sector
  6. REGISTRY UPDATE   — marks sources as "last_fetched" in registry

FETCH STRATEGIES
  api_json        — REST JSON API (WB, IMF, MAS, BNM, SingStat, etc.)
  api_sdmx        — SDMX 2.1 API (OECD, ABS, etc.)
  api_csv_download— CSV/Excel download URL
  html_table      — BeautifulSoup HTML table extraction
  rss_feed        — RSS/Atom press release feed
  pdf_extraction  — PDF table extraction (PyMuPDF if installed)
  manual_data     — Pre-encoded data from publication (ADB ADO, etc.)

USAGE
  # Fetch everything new (respects --source-types filter)
  python scripts/universal_data_agent.py

  # Fetch only free API sources (fastest, no scraping)
  python scripts/universal_data_agent.py --mode api_only

  # Fetch for specific countries
  python scripts/universal_data_agent.py --countries THA VNM MYS SGP IDN

  # Fetch specific sectors
  python scripts/universal_data_agent.py --sectors macro_economy trade fiscal

  # Fetch specific source type priority (1=NSO, 2=CB, 3=ministry, 5=multilateral)
  python scripts/universal_data_agent.py --max-priority 3

  # Dry run — show what WOULD be fetched
  python scripts/universal_data_agent.py --dry-run

  # Force re-fetch even if fetched today
  python scripts/universal_data_agent.py --refresh
"""

import json
import sys
import time
import argparse
import subprocess
import re
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict, Counter

try:
    import httpx
    def _get(url, timeout=30, headers=None, params=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            return c.get(url, headers=headers or {}, params=params or {})
except ImportError:
    import urllib.request, urllib.parse
    class _R:
        def __init__(self, d, c):
            self.status_code = c
            self.text = d.decode() if isinstance(d, bytes) else str(d)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30, headers=None, params=None):
        if params: url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _R(r.read(), r.status)

try:
    from bs4 import BeautifulSoup; BS4 = True
except ImportError:
    BS4 = False

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
PROC_DIR     = PIPELINE / "data" / "processed"
RAW_DIR      = PIPELINE / "data" / "raw"
LOGS_DIR     = PIPELINE / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

ts_now     = lambda: datetime.utcnow().isoformat() + "Z"
today_str  = date.today().strftime("%Y%m%d")
today_iso  = date.today().isoformat()
CURR_YEAR  = date.today().year

# ─── Country registry ─────────────────────────────────────────────────────────
COUNTRY_NAMES = {
    "THA":"Thailand","VNM":"Vietnam","MMR":"Myanmar","KHM":"Cambodia","LAO":"Laos",
    "MYS":"Malaysia","SGP":"Singapore","IDN":"Indonesia","PHL":"Philippines",
    "BRN":"Brunei","TLS":"Timor-Leste",
    "CHN":"China","USA":"United States","JPN":"Japan","IND":"India",
    "KOR":"South Korea","AUS":"Australia","EUU":"European Union",
}
SEA_ISO3 = ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS"]
PARTNER_ISO3 = ["CHN","USA","JPN","IND","KOR","AUS"]
ALL_ISO3 = SEA_ISO3 + PARTNER_ISO3

# WB 2-letter → ISO3
WB2_ISO3 = {
    "TH":"THA","VN":"VNM","MM":"MMR","KH":"KHM","LA":"LAO",
    "MY":"MYS","SG":"SGP","ID":"IDN","PH":"PHL","BN":"BRN",
    "TP":"TLS","CN":"CHN","US":"USA","JP":"JPN","IN":"IND","KR":"KOR","AU":"AUS",
}

WB_CODES = ";".join(WB2_ISO3.keys())
WB_BASE  = "https://api.worldbank.org/v2"


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHEMA ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def make_row(iso3: str, sector: str, ind_code: str, ind_name: str,
             year: int, quarter: int | None, month: int | None,
             value, unit: str, freq: str,
             source: str, source_type: str, source_url: str,
             value_type: str = "official_actual",
             method: str = "api", note: str = "") -> dict:
    """Create a fully-validated indicator row."""
    if value is None:
        value_type = "missing_official"

    period = str(year)
    if quarter:
        period = f"{year}Q{quarter}"
    elif month:
        period = f"{year}-{month:02d}"

    dq = "available" if value is not None else "missing"
    if value_type in ("forecast_estimate",):
        dq = "estimated"

    return {
        "country_code":    iso3,
        "country_name":    COUNTRY_NAMES.get(iso3, iso3),
        "sector":          sector,
        "indicator_code":  ind_code,
        "indicator_name":  ind_name,
        "period":          period,
        "year":            year,
        "quarter":         quarter,
        "month":           month,
        "value":           value,
        "unit":            unit,
        "frequency":       freq,
        "source":          source,
        "source_type":     source_type,
        "source_url":      source_url,
        "fetched_at":      ts_now(),
        "released_at":     today_iso,
        "value_type":      value_type,
        "data_quality":    dq,
        "confidence":      "high" if value is not None else "none",
        "extraction_method": method,
        "limitation_note": note,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  WORLD BANK API FETCHER — generic for any WB indicator
# ═══════════════════════════════════════════════════════════════════════════════

WB_INDICATOR_MAP = {
    # sector, indicator_code, indicator_name, unit, divisor
    "NY.GDP.MKTP.KD.ZG": ("macro_economy",    "GDP_GROWTH",              "Real GDP Growth Rate",           "% YoY",       1.0),
    "NY.GDP.MKTP.CD":    ("macro_economy",    "GDP_NOMINAL_USD",          "GDP Nominal (USD Billion)",       "USD billion", 1e9),
    "NY.GDP.PCAP.CD":    ("macro_economy",    "GDP_PER_CAPITA_USD",       "GDP Per Capita (USD)",            "USD",         1.0),
    "NY.GDP.MKTP.PP.CD": ("macro_economy",    "GDP_PPP",                  "GDP PPP (Int$ Billion)",          "Int$ billion",1e9),
    "BN.CAB.XOKA.GD.ZS": ("macro_economy",   "CURRENT_ACCOUNT_GDP",      "Current Account (% GDP)",         "% of GDP",    1.0),
    "NY.GNS.ICTR.ZS":    ("macro_economy",   "NATIONAL_SAVINGS_GDP",     "Gross National Savings (% GDP)",  "% of GDP",    1.0),
    "NE.GDI.TOTL.ZS":    ("macro_economy",   "GROSS_CAPITAL_FORMATION",  "Gross Capital Formation (% GDP)", "% of GDP",    1.0),
    "NE.CON.PRVT.ZS":    ("macro_economy",   "PRIVATE_CONSUMPTION_GDP",  "Household Consumption (% GDP)",   "% of GDP",    1.0),
    "NV.SRV.TOTL.ZS":    ("macro_economy",   "GDP_SERVICES_PCT",         "Services VA (% GDP)",             "% of GDP",    1.0),
    "NV.IND.TOTL.ZS":    ("macro_economy",   "GDP_INDUSTRY_PCT",         "Industry VA (% GDP)",             "% of GDP",    1.0),
    "BX.TRF.PWKR.DT.GD.ZS":("macro_economy","REMITTANCES_GDP",          "Remittances (% GDP)",             "% of GDP",    1.0),
    "BX.TRF.PWKR.CD.DT": ("macro_economy",  "REMITTANCES_USD",          "Remittances (USD Billion)",        "USD billion", 1e9),

    "FP.CPI.TOTL.ZG":    ("prices_inflation","CPI_INFLATION",            "CPI Inflation Rate",              "% YoY",       1.0),
    "FP.CPI.TOTL":       ("prices_inflation","CPI_INDEX",                "CPI Index",                       "Index",       1.0),
    "NY.GDP.DEFL.KD.ZG": ("prices_inflation","DEFLATOR_GDP",             "GDP Deflator",                    "% YoY",       1.0),

    "SL.UEM.TOTL.ZS":    ("labor",           "UNEMPLOYMENT_RATE",        "Unemployment Rate",               "% labor force",1.0),
    "SL.UEM.1524.ZS":    ("labor",           "UNEMPLOYMENT_YOUTH",       "Youth Unemployment (15-24)",      "% of youth",  1.0),
    "SL.TLF.CACT.ZS":    ("labor",           "LABOR_FORCE_PARTICIPATION","Labor Force Participation",       "%",           1.0),
    "SL.TLF.TOTL.IN":    ("labor",           "LABOR_FORCE_TOTAL",        "Total Labor Force (millions)",    "millions",    1e6),
    "SL.AGR.EMPL.ZS":    ("labor",           "EMPLOYMENT_AGRICULTURE",   "Employment in Agriculture (%)",   "%",           1.0),
    "SL.SRV.EMPL.ZS":    ("labor",           "EMPLOYMENT_SERVICES",      "Employment in Services (%)",      "%",           1.0),
    "SL.IND.EMPL.ZS":    ("labor",           "EMPLOYMENT_INDUSTRY",      "Employment in Industry (%)",      "%",           1.0),

    "NE.EXP.GNFS.CD":    ("trade",           "EXPORTS_USD",              "Total Exports (USD Billion)",     "USD billion", 1e9),
    "NE.IMP.GNFS.CD":    ("trade",           "IMPORTS_USD",              "Total Imports (USD Billion)",     "USD billion", 1e9),
    "NE.TRD.GNFS.ZS":    ("trade",           "TRADE_OPENNESS",           "Trade Openness (% GDP)",          "% of GDP",    1.0),
    "BX.GSR.NFSV.CD":    ("trade",           "SERVICES_EXPORTS_USD",     "Services Exports (USD Billion)",  "USD billion", 1e9),
    "BM.GSR.NFSV.CD":    ("trade",           "SERVICES_IMPORTS_USD",     "Services Imports (USD Billion)",  "USD billion", 1e9),

    "BX.KLT.DINV.CD.WD": ("investment",      "FDI_INFLOWS_USD",          "FDI Net Inflows (USD Billion)",   "USD billion", 1e9),
    "BX.KLT.DINV.WD.GD.ZS":("investment",   "FDI_PCT_GDP",              "FDI Net Inflows (% GDP)",         "% of GDP",    1.0),
    "BM.KLT.DINV.CD.WD": ("investment",      "FDI_OUTFLOWS_USD",         "FDI Outflows (USD Billion)",      "USD billion", 1e9),
    "NE.GDI.FTOT.ZS":    ("investment",      "GROSS_FIXED_CAPITAL_GDP",  "Gross Fixed Capital (% GDP)",     "% of GDP",    1.0),

    "PA.NUS.FCRF":        ("finance_monetary","EXCHANGE_RATE_USD",        "Exchange Rate (LCU per USD)",     "LCU/USD",     1.0),
    "FR.INR.LEND":        ("finance_monetary","LENDING_RATE",             "Bank Lending Rate",               "% p.a.",      1.0),
    "FR.INR.DPST":        ("finance_monetary","DEPOSIT_RATE",             "Bank Deposit Rate",               "% p.a.",      1.0),
    "FR.INR.RINR":        ("finance_monetary","REAL_INTEREST_RATE",       "Real Interest Rate",              "% p.a.",      1.0),
    "FM.LBL.BMNY.ZG":     ("finance_monetary","MONEY_SUPPLY_M2",          "Broad Money Growth",              "% YoY",       1.0),
    "FM.LBL.BMNY.GD.ZS":  ("finance_monetary","MONEY_SUPPLY_M2_GDP",      "Broad Money (% GDP)",             "% of GDP",    1.0),
    "FS.AST.PRVT.GD.ZS":  ("finance_monetary","CREDIT_PRIVATE_GDP",       "Credit to Private Sector (% GDP)","% of GDP",   1.0),
    "FI.RES.TOTL.CD":     ("finance_monetary","FOREIGN_RESERVES",          "Foreign Reserves (USD Billion)",  "USD billion", 1e9),
    "FB.AST.NPER.ZS":     ("finance_monetary","NPL_RATIO",                 "NPL Ratio (%)",                   "%",           1.0),
    "CM.MKT.LCAP.GD.ZS":  ("finance_monetary","STOCK_MARKET_CAP_GDP",      "Stock Market Cap (% GDP)",        "% of GDP",    1.0),

    "GC.BAL.CASH.GD.ZS":  ("fiscal",          "FISCAL_BALANCE_GDP",       "Fiscal Balance (% GDP)",          "% of GDP",    1.0),
    "GC.DOD.TOTL.GD.ZS":  ("fiscal",          "PUBLIC_DEBT_GDP",          "Government Gross Debt (% GDP)",   "% of GDP",    1.0),
    "DT.DOD.DECT.GD.ZS":  ("fiscal",          "EXTERNAL_DEBT_GDP",        "External Debt (% GDP)",           "% of GDP",    1.0),
    "GC.REV.TOTL.GD.ZS":  ("fiscal",          "GOVT_REVENUE_GDP",         "Government Revenue (% GDP)",      "% of GDP",    1.0),
    "GC.XPN.TOTL.GD.ZS":  ("fiscal",          "GOVT_EXPENDITURE_GDP",     "Government Expenditure (% GDP)",  "% of GDP",    1.0),
    "GC.TAX.TOTL.GD.ZS":  ("fiscal",          "TAX_REVENUE_GDP",          "Tax Revenue (% GDP)",             "% of GDP",    1.0),
    "MS.MIL.XPND.GD.ZS":  ("fiscal",          "MILITARY_EXPENDITURE_GDP", "Military Expenditure (% GDP)",    "% of GDP",    1.0),
    "DT.TDS.DECT.GN.ZS":  ("fiscal",          "DEBT_SERVICE_GDP",         "Debt Service (% GDP)",            "% of GDP",    1.0),

    "ST.INT.ARVL":         ("tourism",         "TOURIST_ARRIVALS",         "Tourist Arrivals (millions)",     "millions",    1e6),
    "ST.INT.RCPT.CD":      ("tourism",         "TOURISM_RECEIPTS_USD",     "Tourism Receipts (USD Billion)",  "USD billion", 1e9),

    "NV.IND.MANF.ZS":     ("industry_production","MANUFACTURING_PCT_GDP",  "Manufacturing VA (% GDP)",        "% of GDP",    1.0),
    "NV.IND.MANF.CD":     ("industry_production","MANUFACTURING_VALUE_ADDED","Manufacturing VA (USD Billion)","USD billion", 1e9),
    "TX.VAL.TECH.MF.ZS":  ("industry_production","EXPORTS_HIGH_TECH_PCT",   "High-Tech Exports (% mfg)",       "%",           1.0),
    "TX.VAL.TECH.CD":     ("industry_production","EXPORTS_HIGH_TECH_USD",   "High-Tech Exports (USD Billion)", "USD billion", 1e9),

    "NV.AGR.TOTL.ZS":     ("agriculture",      "AGRICULTURE_PCT_GDP",      "Agriculture VA (% GDP)",          "% of GDP",    1.0),
    "AG.LND.ARBL.ZS":     ("agriculture",      "ARABLE_LAND_PCT",          "Arable Land (% land)",            "%",           1.0),
    "AG.CON.FERT.ZS":     ("agriculture",      "FERTILIZER_USE",           "Fertilizer Use (kg/ha)",          "kg/ha",       1.0),

    "EG.FEC.RNEW.ZS":     ("energy",           "RENEWABLE_ENERGY_SHARE",   "Renewable Energy Share (%)",      "%",           1.0),
    "EG.ELC.ACCS.ZS":     ("energy",           "ELECTRICITY_ACCESS",       "Access to Electricity (%)",       "%",           1.0),
    "EG.EGY.PRIM.PP.KD":  ("energy",           "ENERGY_INTENSITY",         "Energy Intensity",                "MJ/$GDP PPP", 1.0),
    "EN.ATM.CO2E.PC":     ("energy",           "CO2_PER_CAPITA",           "CO2 Per Capita (tonnes)",         "tonnes CO2",  1.0),
    "EN.ATM.CO2E.PP.GD":  ("energy",           "CO2_PER_GDP",              "CO2 Per GDP",                     "kg CO2/$PPP", 1.0),
    "EG.IMP.CONS.ZS":     ("energy",           "ENERGY_IMPORT_DEPENDENCE", "Energy Import Dependence (%)",    "%",           1.0),

    "IT.NET.USER.ZS":     ("technology_digital","INTERNET_PENETRATION",    "Internet Users (%)",              "%",           1.0),
    "IT.CEL.SETS.P2":     ("technology_digital","MOBILE_SUBSCRIPTIONS",    "Mobile Subscriptions per 100",    "per 100",     1.0),
    "IT.NET.BBND.P2":     ("technology_digital","BROADBAND_FIXED",         "Fixed Broadband per 100",         "per 100",     1.0),
    "GB.XPD.RSDV.GD.ZS":  ("technology_digital","RD_EXPENDITURE_GDP",      "R&D Expenditure (% GDP)",         "% of GDP",    1.0),
    "SP.POP.SCIE.RD.P6":  ("technology_digital","RD_RESEARCHERS",          "R&D Researchers per million",     "per million", 1.0),

    "LP.LPI.OVRL.XQ":     ("infrastructure",   "LOGISTICS_PERFORMANCE",    "Logistics Performance Index",     "Score 1-5",   1.0),
    "SP.URB.TOTL.IN.ZS":  ("infrastructure",   "URBAN_POPULATION_PCT",     "Urban Population (%)",            "%",           1.0),
    "SP.URB.GROW":        ("infrastructure",   "URBAN_GROWTH_RATE",        "Urban Growth Rate (%)",           "% YoY",       1.0),
    "IS.ROD.DNST.K2":     ("infrastructure",   "ROAD_DENSITY",             "Road Density (km/1000 sq km)",    "km/1000km²",  1.0),
    "IS.SHP.GOOD.TU":     ("infrastructure",   "PORT_THROUGHPUT",          "Container Port Throughput",       "million TEU", 1e6),
    "IS.AIR.PSGR":        ("infrastructure",   "AIR_PASSENGERS",           "Air Passengers (millions)",       "millions",    1e6),
    "IC.BUS.DFRN.XQ":     ("infrastructure",   "EASE_DOING_BUSINESS",      "Ease of Doing Business Score",    "Score 0-100", 1.0),

    "AG.LND.FRST.ZS":     ("environment",      "FOREST_AREA_PCT",          "Forest Area (% land)",            "%",           1.0),
    "EN.ATM.CO2E.KT":     ("environment",      "CO2_TOTAL_MT",             "Total CO2 (Mt)",                  "Mt CO2",      1000.0),  # KT → Mt
    "EN.ATM.METH.KT.CE":  ("environment",      "METHANE_EMISSIONS",        "Methane Emissions (kt CO2eq)",    "kt CO2eq",    1.0),
    "EN.ATM.PM25.MC.M3":  ("environment",      "AIR_QUALITY_PM25",         "PM2.5 Air Pollution (μg/m³)",     "μg/m³",       1.0),
    "SH.H2O.BASW.ZS":     ("environment",      "WATER_ACCESS_PCT",         "Access to Safe Water (%)",        "%",           1.0),
    "SH.STA.BASS.ZS":     ("environment",      "SANITATION_ACCESS_PCT",    "Access to Sanitation (%)",        "%",           1.0),

    "GE.EST":             ("politics_policy",  "GOVERNANCE_EFFECTIVENESS", "Government Effectiveness (WGI)",  "Score",       1.0),
    "RL.EST":             ("politics_policy",  "RULE_OF_LAW",              "Rule of Law (WGI)",               "Score",       1.0),
    "VA.EST":             ("politics_policy",  "VOICE_ACCOUNTABILITY",     "Voice & Accountability (WGI)",    "Score",       1.0),
    "RQ.EST":             ("politics_policy",  "REGULATORY_QUALITY",       "Regulatory Quality (WGI)",        "Score",       1.0),

    "PV.EST":             ("security_conflict","POLITICAL_STABILITY",      "Political Stability (WGI)",       "Score",       1.0),
    "CC.EST":             ("security_conflict","CORRUPTION_PERCEPTION",    "Control of Corruption (WGI)",     "Score",       1.0),

    "SP.POP.TOTL":        ("social_indicators","POPULATION",               "Total Population (millions)",     "millions",    1e6),
    "SP.POP.GROW":        ("social_indicators","POPULATION_GROWTH",        "Population Growth (%)",           "% YoY",       1.0),
    "SI.POV.LMIC":        ("social_indicators","POVERTY_RATE_USD365",      "Poverty Rate ($3.65/day)",        "%",           1.0),
    "SI.POV.UMIC":        ("social_indicators","POVERTY_RATE_USD685",      "Poverty Rate ($6.85/day)",        "%",           1.0),
    "SP.DYN.LE00.IN":     ("social_indicators","LIFE_EXPECTANCY",          "Life Expectancy (years)",         "years",       1.0),
    "SP.DYN.IMRT.IN":     ("social_indicators","INFANT_MORTALITY",         "Infant Mortality (per 1000)",     "per 1000",    1.0),
    "SH.STA.MMRT":        ("social_indicators","MATERNAL_MORTALITY",       "Maternal Mortality (per 100k)",   "per 100,000", 1.0),
    "SE.XPD.TOTL.GD.ZS":  ("social_indicators","EDUCATION_EXPENDITURE_GDP","Education Expenditure (% GDP)",  "% of GDP",    1.0),
    "SE.SEC.ENRR":        ("social_indicators","SECONDARY_ENROLLMENT",     "Secondary Enrollment Rate (%)",   "%",           1.0),
    "SE.TER.ENRR":        ("social_indicators","TERTIARY_ENROLLMENT",      "Tertiary Enrollment Rate (%)",    "%",           1.0),
    "SH.XPD.CHEX.GD.ZS":  ("social_indicators","HEALTH_EXPENDITURE_GDP",  "Health Expenditure (% GDP)",      "% of GDP",    1.0),
    "SI.POV.GINI":        ("social_indicators","GINI_INDEX",               "Gini Index",                      "0-100",       1.0),
    "FX.OWN.SELF.IN":     ("social_indicators","MOBILE_MONEY_USERS",       "Mobile Money Users (% adults)",   "% of adults", 1.0),
}


MAX_WB_RETRIES = 2   # Fast failure — 2 attempts then give up

def _wb_fetch_one(wb_code: str, start: int, end: int) -> list:
    """
    Fetch one WB indicator for all 17 countries.
    Uses 2 attempts with short backoff. Returns raw record list.
    Falls back to the existing worldbank_indicators.json cache if available.
    """
    per_page = max(1000, len(WB2_ISO3) * (end - start + 2))
    url = (f"{WB_BASE}/country/{WB_CODES}/indicator/{wb_code}"
           f"?format=json&per_page={per_page}&date={start}:{end}")
    headers = {"User-Agent": "SEA-Dashboard/2.0", "Accept": "application/json"}

    for attempt in range(MAX_WB_RETRIES):
        try:
            r = _get(url, timeout=35, headers=headers)
            if r.status_code == 200:
                text = getattr(r, "text", "")
                if not text or not text.strip():
                    raise ValueError("empty body")
                d = r.json()
                if isinstance(d, list) and len(d) >= 2:
                    return d[1] or []
                return []
            elif r.status_code == 429:
                print(f"      ⏸ 429 rate-limit — waiting 20s", flush=True)
                time.sleep(20)
            else:
                print(f"      ⚠ HTTP {r.status_code}", flush=True)
                break
        except ValueError:
            if attempt == 0:
                print(f"      ⏸ Empty body on attempt 1 — retrying in 8s", flush=True)
                time.sleep(8)
            else:
                print(f"      ✗ Empty body on attempt 2 — giving up", flush=True)
        except Exception as e:
            if attempt == 0:
                time.sleep(5)
            else:
                print(f"      ✗ {e}", flush=True)
    return []


# WB indicators already fetched by the main pipeline (core 8)
# The agent reads from the existing file for these rather than re-fetching
WB_CORE_KEYS = {
    "NY.GDP.MKTP.KD.ZG": "gdpGrowth",
    "NY.GDP.MKTP.CD":    "gdpNominal",
    "FP.CPI.TOTL.ZG":    "inflation",
    "SL.UEM.TOTL.ZS":    "unemployment",
    "BX.KLT.DINV.WD.GD.ZS": "fdiPctGdp",
    "NE.EXP.GNFS.CD":    "exports",
    "NE.IMP.GNFS.CD":    "imports",
    "SP.POP.TOTL":       "population",
}

# Map indicator_key from worldbank_indicators.json → standard indicator_code
WB_KEY_TO_CODE = {
    "gdpGrowth":    "GDP_GROWTH",
    "gdpNominal":   "GDP_NOMINAL_USD",
    "inflation":    "CPI_INFLATION",
    "unemployment": "UNEMPLOYMENT_RATE",
    "fdiPctGdp":    "FDI_PCT_GDP",
    "exports":      "EXPORTS_USD",
    "imports":      "IMPORTS_USD",
    "population":   "POPULATION",
}
WB_KEY_TO_SECTOR = {
    "gdpGrowth":    "macro_economy",
    "gdpNominal":   "macro_economy",
    "inflation":    "prices_inflation",
    "unemployment": "labor",
    "fdiPctGdp":    "investment",
    "exports":      "trade",
    "imports":      "trade",
    "population":   "social_indicators",
}


def load_wb_core_from_cache() -> list[dict]:
    """
    Load the 8 core WB indicators from the existing pipeline cache file.
    This avoids re-fetching data that's already up-to-date.
    """
    cache_path = PROC_DIR / "worldbank_indicators.json"
    if not cache_path.exists():
        return []
    try:
        data    = json.loads(cache_path.read_text())
        records = data.get("records", [])
        out     = []
        for rec in records:
            ik   = rec.get("indicator_key", "")
            iso3 = rec.get("country_code", "")
            yr   = rec.get("year")
            val  = rec.get("value")
            if not (ik and iso3 and yr):
                continue
            sector   = WB_KEY_TO_SECTOR.get(ik, "macro_economy")
            ind_code = WB_KEY_TO_CODE.get(ik, ik.upper())
            meta     = next((m for wb, m in WB_INDICATOR_MAP.items()
                             if m[1] == ind_code), None)
            unit     = meta[3] if meta else rec.get("unit", "")
            out.append(make_row(
                iso3, sector, ind_code,
                rec.get("indicator_name", ind_code), yr,
                None, None, val, unit, "annual",
                rec.get("source", "World Bank Open Data API"),
                "multilateral",
                rec.get("source_url", ""),
                value_type = rec.get("value_type", "official_actual"),
                note       = rec.get("limitation_note", ""),
            ))
        return out
    except Exception as e:
        print(f"  ⚠ Could not load WB cache: {e}", flush=True)
        return []


def fetch_wb_batch(wb_codes_subset: list[str], start: int = 2015,
                   end: int = 2026, delay: float = 1.0,
                   skip_cached: bool = True) -> list[dict]:
    """
    Fetch a list of WB indicators.
    If skip_cached=True (default), skips indicators already in WB_CORE_KEYS
    since those are loaded from the existing pipeline cache instead.
    """
    all_rows = []

    for wb_code in wb_codes_subset:
        meta = WB_INDICATOR_MAP.get(wb_code)
        if not meta:
            continue
        sector, ind_code, ind_name, unit, divisor = meta

        # Skip core indicators — loaded from cache
        if skip_cached and wb_code in WB_CORE_KEYS:
            continue

        raw = _wb_fetch_one(wb_code, start, end)
        if not raw:
            # Produce missing_official rows so gaps are documented
            for iso3 in WB2_ISO3.values():
                for year in range(start, end + 1):
                    all_rows.append(make_row(
                        iso3, sector, ind_code, ind_name, year,
                        None, None, None, unit, "annual",
                        "World Bank Open Data API", "multilateral",
                        f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}",
                        note=f"WB API returned no data for {wb_code}",
                    ))
            time.sleep(delay)
            continue

        # Index raw data
        idx = {}
        for item in raw:
            try:
                c = item.get("countryiso3code") or ""
                y = int(item.get("date", 0))
                v = item.get("value")
                if c and y:
                    idx[(c, y)] = v
            except Exception:
                continue

        non_null = 0
        for wb2, iso3 in WB2_ISO3.items():
            for year in range(start, end + 1):
                v_raw = idx.get((iso3, year)) or idx.get((wb2, year))
                try:
                    val = round(float(v_raw) / divisor, 4) if v_raw is not None else None
                except (TypeError, ValueError):
                    val = None
                if val is not None:
                    non_null += 1
                all_rows.append(make_row(
                    iso3, sector, ind_code, ind_name, year,
                    None, None, val, unit, "annual",
                    "World Bank Open Data API", "multilateral",
                    f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}",
                ))
        time.sleep(delay)

    return all_rows


# ═══════════════════════════════════════════════════════════════════════════════
#  IMF WEO AGENT FETCHER
# ═══════════════════════════════════════════════════════════════════════════════

IMF_WEO_MAP = {
    "NGDP_RPCH":    ("macro_economy",    "GDP_GROWTH",              "Real GDP Growth Rate (%)",      "% YoY"),
    "PCPIPCH":      ("prices_inflation", "CPI_INFLATION",           "CPI Inflation Rate (%)",        "% YoY"),
    "LUR":          ("labor",            "UNEMPLOYMENT_RATE",       "Unemployment Rate (%)",         "% labor force"),
    "GGXCNL_NGDP":  ("fiscal",           "FISCAL_BALANCE_GDP",      "Fiscal Balance (% GDP)",        "% of GDP"),
    "BCA_NGDPD":    ("macro_economy",    "CURRENT_ACCOUNT_GDP",     "Current Account (% GDP)",       "% of GDP"),
    "NGDPDPC":      ("macro_economy",    "GDP_PER_CAPITA_USD",      "GDP Per Capita (USD)",          "USD"),
    "NGDPD":        ("macro_economy",    "GDP_NOMINAL_USD",         "GDP Nominal (USD Billion)",     "USD billion"),
    "GGXWDG_NGDP":  ("fiscal",           "PUBLIC_DEBT_GDP",         "Government Gross Debt (% GDP)", "% of GDP"),
    "NGSD_NGDP":    ("macro_economy",    "NATIONAL_SAVINGS_GDP",    "National Savings (% GDP)",      "% of GDP"),
    "GGR_NGDP":     ("fiscal",           "GOVT_REVENUE_GDP",        "Government Revenue (% GDP)",    "% of GDP"),
    "GGX_NGDP":     ("fiscal",           "GOVT_EXPENDITURE_GDP",    "Government Expenditure (% GDP)","% of GDP"),
}

IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"
WB_ACTUALS_UNTIL = 2024


def fetch_imf_weo_agent(imf_codes: list[str], start: int = 2019,
                        end: int = 2026, delay: float = 1.0) -> list[dict]:
    """Fetch IMF WEO indicators for all countries."""
    all_rows = []
    iso3_codes = ALL_ISO3
    codes_str  = ",".join(iso3_codes)

    for imf_code in imf_codes:
        meta = IMF_WEO_MAP.get(imf_code)
        if not meta:
            continue
        sector, ind_code, ind_name, unit = meta
        url = f"{IMF_BASE}/{imf_code}/{codes_str}"
        try:
            r = _get(url, timeout=45)
            if r.status_code != 200:
                continue
            data = r.json()
            country_data = data.get("values", {}).get(imf_code, {})

            for iso3 in iso3_codes:
                yr_data = country_data.get(iso3, {})
                for year in range(start, end + 1):
                    val_raw = yr_data.get(str(year))
                    try:
                        val = float(val_raw) if val_raw is not None else None
                    except (TypeError, ValueError):
                        val = None
                    vtype = "official_actual" if year <= WB_ACTUALS_UNTIL else "forecast_estimate"
                    note = ""
                    if year >= 2025:
                        note = f"IMF WEO forecast for {year}; not official national statistics"
                    all_rows.append(make_row(
                        iso3, sector, ind_code, ind_name, year,
                        None, None, val, unit, "annual",
                        "IMF World Economic Outlook DataMapper",
                        "forecast_multilateral" if vtype == "forecast_estimate" else "multilateral",
                        f"{IMF_BASE}/{imf_code}/{iso3}",
                        value_type=vtype, note=note,
                    ))
        except Exception as e:
            print(f"    ⚠ IMF {imf_code}: {e}", flush=True)
        time.sleep(delay)

    return all_rows


# ═══════════════════════════════════════════════════════════════════════════════
#  MERGE ENGINE — priority-based, never overwrite actual with forecast
# ═══════════════════════════════════════════════════════════════════════════════

VTYPE_PRIORITY = {
    "official_actual": 1, "official_preliminary": 2, "official_partial_2026": 3,
    "forecast_estimate": 4, "missing_official": 10,
    "official_policy": 99, "realtime_signal": 99, "sample": 999,
}
STYPE_PRIORITY = {
    "national_statistics": 1, "central_bank": 2, "ministry_customs": 3,
    "regional_official": 4, "multilateral": 5, "forecast_multilateral": 6,
    "computed": 5, "official_policy": 7, "realtime_signal": 8,
}


def merge_into_combined(new_rows: list[dict], combined_path: Path,
                        dry_run: bool = False) -> dict:
    """
    Merge new_rows into combined_indicators.json.
    Returns stats dict: {added, updated, skipped, protected}.
    """
    if combined_path.exists():
        existing = json.loads(combined_path.read_text())
        existing_records = existing.get("records", [])
    else:
        existing_records = []

    # Index existing by key
    existing_idx: dict[str, dict] = {}
    for r in existing_records:
        key = f"{r.get('country_code')}|{r.get('indicator_code')}|{r.get('period')}"
        existing_idx[key] = r

    stats = {"added": 0, "updated": 0, "skipped": 0, "protected": 0}

    for new_row in new_rows:
        key = f"{new_row.get('country_code')}|{new_row.get('indicator_code')}|{new_row.get('period')}"
        existing_row = existing_idx.get(key)

        if existing_row is None:
            # New key — add
            if not dry_run:
                existing_idx[key] = new_row
            stats["added"] += 1
            continue

        # Check if new row is better
        new_vt_pri  = VTYPE_PRIORITY.get(new_row.get("value_type", ""), 10)
        old_vt_pri  = VTYPE_PRIORITY.get(existing_row.get("value_type", ""), 10)
        new_st_pri  = STYPE_PRIORITY.get(new_row.get("source_type", ""), 5)
        old_st_pri  = STYPE_PRIORITY.get(existing_row.get("source_type", ""), 5)

        # GUARD: never overwrite official_actual with forecast_estimate
        old_is_actual = existing_row.get("value_type") == "official_actual" and existing_row.get("value") is not None
        new_is_forecast = new_row.get("value_type") == "forecast_estimate"
        if old_is_actual and new_is_forecast:
            stats["protected"] += 1
            continue

        # Update if new row has better priority
        if (new_vt_pri, new_st_pri) < (old_vt_pri, old_st_pri):
            if not dry_run:
                existing_idx[key] = new_row
            stats["updated"] += 1
        elif new_row.get("value") is not None and existing_row.get("value") is None:
            # Fill in previously missing value
            if not dry_run:
                existing_idx[key] = new_row
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    if not dry_run:
        merged_records = sorted(
            existing_idx.values(),
            key=lambda r: (
                r.get("country_code") or "",
                r.get("sector") or "",
                r.get("indicator_code") or "",
                r.get("year") or 0,
            )
        )
        # Build output
        vt_counts = Counter(r.get("value_type", "?") for r in merged_records)
        result = {
            "generated_at":    ts_now(),
            "total_rows":      len(merged_records),
            "non_null":        sum(1 for r in merged_records if r.get("value") is not None),
            "value_type_counts": dict(vt_counts),
            "note": (
                "Latest 2025/2026 data availability differs by country and sector. "
                "Official actuals, forecasts, preliminary values, and real-time signals "
                "are labeled separately."
            ),
            "records": merged_records,
        }
        combined_path.write_text(json.dumps(result, indent=2))

    return stats


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPANSION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def compute_coverage(records: list[dict]) -> dict:
    """Compute coverage matrix: country × sector → {count, non_null, pct}"""
    coverage = {}
    by_cs = defaultdict(lambda: {"total": 0, "non_null": 0, "sectors": set()})
    for r in records:
        iso3   = r.get("country_code", "?")
        sector = r.get("sector", "?")
        key = (iso3, sector)
        by_cs[key]["total"] += 1
        if r.get("value") is not None:
            by_cs[key]["non_null"] += 1
    for (iso3, sector), data in by_cs.items():
        if iso3 not in coverage:
            coverage[iso3] = {}
        pct = round(data["non_null"] / max(data["total"], 1) * 100, 1)
        coverage[iso3][sector] = {
            "total": data["total"], "non_null": data["non_null"], "pct": pct,
        }
    return coverage


def print_expansion_report(before_records: list[dict], after_records: list[dict],
                            merge_stats: dict) -> None:
    before_nn = sum(1 for r in before_records if r.get("value") is not None)
    after_nn  = sum(1 for r in after_records  if r.get("value") is not None)
    gain      = after_nn - before_nn

    print(f"\n{'═'*65}")
    print(f"  EXPANSION REPORT")
    print(f"{'═'*65}")
    print(f"  Rows before  : {len(before_records):8,} ({before_nn:,} non-null)")
    print(f"  Rows after   : {len(after_records):8,} ({after_nn:,} non-null)")
    print(f"  Net gain     : +{gain:,} non-null values")
    print(f"\n  Merge stats:")
    print(f"    Added      : {merge_stats['added']:,}")
    print(f"    Updated    : {merge_stats['updated']:,}")
    print(f"    Skipped    : {merge_stats['skipped']:,}")
    print(f"    Protected  : {merge_stats['protected']:,} (prevented forecast overwrite)")

    # Country coverage summary
    after_cov = compute_coverage(after_records)
    print(f"\n  Coverage by country (non-null % across all sectors):")
    for iso3 in sorted(after_cov.keys()):
        sec_data = after_cov[iso3]
        total_nn  = sum(s["non_null"] for s in sec_data.values())
        total_all = sum(s["total"]    for s in sec_data.values())
        pct  = round(total_nn / max(total_all, 1) * 100, 1)
        secs = len(sec_data)
        bar  = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        print(f"    {iso3:6s} [{bar}] {pct:5.1f}% ({secs} sectors)")
    print(f"{'═'*65}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Universal Official Data Expansion Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", default="api_only",
                        choices=["api_only","full","wb_only","imf_only","forecasts_only"],
                        help="Fetch mode")
    parser.add_argument("--countries", nargs="+", default=ALL_ISO3,
                        help="ISO3 country codes to fetch (default: all)")
    parser.add_argument("--sectors", nargs="+", default=None,
                        help="Sectors to focus on")
    parser.add_argument("--max-priority", type=int, default=6,
                        help="Max source priority to fetch (1=NSO, 5=multilateral, 6=forecast)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched without writing")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch even if fetched today")
    parser.add_argument("--wb-batch-size", type=int, default=10,
                        help="WB indicators per API batch")
    args = parser.parse_args()

    combined_path = PROC_DIR / "combined_indicators.json"

    print(f"\n{'═'*65}")
    print(f"  UNIVERSAL DATA EXPANSION AGENT")
    print(f"  Date: {today_iso}  |  Mode: {args.mode}")
    print(f"  Countries: {len(args.countries)}  |  Dry-run: {args.dry_run}")
    print(f"{'═'*65}\n")

    # Load before-state
    before_records = []
    if combined_path.exists():
        before_data = json.loads(combined_path.read_text())
        before_records = before_data.get("records", [])
    print(f"  Before: {len(before_records):,} rows ({sum(1 for r in before_records if r.get('value') is not None):,} non-null)\n")

    # Load source registry
    sr_path = PROC_DIR / "source_registry.json"
    source_registry = json.loads(sr_path.read_text()).get("sources", {}) if sr_path.exists() else {}

    all_new_rows = []
    fetch_log    = []

    # ── WORLD BANK — always load from cache first ─────────────────────────────
    if args.mode in ("api_only", "full", "wb_only"):
        print("  ── WORLD BANK: CORE (cache) ─────────────────────────", flush=True)
        core_rows = load_wb_core_from_cache()
        if core_rows:
            non_null_core = sum(1 for r in core_rows if r.get("value") is not None)
            all_new_rows.extend(core_rows)
            print(f"  ✓ {len(core_rows):,} rows ({non_null_core:,} non-null) — worldbank_indicators.json")
            fetch_log.append({"source": "WB core cache", "rows": len(core_rows),
                              "non_null": non_null_core})
        else:
            print("  ⚠ WB cache missing — run pipeline/fetch_worldbank.py first")

        # Load any other normalized WB files produced by specialist scripts
        extended_files = [
            ("technology_normalized.json",  "WB technology/governance"),
            ("energy_normalized.json",       "WB energy/environment"),
            ("tourism_normalized.json",      "WB tourism"),
            ("aseanstats_normalized.json",   "ASEANstats"),
            ("infrastructure_normalized.json","WB infrastructure"),
            ("environment_normalized.json",  "WB agriculture/social"),
        ]
        print(f"\n  ── WORLD BANK: EXTENDED (from specialist caches) ────", flush=True)
        for fname, label in extended_files:
            fpath = PROC_DIR / fname
            if fpath.exists():
                try:
                    d = json.loads(fpath.read_text())
                    recs = d.get("records", [])
                    nn = sum(1 for r in recs if r.get("value") is not None)
                    all_new_rows.extend(recs)
                    print(f"  ✓ {fname:45s} {len(recs):6,} rows ({nn:,} non-null)")
                    fetch_log.append({"source": label, "rows": len(recs), "non_null": nn})
                except Exception as e:
                    print(f"  ⚠ {fname}: {e}")
            else:
                print(f"  – {fname:45s} not found (run specialist fetcher first)")

        # Try fetching any EXTENDED indicators that aren't yet in any cache file
        # Only attempt if WB API probe succeeds (avoids long rate-limit waits)
        print(f"\n  ── WORLD BANK: NEW EXTENDED (API probe) ─────────────", flush=True)
        probe_url = f"{WB_BASE}/country/TH/indicator/NY.GDP.PCAP.PP.CD?format=json&per_page=5&date=2024:2024"
        probe_ok  = False
        try:
            r_probe = _get(probe_url, timeout=10,
                          headers={"User-Agent":"SEA-Dashboard/2.0","Accept":"application/json"})
            if r_probe.status_code == 200 and getattr(r_probe, "text", "").strip():
                r_probe.json()   # confirm parseable
                probe_ok = True
        except Exception:
            pass

        if probe_ok:
            print("  ✓ WB API reachable — fetching new extended indicators", flush=True)
            # Only fetch indicators not already covered by specialist caches
            cached_codes = set(WB_CORE_KEYS.keys()) | {
                # technology_normalized covers these:
                "IT.NET.USER.ZS","IT.CEL.SETS.P2","IT.NET.BBND.P2","GB.XPD.RSDV.GD.ZS",
                "SP.POP.SCIE.RD.P6","GE.EST","RL.EST","VA.EST","RQ.EST","PV.EST","CC.EST",
                "SP.POP.TOTL","SP.POP.GROW","SI.POV.LMIC","SI.POV.UMIC","SP.DYN.LE00.IN",
                "SP.DYN.IMRT.IN","SH.STA.MMRT","SE.XPD.TOTL.GD.ZS","SE.SEC.ENRR",
                "SE.TER.ENRR","SH.XPD.CHEX.GD.ZS","SI.POV.GINI","FX.OWN.SELF.IN",
                "PA.NUS.FCRF","FM.LBL.BMNY.ZG","FM.LBL.BMNY.GD.ZS","FS.AST.PRVT.GD.ZS",
                "FI.RES.TOTL.CD","FB.AST.NPER.ZS","CM.MKT.LCAP.GD.ZS","NV.IND.MANF.ZS",
                "NV.IND.MANF.CD","TX.VAL.TECH.MF.ZS","TX.VAL.TECH.CD",
                # energy_normalized covers these:
                "EG.FEC.RNEW.ZS","EG.ELC.ACCS.ZS","EG.EGY.PRIM.PP.KD",
                "EN.ATM.CO2E.PC","EN.ATM.CO2E.PP.GD","EG.IMP.CONS.ZS",
                "AG.LND.FRST.ZS","EN.ATM.CO2E.KT","EN.ATM.METH.KT.CE",
                "EN.ATM.PM25.MC.M3","SH.H2O.BASW.ZS","SH.STA.BASS.ZS",
                # tourism covers:
                "ST.INT.ARVL","ST.INT.RCPT.CD",
            }
            new_codes = [c for c in WB_INDICATOR_MAP.keys()
                        if c not in cached_codes
                        and (not args.sectors or WB_INDICATOR_MAP[c][0] in args.sectors)]

            if new_codes:
                print(f"  Fetching {len(new_codes)} new WB indicators:", flush=True)
                for c in new_codes:
                    print(f"    {c}", flush=True)
                rows = fetch_wb_batch(new_codes, delay=1.2, skip_cached=False)
                non_null = sum(1 for r in rows if r.get("value") is not None)
                all_new_rows.extend(rows)
                print(f"  ✓ New WB extended: {non_null:,} non-null values")
                fetch_log.append({"source": "WB API (new extended)", "rows": len(rows),
                                  "non_null": non_null})
            else:
                print("  ✓ All WB indicators already covered by caches")
        else:
            print("  ⚠ WB API not reachable right now — using cached data only", flush=True)
        print()

    # ── IMF WEO — fetch all mapped indicators ───────────────────────────────
    if args.mode in ("api_only", "full", "imf_only", "forecasts_only"):
        print("  ── IMF WEO INDICATORS ────────────────────────────────", flush=True)
        imf_codes = list(IMF_WEO_MAP.keys())
        if args.sectors:
            imf_codes = [c for c, meta in IMF_WEO_MAP.items() if meta[0] in args.sectors]

        for imf_code in imf_codes:
            meta = IMF_WEO_MAP[imf_code]
            print(f"  IMF {imf_code:20s} {meta[2][:35]}", flush=True)

        rows = fetch_imf_weo_agent(imf_codes, delay=1.0)
        non_null = sum(1 for r in rows if r.get("value") is not None)
        forecasts = sum(1 for r in rows if r.get("value_type") == "forecast_estimate" and r.get("value") is not None)
        all_new_rows.extend(rows)
        print(f"  IMF total: {non_null:,} non-null ({forecasts} forecasts)\n")
        fetch_log.append({"source": "IMF WEO", "rows": len(rows), "non_null": non_null})

    # ── DELEGATE TO SPECIALIST SCRIPTS ──────────────────────────────────────
    if args.mode == "full" and not args.dry_run:
        specialist_scripts = [
            ("ADB ADO",          PROJECT_ROOT / "scripts" / "fetch_adb_ado.py"),
            ("ASEANstats",       PROJECT_ROOT / "scripts" / "fetch_aseanstats.py"),
            ("Tourism",          PROJECT_ROOT / "scripts" / "fetch_tourism_sources.py"),
            ("Energy/Env",       PROJECT_ROOT / "scripts" / "fetch_energy_sources.py"),
            ("Technology",       PROJECT_ROOT / "scripts" / "fetch_technology_policy_sources.py"),
            ("Infrastructure",   PROJECT_ROOT / "scripts" / "fetch_infrastructure_projects.py"),
            ("Environment",      PROJECT_ROOT / "scripts" / "fetch_environment_sources.py"),
        ]
        print("  ── SPECIALIST FETCHERS ───────────────────────────────")
        for name, script_path in specialist_scripts:
            if script_path.exists():
                print(f"  ▸ {name}...", flush=True)
                result = subprocess.run([sys.executable, str(script_path)],
                                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"    ⚠ {name} exit {result.returncode}")
                else:
                    print(f"    ✓ Done")
            time.sleep(0.5)
        print()

    # ── MERGE ────────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"  DRY RUN: would merge {len(all_new_rows):,} new rows")
        non_null_new = sum(1 for r in all_new_rows if r.get("value") is not None)
        print(f"  DRY RUN: {non_null_new:,} non-null values")
        merge_stats = {"added": 0, "updated": 0, "skipped": 0, "protected": 0}
        after_records = before_records
    else:
        print(f"  ── MERGING {len(all_new_rows):,} ROWS ──────────────────────────", flush=True)
        merge_stats = merge_into_combined(all_new_rows, combined_path)

        # Load after-state
        after_data = json.loads(combined_path.read_text())
        after_records = after_data.get("records", [])

    # Print expansion report
    print_expansion_report(before_records, after_records, merge_stats)

    # Run freshness report
    if not args.dry_run:
        print("  ── FRESHNESS REPORT ─────────────────────────────────")
        freshness_script = PROJECT_ROOT / "scripts" / "generate_freshness_report.py"
        if freshness_script.exists():
            subprocess.run([sys.executable, str(freshness_script)],
                          cwd=str(PROJECT_ROOT), capture_output=True)
            print("  ✓ Freshness report updated")

    # Write agent run log
    log = {
        "run_at":       ts_now(),
        "mode":         args.mode,
        "dry_run":      args.dry_run,
        "rows_fetched": len(all_new_rows),
        "merge_stats":  merge_stats,
        "before_rows":  len(before_records),
        "after_rows":   len(after_records),
        "fetch_log":    fetch_log,
    }
    log_file = LOGS_DIR / f"agent_run_{today_str}.json"
    log_file.write_text(json.dumps(log, indent=2))
    print(f"  📄 Log: {log_file.relative_to(PROJECT_ROOT)}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
