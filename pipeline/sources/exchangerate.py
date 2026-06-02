"""
Exchange rate fetcher — daily rates vs USD.
Free tier at: https://www.exchangerate-api.com
No key needed for basic endpoint.
"""
import httpx

CURRENCIES = {
    "MMR": "MMK", "THA": "THB", "VNM": "VND", "KHM": "KHR",
    "LAO": "LAK", "MYS": "MYR", "SGP": "SGD", "IDN": "IDR",
    "PHL": "PHP", "BRN": "BND", "CHN": "CNY", "IND": "INR",
    "JPN": "JPY",
    # USA is the base — no rate row needed
}


def fetch_rates() -> list[dict]:
    """Fetch latest exchange rates vs USD for all tracked currencies."""
    url = "https://open.er-api.com/v6/latest/USD"
    with httpx.Client(timeout=10) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    rates = data.get("rates", {})
    results = []
    for country_id, currency in CURRENCIES.items():
        rate = rates.get(currency)
        if rate:
            results.append({
                "country_id": country_id,
                "value": rate,
                "year": int(data["time_last_update_utc"][:4]),
            })
    return results
