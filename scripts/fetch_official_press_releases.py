#!/usr/bin/env python3
"""
scripts/fetch_official_press_releases.py
────────────────────────────────────────────────────────────────────────────
Fetches official policy updates and press releases from:
  1. IMF Country Reports / Article IV (RSS/API)
  2. World Bank Country Economy Updates (RSS)
  3. ADB Press Releases (RSS)
  4. Central bank press releases for policy rate decisions

These are labeled value_type="official_policy" — they contain
announcements and qualitative assessments, NOT statistical values.

OUTPUT  pipeline/data/processed/press_releases_normalized.json
"""
import json, sys, time, re
from pathlib import Path
from datetime import datetime, date
from xml.etree import ElementTree as ET

try:
    import httpx
    def _get(url, timeout=30):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c: return c.get(url)
except ImportError:
    import urllib.request
    class _R:
        def __init__(self,d,c): self.status_code=c; self.text=d.decode() if isinstance(d,bytes) else str(d)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30):
        req=urllib.request.Request(url, headers={"User-Agent":"SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r: return _R(r.read(),r.status)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"
ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")
curr_year = date.today().year

# RSS feeds for official press releases
RSS_SOURCES = [
    {"id": "IMF_RSS", "name": "IMF News", "url": "https://www.imf.org/en/News/rss", "type": "official_policy"},
    {"id": "WB_RSS",  "name": "World Bank News", "url": "https://www.worldbank.org/en/rss/news", "type": "official_policy"},
    {"id": "ADB_RSS", "name": "ADB News", "url": "https://www.adb.org/news/rss/topics/all", "type": "official_policy"},
]

SEA_COUNTRIES = {
    "thailand":"THA","vietnam":"VNM","myanmar":"MMR","cambodia":"KHM","laos":"LAO","lao":"LAO",
    "malaysia":"MYS","singapore":"SGP","indonesia":"IDN","philippines":"PHL","brunei":"BRN",
    "timor-leste":"TLS","timor leste":"TLS",
}

def _parse_rss(xml_text: str, source_meta: dict) -> list[dict]:
    rows = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for item in items[:50]:
            title = (item.findtext("title") or item.findtext("atom:title", namespaces=ns) or "").strip()
            link  = (item.findtext("link") or item.findtext("atom:link", namespaces=ns) or "").strip()
            pubdt = (item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or "").strip()
            desc  = (item.findtext("description") or item.findtext("atom:summary", namespaces=ns) or "").strip()
            full_text = f"{title} {desc}".lower()
            # Match to countries
            matched = set()
            for kw, iso3 in SEA_COUNTRIES.items():
                if kw in full_text:
                    matched.add(iso3)
            yr_m = re.search(r"\b(202[0-9])\b", pubdt or full_text)
            yr = int(yr_m.group(1)) if yr_m else curr_year
            for iso3 in (matched if matched else {"ALL"}):
                rows.append({
                    "country_code": iso3, "sector": "politics_policy",
                    "indicator_code": "OFFICIAL_POLICY_UPDATE",
                    "indicator_name": "Official Policy Update / Press Release",
                    "period": str(yr), "year": yr, "quarter": None, "month": None,
                    "value": None, "unit": "text", "frequency": "event-driven",
                    "source": source_meta["name"], "source_type": "official_policy",
                    "source_url": link or source_meta["url"],
                    "fetched_at": ts_now(), "released_at": pubdt[:10] if pubdt and len(pubdt) >= 10 else None,
                    "value_type": "official_policy",
                    "data_quality": "available",
                    "confidence": "high",
                    "extraction_method": "rss",
                    "limitation_note": f"Title: {title[:200]}",
                })
    except Exception:
        pass
    return rows

def main():
    print(f"\n{'═'*60}\n  Official Press Releases Fetcher — {today_str}\n{'═'*60}\n")
    all_rows=[]; errors=[]
    for src in RSS_SOURCES:
        print(f"  ▸ {src['name']}...", flush=True)
        try:
            r = _get(src["url"], timeout=20)
            if r.status_code == 200:
                rows = _parse_rss(r.text, src)
                all_rows.extend(rows)
                print(f"    ✓ {len(rows)} items", flush=True)
            else:
                print(f"    ⚠ HTTP {r.status_code}", flush=True)
        except Exception as e:
            errors.append(f"{src['id']}: {e}"); print(f"    ✗ {e}", flush=True)
        time.sleep(1.0)
    out_file = PROC_DIR / "press_releases_normalized.json"
    result = {"source":"Official Press Releases (IMF, WB, ADB)","source_id":"PRESS_RELEASES","fetched_at":ts_now(),"total_rows":len(all_rows),"errors":errors,"records":all_rows}
    out_file.write_text(json.dumps(result,indent=2))
    print(f"\n  ✓ Rows: {len(all_rows)}\n  📄 {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0

if __name__=="__main__": sys.exit(main())
