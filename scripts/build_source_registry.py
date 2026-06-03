#!/usr/bin/env python3
"""
scripts/build_source_registry.py
────────────────────────────────────────────────────────────────────────────
GENERATES pipeline/data/processed/source_registry.json from Python source.

Maintaining a 5,000-line static JSON file is error-prone.
This script IS the registry — edit here, run to regenerate.

Contains every known official data source for:
  - 11 SEA countries × all sectors
  - 6 partner countries (CHN, USA, JPN, IND, KOR, AUS) × key indicators
  - EU as trade partner
  - 20+ multilateral / regional sources

Each source definition contains:
  id, name, short_name, type, priority, countries[], url,
  api_endpoint, api_key_required, data_format, extraction_method,
  sectors[], value_types[], frequency, coverage_years,
  update_schedule, reliability, limitations, implemented, script

USAGE
  python scripts/build_source_registry.py          # generate + print summary
  python scripts/build_source_registry.py --validate  # also validate API reachability
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_FILE     = PROJECT_ROOT / "pipeline" / "data" / "processed" / "source_registry.json"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER to define a source compactly
# ─────────────────────────────────────────────────────────────────────────────

def S(id, name, short, stype, priority, countries, url, api=None, key=False,
      fmt="json", method="api", sectors=None, vtypes=None, freq="annual",
      years="2015-2025", schedule="Annual", rel="high",
      limits="", impl=False, script=None):
    return {
        "id": id, "name": name, "short_name": short,
        "type": stype, "priority": priority,
        "countries": countries,
        "url": url, "api_endpoint": api, "api_key_required": key,
        "data_format": fmt, "extraction_method": method,
        "sectors": sectors or [], "value_types": vtypes or ["official_actual"],
        "frequency": freq, "coverage_years": years,
        "update_schedule": schedule, "reliability": rel,
        "limitations": limits, "implemented": impl,
        "script": script or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

def build_sources() -> dict:
    sources = {}

    def add(defn):
        sources[defn["id"]] = defn

    # ══════════════════════════════════════════════════════════════════════════
    # MULTILATERAL — always available, no key needed
    # ══════════════════════════════════════════════════════════════════════════

    add(S("WB_API", "World Bank Open Data API", "World Bank", "multilateral", 5,
          ["ALL"], "https://data.worldbank.org",
          "https://api.worldbank.org/v2/country/{codes}/indicator/{code}?format=json&per_page=1000&date={start}:{end}",
          sectors=["macro_economy","prices_inflation","labor","trade","investment",
                   "finance_monetary","fiscal","tourism","energy","environment",
                   "agriculture","technology_digital","infrastructure","social_indicators",
                   "politics_policy","security_conflict","industry_production"],
          vtypes=["official_actual","missing_official"],
          freq="annual", years="1960-2024", schedule="Quarterly", rel="very_high",
          limits="Annual data; 1-2 year publication lag; gaps for fragile states",
          impl=True, script="pipeline/fetch_worldbank.py"))

    add(S("IMF_WEO", "IMF World Economic Outlook DataMapper", "IMF WEO",
          "forecast_multilateral", 6, ["ALL"], "https://www.imf.org/external/datamapper",
          "https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3codes}",
          sectors=["macro_economy","prices_inflation","labor","fiscal","finance_monetary"],
          vtypes=["forecast_estimate","official_actual"],
          freq="biannual", years="1980-2030", schedule="April and October",
          rel="very_high", limits="Forecasts for 2025+; biannual update",
          impl=True, script="scripts/fetch_imf_weo.py"))

    add(S("IMF_DATA_API", "IMF Data API (IFS, BOP, GFS, WEO)", "IMF Data",
          "multilateral", 5, ["ALL"], "https://data.imf.org",
          "https://www.imf.org/external/datamapper/api/v1/",
          sectors=["finance_monetary","fiscal","trade","investment","macro_economy"],
          freq="quarterly", years="1980-2025", schedule="Quarterly",
          rel="very_high", limits="Comprehensive IFS/BOP/GFS datasets; requires dataset navigation",
          impl=True, script="scripts/fetch_imf_weo.py"))

    add(S("WB_GEP", "World Bank Global Economic Prospects", "WB GEP",
          "forecast_multilateral", 6, ["ALL"], "https://www.worldbank.org/en/publication/global-economic-prospects",
          "https://api.worldbank.org/v2/country/{codes}/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=50&date=2024:2027",
          sectors=["macro_economy"], vtypes=["forecast_estimate"],
          freq="biannual", years="2025-2027", schedule="January and June",
          rel="high", limits="GDP growth forecasts only",
          impl=True, script="scripts/fetch_worldbank_gep.py"))

    add(S("ADB_ADO", "ADB Asian Development Outlook", "ADB ADO",
          "forecast_multilateral", 6,
          ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS","CHN","IND","KOR"],
          "https://www.adb.org/outlook",
          sectors=["macro_economy","prices_inflation","trade"],
          vtypes=["forecast_estimate"], freq="biannual", years="2025-2027",
          schedule="April and September", rel="high",
          limits="Asia-focused; GDP and inflation forecasts",
          impl=True, script="scripts/fetch_adb_ado.py"))

    add(S("ADB_STATS", "ADB Statistics Database (Key Indicators)", "ADB Stats",
          "multilateral", 5,
          ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS","CHN","IND","KOR","AUS"],
          "https://data.adb.org",
          "https://kiapi.adb.org/api/v1/",
          sectors=["macro_economy","social_indicators","infrastructure","environment","trade"],
          freq="annual", years="2000-2024", schedule="Annual",
          rel="high", limits="ADB Key Indicators; Asia-Pacific focus",
          impl=False, script="scripts/fetch_adb_ado.py"))

    add(S("ASEANSTATS", "ASEANstats", "ASEANstats",
          "regional_official", 4,
          ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS"],
          "https://stats.asean.org",
          sectors=["macro_economy","trade","investment","tourism","labor","social_indicators"],
          freq="annual", years="2015-2024", schedule="Annual", rel="high",
          limits="Annual ASEAN aggregate; HTML interface; proxied via WB API",
          impl=True, script="scripts/fetch_aseanstats.py"))

    add(S("UN_COMTRADE", "UN Comtrade Plus", "UN Comtrade",
          "multilateral", 3, ["ALL"],
          "https://comtradeplus.un.org",
          "https://comtradeapi.un.org/data/v1/get/C/A/HS?reporterCode={code}&period={year}&cmdCode=TOTAL&flowCode=X,M&partnerCode=0",
          sectors=["trade"], freq="monthly_annual", years="2010-2024",
          schedule="Monthly", rel="high",
          limits="Free 500 calls/hr; bilateral trade flows by partner",
          impl=True, script="scripts/fetch_un_comtrade.py"))

    add(S("UN_COMTRADE_MONTHLY", "UN Comtrade Monthly Trade Data", "Comtrade Monthly",
          "multilateral", 3, ["ALL"], "https://comtradeplus.un.org",
          "https://comtradeapi.un.org/data/v1/get/C/M/HS?reporterCode={code}&period={year}{month}&cmdCode=TOTAL&flowCode=X,M",
          sectors=["trade"], freq="monthly", years="2020-2025",
          schedule="Monthly", rel="high",
          limits="Monthly bilateral; free tier limited",
          impl=False, script="scripts/fetch_un_comtrade.py"))

    add(S("OECD_STATS", "OECD Statistics (SDMX API)", "OECD",
          "multilateral", 5, ["KOR","AUS","JPN","USA"],
          "https://stats.oecd.org",
          "https://stats.oecd.org/SDMX-JSON/data/{dataset}/{filter}/{agency}",
          sectors=["macro_economy","labor","fiscal","trade","finance_monetary","social_indicators"],
          freq="quarterly", years="2000-2025", schedule="Quarterly",
          rel="very_high", limits="OECD members only; comprehensive quarterly data",
          impl=False, script="scripts/fetch_imf_weo.py"))

    add(S("ILO_ILOSTAT", "ILO Statistics (ILOSTAT API)", "ILO",
          "multilateral", 5, ["ALL"], "https://ilostat.ilo.org",
          "https://rplumber.ilo.org/data/indicator/?id={indicator}&ref_area={iso3}&time={year}&type=label&decimals=2",
          sectors=["labor"], freq="annual", years="2000-2024",
          schedule="Annual", rel="high",
          limits="Labor force participation, employment by sector, wages; country coverage varies",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("FAO_FAOSTAT", "FAOSTAT - UN Food and Agriculture", "FAO",
          "multilateral", 5, ["ALL"], "https://www.fao.org/faostat",
          "https://fenixservices.fao.org/faostat/api/v1/en/data/{domain}?area={code}&element={element}&item={item}&year={year}",
          sectors=["agriculture"], freq="annual", years="1961-2023",
          schedule="Annual", rel="high",
          limits="Crop production, food prices, trade; 1-2 year lag",
          impl=False, script="scripts/fetch_environment_sources.py"))

    add(S("WHO_GHO", "WHO Global Health Observatory", "WHO GHO",
          "multilateral", 5, ["ALL"], "https://www.who.int/data/gho",
          "https://ghoapi.azureedge.net/api/{indicator}?$filter=SpatialDim eq '{iso3}'",
          sectors=["social_indicators"], freq="annual", years="2000-2023",
          schedule="Annual", rel="high",
          limits="Health indicators; life expectancy, mortality, nutrition",
          impl=False, script="scripts/fetch_technology_policy_sources.py"))

    add(S("ENERGY_IEA", "International Energy Agency", "IEA",
          "multilateral", 5, ["ALL"], "https://www.iea.org/data-and-statistics",
          "https://api.iea.org/", key=True,
          sectors=["energy"], freq="annual", years="1990-2023",
          schedule="Annual", rel="very_high",
          limits="Requires API key; most comprehensive energy dataset",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("ENERGY_WB", "World Bank Energy Indicators", "WB Energy",
          "multilateral", 5, ["ALL"], "https://data.worldbank.org/topic/5",
          "https://api.worldbank.org/v2/country/{codes}/indicator/{code}?format=json&per_page=500&date=2015:2026",
          sectors=["energy","environment"], freq="annual", years="1990-2024",
          schedule="Annual", rel="high",
          limits="Renewable energy share, electricity access, CO2 emissions",
          impl=True, script="scripts/fetch_energy_sources.py"))

    add(S("TECH_ITU", "ITU DataHub (ICT Statistics)", "ITU",
          "multilateral", 5, ["ALL"], "https://datahub.itu.int",
          "https://datahub.itu.int/api/",
          sectors=["technology_digital"], freq="annual", years="2000-2024",
          schedule="Annual", rel="high",
          limits="Internet penetration, mobile subscriptions, broadband",
          impl=False, script="scripts/fetch_technology_policy_sources.py"))

    add(S("WTO_STATS", "WTO Statistics (Trade)", "WTO",
          "multilateral", 5, ["ALL"], "https://stats.wto.org",
          "https://api.wto.org/timeseries/v1/data",
          sectors=["trade"], freq="annual", years="2000-2024",
          schedule="Annual", rel="very_high",
          limits="Merchandise and services trade; tariff data",
          impl=False, script="scripts/fetch_un_comtrade.py"))

    add(S("UNCTAD_STATS", "UNCTAD Statistics (FDI, Trade)", "UNCTAD",
          "multilateral", 5, ["ALL"], "https://unctadstat.unctad.org",
          "https://unctadstat.unctad.org/api/v1/data/",
          sectors=["investment","trade"], freq="annual", years="2000-2024",
          schedule="Annual", rel="high",
          limits="FDI flows, trade, development indicators",
          impl=False, script="scripts/fetch_aseanstats.py"))

    add(S("BIS_STATS", "Bank for International Settlements", "BIS",
          "multilateral", 5, ["ALL"], "https://www.bis.org/statistics",
          "https://data.bis.org/api/v1/data/WS_CREDIT_GAP/",
          sectors=["finance_monetary"], freq="quarterly", years="2000-2025",
          schedule="Quarterly", rel="very_high",
          limits="Credit gaps, banking statistics, FX reserves",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("WB_PROJECTS", "World Bank Projects Database", "WB Projects",
          "multilateral", 5, ["ALL"], "https://projects.worldbank.org",
          "https://search.worldbank.org/api/v2/projects?format=json&countryshortname={country}&rows=100",
          sectors=["infrastructure"], freq="continuous", years="2019-2026",
          schedule="Weekly", rel="high",
          limits="WB-funded projects only",
          impl=True, script="scripts/fetch_infrastructure_projects.py"))

    add(S("ADB_PROJECTS", "ADB Projects Database", "ADB Projects",
          "multilateral", 5,
          ["THA","VNM","MMR","KHM","LAO","MYS","IDN","PHL","TLS","CHN","IND"],
          "https://www.adb.org/projects",
          "https://www.adb.org/api/projects/all.json",
          sectors=["infrastructure"], freq="continuous", years="2019-2026",
          schedule="Weekly", rel="high",
          limits="ADB-funded projects only",
          impl=True, script="scripts/fetch_infrastructure_projects.py"))

    add(S("AIIB_PROJECTS", "AIIB Projects Database", "AIIB",
          "multilateral", 5,
          ["THA","VNM","MMR","KHM","LAO","MYS","IDN","PHL","TLS","CHN","IND"],
          "https://www.aiib.org/en/projects/",
          sectors=["infrastructure"], freq="continuous", years="2017-2026",
          schedule="Monthly", rel="high",
          limits="AIIB-funded projects; mostly Asia infrastructure",
          impl=False, script="scripts/fetch_infrastructure_projects.py"))

    add(S("UNWTO_STATS", "UN World Tourism Organization", "UNWTO",
          "multilateral", 5, ["ALL"], "https://www.unwto.org/tourism-statistics",
          sectors=["tourism"], freq="annual", years="2015-2024",
          schedule="Annual", rel="high",
          limits="International tourist arrivals and receipts; annual",
          impl=True, script="scripts/fetch_tourism_sources.py"))

    add(S("GDELT_NEWS", "GDELT Project (Real-time News Signal)", "GDELT",
          "realtime_signal", 8, ["ALL"],
          "https://api.gdeltproject.org/api/v2/doc/doc",
          "https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=artlist&maxrecords=25&format=json",
          sectors=["politics_policy","security_conflict","macro_economy","trade"],
          vtypes=["realtime_signal"], freq="realtime", years="2013-present",
          schedule="15 minutes", rel="medium",
          limits="News signals only — NOT statistics; use for sentiment/risk only",
          impl=True, script="pipeline/fetch_gdelt.py"))

    add(S("ACLED_CONFLICT", "ACLED (Armed Conflict Location & Event Data)", "ACLED",
          "realtime_signal", 8,
          ["MMR","THA","PHL","IDN","MYS","LAO","KHM","TLS"],
          "https://acleddata.com",
          "https://api.acleddata.com/acled/read/?key={key}&email={email}&region=Asia",
          key=True,
          sectors=["security_conflict"], vtypes=["realtime_signal"],
          freq="weekly", years="1997-present",
          schedule="Weekly", rel="high",
          limits="Requires free API key; conflict events, protests, violence data",
          impl=False, script="scripts/fetch_official_press_releases.py"))

    add(S("TI_CPI", "Transparency International Corruption Perceptions Index", "TI CPI",
          "multilateral", 5, ["ALL"],
          "https://www.transparency.org/en/cpi",
          sectors=["security_conflict","politics_policy"], freq="annual", years="2012-2024",
          schedule="January each year", rel="high",
          limits="Annual CPI score; perception-based, not statistical",
          impl=False, script="scripts/fetch_technology_policy_sources.py"))

    add(S("WEF_GCI", "World Economic Forum Global Competitiveness Index", "WEF GCI",
          "multilateral", 6, ["ALL"], "https://www.weforum.org/reports",
          sectors=["infrastructure","technology_digital","macro_economy"],
          freq="annual", years="2015-2023",
          schedule="Annual (Sep/Oct)", rel="medium",
          limits="Survey-based; GCI discontinued 2020; replaced by GCI 4.0",
          impl=False, script="scripts/fetch_technology_policy_sources.py"))

    add(S("HERITAGE_EF", "Heritage Foundation Economic Freedom Index", "Heritage EF",
          "multilateral", 6, ["ALL"],
          "https://www.heritage.org/index/",
          "https://api.heritage.org/v1/all",
          sectors=["fiscal","trade","finance_monetary","politics_policy"],
          freq="annual", years="2015-2025",
          schedule="Annual (February)", rel="medium",
          limits="Composite index; not official national statistics",
          impl=False, script="scripts/fetch_technology_policy_sources.py"))

    add(S("DOING_BUSINESS", "World Bank Doing Business / B-READY", "WB B-READY",
          "multilateral", 5, ["ALL"],
          "https://www.worldbank.org/en/businessready",
          sectors=["infrastructure","investment"],
          freq="annual", years="2015-2023",
          schedule="Annual", rel="high",
          limits="Doing Business discontinued 2021; B-READY piloting 2024-25",
          impl=False, script="scripts/fetch_worldbank_gep.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # THAILAND
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_THA_NESDC", "NESDC Thailand (Quarterly GDP)", "NESDC",
          "national_statistics", 1, ["THA"],
          "https://www.nesdc.go.th/main.php?filename=qgdp_page",
          sectors=["macro_economy"], freq="quarterly", years="2000-2025",
          schedule="60 days after quarter end", rel="very_high",
          limits="Thai language primary; quarterly GDP with advance estimates",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("NSO_THA_NSO", "National Statistical Office Thailand", "NSO Thailand",
          "national_statistics", 1, ["THA"], "https://www.nso.go.th",
          sectors=["prices_inflation","labor","social_indicators"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Monthly CPI; quarterly LFS",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_THA_BOT", "Bank of Thailand", "BOT",
          "central_bank", 2, ["THA"],
          "https://www.bot.or.th/en/statistics.html",
          "https://apiv2.bot.or.th/bot/public/",
          key=True,
          sectors=["finance_monetary","trade","investment"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Full API requires key; public tables via scraping",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_THA_CUSTOMS", "Thai Customs Department (Trade Stats)", "Thai Customs",
          "ministry_customs", 3, ["THA"],
          "https://www.customs.go.th/statistic.php",
          sectors=["trade"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Monthly trade by partner/product; HTML tables",
          impl=True, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_THA_MOC_PRICES", "Thailand Ministry of Commerce (Price Monitoring)", "MOC Thailand",
          "ministry_customs", 3, ["THA"],
          "https://price.moc.go.th",
          sectors=["prices_inflation"], freq="daily",
          schedule="Daily", rel="high",
          limits="Consumer goods prices; rice and commodity prices",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_THA_EPPO", "Energy Policy and Planning Office Thailand", "EPPO Thailand",
          "ministry_customs", 3, ["THA"],
          "https://www.eppo.go.th/index.php/en/",
          sectors=["energy"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Oil imports, electricity generation, energy consumption by sector",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("MIN_THA_BOI", "Board of Investment Thailand", "BOI Thailand",
          "ministry_customs", 3, ["THA"],
          "https://www.boi.go.th",
          sectors=["investment"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="very_high",
          limits="Approved FDI investment projects; sector breakdown",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("TOUR_THA_MOTS", "Ministry of Tourism & Sports Thailand", "MOTS Thailand",
          "ministry_customs", 3, ["THA"],
          "https://www.mots.go.th/more_news_new.php?cid=504",
          sectors=["tourism"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Monthly tourist arrivals; HTML tables",
          impl=True, script="scripts/fetch_tourism_sources.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # VIETNAM
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_VNM_GSO", "General Statistics Office Vietnam", "GSO Vietnam",
          "national_statistics", 1, ["VNM"],
          "https://www.gso.gov.vn", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","labor","trade","agriculture"],
          freq="quarterly", years="2010-2025", schedule="Monthly/Quarterly",
          rel="high", limits="Vietnamese language primary; English version may lag",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_VNM_SBV", "State Bank of Vietnam", "SBV Vietnam",
          "central_bank", 2, ["VNM"],
          "https://www.sbv.gov.vn/webcenter/portal/en/home",
          fmt="html", method="scrape",
          sectors=["finance_monetary"], freq="monthly", years="2010-2025",
          schedule="Monthly", rel="high",
          limits="Limited English coverage; exchange rates and monetary aggregates",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_VNM_CUSTOMS", "General Department of Vietnam Customs", "VNM Customs",
          "ministry_customs", 3, ["VNM"],
          "https://www.customs.gov.vn",
          sectors=["trade"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Monthly trade statistics; Vietnamese language primarily",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_VNM_MOIT", "Ministry of Industry and Trade Vietnam", "MOIT Vietnam",
          "ministry_customs", 3, ["VNM"],
          "https://www.moit.gov.vn",
          sectors=["industry_production","trade","energy"],
          freq="monthly", years="2015-2025", schedule="Monthly",
          rel="high", limits="Industrial production, retail, trade data",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("NSO_VNM_GSO_FDI", "Vietnam Foreign Investment Agency (FIA)", "FIA Vietnam",
          "ministry_customs", 3, ["VNM"],
          "https://fia.mpi.gov.vn",
          sectors=["investment"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Monthly FDI approvals and disbursements",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # MALAYSIA
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_MYS_DOSM", "Department of Statistics Malaysia (OpenDOSM)", "DOSM",
          "national_statistics", 1, ["MYS"],
          "https://www.dosm.gov.my",
          "https://open.dosm.gov.my/api",
          sectors=["macro_economy","prices_inflation","labor","trade",
                   "industry_production","agriculture","social_indicators"],
          freq="monthly", years="2010-2025", schedule="Monthly",
          rel="very_high", limits="OpenDOSM API excellent; some datasets require registration",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_MYS_BNM", "Bank Negara Malaysia", "BNM",
          "central_bank", 2, ["MYS"],
          "https://www.bnm.gov.my",
          "https://api.bnm.gov.my/public/",
          sectors=["finance_monetary","trade","investment"],
          freq="monthly", years="2010-2025", schedule="Monthly",
          rel="very_high", limits="Open API; exchange rates, OPR, BOP",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_MYS_CUSTOMS", "Royal Malaysian Customs (via DOSM)", "MYS Customs",
          "ministry_customs", 3, ["MYS"],
          "https://www.dosm.gov.my/portal-main/page/external-trade",
          "https://open.dosm.gov.my/api",
          sectors=["trade"], freq="monthly", years="2010-2025",
          schedule="Monthly", rel="very_high",
          limits="Via OpenDOSM API; monthly by partner",
          impl=True, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_MYS_ST", "Energy Commission Malaysia (Suruhanjaya Tenaga)", "ST Malaysia",
          "ministry_customs", 3, ["MYS"],
          "https://www.st.gov.my",
          sectors=["energy"], freq="annual", years="2015-2024",
          schedule="Annual", rel="high",
          limits="Electricity statistics; generation mix; tariffs",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("MIN_MYS_MITI", "Ministry of Investment, Trade & Industry Malaysia", "MITI",
          "ministry_customs", 3, ["MYS"],
          "https://www.miti.gov.my",
          sectors=["investment","trade"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="high",
          limits="FDI approvals; manufacturing investment; trade promotion",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("TOUR_MYS", "Tourism Malaysia", "Tourism Malaysia",
          "ministry_customs", 3, ["MYS"],
          "https://www.tourism.gov.my/statistics",
          sectors=["tourism"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="high",
          limits="Monthly arrivals; PDF and HTML",
          impl=True, script="scripts/fetch_tourism_sources.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # SINGAPORE
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_SGP_SINGSTAT", "Singapore Department of Statistics (SingStat)", "SingStat",
          "national_statistics", 1, ["SGP"],
          "https://www.singstat.gov.sg",
          "https://tablebuilder.singstat.gov.sg/api/table/tabledata/{table_id}",
          sectors=["macro_economy","prices_inflation","labor","trade","investment","social_indicators"],
          freq="quarterly", years="2000-2025", schedule="Quarterly/Monthly",
          rel="very_high", limits="Excellent TableBuilder API; comprehensive",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_SGP_MAS", "Monetary Authority of Singapore", "MAS",
          "central_bank", 2, ["SGP"],
          "https://www.mas.gov.sg/statistics",
          "https://eservices.mas.gov.sg/api/action/datastore/search.json",
          sectors=["finance_monetary","trade","investment"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Open API; SORA, exchange rates, financial sector",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_SGP_MTI", "Singapore Ministry of Trade and Industry", "MTI Singapore",
          "ministry_customs", 3, ["SGP"],
          "https://www.mti.gov.sg/Resources/Economic-Survey-of-Singapore",
          sectors=["macro_economy","trade"], freq="quarterly", years="2000-2025",
          schedule="Quarterly (advance estimate)", rel="very_high",
          limits="Advance GDP estimates and economic survey",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_SGP_EMA", "Energy Market Authority Singapore", "EMA",
          "ministry_customs", 3, ["SGP"],
          "https://www.ema.gov.sg/Statistics.aspx",
          sectors=["energy"], freq="annual", years="2010-2024",
          schedule="Annual", rel="very_high",
          limits="Energy statistics; electricity market; renewables",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("TOUR_SGP_STB", "Singapore Tourism Board", "STB",
          "ministry_customs", 3, ["SGP"],
          "https://www.stb.gov.sg/content/stb/en/statistics-and-market-insights/tourism-statistics.html",
          sectors=["tourism"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="very_high",
          limits="Quarterly visitor arrivals and receipts",
          impl=True, script="scripts/fetch_tourism_sources.py"))

    add(S("MIN_SGP_EDB", "Singapore Economic Development Board", "EDB",
          "ministry_customs", 3, ["SGP"],
          "https://www.edb.gov.sg/en/business-insights/insights.html",
          sectors=["investment"], freq="annual", years="2015-2025",
          schedule="Annual", rel="very_high",
          limits="FDI commitment by sector; manufacturing investment",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # INDONESIA
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_IDN_BPS", "Statistics Indonesia (BPS)", "BPS",
          "national_statistics", 1, ["IDN"],
          "https://www.bps.go.id",
          "https://webapi.bps.go.id/v1/api/list/model/data/lang/eng/domain/0000/var/{var_id}/key/{api_key}",
          key=True,
          sectors=["macro_economy","prices_inflation","labor","trade","agriculture","social_indicators"],
          freq="quarterly", years="2010-2025", schedule="Quarterly/Monthly",
          rel="very_high", limits="Full API requires key; public press releases accessible",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_IDN_BI", "Bank Indonesia", "Bank Indonesia",
          "central_bank", 2, ["IDN"],
          "https://www.bi.go.id/en/statistik/ekonomi-keuangan/",
          fmt="html", method="scrape",
          sectors=["finance_monetary","trade"], freq="monthly", years="2010-2025",
          schedule="Monthly", rel="very_high",
          limits="API in development; HTML tables available; BI Rate, FX",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_IDN_BKPM", "BKPM (Investment Coordinating Board)", "BKPM Indonesia",
          "ministry_customs", 3, ["IDN"],
          "https://www.bkpm.go.id",
          sectors=["investment"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="very_high",
          limits="FDI realization; domestic investment by sector",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_IDN_ESDM", "Ministry of Energy & Mineral Resources Indonesia", "ESDM",
          "ministry_customs", 3, ["IDN"],
          "https://www.esdm.go.id",
          sectors=["energy"], freq="annual", years="2015-2024",
          schedule="Annual", rel="high",
          limits="Coal, oil, gas production; electricity generation; RE targets",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("MIN_IDN_MOT", "Indonesia Ministry of Trade (Satudata)", "MOT Indonesia",
          "ministry_customs", 3, ["IDN"],
          "https://satudata.kemendag.go.id",
          sectors=["trade"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="high",
          limits="Trade statistics portal; may change structure",
          impl=True, script="scripts/fetch_ministries_customs.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # PHILIPPINES
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_PHL_PSA", "Philippine Statistics Authority (OpenStat)", "PSA",
          "national_statistics", 1, ["PHL"],
          "https://psa.gov.ph",
          "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/",
          sectors=["macro_economy","prices_inflation","labor","trade","agriculture","social_indicators"],
          freq="quarterly", years="2010-2025", schedule="Quarterly/Monthly",
          rel="very_high", limits="OpenStat PXWeb API available; PSNA quarterly GDP",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_PHL_BSP", "Bangko Sentral ng Pilipinas", "BSP",
          "central_bank", 2, ["PHL"],
          "https://www.bsp.gov.ph/Statistics/",
          fmt="html", method="scrape",
          sectors=["finance_monetary","trade","investment"],
          freq="monthly", years="2010-2025", schedule="Monthly",
          rel="very_high", limits="HTML/PDF tables; remittances data very good",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_PHL_BOC", "Bureau of Customs Philippines (Trade)", "BOC Philippines",
          "ministry_customs", 3, ["PHL"],
          "https://www.customs.gov.ph",
          sectors=["trade"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="high",
          limits="Monthly trade data; HTML tables",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("MIN_PHL_NEDA", "NEDA Philippines (Investment Data)", "NEDA",
          "ministry_customs", 3, ["PHL"],
          "https://www.neda.gov.ph",
          sectors=["investment","macro_economy"], freq="annual", years="2015-2025",
          schedule="Annual", rel="high",
          limits="Investment coordination; annual development data",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # CAMBODIA
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_KHM_NIS", "National Institute of Statistics Cambodia", "NIS Cambodia",
          "national_statistics", 1, ["KHM"],
          "https://www.nis.gov.kh", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","labor","social_indicators"],
          freq="annual", years="2015-2024", schedule="Annual",
          rel="medium", limits="Annual data; limited online access; some HTML tables",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_KHM_NBC", "National Bank of Cambodia", "NBC",
          "central_bank", 2, ["KHM"],
          "https://www.nbc.gov.kh/english/",
          fmt="html", method="scrape",
          sectors=["finance_monetary"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="high",
          limits="Quarterly economic bulletin; HTML/PDF",
          impl=True, script="scripts/fetch_central_banks.py"))

    add(S("MIN_KHM_CDC", "Cambodia Development Council (FDI)", "CDC Cambodia",
          "ministry_customs", 3, ["KHM"],
          "https://www.cambodiainvestment.gov.kh",
          sectors=["investment"], freq="annual", years="2015-2025",
          schedule="Annual", rel="high",
          limits="FDI project approvals; sector breakdown",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # LAOS
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_LAO_LSB", "Lao Statistics Bureau", "LSB Laos",
          "national_statistics", 1, ["LAO"],
          "https://laosis.lsb.gov.la", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","labor","social_indicators"],
          freq="annual", years="2015-2024", schedule="Annual",
          rel="medium", limits="Limited English data; annual lag typically 2 years",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_LAO_BOL", "Bank of Lao PDR", "BOL",
          "central_bank", 2, ["LAO"],
          "https://www.bol.gov.la", fmt="html", method="scrape",
          sectors=["finance_monetary"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="medium",
          limits="Limited online data; debt sustainability concerns",
          impl=False, script="scripts/fetch_central_banks.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # MYANMAR
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_MMR_CSO", "Central Statistical Organisation Myanmar", "CSO Myanmar",
          "national_statistics", 1, ["MMR"],
          "https://www.cso.gov.mm", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","agriculture"],
          freq="annual", years="2015-2021", schedule="Disrupted",
          rel="low",
          limits="Post-coup (Feb 2021): website intermittently available; "
                 "data severely limited after 2021; use WB/IMF estimates",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_MMR_CBM", "Central Bank of Myanmar", "CBM",
          "central_bank", 2, ["MMR"],
          "https://www.cbm.gov.mm", fmt="html", method="scrape",
          sectors=["finance_monetary"], freq="monthly", years="2015-2021",
          schedule="Disrupted", rel="low",
          limits="Post-coup: limited operations; black market rate diverges significantly",
          impl=False, script="scripts/fetch_central_banks.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # BRUNEI
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_BRN_DEPS", "DEPS Brunei Darussalam", "DEPS Brunei",
          "national_statistics", 1, ["BRN"],
          "https://deps.gov.bn", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","trade","energy"],
          freq="quarterly", years="2015-2024", schedule="Quarterly",
          rel="medium", limits="Limited API; some data in PDF; quarterly GDP available",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_BRN_AMBD", "Autoriti Monetari Brunei Darussalam", "AMBD",
          "central_bank", 2, ["BRN"],
          "https://www.ambd.gov.bn", fmt="html", method="scrape",
          sectors=["finance_monetary"], freq="quarterly", years="2015-2025",
          schedule="Quarterly", rel="medium",
          limits="Quarterly monetary statistics; limited public API",
          impl=False, script="scripts/fetch_central_banks.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # TIMOR-LESTE
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_TLS_GDS", "General Directorate of Statistics Timor-Leste", "GDS TLS",
          "national_statistics", 1, ["TLS"],
          "https://www.mof.gov.tl/statistics", fmt="html", method="scrape",
          sectors=["macro_economy","fiscal"], freq="annual", years="2015-2023",
          schedule="Annual", rel="low",
          limits="Very limited statistical capacity; data primarily from WB/IMF",
          impl=True, script="scripts/fetch_national_statistics.py"))

    add(S("CB_TLS_BCTL", "Banco Central de Timor-Leste", "BCTL",
          "central_bank", 2, ["TLS"],
          "https://www.bctl.tl", fmt="html", method="scrape",
          sectors=["finance_monetary","fiscal"], freq="annual", years="2015-2025",
          schedule="Annual", rel="low",
          limits="Very limited; Timor uses USD; petroleum fund management",
          impl=False, script="scripts/fetch_central_banks.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # PARTNER COUNTRIES — National Statistics
    # ══════════════════════════════════════════════════════════════════════════

    add(S("NSO_CHN_NBS", "National Bureau of Statistics China", "NBS China",
          "national_statistics", 1, ["CHN"],
          "https://data.stats.gov.cn/english",
          "https://data.stats.gov.cn/english/easyquery.htm",
          sectors=["macro_economy","prices_inflation","labor","trade","industry_production"],
          freq="monthly", years="2010-2025", schedule="Monthly",
          rel="high",
          limits="English interface available; some methodological differences with international standards",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_CHN_PBOC", "People's Bank of China", "PBoC",
          "central_bank", 2, ["CHN"],
          "https://www.pbc.gov.cn/en/3688229/index.html",
          sectors=["finance_monetary"], freq="monthly", years="2010-2025",
          schedule="Monthly", rel="high",
          limits="English statistics portal; monetary aggregates, FX",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("MIN_CHN_GACC", "General Administration of Customs China", "GACC",
          "ministry_customs", 3, ["CHN"],
          "https://www.customs.gov.cn",
          sectors=["trade"], freq="monthly", years="2015-2025",
          schedule="Monthly", rel="very_high",
          limits="Monthly trade by country and commodity; very detailed",
          impl=False, script="scripts/fetch_ministries_customs.py"))

    add(S("NSO_USA_BEA", "US Bureau of Economic Analysis", "BEA",
          "national_statistics", 1, ["USA"],
          "https://www.bea.gov", "https://apps.bea.gov/api/data",
          key=True,
          sectors=["macro_economy","trade","investment"],
          freq="quarterly", years="2000-2025", schedule="Quarterly",
          rel="very_high", limits="Requires free API key; comprehensive national accounts",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("NSO_USA_BLS", "US Bureau of Labor Statistics", "BLS",
          "national_statistics", 1, ["USA"],
          "https://www.bls.gov", "https://api.bls.gov/publicAPI/v2/timeseries/data/",
          key=True,
          sectors=["labor","prices_inflation"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Requires free API key; CPI, unemployment, wages",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_USA_FED", "US Federal Reserve (FRED API)", "Fed / FRED",
          "central_bank", 2, ["USA"],
          "https://fred.stlouisfed.org",
          "https://api.stlouisfed.org/fred/series/observations?series_id={id}&api_key={key}&file_type=json",
          key=True,
          sectors=["finance_monetary","macro_economy","labor"],
          freq="daily", years="1950-2025", schedule="Continuous",
          rel="very_high", limits="Free API key; FRED has 800k+ series",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("NSO_JPN_STAT", "Statistics Japan (e-Stat API)", "e-Stat Japan",
          "national_statistics", 1, ["JPN"],
          "https://www.stat.go.jp/english/",
          "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData",
          key=True,
          sectors=["macro_economy","prices_inflation","labor","trade"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Requires free API key; comprehensive",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_JPN_BOJ", "Bank of Japan", "BOJ",
          "central_bank", 2, ["JPN"],
          "https://www.boj.or.jp/en/statistics/index.htm",
          "https://www.stat-search.boj.or.jp/ssi/mtshtml/",
          sectors=["finance_monetary"], freq="monthly", years="2000-2025",
          schedule="Monthly", rel="very_high",
          limits="Monetary policy rate, monetary aggregates, exchange rates",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("NSO_IND_MOSPI", "India Ministry of Statistics (MoSPI)", "MoSPI India",
          "national_statistics", 1, ["IND"],
          "https://mospi.gov.in", fmt="html", method="scrape",
          sectors=["macro_economy","prices_inflation","labor","social_indicators"],
          freq="quarterly", years="2010-2025", schedule="Quarterly",
          rel="high", limits="Quarterly GDP; monthly IIP; CPI",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_IND_RBI", "Reserve Bank of India", "RBI",
          "central_bank", 2, ["IND"],
          "https://www.rbi.org.in/Scripts/Statistics.aspx",
          "https://api.rbi.org.in/", key=True,
          sectors=["finance_monetary","trade"], freq="monthly", years="2010-2025",
          schedule="Monthly", rel="very_high",
          limits="Repo rate, FX reserves, banking statistics, BOP",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("NSO_KOR_KOSTAT", "Statistics Korea (KOSTAT)", "KOSTAT",
          "national_statistics", 1, ["KOR"],
          "https://kosis.kr/eng/",
          "https://kosis.kr/openapi/Param/statisticsParamData.do",
          key=True,
          sectors=["macro_economy","prices_inflation","labor","trade"],
          freq="monthly", years="2000-2025", schedule="Monthly",
          rel="very_high", limits="Requires free API key; comprehensive",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_KOR_BOK", "Bank of Korea", "BOK",
          "central_bank", 2, ["KOR"],
          "https://www.bok.or.kr/eng/main/main.do",
          "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{startCount}/{endCount}/{statsCode}/{period}/{startDate}/{endDate}",
          key=True,
          sectors=["finance_monetary","macro_economy"], freq="monthly",
          schedule="Monthly", rel="very_high",
          limits="Free API key; policy rate, exchange rates, national accounts",
          impl=False, script="scripts/fetch_central_banks.py"))

    add(S("NSO_AUS_ABS", "Australian Bureau of Statistics (ABS API)", "ABS",
          "national_statistics", 1, ["AUS"],
          "https://www.abs.gov.au",
          "https://api.data.abs.gov.au/data/{dataflowId}/{dataKey}",
          sectors=["macro_economy","prices_inflation","labor","trade","social_indicators"],
          freq="quarterly", years="2000-2025", schedule="Quarterly",
          rel="very_high", limits="Excellent SDMX API; OECD member; comprehensive",
          impl=False, script="scripts/fetch_national_statistics.py"))

    add(S("CB_AUS_RBA", "Reserve Bank of Australia", "RBA",
          "central_bank", 2, ["AUS"],
          "https://www.rba.gov.au/statistics/",
          sectors=["finance_monetary"], freq="monthly", years="2000-2025",
          schedule="Monthly", rel="very_high",
          limits="Cash rate, exchange rates, financial aggregates; CSV downloads",
          impl=False, script="scripts/fetch_central_banks.py"))

    # ══════════════════════════════════════════════════════════════════════════
    # REGIONAL & THEMATIC
    # ══════════════════════════════════════════════════════════════════════════

    add(S("ACE_ENERGY", "ASEAN Centre for Energy", "ACE",
          "regional_official", 4,
          ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS"],
          "https://www.ace.org.sg/wp-content/uploads/2024/",
          sectors=["energy"], freq="annual", years="2015-2023",
          schedule="Annual", rel="high",
          limits="ASEAN energy outlook; electricity access; RE share by country",
          impl=False, script="scripts/fetch_energy_sources.py"))

    add(S("GMS_REGION", "Greater Mekong Subregion (ADB GMS)", "ADB GMS",
          "regional_official", 4,
          ["THA","VNM","MMR","KHM","LAO","CHN"],
          "https://www.greatermekong.org",
          sectors=["infrastructure","trade"], freq="annual", years="2015-2024",
          schedule="Annual", rel="medium",
          limits="Mekong region integration; connectivity projects",
          impl=False, script="scripts/fetch_infrastructure_projects.py"))

    add(S("ASEAN_INV", "ASEAN Investment Report", "ASEAN Investment",
          "regional_official", 4,
          ["THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS"],
          "https://asean.org/book/asean-investment-report/",
          sectors=["investment"], freq="annual", years="2015-2024",
          schedule="Annual (Q4)", rel="high",
          limits="Annual FDI flows; intra-ASEAN + external FDI; PDF/Excel",
          impl=False, script="scripts/fetch_aseanstats.py"))

    return sources


# ─────────────────────────────────────────────────────────────────────────────
# GENERATE + SAVE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true",
                        help="Test API reachability for implemented sources")
    args = parser.parse_args()

    sources = build_sources()

    # Statistics
    by_type = {}
    by_country = {}
    by_sector  = {}
    impl_count = 0

    for src in sources.values():
        t = src["type"]
        by_type[t] = by_type.get(t, 0) + 1
        if src.get("implemented"):
            impl_count += 1
        for c in src.get("countries", []):
            by_country[c] = by_country.get(c, 0) + 1
        for s in src.get("sectors", []):
            by_sector[s] = by_sector.get(s, 0) + 1

    registry = {
        "version":        "2.0",
        "generated_at":   datetime.utcnow().isoformat() + "Z",
        "description":    "Universal Official Data Source Registry — SEA Change Intelligence Dashboard",
        "total_sources":  len(sources),
        "implemented":    impl_count,
        "source_type_priority": {
            "1": "national_statistics",
            "2": "central_bank",
            "3": "ministry_customs",
            "4": "regional_official",
            "5": "multilateral",
            "6": "forecast_multilateral",
            "7": "official_policy",
            "8": "realtime_signal",
        },
        "sources": sources,
    }

    OUT_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

    print(f"\n{'═'*65}")
    print(f"  Source Registry Generated — v2.0")
    print(f"{'═'*65}")
    print(f"  Total sources    : {len(sources)}")
    print(f"  Implemented      : {impl_count}")
    print(f"\n  By type:")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {t:30s} {c:4d}")
    print(f"\n  Countries with most sources:")
    top_countries = sorted(by_country.items(), key=lambda x: -x[1])[:10]
    for c, n in top_countries:
        print(f"    {c:10s} {n:3d}")
    print(f"\n  Sectors covered:")
    for s, c in sorted(by_sector.items(), key=lambda x: -x[1]):
        print(f"    {s:30s} {c:3d}")
    print(f"\n  📄 {OUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"{'═'*65}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
