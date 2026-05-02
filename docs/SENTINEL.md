# SENTINEL — news guard, calendar, and free RSS feeds

SENTINEL (`python/sentinel.py`) does two jobs:

1. **Economic calendar guard** — Scrapes [ForexFactory](https://www.forexfactory.com/calendar) for **high-impact** rows. When a listed event is inside the guard window, BRIDGE treats **effective mode** as **WATCH** (auto-scalper off; AURUM `OPEN_GROUP` blocked until clear).
2. **Headline feeds (optional)** — Pulls **free RSS** from **FXStreet**, **Google News** (forex/central-bank query), **Investing.com** (forex news), optional **DailyFX**, and any URLs you add. These **do not** flip the guard by default; they enrich `sentinel_status.json` and **AURUM** context.

**Note:** Yahoo Finance’s public headline RSS URLs now return **404**; this stack uses **FXStreet + Google News** instead. **DailyFX** often returns **403** from cloud/datacenter IPs — it is **off** unless you set `SENTINEL_ENABLE_DAILYFX_RSS=1` (may work from a home connection).

---

## Calendar: currencies (EU / Asia / US)

Default monitored currencies (comma-separated, uppercase):

`USD,EUR,GBP,JPY,AUD,NZD,CAD,CHF`

Override with:

```bash
SENTINEL_CALENDAR_CURRENCIES=USD,EUR,GBP,JPY,CNY
```

- **USD-only** (legacy behaviour): `SENTINEL_CALENDAR_CURRENCIES=USD`
- ForexFactory uses **currency column** per row; only rows in this set are considered.
- **Guard** still applies only to events classified **HIGH** impact in the HTML (red icon).

### Fetch failure behaviour

If the ForexFactory HTTP request fails (connection error, timeout, non-200 response), SENTINEL retries up to 2 times with a 3-second pause between attempts. If all attempts fail, SENTINEL returns a synthetic high-impact event that activates the guard — trading is blocked until the next successful fetch. This is intentional fail-safe behaviour. Do not treat a SENTINEL fetch error as clear-to-trade.

Other env vars:

| Variable | Default | Role |
|----------|---------|------|
| `SENTINEL_GUARD_MIN` | `30` | Minutes **before** event to activate guard |
| `SENTINEL_POST_GUARD_MIN` | `5` | Minutes **after** an instant data event (NFP, CPI) to keep guard up |
| `SENTINEL_EXTENDED_GUARD_MIN` | `60` | Minutes **after** an extended event (speech, FOMC, press conference) to keep guard up |
| `SENTINEL_POLL_SEC` | `60` | Standalone sentinel loop interval (if used) |
| `BRIDGE_SENTINEL_SEC` | `60` | How often **BRIDGE** calls `Sentinel.check()` |
| `SENTINEL_STATUS` / `SENTINEL_STATUS_FILE` | `python/config/sentinel_status.json` | Output JSON path |

### Extended vs instant events

ForexFactory only lists the **start time** of events. An NFP release is over in seconds, but a presidential speech or FOMC press conference can last 30–60+ minutes with markets moving throughout.

SENTINEL auto-detects extended events by matching keywords in the event name:
`speaks`, `speech`, `press conference`, `testimony`, `testifies`, `hearing`, `fomc`, `ecb press`, `boj press`, `summit`, `address`, `statement`, `remarks`

When an extended event is detected:
- Guard stays active for `SENTINEL_EXTENDED_GUARD_MIN` (default **60min**) after the scheduled start
- `sentinel_status.json` shows `extended_event: true` and `post_guard_min: 60`
- Log and Telegram notifications include an `[EXTENDED]` tag

For instant events (everything else): guard lifts after `SENTINEL_POST_GUARD_MIN` (default **5min**).

After edits, **`make restart`** (or restart **bridge**).

---

## RSS feeds (FXStreet, Google News, Investing.com, …)

Implemented in `python/sentinel_feeds.py`. Each BRIDGE sentinel tick merges into `sentinel_status.json` under **`news_feeds`**:

| Key | Source |
|-----|--------|
| `fxstreet` | [FXStreet news RSS](https://www.fxstreet.com/rss/news) (override URL with `SENTINEL_FXSTREET_RSS`) |
| `google_news` | [Google News RSS](https://news.google.com/) search (query from `SENTINEL_GOOGLE_NEWS_QUERY`) |
| `investing_forex` | [Investing.com Forex news RSS](https://www.investing.com/rss/news_301.rss) |
| `dailyfx` | DailyFX market RSS — **default off** (often 403) |
| `extra` | Your custom URLs (see below) |

### Env vars

| Variable | Default | Role |
|----------|---------|------|
| `SENTINEL_ENABLE_NEWS_FEEDS` | `1` | Set `0` / `false` / `no` to disable all RSS |
| `SENTINEL_ENABLE_FXSTREET_RSS` | `1` | `0` to skip FXStreet |
| `SENTINEL_FXSTREET_RSS` | FXStreet news URL | Alternate FXStreet or other XML feed |
| `SENTINEL_ENABLE_GOOGLE_NEWS` | `1` | `0` to skip Google News RSS |
| `SENTINEL_GOOGLE_NEWS_QUERY` | `forex OR XAUUSD OR gold OR ECB OR BOJ OR FOMC OR CPI NFP` | Search terms (EU/Asia/US macro) |
| `SENTINEL_ENABLE_INVESTING_RSS` | `1` | `0` to skip Investing.com |
| `SENTINEL_ENABLE_DAILYFX_RSS` | `0` | Set `1` if your network can reach DailyFX |
| `SENTINEL_EXTRA_RSS_URLS` | *(empty)* | Comma-separated **RSS/Atom XML** URLs (max **6**) |
| `SENTINEL_RSS_MAX_PER_FEED` | `8` | Max items per feed pull |
| `SENTINEL_RSS_TOTAL_CAP` | `40` | Max items per bucket after merge |
| `SENTINEL_RSS_TIMEOUT` | `12` | HTTP timeout seconds |

**Note:** Sites may **403** or change layout; failures are logged at debug and leave that bucket empty. No API keys required.

### Adding an Asian / European RSS you trust

1. Find a **direct RSS link** (URL ending in `.rss`, `/rss`, or `format=xml`).
2. Append to `.env`:

   ```bash
   SENTINEL_EXTRA_RSS_URLS=https://example.com/forex/rss
   ```

3. Restart bridge. Items appear under `news_feeds.extra` and in **AURUM** prompt (top lines).

---

## Output file shape (`sentinel_status.json`)

Relevant fields:

- `active`, `block_trading`, `next_event`, `next_in_min`, `next_time`
- `calendar_currencies` — list of currency codes used for the calendar scrape
- `news_feeds` — `{ fxstreet, google_news, investing_forex, dailyfx, extra, errors }` with `{source, title, link, pubDate}` items

ATHENA **`/api/live`** passes through `sentinel` as read from this file (including **`news_feeds`**). The dashboard **SENTINEL** panel shows **HEADLINES** (scrollable) from those buckets.

---

## Related

- BRIDGE effective mode: `python/bridge.py` (`_effective_mode`, `_sentinel_override`)
- AURUM context: `python/aurum.py` (SENTINEL + RSS headline lines)
- [OPERATIONS.md](OPERATIONS.md) — restart after `.env` changes  
