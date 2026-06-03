#!/usr/bin/env python3
"""
scripts/build_indicator_registry.py
────────────────────────────────────────────────────────────────────────────
GENERATES pipeline/data/processed/indicator_registry.json from Python source.

This script IS the indicator registry — edit here, run to regenerate.

Contains 200+ indicators across all 17 sectors, with:
  - Standard indicator code (e.g. "GDP_GROWTH")
  - All source API codes (WB, IMF, ILO, FAO, ITU, etc.)
  - Unit, frequency, plausible range
  - Priority source list
  - Notes for interpretation

USAGE
  python scripts/build_indicator_registry.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_FILE     = PROJECT_ROOT / "pipeline" / "data" / "processed" / "indicator_registry.json"

# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def I(code, name, unit, freq="annual", wb=None, imf=None, ilo=None,
      fao=None, itu=None, oecd=None, sources=None, plausible=None,
      note="", dashboard=False):
    """Define one indicator compactly."""
    return {
        "code": code, "name": name, "unit": unit,
        "frequency": freq, "annual_ok": freq in ("annual","quarterly","monthly"),
        "wb_code":   wb,   "imf_code":  imf, "ilo_code": ilo,
        "fao_code":  fao,  "itu_code":  itu, "oecd_code": oecd,
        "sources_priority": sources or [],
        "plausible_range":  plausible,
        "description": note,
        "show_on_dashboard": dashboard,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

def build_sectors() -> dict:
    return {

        # ══════════════════════════════════════════════════════════════════════
        "macro_economy": {
            "sector_name": "Macro Economy",
            "sector_code": "MACRO",
            "description": "GDP, growth rates, national accounts, savings, current account",
            "indicators": {
                "GDP_GROWTH": I("GDP_GROWTH","Real GDP Growth Rate","% YoY",
                    wb="NY.GDP.MKTP.KD.ZG", imf="NGDP_RPCH",
                    sources=["NSO_national","WB_API","IMF_WEO","ADB_ADO"],
                    plausible=(-30,20), note="Real GDP growth year over year", dashboard=True),

                "GDP_GROWTH_QUARTERLY": I("GDP_GROWTH_QUARTERLY","Real GDP Growth Quarterly","% YoY","quarterly",
                    sources=["NSO_national"],
                    plausible=(-30,20), note="Quarterly GDP growth from national statistics"),

                "GDP_GROWTH_QOQ": I("GDP_GROWTH_QOQ","GDP Growth Quarter-on-Quarter","% QoQ","quarterly",
                    sources=["NSO_national"],
                    plausible=(-15,15), note="Quarter-over-quarter seasonally adjusted"),

                "GDP_NOMINAL_USD": I("GDP_NOMINAL_USD","GDP Nominal (USD Billion)","USD billion",
                    wb="NY.GDP.MKTP.CD", imf="NGDPD",
                    sources=["WB_API","IMF_WEO"],
                    plausible=(0.5,30000), dashboard=True),

                "GDP_PPP": I("GDP_PPP","GDP PPP (Int$ Billion)","Int$ billion",
                    wb="NY.GDP.MKTP.PP.CD", imf="PPPGDP",
                    sources=["WB_API","IMF_WEO"],
                    plausible=(1,35000)),

                "GDP_PER_CAPITA_USD": I("GDP_PER_CAPITA_USD","GDP Per Capita (USD)","USD",
                    wb="NY.GDP.PCAP.CD", imf="NGDPDPC",
                    sources=["WB_API","IMF_WEO"],
                    plausible=(400,90000), dashboard=True),

                "GDP_PER_CAPITA_PPP": I("GDP_PER_CAPITA_PPP","GDP Per Capita PPP (Int$)","Int$",
                    wb="NY.GDP.PCAP.PP.CD", imf="PPPPC",
                    sources=["WB_API","IMF_WEO"],
                    plausible=(1000,120000)),

                "GDP_SERVICES_PCT": I("GDP_SERVICES_PCT","Services Value Added (% GDP)","% of GDP",
                    wb="NV.SRV.TOTL.ZS",
                    sources=["WB_API"], plausible=(10,90)),

                "GDP_INDUSTRY_PCT": I("GDP_INDUSTRY_PCT","Industry Value Added (% GDP)","% of GDP",
                    wb="NV.IND.TOTL.ZS",
                    sources=["WB_API"], plausible=(5,80)),

                "GDP_AGRICULTURE_PCT": I("GDP_AGRICULTURE_PCT","Agriculture Value Added (% GDP)","% of GDP",
                    wb="NV.AGR.TOTL.ZS",
                    sources=["WB_API"], plausible=(0.5,50)),

                "GNI_PER_CAPITA": I("GNI_PER_CAPITA","GNI Per Capita Atlas Method (USD)","USD",
                    wb="NY.GNP.PCAP.CD",
                    sources=["WB_API"], plausible=(400,90000)),

                "CURRENT_ACCOUNT_USD": I("CURRENT_ACCOUNT_USD","Current Account Balance (USD Billion)","USD billion",
                    wb="BN.CAB.XOKA.CD",
                    sources=["WB_API","IMF_DATA_API","CB_national"], plausible=(-500,500)),

                "CURRENT_ACCOUNT_GDP": I("CURRENT_ACCOUNT_GDP","Current Account Balance (% GDP)","% of GDP",
                    wb="BN.CAB.XOKA.GD.ZS", imf="BCA_NGDPD",
                    sources=["WB_API","IMF_WEO","CB_national"],
                    plausible=(-30,30), dashboard=True),

                "NATIONAL_SAVINGS_GDP": I("NATIONAL_SAVINGS_GDP","Gross National Savings (% GDP)","% of GDP",
                    wb="NY.GNS.ICTR.ZS", imf="NGSD_NGDP",
                    sources=["WB_API","IMF_WEO"], plausible=(0,60)),

                "GROSS_CAPITAL_FORMATION_GDP": I("GROSS_CAPITAL_FORMATION_GDP","Gross Capital Formation (% GDP)","% of GDP",
                    wb="NE.GDI.TOTL.ZS",
                    sources=["WB_API"], plausible=(5,65)),

                "PRIVATE_CONSUMPTION_GDP": I("PRIVATE_CONSUMPTION_GDP","Household Consumption (% GDP)","% of GDP",
                    wb="NE.CON.PRVT.ZS",
                    sources=["WB_API"], plausible=(20,90)),

                "REMITTANCES_GDP": I("REMITTANCES_GDP","Remittances Received (% GDP)","% of GDP",
                    wb="BX.TRF.PWKR.DT.GD.ZS",
                    sources=["WB_API","CB_PHL_BSP"],
                    plausible=(0,35), note="Important for PHL, VNM, MMR"),

                "REMITTANCES_USD": I("REMITTANCES_USD","Remittances Received (USD Billion)","USD billion",
                    wb="BX.TRF.PWKR.CD.DT",
                    sources=["WB_API"], plausible=(0,40)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "prices_inflation": {
            "sector_name": "Prices & Inflation",
            "sector_code": "PRICES",
            "description": "Consumer prices, producer prices, commodity prices",
            "indicators": {
                "CPI_INFLATION": I("CPI_INFLATION","CPI Inflation Rate","% YoY","monthly",
                    wb="FP.CPI.TOTL.ZG", imf="PCPIPCH",
                    sources=["NSO_national","WB_API","IMF_WEO"],
                    plausible=(-5,100), dashboard=True),

                "CPI_MONTHLY": I("CPI_MONTHLY","CPI Monthly Change","% MoM","monthly",
                    sources=["NSO_national"],
                    plausible=(-5,20)),

                "CPI_INDEX": I("CPI_INDEX","CPI Index Level","Index",
                    wb="FP.CPI.TOTL",
                    sources=["NSO_national","WB_API"], plausible=(50,500)),

                "CORE_INFLATION": I("CORE_INFLATION","Core Inflation (ex food & energy)","% YoY","monthly",
                    sources=["NSO_national","CB_national"],
                    plausible=(-5,30), note="Excludes food and energy"),

                "FOOD_INFLATION": I("FOOD_INFLATION","Food Price Inflation","% YoY","monthly",
                    sources=["NSO_national"],
                    plausible=(-10,50)),

                "FOOD_PRICE_INDEX_FAO": I("FOOD_PRICE_INDEX_FAO","FAO Food Price Index","Index 2014-16=100","monthly",
                    fao="FPPI",
                    sources=["FAO_FAOSTAT"], plausible=(50,200)),

                "PPI": I("PPI","Producer Price Index Change","% YoY","monthly",
                    sources=["NSO_national","CB_national"],
                    plausible=(-20,50)),

                "RICE_PRICE_USD": I("RICE_PRICE_USD","Rice Wholesale Price (USD/tonne)","USD per tonne","monthly",
                    sources=["FAO_FAOSTAT","WB_COMMODITY"],
                    plausible=(100,1500), note="Thai 25% broken as benchmark"),

                "DEFLATOR_GDP": I("DEFLATOR_GDP","GDP Deflator","% YoY",
                    wb="NY.GDP.DEFL.KD.ZG",
                    sources=["WB_API"], plausible=(-10,50)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "labor": {
            "sector_name": "Labor & Employment",
            "sector_code": "LABOR",
            "description": "Unemployment, employment, wages, labor force",
            "indicators": {
                "UNEMPLOYMENT_RATE": I("UNEMPLOYMENT_RATE","Unemployment Rate","% of labor force","quarterly",
                    wb="SL.UEM.TOTL.ZS", imf="LUR",
                    ilo="UNE_DEAP_SEX_AGE_EDU_RT",
                    sources=["NSO_national","ILO","WB_API","IMF_WEO"],
                    plausible=(0.1,40), dashboard=True),

                "UNEMPLOYMENT_YOUTH": I("UNEMPLOYMENT_YOUTH","Youth Unemployment Rate (15-24)","% of youth labor","annual",
                    wb="SL.UEM.1524.ZS",
                    ilo="UNE_DEAP_SEX_AGE_EDU_RT",
                    sources=["ILO","WB_API"], plausible=(0,70)),

                "LABOR_FORCE_PARTICIPATION": I("LABOR_FORCE_PARTICIPATION","Labor Force Participation Rate","% of pop","annual",
                    wb="SL.TLF.CACT.ZS",
                    ilo="EAP_DWAP_SEX_AGE_RT",
                    sources=["NSO_national","ILO","WB_API"],
                    plausible=(30,90)),

                "LABOR_FORCE_TOTAL": I("LABOR_FORCE_TOTAL","Total Labor Force (millions)","millions","annual",
                    wb="SL.TLF.TOTL.IN",
                    sources=["WB_API"], plausible=(0.1,800)),

                "EMPLOYMENT_AGRICULTURE": I("EMPLOYMENT_AGRICULTURE","Employment in Agriculture (%)","% of total","annual",
                    wb="SL.AGR.EMPL.ZS",
                    ilo="EMP_TEMP_SEX_ECO_NB_A",
                    sources=["ILO","WB_API"], plausible=(1,80)),

                "EMPLOYMENT_SERVICES": I("EMPLOYMENT_SERVICES","Employment in Services (%)","% of total","annual",
                    wb="SL.SRV.EMPL.ZS",
                    sources=["WB_API"], plausible=(10,85)),

                "EMPLOYMENT_INDUSTRY": I("EMPLOYMENT_INDUSTRY","Employment in Industry (%)","% of total","annual",
                    wb="SL.IND.EMPL.ZS",
                    sources=["WB_API"], plausible=(5,45)),

                "WAGE_MINIMUM": I("WAGE_MINIMUM","Minimum Wage (USD/month)","USD per month","annual",
                    sources=["NSO_national","ILO"],
                    plausible=(10,3000)),

                "WAGE_AVERAGE_MANUFACTURING": I("WAGE_AVERAGE_MANUFACTURING","Average Manufacturing Wage","national currency/month","annual",
                    sources=["NSO_national","ILO"],
                    plausible=None),

                "LABOR_PRODUCTIVITY_GROWTH": I("LABOR_PRODUCTIVITY_GROWTH","Labor Productivity Growth","% YoY","annual",
                    ilo="LAP_2EMP_SEX_ECO_RT_A",
                    sources=["ILO"], plausible=(-20,20)),

                "INFORMAL_EMPLOYMENT": I("INFORMAL_EMPLOYMENT","Informal Employment Rate","% of total","annual",
                    ilo="EMP_TEMP_SEX_ECO_NB_A",
                    sources=["ILO","NSO_national"],
                    plausible=(5,95), note="High in SEA; key development indicator"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "trade": {
            "sector_name": "Trade",
            "sector_code": "TRADE",
            "description": "Exports, imports, trade balance, bilateral flows, dependency",
            "indicators": {
                "EXPORTS_USD": I("EXPORTS_USD","Total Exports (USD Billion)","USD billion","monthly",
                    wb="NE.EXP.GNFS.CD",
                    sources=["MIN_customs","NSO_national","WB_API","UN_COMTRADE"],
                    plausible=(0.1,5000), dashboard=True),

                "IMPORTS_USD": I("IMPORTS_USD","Total Imports (USD Billion)","USD billion","monthly",
                    wb="NE.IMP.GNFS.CD",
                    sources=["MIN_customs","NSO_national","WB_API","UN_COMTRADE"],
                    plausible=(0.1,5000), dashboard=True),

                "TRADE_BALANCE_USD": I("TRADE_BALANCE_USD","Trade Balance (USD Billion)","USD billion","monthly",
                    sources=["computed"], plausible=(-500,500), dashboard=True),

                "TRADE_OPENNESS": I("TRADE_OPENNESS","Trade Openness (Exports+Imports / GDP)","% of GDP","annual",
                    wb="NE.TRD.GNFS.ZS",
                    sources=["WB_API"], plausible=(0,400)),

                "EXPORTS_TO_CHN": I("EXPORTS_TO_CHN","Exports to China (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE","MIN_customs"], plausible=(0,1000)),

                "IMPORTS_FROM_CHN": I("IMPORTS_FROM_CHN","Imports from China (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE","MIN_customs"], plausible=(0,1000)),

                "EXPORTS_TO_USA": I("EXPORTS_TO_USA","Exports to USA (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE","MIN_customs"], plausible=(0,1000)),

                "IMPORTS_FROM_USA": I("IMPORTS_FROM_USA","Imports from USA (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE"], plausible=(0,1000)),

                "EXPORTS_TO_JPN": I("EXPORTS_TO_JPN","Exports to Japan (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE","MIN_customs"], plausible=(0,500)),

                "EXPORTS_TO_EU": I("EXPORTS_TO_EU","Exports to EU (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE"], plausible=(0,500)),

                "EXPORTS_TO_KOR": I("EXPORTS_TO_KOR","Exports to South Korea (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE"], plausible=(0,200)),

                "EXPORTS_TO_AUS": I("EXPORTS_TO_AUS","Exports to Australia (USD Billion)","USD billion","annual",
                    sources=["UN_COMTRADE"], plausible=(0,100)),

                "TRADE_DEPENDENCY_CHN": I("TRADE_DEPENDENCY_CHN","China Trade Dependency","% of total trade","annual",
                    sources=["computed"],
                    plausible=(0,80), dashboard=True,
                    note=">40% high; 20-40% medium; <20% low"),

                "TRADE_DEPENDENCY_USA": I("TRADE_DEPENDENCY_USA","USA Trade Dependency","% of total trade","annual",
                    sources=["computed"], plausible=(0,60)),

                "EXPORTS_TOP_PRODUCT": I("EXPORTS_TOP_PRODUCT","Top Export Product Category","HS2 code","annual",
                    sources=["UN_COMTRADE"],
                    note="Main export commodity (electronics, agriculture, energy etc.)"),

                "SERVICES_EXPORTS_USD": I("SERVICES_EXPORTS_USD","Services Exports (USD Billion)","USD billion","annual",
                    wb="BX.GSR.NFSV.CD",
                    sources=["WB_API","CB_national"], plausible=(0,1000)),

                "SERVICES_IMPORTS_USD": I("SERVICES_IMPORTS_USD","Services Imports (USD Billion)","USD billion","annual",
                    wb="BM.GSR.NFSV.CD",
                    sources=["WB_API","CB_national"], plausible=(0,1000)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "investment": {
            "sector_name": "Investment & FDI",
            "sector_code": "INVEST",
            "indicators": {
                "FDI_INFLOWS_USD": I("FDI_INFLOWS_USD","FDI Net Inflows (USD Billion)","USD billion","annual",
                    wb="BX.KLT.DINV.CD.WD",
                    sources=["CB_national","NSO_national","WB_API"],
                    plausible=(-10,300), dashboard=True),

                "FDI_PCT_GDP": I("FDI_PCT_GDP","FDI Net Inflows (% GDP)","% of GDP","annual",
                    wb="BX.KLT.DINV.WD.GD.ZS",
                    sources=["WB_API","CB_national"],
                    plausible=(-10,30), dashboard=True),

                "FDI_OUTFLOWS_USD": I("FDI_OUTFLOWS_USD","FDI Outflows (USD Billion)","USD billion","annual",
                    wb="BM.KLT.DINV.CD.WD",
                    sources=["WB_API","CB_national"], plausible=(-50,200)),

                "FDI_STOCK_INWARD_USD": I("FDI_STOCK_INWARD_USD","FDI Inward Stock (USD Billion)","USD billion","annual",
                    sources=["UNCTAD_STATS"], plausible=(0,3000)),

                "GROSS_FIXED_CAPITAL_GDP": I("GROSS_FIXED_CAPITAL_GDP","Gross Fixed Capital Formation (% GDP)","% of GDP","annual",
                    wb="NE.GDI.FTOT.ZS",
                    sources=["WB_API","NSO_national"],
                    plausible=(5,60)),

                "PORTFOLIO_INVESTMENT": I("PORTFOLIO_INVESTMENT","Portfolio Investment Net (% GDP)","% of GDP","annual",
                    sources=["CB_national","IMF_DATA_API"], plausible=(-20,20)),

                "FDI_BY_CHINA": I("FDI_BY_CHINA","FDI from China (USD Billion)","USD billion","annual",
                    sources=["UNCTAD_STATS","MIN_investment"],
                    plausible=(0,100), note="BRI-related flows important"),

                "FDI_APPROVED_USD": I("FDI_APPROVED_USD","Approved FDI Projects (USD Billion)","USD billion","annual",
                    sources=["MIN_investment"],
                    plausible=(0,200), note="Approved vs realized may differ"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "finance_monetary": {
            "sector_name": "Finance & Monetary",
            "sector_code": "FINANCE",
            "indicators": {
                "EXCHANGE_RATE_USD": I("EXCHANGE_RATE_USD","Exchange Rate (LCU per USD)","LCU per USD","daily",
                    wb="PA.NUS.FCRF",
                    sources=["CB_national","WB_API","IMF_DATA_API"],
                    plausible=(0.0001,100000), dashboard=True),

                "EXCHANGE_RATE_YOY": I("EXCHANGE_RATE_YOY","Exchange Rate Change YoY","% change","monthly",
                    sources=["computed","CB_national"], plausible=(-60,60)),

                "POLICY_INTEREST_RATE": I("POLICY_INTEREST_RATE","Central Bank Policy Rate","% p.a.","monthly",
                    sources=["CB_national","IMF_DATA_API"],
                    plausible=(-2,30), dashboard=True),

                "LENDING_RATE": I("LENDING_RATE","Bank Lending Rate","% p.a.","monthly",
                    wb="FR.INR.LEND",
                    sources=["CB_national","WB_API"], plausible=(0,50)),

                "DEPOSIT_RATE": I("DEPOSIT_RATE","Bank Deposit Rate","% p.a.","monthly",
                    wb="FR.INR.DPST",
                    sources=["CB_national","WB_API"], plausible=(-2,30)),

                "REAL_INTEREST_RATE": I("REAL_INTEREST_RATE","Real Interest Rate","% p.a.","annual",
                    wb="FR.INR.RINR",
                    sources=["WB_API"], plausible=(-30,30)),

                "MONEY_SUPPLY_M2": I("MONEY_SUPPLY_M2","Broad Money Growth (M2)","% YoY","monthly",
                    wb="FM.LBL.BMNY.ZG",
                    sources=["CB_national","WB_API"], plausible=(-10,50)),

                "MONEY_SUPPLY_M2_GDP": I("MONEY_SUPPLY_M2_GDP","Broad Money (% GDP)","% of GDP","annual",
                    wb="FM.LBL.BMNY.GD.ZS",
                    sources=["WB_API"], plausible=(0,400)),

                "CREDIT_PRIVATE_GDP": I("CREDIT_PRIVATE_GDP","Domestic Credit to Private Sector (% GDP)","% of GDP","annual",
                    wb="FS.AST.PRVT.GD.ZS",
                    sources=["WB_API","CB_national"], plausible=(0,250)),

                "CREDIT_GROWTH": I("CREDIT_GROWTH","Private Sector Credit Growth","% YoY","monthly",
                    sources=["CB_national","BIS_STATS"], plausible=(-20,60)),

                "FOREIGN_RESERVES": I("FOREIGN_RESERVES","Foreign Exchange Reserves (USD Billion)","USD billion","monthly",
                    wb="FI.RES.TOTL.CD",
                    sources=["CB_national","WB_API","IMF_DATA_API"],
                    plausible=(0.01,4000), dashboard=True),

                "IMPORT_COVER_MONTHS": I("IMPORT_COVER_MONTHS","Reserves as Months of Imports","months","annual",
                    sources=["CB_national","IMF_DATA_API"], plausible=(0,100)),

                "NPL_RATIO": I("NPL_RATIO","Non-Performing Loan Ratio","% of gross loans","annual",
                    wb="FB.AST.NPER.ZS",
                    sources=["WB_API","CB_national"], plausible=(0,50)),

                "STOCK_MARKET_INDEX": I("STOCK_MARKET_INDEX","Stock Market Index Level","Index points","daily",
                    sources=["exchange_official"], plausible=None),

                "STOCK_MARKET_CAP_GDP": I("STOCK_MARKET_CAP_GDP","Stock Market Cap (% GDP)","% of GDP","annual",
                    wb="CM.MKT.LCAP.GD.ZS",
                    sources=["WB_API"], plausible=(0,400)),

                "INSURANCE_PENETRATION": I("INSURANCE_PENETRATION","Insurance Penetration (% GDP)","% of GDP","annual",
                    sources=["CB_national"], plausible=(0,15)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "fiscal": {
            "sector_name": "Fiscal & Government Finance",
            "sector_code": "FISCAL",
            "indicators": {
                "FISCAL_BALANCE_GDP": I("FISCAL_BALANCE_GDP","Fiscal Balance (% GDP)","% of GDP","annual",
                    wb="GC.BAL.CASH.GD.ZS", imf="GGXCNL_NGDP",
                    sources=["MOF_national","WB_API","IMF_WEO"],
                    plausible=(-80,20), dashboard=True),

                "PUBLIC_DEBT_GDP": I("PUBLIC_DEBT_GDP","Government Gross Debt (% GDP)","% of GDP","annual",
                    wb="GC.DOD.TOTL.GD.ZS", imf="GGXWDG_NGDP",
                    sources=["MOF_national","WB_API","IMF_WEO"],
                    plausible=(0,300), dashboard=True),

                "EXTERNAL_DEBT_GDP": I("EXTERNAL_DEBT_GDP","External Debt Stocks (% GDP)","% of GDP","annual",
                    wb="DT.DOD.DECT.GD.ZS",
                    sources=["WB_API"], plausible=(0,300)),

                "GOVT_REVENUE_GDP": I("GOVT_REVENUE_GDP","Government Revenue (% GDP)","% of GDP","annual",
                    wb="GC.REV.TOTL.GD.ZS", imf="GGR_NGDP",
                    sources=["MOF_national","WB_API","IMF_WEO"],
                    plausible=(5,70)),

                "GOVT_EXPENDITURE_GDP": I("GOVT_EXPENDITURE_GDP","Government Expenditure (% GDP)","% of GDP","annual",
                    wb="GC.XPN.TOTL.GD.ZS", imf="GGX_NGDP",
                    sources=["MOF_national","WB_API","IMF_WEO"],
                    plausible=(5,80)),

                "TAX_REVENUE_GDP": I("TAX_REVENUE_GDP","Tax Revenue (% GDP)","% of GDP","annual",
                    wb="GC.TAX.TOTL.GD.ZS", imf="GGR_NGDP",
                    sources=["MOF_national","WB_API","IMF_WEO"],
                    plausible=(2,50)),

                "CAPITAL_EXPENDITURE_GDP": I("CAPITAL_EXPENDITURE_GDP","Capital Expenditure (% GDP)","% of GDP","annual",
                    sources=["MOF_national","IMF_DATA_API"], plausible=(0,20)),

                "MILITARY_EXPENDITURE_GDP": I("MILITARY_EXPENDITURE_GDP","Military Expenditure (% GDP)","% of GDP","annual",
                    wb="MS.MIL.XPND.GD.ZS",
                    sources=["WB_API"], plausible=(0,10)),

                "PRIMARY_BALANCE_GDP": I("PRIMARY_BALANCE_GDP","Primary Fiscal Balance (% GDP)","% of GDP","annual",
                    imf="GGXONLB_NGDP",
                    sources=["IMF_WEO"], plausible=(-30,20)),

                "DEBT_SERVICE_GDP": I("DEBT_SERVICE_GDP","Debt Service (% GDP)","% of GDP","annual",
                    wb="DT.TDS.DECT.GN.ZS",
                    sources=["WB_API"], plausible=(0,30)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "tourism": {
            "sector_name": "Tourism",
            "sector_code": "TOURISM",
            "indicators": {
                "TOURIST_ARRIVALS": I("TOURIST_ARRIVALS","International Tourist Arrivals (millions)","millions","monthly",
                    wb="ST.INT.ARVL",
                    sources=["TOUR_national","WB_API","UNWTO"],
                    plausible=(0,1500), dashboard=True),

                "TOURIST_ARRIVALS_MONTHLY": I("TOURIST_ARRIVALS_MONTHLY","Tourist Arrivals Monthly (thousands)","thousands","monthly",
                    sources=["TOUR_national"],
                    plausible=(0,5000)),

                "TOURISM_RECEIPTS_USD": I("TOURISM_RECEIPTS_USD","Tourism Receipts (USD Billion)","USD billion","annual",
                    wb="ST.INT.RCPT.CD",
                    sources=["TOUR_national","WB_API","UNWTO"],
                    plausible=(0.01,200), dashboard=True),

                "TOURISM_PCT_GDP": I("TOURISM_PCT_GDP","Tourism Revenue (% GDP)","% of GDP","annual",
                    sources=["computed","TOUR_national","WB_API"],
                    plausible=(0.1,50)),

                "TOURISM_SPEND_PER_VISITOR": I("TOURISM_SPEND_PER_VISITOR","Avg Spend Per Tourist (USD)","USD per visitor","annual",
                    sources=["TOUR_national","UNWTO"],
                    plausible=(50,5000)),

                "HOTEL_OCCUPANCY": I("HOTEL_OCCUPANCY","Hotel Occupancy Rate","% of rooms","monthly",
                    sources=["TOUR_national"],
                    plausible=(0,100)),

                "TOP_TOURIST_ORIGIN": I("TOP_TOURIST_ORIGIN","Top Tourist Origin Country","country name","annual",
                    sources=["TOUR_national"],
                    note="Main source market for inbound tourism"),

                "TOURISM_EMPLOYMENT_PCT": I("TOURISM_EMPLOYMENT_PCT","Tourism Employment (% total)","% of total","annual",
                    sources=["TOUR_national","ILO"],
                    plausible=(0,25)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "industry_production": {
            "sector_name": "Industry & Production",
            "sector_code": "INDUSTRY",
            "indicators": {
                "INDUSTRIAL_PRODUCTION": I("INDUSTRIAL_PRODUCTION","Industrial Production Index Change","% YoY","monthly",
                    sources=["NSO_national"],
                    plausible=(-40,40), dashboard=True),

                "MANUFACTURING_PCT_GDP": I("MANUFACTURING_PCT_GDP","Manufacturing Value Added (% GDP)","% of GDP","annual",
                    wb="NV.IND.MANF.ZS",
                    sources=["WB_API","NSO_national"],
                    plausible=(2,50)),

                "MANUFACTURING_VALUE_ADDED": I("MANUFACTURING_VALUE_ADDED","Manufacturing Value Added (USD Billion)","USD billion","annual",
                    wb="NV.IND.MANF.CD",
                    sources=["WB_API"], plausible=(0,5000)),

                "PMI_MANUFACTURING": I("PMI_MANUFACTURING","Manufacturing PMI","Index (50=neutral)","monthly",
                    sources=["SPGlobal_PMI"],
                    plausible=(20,65),
                    note="S&P Global/IHS Markit PMI; >50=expansion; available for THA, VNM, MYS, IDN, PHL, SGP"),

                "EXPORTS_HIGH_TECH_PCT": I("EXPORTS_HIGH_TECH_PCT","High-Tech Exports (% mfg exports)","% of mfg exports","annual",
                    wb="TX.VAL.TECH.MF.ZS",
                    sources=["WB_API","NSO_national"],
                    plausible=(0,80)),

                "EXPORTS_HIGH_TECH_USD": I("EXPORTS_HIGH_TECH_USD","High-Tech Exports (USD Billion)","USD billion","annual",
                    wb="TX.VAL.TECH.CD",
                    sources=["WB_API"], plausible=(0,1000)),

                "SEMICONDUCTOR_EXPORTS": I("SEMICONDUCTOR_EXPORTS","Semiconductor/Electronics Exports (USD Billion)","USD billion","annual",
                    sources=["NSO_national","UN_COMTRADE"],
                    plausible=(0,500), note="Critical for SGP, MYS, PHL, THA, VNM"),

                "CAPACITY_UTILIZATION": I("CAPACITY_UTILIZATION","Manufacturing Capacity Utilization","% of capacity","quarterly",
                    sources=["NSO_national"],
                    plausible=(30,100)),

                "MINING_PRODUCTION": I("MINING_PRODUCTION","Mining/Energy Production Index Change","% YoY","annual",
                    sources=["NSO_national","MIN_energy"],
                    plausible=(-30,30)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "agriculture": {
            "sector_name": "Agriculture & Food",
            "sector_code": "AGRI",
            "indicators": {
                "AGRICULTURE_PCT_GDP": I("AGRICULTURE_PCT_GDP","Agriculture Value Added (% GDP)","% of GDP","annual",
                    wb="NV.AGR.TOTL.ZS",
                    sources=["WB_API","NSO_national"],
                    plausible=(0.5,60), dashboard=True),

                "RICE_PRODUCTION_KT": I("RICE_PRODUCTION_KT","Rice Production (thousand tonnes)","thousand tonnes","annual",
                    fao="QCL",
                    sources=["FAO_FAOSTAT","NSO_national"],
                    plausible=(0,90000), note="Critical for THA, VNM, IDN, MMR"),

                "RICE_EXPORTS_USD": I("RICE_EXPORTS_USD","Rice Exports (USD Million)","USD million","annual",
                    sources=["FAO_FAOSTAT","NSO_national"],
                    plausible=(0,5000)),

                "RUBBER_PRODUCTION_KT": I("RUBBER_PRODUCTION_KT","Natural Rubber Production (kt)","thousand tonnes","annual",
                    fao="QCL",
                    sources=["FAO_FAOSTAT","NSO_national"],
                    plausible=(0,5000), note="THA and IDN are top producers"),

                "PALM_OIL_PRODUCTION_KT": I("PALM_OIL_PRODUCTION_KT","Palm Oil Production (kt)","thousand tonnes","annual",
                    fao="QCL",
                    sources=["FAO_FAOSTAT","NSO_national"],
                    plausible=(0,50000), note="IDN and MYS = 85% of world supply"),

                "FOOD_EXPORTS_USD": I("FOOD_EXPORTS_USD","Food Exports (USD Billion)","USD billion","annual",
                    wb="TX.VAL.FOOD.ZS.UN",
                    sources=["WB_API","FAO_FAOSTAT"], plausible=(0,100)),

                "FOOD_IMPORTS_USD": I("FOOD_IMPORTS_USD","Food Imports (USD Billion)","USD billion","annual",
                    wb="TM.VAL.FOOD.ZS.UN",
                    sources=["WB_API"], plausible=(0,100)),

                "ARABLE_LAND_PCT": I("ARABLE_LAND_PCT","Arable Land (% land area)","% of land","annual",
                    wb="AG.LND.ARBL.ZS",
                    sources=["WB_API"], plausible=(0,60)),

                "FOOD_SECURITY_INDEX": I("FOOD_SECURITY_INDEX","Global Food Security Index","Score 0-100","annual",
                    sources=["EIU_GFSI"],
                    plausible=(0,100)),

                "FERTILIZER_USE": I("FERTILIZER_USE","Fertilizer Consumption (kg/ha arable)","kg per ha","annual",
                    wb="AG.CON.FERT.ZS",
                    sources=["WB_API"], plausible=(0,1500)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "energy": {
            "sector_name": "Energy",
            "sector_code": "ENERGY",
            "indicators": {
                "RENEWABLE_ENERGY_SHARE": I("RENEWABLE_ENERGY_SHARE","Renewable Energy Share","% of total final energy","annual",
                    wb="EG.FEC.RNEW.ZS",
                    sources=["ENERGY_WB","ENERGY_IEA"],
                    plausible=(0,100), dashboard=True),

                "ELECTRICITY_ACCESS": I("ELECTRICITY_ACCESS","Access to Electricity (%)","% of population","annual",
                    wb="EG.ELC.ACCS.ZS",
                    sources=["ENERGY_WB","ENERGY_IEA"],
                    plausible=(0,100), dashboard=True),

                "ENERGY_INTENSITY": I("ENERGY_INTENSITY","Energy Intensity (MJ/$GDP PPP)","MJ per $2017 PPP GDP","annual",
                    wb="EG.EGY.PRIM.PP.KD",
                    sources=["ENERGY_WB","ENERGY_IEA"],
                    plausible=(1,25)),

                "ELECTRICITY_PRODUCTION_GWH": I("ELECTRICITY_PRODUCTION_GWH","Electricity Production (GWh)","GWh","annual",
                    wb="EG.ELC.PROD.KH",
                    sources=["ENERGY_WB","ENERGY_IEA","MIN_energy"],
                    plausible=(100,10000000)),

                "SOLAR_CAPACITY_GW": I("SOLAR_CAPACITY_GW","Installed Solar Capacity (GW)","GW","annual",
                    sources=["IRENA","ENERGY_IEA","MIN_energy"],
                    plausible=(0,500)),

                "OIL_PRODUCTION_MBPD": I("OIL_PRODUCTION_MBPD","Oil Production (thousand barrels/day)","kb/d","annual",
                    sources=["ENERGY_IEA","EIA"],
                    plausible=(0,12000), note="Relevant for BRN, MYS, VNM, IDN"),

                "COAL_PRODUCTION_MT": I("COAL_PRODUCTION_MT","Coal Production (million tonnes)","Mt","annual",
                    sources=["ENERGY_IEA","MIN_energy"],
                    plausible=(0,4000)),

                "CO2_PER_CAPITA": I("CO2_PER_CAPITA","CO2 Emissions Per Capita","tonnes CO2/person","annual",
                    wb="EN.ATM.CO2E.PC",
                    sources=["ENERGY_WB","ENERGY_IEA"],
                    plausible=(0.1,30), dashboard=True),

                "CO2_PER_GDP": I("CO2_PER_GDP","CO2 Emissions Per GDP (kg/$GDP PPP)","kg CO2 per $GDP PPP","annual",
                    wb="EN.ATM.CO2E.PP.GD",
                    sources=["ENERGY_WB"], plausible=(0,2)),

                "ENERGY_IMPORT_DEPENDENCE": I("ENERGY_IMPORT_DEPENDENCE","Net Energy Imports (% energy use)","% of energy use","annual",
                    wb="EG.IMP.CONS.ZS",
                    sources=["ENERGY_WB"], plausible=(-500,100)),

                "FUEL_SUBSIDY_GDP": I("FUEL_SUBSIDY_GDP","Fossil Fuel Subsidies (% GDP)","% of GDP","annual",
                    sources=["IMF_DATA_API"],
                    plausible=(0,10), note="IMF inclusive measurement"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "technology_digital": {
            "sector_name": "Technology & Digital Economy",
            "sector_code": "TECH",
            "indicators": {
                "INTERNET_PENETRATION": I("INTERNET_PENETRATION","Internet Users (% population)","% of population","annual",
                    wb="IT.NET.USER.ZS", itu="i99H",
                    sources=["TECH_ITU","TECH_WB"],
                    plausible=(0,100), dashboard=True),

                "MOBILE_SUBSCRIPTIONS": I("MOBILE_SUBSCRIPTIONS","Mobile Subscriptions per 100","per 100 people","annual",
                    wb="IT.CEL.SETS.P2", itu="mobileSubscriptions",
                    sources=["TECH_ITU","TECH_WB"],
                    plausible=(0,250)),

                "BROADBAND_FIXED": I("BROADBAND_FIXED","Fixed Broadband per 100 people","per 100","annual",
                    wb="IT.NET.BBND.P2", itu="i112",
                    sources=["TECH_ITU","TECH_WB"],
                    plausible=(0,100)),

                "MOBILE_INTERNET_PCT": I("MOBILE_INTERNET_PCT","Mobile Internet Penetration (%)","% of population","annual",
                    itu="i5019",
                    sources=["TECH_ITU"],
                    plausible=(0,100)),

                "DIGITAL_ECONOMY_GDP": I("DIGITAL_ECONOMY_GDP","Digital Economy (% GDP)","% of GDP","annual",
                    sources=["Google_Temasek","NSO_national"],
                    plausible=(0,20), note="Google-Temasek-Bain SEA Internet Economy Report"),

                "ECOMMERCE_GMV_USD": I("ECOMMERCE_GMV_USD","E-commerce GMV (USD Billion)","USD billion","annual",
                    sources=["Google_Temasek","NSO_national"],
                    plausible=(0,500)),

                "FINTECH_TRANSACTIONS": I("FINTECH_TRANSACTIONS","Digital Payments Value (% GDP)","% of GDP","annual",
                    sources=["BIS_STATS","CB_national"],
                    plausible=(0,50)),

                "RD_EXPENDITURE_GDP": I("RD_EXPENDITURE_GDP","R&D Expenditure (% GDP)","% of GDP","annual",
                    wb="GB.XPD.RSDV.GD.ZS",
                    sources=["WB_API","NSO_national"],
                    plausible=(0,5), dashboard=True),

                "RD_RESEARCHERS": I("RD_RESEARCHERS","R&D Researchers per million","per million people","annual",
                    wb="SP.POP.SCIE.RD.P6",
                    sources=["WB_API"], plausible=(0,10000)),

                "STARTUP_FUNDING_USD": I("STARTUP_FUNDING_USD","Startup Funding Received (USD Million)","USD million","annual",
                    sources=["Crunchbase","DealStreetAsia"],
                    plausible=(0,20000)),

                "CLOUD_COMPUTING_ADOPTION": I("CLOUD_COMPUTING_ADOPTION","Cloud Computing Enterprise Adoption (%)","% of firms","annual",
                    sources=["ITU","NSO_national"],
                    plausible=(0,100)),

                "CYBERSECURITY_INDEX": I("CYBERSECURITY_INDEX","ITU Global Cybersecurity Index","Score 0-100","annual",
                    itu="GCI",
                    sources=["TECH_ITU"],
                    plausible=(0,100)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "infrastructure": {
            "sector_name": "Infrastructure & Connectivity",
            "sector_code": "INFRA",
            "indicators": {
                "LOGISTICS_PERFORMANCE": I("LOGISTICS_PERFORMANCE","Logistics Performance Index (LPI)","Score 1-5","biennial",
                    wb="LP.LPI.OVRL.XQ",
                    sources=["WB_API"],
                    plausible=(1,5), dashboard=True),

                "ACTIVE_WB_PROJECTS": I("ACTIVE_WB_PROJECTS","Active World Bank Projects (count)","count","annual",
                    sources=["WB_PROJECTS"],
                    plausible=(0,100)),

                "ACTIVE_WB_COMMITMENT": I("ACTIVE_WB_COMMITMENT","WB Project Commitment (USD Million)","USD million","annual",
                    sources=["WB_PROJECTS"],
                    plausible=(0,30000)),

                "ROAD_DENSITY": I("ROAD_DENSITY","Road Density (km/1000 sq km)","km per 1000 km²","annual",
                    wb="IS.ROD.DNST.K2",
                    sources=["WB_API"], plausible=(0,2000)),

                "URBAN_POPULATION_PCT": I("URBAN_POPULATION_PCT","Urban Population (% of total)","% of total","annual",
                    wb="SP.URB.TOTL.IN.ZS",
                    sources=["WB_API"], plausible=(0,100)),

                "URBAN_GROWTH_RATE": I("URBAN_GROWTH_RATE","Urban Population Growth","% YoY","annual",
                    wb="SP.URB.GROW",
                    sources=["WB_API"], plausible=(-5,10)),

                "PORT_THROUGHPUT": I("PORT_THROUGHPUT","Container Port Throughput (TEU million)","million TEU","annual",
                    wb="IS.SHP.GOOD.TU",
                    sources=["WB_API"], plausible=(0,50)),

                "AIR_PASSENGERS": I("AIR_PASSENGERS","Air Passengers Carried (millions)","millions","annual",
                    wb="IS.AIR.PSGR",
                    sources=["WB_API"], plausible=(0,1500)),

                "INFRASTRUCTURE_QUALITY_WEF": I("INFRASTRUCTURE_QUALITY_WEF","Infrastructure Quality (WEF GCI)","Score 1-7","annual",
                    sources=["WEF_GCI"],
                    plausible=(1,7)),

                "EASE_DOING_BUSINESS": I("EASE_DOING_BUSINESS","Ease of Doing Business Score","Score 0-100","annual",
                    wb="IC.BUS.DFRN.XQ",
                    sources=["WB_API"],
                    plausible=(0,100), note="DB discontinued 2021; B-READY pilot 2024"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "environment": {
            "sector_name": "Environment & Geography",
            "sector_code": "ENVIRON",
            "indicators": {
                "FOREST_AREA_PCT": I("FOREST_AREA_PCT","Forest Area (% land area)","% of land area","annual",
                    wb="AG.LND.FRST.ZS",
                    sources=["ENV_WB","FAO_FAOSTAT"],
                    plausible=(0,100), dashboard=True),

                "CO2_TOTAL_MT": I("CO2_TOTAL_MT","Total CO2 Emissions (Mt)","Mt CO2","annual",
                    wb="EN.ATM.CO2E.KT",
                    sources=["ENV_WB","ENERGY_IEA"],
                    plausible=(0.1,15000)),

                "METHANE_EMISSIONS": I("METHANE_EMISSIONS","Methane Emissions (kt CO2eq)","kt CO2eq","annual",
                    wb="EN.ATM.METH.KT.CE",
                    sources=["ENV_WB"], plausible=(0,1000000)),

                "PLASTIC_WASTE_MT": I("PLASTIC_WASTE_MT","Plastic Waste Generated (million tonnes)","Mt","annual",
                    sources=["UNEP"],
                    plausible=(0,100)),

                "AIR_QUALITY_PM25": I("AIR_QUALITY_PM25","PM2.5 Air Pollution (μg/m³)","μg/m³","annual",
                    wb="EN.ATM.PM25.MC.M3",
                    sources=["ENV_WB","WHO_GHO"],
                    plausible=(0,200)),

                "WATER_ACCESS_PCT": I("WATER_ACCESS_PCT","Access to Safe Water (%)","% of population","annual",
                    wb="SH.H2O.BASW.ZS",
                    sources=["WHO_GHO","ENV_WB"],
                    plausible=(0,100)),

                "SANITATION_ACCESS_PCT": I("SANITATION_ACCESS_PCT","Access to Sanitation (%)","% of population","annual",
                    wb="SH.STA.BASS.ZS",
                    sources=["WHO_GHO","ENV_WB"],
                    plausible=(0,100)),

                "CLIMATE_RISK_INDEX": I("CLIMATE_RISK_INDEX","Climate Risk Index Score","Score","annual",
                    sources=["Germanwatch_CRI"],
                    plausible=(0,200), note="Lower = more at risk; Germanwatch CRI"),

                "SEA_LEVEL_RISE_RISK": I("SEA_LEVEL_RISE_RISK","Coastline at Risk of Sea Level Rise (km)","km","annual",
                    sources=["UNEP","WB_CLIMATE"],
                    plausible=(0,50000)),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "politics_policy": {
            "sector_name": "Politics & Policy",
            "sector_code": "POLITICS",
            "indicators": {
                "GOVERNANCE_EFFECTIVENESS": I("GOVERNANCE_EFFECTIVENESS","Government Effectiveness (WGI)","Score -2.5 to 2.5","annual",
                    wb="GE.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5), dashboard=True),

                "RULE_OF_LAW": I("RULE_OF_LAW","Rule of Law (WGI)","Score -2.5 to 2.5","annual",
                    wb="RL.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5)),

                "VOICE_ACCOUNTABILITY": I("VOICE_ACCOUNTABILITY","Voice & Accountability (WGI)","Score -2.5 to 2.5","annual",
                    wb="VA.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5)),

                "REGULATORY_QUALITY": I("REGULATORY_QUALITY","Regulatory Quality (WGI)","Score -2.5 to 2.5","annual",
                    wb="RQ.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5)),

                "ECONOMIC_FREEDOM": I("ECONOMIC_FREEDOM","Economic Freedom Index (Heritage)","Score 0-100","annual",
                    sources=["HERITAGE_EF"],
                    plausible=(0,100)),

                "PRESS_FREEDOM_INDEX": I("PRESS_FREEDOM_INDEX","Press Freedom Index (RSF)","Rank/Score","annual",
                    sources=["RSF_PFI"],
                    plausible=(0,100), note="Lower rank = more free; RSF World Press Freedom Index"),

                "POLITICAL_RISK_NEWS": I("POLITICAL_RISK_NEWS","Political Risk News Count (GDELT)","article count","realtime",
                    sources=["GDELT_NEWS"],
                    plausible=(0,10000),
                    note="REAL-TIME SIGNAL ONLY — not official statistics"),

                "POLICY_RATE_CHANGE": I("POLICY_RATE_CHANGE","Central Bank Rate Change","basis points","event",
                    sources=["CB_national"],
                    plausible=(-200,200)),

                "OFFICIAL_POLICY_UPDATE": I("OFFICIAL_POLICY_UPDATE","Official Policy Update","text","event-driven",
                    sources=["IMF_RSS","WB_RSS","ADB_RSS"],
                    note="Policy announcements from official sources"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "security_conflict": {
            "sector_name": "Security & Conflict",
            "sector_code": "SECURITY",
            "indicators": {
                "POLITICAL_STABILITY": I("POLITICAL_STABILITY","Political Stability & No Violence (WGI)","Score -2.5 to 2.5","annual",
                    wb="PV.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5), dashboard=True),

                "CORRUPTION_PERCEPTION": I("CORRUPTION_PERCEPTION","Control of Corruption (WGI)","Score -2.5 to 2.5","annual",
                    wb="CC.EST",
                    sources=["WB_API"],
                    plausible=(-2.5,2.5)),

                "CPI_SCORE_TI": I("CPI_SCORE_TI","Corruption Perceptions Index (TI)","Score 0-100","annual",
                    sources=["TI_CPI"],
                    plausible=(0,100), note="Higher = less corrupt"),

                "CONFLICT_NEWS_COUNT": I("CONFLICT_NEWS_COUNT","Conflict News Count (GDELT)","article count","realtime",
                    sources=["GDELT_NEWS"],
                    plausible=(0,5000),
                    note="REAL-TIME SIGNAL — NOT official statistics"),

                "ACLED_EVENTS": I("ACLED_EVENTS","Conflict Events (ACLED)","event count","weekly",
                    sources=["ACLED_CONFLICT"],
                    plausible=(0,10000),
                    note="Armed conflict events; protests; violence data"),

                "GLOBAL_PEACE_INDEX": I("GLOBAL_PEACE_INDEX","Global Peace Index Rank","rank","annual",
                    sources=["IEP_GPI"],
                    plausible=(1,163), note="Institute for Economics & Peace; lower = more peaceful"),

                "BORDER_TENSION_NEWS": I("BORDER_TENSION_NEWS","Border/Maritime Tension News Count","article count","realtime",
                    sources=["GDELT_NEWS"],
                    plausible=(0,2000), note="South China Sea disputes; signal only"),
            }
        },

        # ══════════════════════════════════════════════════════════════════════
        "social_indicators": {
            "sector_name": "Social Indicators",
            "sector_code": "SOCIAL",
            "indicators": {
                "POPULATION": I("POPULATION","Total Population (millions)","millions","annual",
                    wb="SP.POP.TOTL",
                    sources=["WB_API","NSO_national"],
                    plausible=(0.1,1500), dashboard=True),

                "POPULATION_GROWTH": I("POPULATION_GROWTH","Population Growth Rate","% YoY","annual",
                    wb="SP.POP.GROW",
                    sources=["WB_API"], plausible=(-5,5)),

                "POVERTY_RATE_USD365": I("POVERTY_RATE_USD365","Poverty Rate ($3.65/day)","% of population","annual",
                    wb="SI.POV.LMIC",
                    sources=["WB_API"],
                    plausible=(0,80)),

                "POVERTY_RATE_USD685": I("POVERTY_RATE_USD685","Poverty Rate ($6.85/day)","% of population","annual",
                    wb="SI.POV.UMIC",
                    sources=["WB_API"],
                    plausible=(0,95)),

                "LIFE_EXPECTANCY": I("LIFE_EXPECTANCY","Life Expectancy at Birth (years)","years","annual",
                    wb="SP.DYN.LE00.IN",
                    sources=["WB_API","WHO_GHO"],
                    plausible=(40,90)),

                "INFANT_MORTALITY": I("INFANT_MORTALITY","Infant Mortality Rate (per 1000)","per 1000 live births","annual",
                    wb="SP.DYN.IMRT.IN",
                    sources=["WB_API","WHO_GHO"],
                    plausible=(0,120)),

                "MATERNAL_MORTALITY": I("MATERNAL_MORTALITY","Maternal Mortality Ratio (per 100k)","per 100,000 births","annual",
                    wb="SH.STA.MMRT",
                    sources=["WHO_GHO","WB_API"],
                    plausible=(0,1000)),

                "EDUCATION_EXPENDITURE_GDP": I("EDUCATION_EXPENDITURE_GDP","Education Expenditure (% GDP)","% of GDP","annual",
                    wb="SE.XPD.TOTL.GD.ZS",
                    sources=["WB_API"],
                    plausible=(0,15)),

                "SECONDARY_ENROLLMENT": I("SECONDARY_ENROLLMENT","Secondary School Enrollment Rate","% of age group","annual",
                    wb="SE.SEC.ENRR",
                    sources=["WB_API","UNESCO"],
                    plausible=(0,130)),

                "TERTIARY_ENROLLMENT": I("TERTIARY_ENROLLMENT","Tertiary Enrollment Rate","% of age group","annual",
                    wb="SE.TER.ENRR",
                    sources=["WB_API","UNESCO"],
                    plausible=(0,100)),

                "HEALTH_EXPENDITURE_GDP": I("HEALTH_EXPENDITURE_GDP","Health Expenditure (% GDP)","% of GDP","annual",
                    wb="SH.XPD.CHEX.GD.ZS",
                    sources=["WHO_GHO","WB_API"],
                    plausible=(0,20)),

                "GINI_INDEX": I("GINI_INDEX","Gini Index (Income Inequality)","0-100","annual",
                    wb="SI.POV.GINI",
                    sources=["WB_API"],
                    plausible=(20,70)),

                "HUMAN_DEVELOPMENT_INDEX": I("HUMAN_DEVELOPMENT_INDEX","Human Development Index (UNDP)","Score 0-1","annual",
                    sources=["UNDP_HDR"],
                    plausible=(0,1)),

                "GENDER_INEQUALITY_INDEX": I("GENDER_INEQUALITY_INDEX","Gender Inequality Index (UNDP)","Score 0-1","annual",
                    sources=["UNDP_HDR"],
                    plausible=(0,1)),

                "MOBILE_MONEY_USERS": I("MOBILE_MONEY_USERS","Mobile Money Account Holders (% adults)","% of adults","annual",
                    wb="FX.OWN.SELF.IN",
                    sources=["WB_API","GSMA"],
                    plausible=(0,100)),
            }
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    sectors = build_sectors()

    total_inds = sum(len(s["indicators"]) for s in sectors.values())
    dashboard_inds = sum(
        1 for s in sectors.values()
        for ind in s["indicators"].values()
        if ind.get("show_on_dashboard")
    )

    registry = {
        "version":     "2.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "description": "Universal Indicator Registry — SEA Change Intelligence Dashboard",
        "total_sectors":    len(sectors),
        "total_indicators": total_inds,
        "dashboard_indicators": dashboard_inds,
        "value_type_definitions": {
            "official_actual":       "Published final/revised data from official body",
            "official_preliminary":  "Advance/preliminary estimate from official body",
            "official_partial_2026": "Official 2026 partial-year data",
            "forecast_estimate":     "IMF/WB/ADB projection — clearly labeled",
            "missing_official":      "Official source checked; not yet published",
            "official_policy":       "Policy update / qualitative announcement",
            "realtime_signal":       "News/event counts — not official statistics",
            "sample":                "Dev placeholder only",
        },
        "sectors": sectors,
    }

    OUT_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

    print(f"\n{'═'*65}")
    print(f"  Indicator Registry Generated — v2.0")
    print(f"{'═'*65}")
    print(f"  Total sectors     : {len(sectors)}")
    print(f"  Total indicators  : {total_inds}")
    print(f"  Dashboard KPIs    : {dashboard_inds}")
    print(f"\n  Indicators per sector:")
    for sid, s in sectors.items():
        n = len(s["indicators"])
        bar = "█" * min(n, 20)
        print(f"    {sid:30s} {n:3d}  {bar}")
    print(f"\n  📄 {OUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"{'═'*65}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
