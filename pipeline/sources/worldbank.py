"""
World Bank Open Data fetcher.
API docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581
No API key required.
"""
import httpx

BASE = "https://api.worldbank.org/v2"

INDICATOR_MAP = {
    "gdp_growth":        "NY.GDP.MKTP.KD.ZG",
    "inflation":         "FP.CPI.TOTL.ZG",
    "unemployment":      "SL.UEM.TOTL.ZS",
    "fdi_inflows":       "BX.KLT.DINV.CD.WD",
    "tourism_arrivals":  "ST.INT.ARVL",
    "govt_debt":         "GC.DOD.TOTL.GD.ZS",
    "current_account":   "BN.CAB.XOKA.GD.ZS",
}

COUNTRY_IDS = [
    "MM", "TH", "VN", "KH", "LA", "MY", "SG", "ID", "PH", "BN",
    "CN", "IN", "JP", "US",
]


def fetch_indicator(wb_code: str, countries: list[str], start_year: int, end_year: int) -> list[dict]:
    """
    Fetch annual values for a World Bank indicator across multiple countries.
    Returns a list of dicts: {country_iso2, year, value}
    """
    country_str = ";".join(countries)
    url = f"{BASE}/country/{country_str}/indicator/{wb_code}"
    params = {
        "format": "json",
        "per_page": 500,
        "mrv": end_year - start_year + 1,
        "date": f"{start_year}:{end_year}",
    }

    results = []
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

        if len(payload) < 2 or not payload[1]:
            return results

        for row in payload[1]:
            if row.get("value") is None:
                continue
            results.append({
                "country_iso2": row["countryiso3code"] or row["country"]["id"],
                "year": int(row["date"]),
                "value": float(row["value"]),
            })

    return results


def fetch_all(start_year: int = 2015, end_year: int = 2024) -> dict[str, list[dict]]:
    """Fetch all mapped indicators. Returns {indicator_code: [rows]}"""
    output = {}
    for code, wb_code in INDICATOR_MAP.items():
        print(f"  Fetching World Bank: {code} ({wb_code})…")
        output[code] = fetch_indicator(wb_code, COUNTRY_IDS, start_year, end_year)
    return output
