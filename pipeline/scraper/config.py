"""
pipeline/scraper/config.py
──────────────────────────
Global scraper configuration: user agents, rate limits per domain,
CSS selectors per site, country→domain mapping, listing URLs,
and central bank page URLs.
"""

from __future__ import annotations

# ── 20+ rotating user agents (real Chrome/Firefox/Safari strings) ──────────────

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
]

# ── Rate limits: (requests, per_seconds) per domain ───────────────────────────
# Keeps us polite and avoids bans. All unlisted domains use "default".

RATE_LIMITS: dict[str, tuple[int, float]] = {
    "default": (2, 3.0),
    "bangkokpost.com": (1, 4.0),
    "nationthailand.com": (1, 4.0),
    "thejakartapost.com": (1, 4.0),
    "channelnewsasia.com": (2, 3.0),
    "straitstimes.com": (1, 5.0),
    "philstar.com": (1, 4.0),
    "inquirer.net": (1, 4.0),
    "thestar.com.my": (1, 4.0),
    "bernama.com": (2, 3.0),
    "phnompenhpost.com": (2, 3.0),
    "khmertimeskh.com": (2, 3.0),
    "laotiantimes.com": (2, 3.0),
    "vnexpress.net": (2, 3.0),
    "vietnamnews.vn": (2, 3.0),
    "bot.or.th": (1, 5.0),
    "bi.go.id": (1, 5.0),
    "bsp.gov.ph": (1, 5.0),
    "bnm.gov.my": (1, 5.0),
    "mas.gov.sg": (1, 5.0),
    "sbv.gov.vn": (1, 5.0),
}

# ── Sites that need a real browser (JS-rendered) ──────────────────────────────

JS_REQUIRED_DOMAINS: set[str] = {
    "channelnewsasia.com",
    "straitstimes.com",
}

# ── Per-site CSS selector configs ─────────────────────────────────────────────
# Keys:
#   listing_sel  — on index/category pages: selectors for article <a> links
#   title_sel    — article title
#   body_sel     — article body container
#   date_sel     — publication date element
#   author_sel   — author name element
#   requires_js  — override JS_REQUIRED_DOMAINS per-site

SITE_CONFIGS: dict[str, dict] = {
    "bangkokpost.com": {
        "requires_js": False,
        "listing_sel": "article h3 a, .article-list a.title, h3.title a, .card-title a",
        "title_sel": "h1.article-title, h1.title, h1",
        "body_sel": "div.article-content, div.articlesDetailBox, div[class*='content']",
        "date_sel": "time[datetime], span.article-date, .post-date",
        "author_sel": "span.author-name, .byline, .post-author",
    },
    "nationthailand.com": {
        "requires_js": False,
        "listing_sel": "h2 a, h3 a, article a.title",
        "title_sel": "h1",
        "body_sel": "div.article-body, div.entry-content",
        "date_sel": "time[datetime], span.post-date",
        "author_sel": ".author, .byline",
    },
    "thejakartapost.com": {
        "requires_js": False,
        "listing_sel": ".article-list h2 a, h3.article-title a, article h2 a",
        "title_sel": "h1.article-title, h1",
        "body_sel": "div.article-body, div.detail-content, div[class*='article']",
        "date_sel": "time[datetime], span.date, .date-author time",
        "author_sel": "span.author, .byline-name, .author-name",
    },
    "channelnewsasia.com": {
        "requires_js": True,
        "listing_sel": "a[class*='title'], h3 a, article h6 a, div[class*='card'] a",
        "title_sel": "h1",
        "body_sel": "div[class*='text-long'], div[class*='article-body'], div[class*='content']",
        "date_sel": "time[datetime], div[class*='timestamp']",
        "author_sel": "div[class*='author'], span[class*='author']",
    },
    "straitstimes.com": {
        "requires_js": True,
        "listing_sel": "a[class*='headline'], h2 a, h3 a",
        "title_sel": "h1",
        "body_sel": "div[class*='article-body'], div[class*='content-body']",
        "date_sel": "time[datetime], div[class*='date']",
        "author_sel": "div[class*='author']",
    },
    "philstar.com": {
        "requires_js": False,
        "listing_sel": ".news-summary h2 a, article h2 a, .article-title a",
        "title_sel": "h1.news-title, h1",
        "body_sel": "div.article-fulltext, div#sports_article_text, div[class*='article']",
        "date_sel": "span.timeago, time, .article-date",
        "author_sel": "span.article-author, .byline",
    },
    "inquirer.net": {
        "requires_js": False,
        "listing_sel": "h2 a, h3 a, .article-title a",
        "title_sel": "h1",
        "body_sel": "div.article-content-body, div#article-body",
        "date_sel": "time[datetime], span.date-published",
        "author_sel": "span.author",
    },
    "thestar.com.my": {
        "requires_js": False,
        "listing_sel": "article h2 a, .article-stories h2 a, .story a",
        "title_sel": "h1",
        "body_sel": "div#story-body, div.article-body, div[class*='story']",
        "date_sel": "time[datetime], span.timestamp, .date",
        "author_sel": "div.author-name, .byline",
    },
    "bernama.com": {
        "requires_js": False,
        "listing_sel": "a.latest-news-title, .news-list a, .article-title a",
        "title_sel": "h1, div.news-title",
        "body_sel": "div.news-content, div#contentNews",
        "date_sel": "div.news-date, time",
        "author_sel": "",
    },
    "phnompenhpost.com": {
        "requires_js": False,
        "listing_sel": "article h2 a, h3 a.post-title, .article-list a",
        "title_sel": "h1",
        "body_sel": "div.article-body, div.field-name-body",
        "date_sel": "time[datetime], span.date-display-single",
        "author_sel": "span.field-name-field-author, .byline",
    },
    "khmertimeskh.com": {
        "requires_js": False,
        "listing_sel": "article h3 a, h2 a, .entry-title a",
        "title_sel": "h1.entry-title, h1",
        "body_sel": "div.entry-content, div.td-post-content",
        "date_sel": "time[datetime], .entry-date",
        "author_sel": ".author-name, .td-post-author-name a",
    },
    "laotiantimes.com": {
        "requires_js": False,
        "listing_sel": "article h2 a, h3.entry-title a, .post-title a",
        "title_sel": "h1.entry-title, h1",
        "body_sel": "div.entry-content",
        "date_sel": "time[datetime], .post-date",
        "author_sel": "span.author, .author a",
    },
    "vnexpress.net": {
        "requires_js": False,
        "listing_sel": "article h3 a, h3.title-news a, .item-news h3 a",
        "title_sel": "h1.title-detail, h1",
        "body_sel": "article.fck_detail, div[class='Normal'], div.article-body",
        "date_sel": "span.date, time, .date-pub",
        "author_sel": "p.Normal strong, .author_mail strong",
    },
    "vietnamnews.vn": {
        "requires_js": False,
        "listing_sel": ".box-category-item a, h3 a, article a",
        "title_sel": "h1",
        "body_sel": "div.article-body, div.detail-content, div[class*='content']",
        "date_sel": "time, div.dateUpdatedArticle, .date",
        "author_sel": "p.author, .author-name",
    },
}

# ── Country ISO3 → list of domains to scrape ─────────────────────────────────

COUNTRY_NEWS_SOURCES: dict[str, list[str]] = {
    "THA": ["bangkokpost.com", "nationthailand.com"],
    "IDN": ["thejakartapost.com"],
    "SGP": ["channelnewsasia.com"],
    "MYS": ["thestar.com.my", "bernama.com"],
    "PHL": ["philstar.com", "inquirer.net"],
    "MMR": ["irrawaddy.com", "mizzima.com"],
    "VNM": ["vnexpress.net", "vietnamnews.vn"],
    "KHM": ["phnompenhpost.com", "khmertimeskh.com"],
    "LAO": ["laotiantimes.com"],
    "BRN": [],
}

# ── Listing/category page URL for each domain ─────────────────────────────────

LISTING_URLS: dict[str, str] = {
    "bangkokpost.com": "https://www.bangkokpost.com/business",
    "nationthailand.com": "https://www.nationthailand.com/business",
    "thejakartapost.com": "https://www.thejakartapost.com/news/business",
    "channelnewsasia.com": "https://www.channelnewsasia.com/asia/south-east-asia",
    "straitstimes.com": "https://www.straitstimes.com/business",
    "philstar.com": "https://www.philstar.com/business",
    "inquirer.net": "https://business.inquirer.net/",
    "thestar.com.my": "https://www.thestar.com.my/business",
    "bernama.com": "https://www.bernama.com/en/business/",
    "phnompenhpost.com": "https://www.phnompenhpost.com/business",
    "khmertimeskh.com": "https://www.khmertimeskh.com/category/business/",
    "laotiantimes.com": "https://laotiantimes.com/economy/",
    "vnexpress.net": "https://e.vnexpress.net/business",
    "vietnamnews.vn": "https://vietnamnews.vn/economy",
}

# ── Central bank configuration ────────────────────────────────────────────────

CENTRAL_BANK_URLS: dict[str, dict] = {
    "THA": {
        "name": "Bank of Thailand",
        "news_url": "https://www.bot.or.th/en/news-and-media/news.html",
        "listing_sel": "a.news-title, .news-list a, h4 a",
        "title_sel": "h1, .news-heading",
        "date_sel": "time[datetime], .news-date, span.date",
        "body_sel": "div.news-content, div.article-content",
    },
    "IDN": {
        "name": "Bank Indonesia",
        "news_url": "https://www.bi.go.id/en/publikasi/laporan/Pages/default.aspx",
        "listing_sel": "a.artikel, .list-publication a, h4 a",
        "title_sel": "h1, .title-content",
        "date_sel": "span.date, time",
        "body_sel": "div.content-detail, div.content-body",
    },
    "PHL": {
        "name": "Bangko Sentral ng Pilipinas",
        "news_url": "https://www.bsp.gov.ph/Pages/MediaAndResearch/PressReleases.aspx",
        "listing_sel": "a[href*='PressRelease'], .ms-listviewtable a",
        "title_sel": "h1, .ms-rtestate-field h2",
        "date_sel": "td.ms-cellstyle, time",
        "body_sel": "div.ms-rtestate-field",
    },
    "MYS": {
        "name": "Bank Negara Malaysia",
        "news_url": "https://www.bnm.gov.my/news-release",
        "listing_sel": "a.news-title, .news-item a, h4 a",
        "title_sel": "h1, .content-title",
        "date_sel": "time[datetime], .news-date",
        "body_sel": "div.article-body, div.content-area",
    },
    "SGP": {
        "name": "Monetary Authority of Singapore",
        "news_url": "https://www.mas.gov.sg/news",
        "listing_sel": "a[class*='title'], .news-list a, article a",
        "title_sel": "h1",
        "date_sel": "time[datetime], .news-date",
        "body_sel": "div.content-body, div[class*='article']",
    },
    "VNM": {
        "name": "State Bank of Vietnam",
        "news_url": "https://www.sbv.gov.vn/webcenter/portal/en/home/sbv/news",
        "listing_sel": "a.news-link, .news-list a, h4 a",
        "title_sel": "h1, .news-title",
        "date_sel": "time, .news-date, span.date",
        "body_sel": "div.news-content, div[class*='content']",
    },
    "MMR": {
        "name": "Central Bank of Myanmar",
        "news_url": "https://www.cbm.gov.mm/content/press-releases",
        "listing_sel": ".views-row a, h3 a",
        "title_sel": "h1",
        "date_sel": "time[datetime], span.date-display-single",
        "body_sel": "div.field-name-body",
    },
}

# ── Country ISO3 → human-readable name (matches existing pipeline data) ────────

COUNTRY_NAMES: dict[str, str] = {
    "THA": "Thailand",
    "IDN": "Indonesia",
    "SGP": "Singapore",
    "MYS": "Malaysia",
    "PHL": "Philippines",
    "MMR": "Myanmar",
    "VNM": "Vietnam",
    "KHM": "Cambodia",
    "LAO": "Laos",
    "BRN": "Brunei",
    "CHN": "China",
    "IND": "India",
    "JPN": "Japan",
    "USA": "United States",
}
