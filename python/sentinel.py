"""
sentinel.py — SENTINEL News Guard & Event Filter
=================================================
Build order: #4 — depends on SCRIBE.
Polls ForexFactory for high-impact calendar events (configurable currencies).
Merges free RSS headlines (Yahoo Finance, Investing.com forex, DailyFX — see sentinel_feeds.py).
Writes sentinel_status.json every cycle.
Auto-pauses 30 min before, auto-resumes after.
Human doc: docs/SENTINEL.md
"""

import os, json, logging, requests, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

from scribe import get_scribe
from sentinel_feeds import gather_news_feeds
from status_report import report_component_status

log = logging.getLogger("sentinel")

STATUS_FILE   = os.environ.get(
    "SENTINEL_STATUS_FILE",
    os.environ.get("SENTINEL_STATUS", "config/sentinel_status.json"),
)
GUARD_MINUTES = int(os.environ.get("SENTINEL_GUARD_MIN", "30"))
POLL_SECONDS  = int(os.environ.get("SENTINEL_POLL_SEC", "60"))
# Post-event guard: instant data releases (NFP, CPI) settle fast; extended
# events (speeches, press conferences, FOMC) keep moving markets for the
# entire duration.  SENTINEL_POST_GUARD_MIN applies to instant events;
# SENTINEL_EXTENDED_GUARD_MIN applies to speech/presser-type events.
POST_GUARD_MIN        = int(os.environ.get("SENTINEL_POST_GUARD_MIN",       "5"))
EXTENDED_GUARD_MIN    = int(os.environ.get("SENTINEL_EXTENDED_GUARD_MIN",   "60"))
# Periodic event digest to Telegram
EVENT_DIGEST_INTERVAL = int(os.environ.get("SENTINEL_DIGEST_INTERVAL_SEC", "600"))  # 10min default
FF_URL        = "https://www.forexfactory.com/calendar"
HEADERS       = {"User-Agent": "Mozilla/5.0 (compatible; SENTINEL/1.0)"}
# Calendar rows: comma-separated ISO currency codes (ForexFactory column). Wider = more EU/Asia events.
_DEFAULT_CAL_CURRENCIES = "USD,EUR,GBP,JPY,AUD,NZD,CAD,CHF"

# ── Extended-event keyword detection ────────────────────────────────
# Events whose names match these keywords last much longer than an instant
# data release.  Guard stays up for EXTENDED_GUARD_MIN after start time.
_EXTENDED_EVENT_KEYWORDS = (
    "speaks", "speech", "press conference", "testimony",
    "testifies", "conference", "presser", "hearing",
    "fomc", "ecb press", "boj press", "boe press",
    "rba press", "rbnz press", "summit", "address",
    "statement", "remarks",
)


def _is_extended_event(event_name: str) -> bool:
    """Return True if the event is a long-running speech/presser type."""
    name_lower = event_name.lower()
    return any(kw in name_lower for kw in _EXTENDED_EVENT_KEYWORDS)


class Sentinel:
    def __init__(self):
        self.scribe       = get_scribe()
        self.guard_active = False
        self._event_id    = None          # SCRIBE news_event row id
        self._guarding_event = None
        self._last_digest_ts = 0
        self._digest_interval = EVENT_DIGEST_INTERVAL
        Path(STATUS_FILE).parent.mkdir(parents=True, exist_ok=True)
        log.info("SENTINEL initialised")

    @staticmethod
    def _calendar_currencies() -> set:
        raw = os.environ.get(
            "SENTINEL_CALENDAR_CURRENCIES", _DEFAULT_CAL_CURRENCIES
        ).strip()
        s = {c.strip().upper() for c in raw.split(",") if c.strip()}
        return s if s else {"USD"}

    # ── Core ───────────────────────────────────────────────────────
    def check(self, current_mode: str) -> dict:
        """
        Returns status dict. Called by BRIDGE every cycle.
        {active, block_trading, event_name, minutes_away, resume_at}
        """
        events = self._fetch_events(self._calendar_currencies())
        now    = datetime.now(timezone.utc)

        # Find closest high-impact event
        upcoming = [
            e for e in events
            if e["impact"] == "HIGH"
            and 0 <= e["minutes_away"] <= GUARD_MINUTES * 2
        ]
        # Recent events: look back far enough to cover extended events
        max_lookback = max(POST_GUARD_MIN, EXTENDED_GUARD_MIN)
        recent = [
            e for e in events
            if e["impact"] == "HIGH"
            and -max_lookback <= e["minutes_away"] < 0
        ]

        # Should guard be active?
        guard_needed = any(
            e["minutes_away"] >= 0 and e["minutes_away"] <= GUARD_MINUTES
            for e in upcoming
        )
        # Post-event guard: use extended window for speeches/pressers,
        # short window for instant data releases (NFP, CPI, etc.)
        for e in recent:
            post_min = EXTENDED_GUARD_MIN if _is_extended_event(e["name"]) else POST_GUARD_MIN
            if e["minutes_away"] >= -post_min:
                guard_needed = True
                break

        if guard_needed and not self.guard_active:
            trigger_event = (upcoming + recent)[0]
            trigger_event["extended"] = _is_extended_event(trigger_event["name"])
            self._activate_guard(trigger_event, current_mode)

        elif not guard_needed and self.guard_active:
            self._deactivate_guard(current_mode)

        # Next upcoming event (for ATHENA display)
        next_event = None
        all_upcoming = sorted(
            [e for e in events if e["minutes_away"] > 0 and e["impact"]=="HIGH"],
            key=lambda x: x["minutes_away"]
        )
        if all_upcoming:
            next_event = all_upcoming[0]

        _guarding_extended = (
            self._guarding_event.get("extended", False) if self._guarding_event else False
        )
        _post_min = EXTENDED_GUARD_MIN if _guarding_extended else POST_GUARD_MIN
        status = {
            "active":        self.guard_active,
            "block_trading": self.guard_active,
            "event_name":    self._guarding_event.get("name") if self._guarding_event else None,
            "extended_event": _guarding_extended,
            "post_guard_min": _post_min if self.guard_active else POST_GUARD_MIN,
            "next_event":    next_event.get("name") if next_event else "None scheduled",
            "next_in_min":   next_event.get("minutes_away") if next_event else None,
            "next_time":     next_event.get("time_str") if next_event else None,
            "timestamp":     now.isoformat(),
            "calendar_currencies": sorted(self._calendar_currencies()),
        }
        try:
            status["news_feeds"] = gather_news_feeds()
        except Exception as e:
            log.debug("SENTINEL news_feeds: %s", e)
            status["news_feeds"] = {"errors": [str(e)[:200]]}

        self._write_status(status)
        try:
            report_component_status(
                "SENTINEL",
                "WARN" if self.guard_active else "OK",
                note=f"Next: {status.get('next_event','?')} in {status.get('next_in_min','?')}min",
                last_action="guard ACTIVE" if self.guard_active else "monitoring",
            )
        except Exception as e:
            log.debug(f"SENTINEL heartbeat error: {e}")

        # Periodic event digest to Telegram (adaptive interval)
        import time as _time
        now_ts = _time.time()

        # Check for manual override
        try:
            override = json.load(open("config/sentinel_digest_override.json"))
            if override.get("interval"):
                self._digest_interval = int(override["interval"])
        except Exception:
            # Adaptive: 30min normally, 10min when <30min to event
            closest_min = next_event.get("minutes_away", 9999) if next_event else 9999
            if closest_min <= 30:
                self._digest_interval = 600   # 10min when close
            else:
                self._digest_interval = 1800  # 30min normally

        if now_ts - self._last_digest_ts >= self._digest_interval:
            self._last_digest_ts = now_ts
            try:
                from herald import get_herald
                high_upcoming = [
                    e for e in events
                    if e.get("impact") == "HIGH" and 0 < e.get("minutes_away", 9999) <= 240
                ]
                if high_upcoming:
                    get_herald().upcoming_events(high_upcoming, self.guard_active)
                    # Extra warning when event is close but guard not yet active
                    closest = high_upcoming[0]
                    mins = closest.get("minutes_away", 9999)
                    if not self.guard_active and mins <= 35:
                        get_herald().send(
                            f"⚠️ <b>Guard activating soon!</b>\n"
                            f"📅 {closest.get('name','?')} in {mins}min\n"
                            f"Trading will pause at {mins-GUARD_MINUTES if mins > GUARD_MINUTES else 0}min mark")
            except Exception as _de:
                log.debug(f"SENTINEL digest error: {_de}")

        return status

    def _activate_guard(self, event: dict, current_mode: str):
        is_ext = event.get("extended", _is_extended_event(event["name"]))
        post = EXTENDED_GUARD_MIN if is_ext else POST_GUARD_MIN
        tag = f" [EXTENDED — guard holds {post}min post-start]" if is_ext else ""
        log.warning(f"SENTINEL GUARD ON — {event['name']} in {event['minutes_away']}min{tag}")
        self.guard_active     = True
        self._guarding_event  = {**event, "extended": is_ext}
        self._event_id = self.scribe.log_news_event(
            event_name=event["name"],
            impact="HIGH",
            currency=event.get("currency", "USD"),
            mode_before=current_mode,
        )
        from herald import get_herald
        get_herald().news_guard_on(
            event["name"], event["minutes_away"], current_mode,
            extended=is_ext, post_guard_min=post,
        )
        self.scribe.log_system_event(
            "NEWS_FILTER_ON", new_mode="WATCH",
            triggered_by="SENTINEL", reason=event["name"],
            news_event=event["name"],
            notes=f"extended={is_ext} post_guard={post}min",
        )

    def _deactivate_guard(self, current_mode: str):
        was_extended = self._guarding_event.get("extended", False) if self._guarding_event else False
        event_name = self._guarding_event.get("name", "Event") if self._guarding_event else "Event"
        tag = " [EXTENDED]" if was_extended else ""
        log.info(f"SENTINEL GUARD OFF{tag} — resuming {current_mode}")
        self.guard_active = False
        if self._event_id:
            self.scribe.close_news_event(self._event_id, current_mode)
        from herald import get_herald
        get_herald().news_guard_off(event_name, current_mode, extended=was_extended)
        self.scribe.log_system_event(
            "NEWS_FILTER_OFF", prev_mode="WATCH", new_mode=current_mode,
            triggered_by="SENTINEL",
            notes=f"extended={was_extended}" if was_extended else None,
        )
        self._guarding_event = None
        self._event_id = None

    # ── ForexFactory scraper ───────────────────────────────────────
    def _fetch_events(self, currencies: set) -> list:
        try:
            resp = requests.get(FF_URL, headers=HEADERS, timeout=10)
            return self._parse_ff(resp.text, currencies)
        except Exception as e:
            log.error(f"SENTINEL fetch error: {e}")
            return self._fallback_events()

    def _parse_ff(self, html: str, currencies: set) -> list:
        """Parse ForexFactory calendar HTML for configured currencies (see SENTINEL_CALENDAR_CURRENCIES)."""
        soup   = BeautifulSoup(html, "html.parser")
        now    = datetime.now(timezone.utc)
        events = []
        current_date = None

        for row in soup.select("tr.calendar__row"):
            # Date cell
            date_cell = row.select_one("td.calendar__date")
            if date_cell and date_cell.get_text(strip=True):
                try:
                    txt = date_cell.get_text(strip=True)
                    current_date = datetime.strptime(
                        f"{txt} {now.year}", "%a%b %d %Y"
                    ).replace(tzinfo=timezone.utc)
                except:
                    pass

            currency = row.select_one("td.calendar__currency")
            impact   = row.select_one("td.calendar__impact span")
            title    = row.select_one("td.calendar__event")
            time_el  = row.select_one("td.calendar__time")

            if not (currency and impact and title):
                continue
            cur = currency.get_text(strip=True).upper()
            if cur not in currencies:
                continue

            impact_cls = impact.get("class", [])
            impact_str = (
                "HIGH"   if any("red"    in c for c in impact_cls) else
                "MEDIUM" if any("orange" in c for c in impact_cls) else
                "LOW"
            )

            time_str = time_el.get_text(strip=True) if time_el else ""
            event_dt = self._parse_time(time_str, current_date or now)
            minutes_away = int((event_dt - now).total_seconds() / 60)

            events.append({
                "name":         title.get_text(strip=True),
                "impact":       impact_str,
                "currency":     cur,
                "minutes_away": minutes_away,
                "time_str":     event_dt.strftime("%H:%M UTC"),
                "event_dt":     event_dt.isoformat(),
            })

        return events

    def _parse_time(self, time_str: str, base: datetime) -> datetime:
        """Parse ForexFactory time string like '8:30am' to UTC datetime."""
        try:
            t = datetime.strptime(time_str.lower().strip(), "%I:%M%p")
            # FF shows Eastern time — convert to UTC (+5 for EST)
            eastern_offset = timedelta(hours=5)
            return base.replace(hour=t.hour, minute=t.minute,
                               second=0, microsecond=0) + eastern_offset
        except:
            return base

    def _fallback_events(self) -> list:
        """Return empty list if FF is unreachable."""
        return []

    def _write_status(self, status: dict):
        try:
            with open(STATUS_FILE, "w") as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            log.error(f"SENTINEL write error: {e}")

    # ── Standalone loop ────────────────────────────────────────────
    def run(self, mode_getter):
        """Run sentinel loop. mode_getter() returns current mode string."""
        log.info(f"SENTINEL running — polling every {POLL_SECONDS}s")
        while True:
            try:
                self.check(mode_getter())
            except Exception as e:
                log.error(f"SENTINEL loop error: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    s = Sentinel()
    result = s.check("HYBRID")
    print("SENTINEL status:", json.dumps(result, indent=2))
