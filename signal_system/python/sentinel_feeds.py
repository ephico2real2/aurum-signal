"""
sentinel_feeds.py — Free RSS headlines for SENTINEL (FXStreet, Google News, Investing.com, DailyFX, extras)
============================================================================================================
No API keys. Enriches sentinel_status.json for ATHENA / AURUM context.
Does not replace the economic calendar guard (ForexFactory).

Note: Yahoo Finance headline RSS endpoints return 404 as of 2026; use FXStreet + Google News instead.
DailyFX often returns 403 from cloud/datacenter IPs — disabled by default.
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET

import requests

log = logging.getLogger("sentinel.feeds")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

INVESTING_FOREX_RSS = "https://www.investing.com/rss/news_301.rss"
FXSTREET_NEWS_RSS = "https://www.fxstreet.com/rss/news"
DAILYFX_RSS = "https://www.dailyfx.com/feeds/market-news"
DEFAULT_GOOGLE_QUERY = "forex OR XAUUSD OR gold OR ECB OR BOJ OR FOMC OR CPI NFP"


def _parse_rss2_items(xml_text: str, source: str, max_items: int) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.debug("RSS XML parse error [%s]: %s", source, e)
        return items

    channel = root.find("channel")
    if channel is None:
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            if title:
                items.append(
                    {"source": source, "title": title, "link": link, "pubDate": pub}
                )
        return items

    for item in channel.findall("item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title:
            items.append(
                {"source": source, "title": title, "link": link, "pubDate": pub}
            )
    return items


def _fetch_rss(url: str, source: str, max_items: int, timeout: float) -> list[dict]:
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        r.raise_for_status()
        return _parse_rss2_items(r.text, source, max_items)
    except Exception as e:
        log.debug("RSS fetch failed [%s] %s: %s", source, url, e)
        return []


def _google_news_rss_url() -> str:
    from urllib.parse import quote_plus

    q = os.environ.get("SENTINEL_GOOGLE_NEWS_QUERY", DEFAULT_GOOGLE_QUERY).strip()
    if not q:
        q = DEFAULT_GOOGLE_QUERY
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(q)
        + "&hl=en&gl=US&ceid=US:en"
    )


def gather_news_feeds(timeout: float | None = None) -> dict:
    """
    Returns dict: fxstreet[], google_news[], investing_forex[], dailyfx[], extra[], errors[].
    Disabled when SENTINEL_ENABLE_NEWS_FEEDS is 0/false/no.
    """
    t = timeout if timeout is not None else float(os.environ.get("SENTINEL_RSS_TIMEOUT", "12"))
    out: dict = {
        "fxstreet": [],
        "google_news": [],
        "investing_forex": [],
        "dailyfx": [],
        "extra": [],
        "errors": [],
    }

    flag = os.environ.get("SENTINEL_ENABLE_NEWS_FEEDS", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return out

    max_per = int(os.environ.get("SENTINEL_RSS_MAX_PER_FEED", "8"))

    fx_url = os.environ.get("SENTINEL_FXSTREET_RSS", FXSTREET_NEWS_RSS).strip()
    if fx_url and os.environ.get("SENTINEL_ENABLE_FXSTREET_RSS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        out["fxstreet"] = _fetch_rss(fx_url, "fxstreet", max_per, t)

    if os.environ.get("SENTINEL_ENABLE_GOOGLE_NEWS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        out["google_news"] = _fetch_rss(
            _google_news_rss_url(), "google_news", max_per, t
        )

    if os.environ.get("SENTINEL_ENABLE_INVESTING_RSS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        out["investing_forex"] = _fetch_rss(
            INVESTING_FOREX_RSS, "investing_forex", max_per, t
        )

    # DailyFX often 403 outside residential IPs — default off
    if os.environ.get("SENTINEL_ENABLE_DAILYFX_RSS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        out["dailyfx"] = _fetch_rss(DAILYFX_RSS, "dailyfx", max_per, t)

    raw_extra = os.environ.get("SENTINEL_EXTRA_RSS_URLS", "").strip()
    if raw_extra:
        for i, u in enumerate([x.strip() for x in raw_extra.split(",") if x.strip()][:6]):
            host = u.split("/")[2] if "://" in u else f"extra_{i}"
            out["extra"].extend(_fetch_rss(u, f"extra:{host}", max_per, t))

    cap = int(os.environ.get("SENTINEL_RSS_TOTAL_CAP", "40"))
    for key in ("fxstreet", "google_news", "investing_forex", "dailyfx", "extra"):
        if len(out[key]) > cap:
            out[key] = out[key][:cap]

    return out
