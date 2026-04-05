"""
sentinel.py — SENTINEL News Guard & Event Filter
=================================================
Build order: #4 — depends on SCRIBE.
Polls ForexFactory for high-impact USD events.
Writes sentinel_status.json every cycle.
Auto-pauses 30 min before, auto-resumes after.
"""

import os, json, logging, requests, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

from scribe import get_scribe

log = logging.getLogger("sentinel")

STATUS_FILE   = os.environ.get("SENTINEL_STATUS", "config/sentinel_status.json")
GUARD_MINUTES = int(os.environ.get("SENTINEL_GUARD_MIN", "30"))
POLL_SECONDS  = int(os.environ.get("SENTINEL_POLL_SEC", "60"))
FF_URL        = "https://www.forexfactory.com/calendar"
HEADERS       = {"User-Agent": "Mozilla/5.0 (compatible; SENTINEL/1.0)"}


class Sentinel:
    def __init__(self):
        self.scribe       = get_scribe()
        self.guard_active = False
        self._event_id    = None          # SCRIBE news_event row id
        self._guarding_event = None
        Path(STATUS_FILE).parent.mkdir(parents=True, exist_ok=True)
        log.info("SENTINEL initialised")

    # ── Core ───────────────────────────────────────────────────────
    def check(self, current_mode: str) -> dict:
        """
        Returns status dict. Called by BRIDGE every cycle.
        {active, block_trading, event_name, minutes_away, resume_at}
        """
        events = self._fetch_events()
        now    = datetime.now(timezone.utc)

        # Find closest high-impact event
        upcoming = [
            e for e in events
            if e["impact"] == "HIGH"
            and 0 <= e["minutes_away"] <= GUARD_MINUTES * 2
        ]
        recent = [
            e for e in events
            if e["impact"] == "HIGH"
            and -10 <= e["minutes_away"] < 0
        ]

        # Should guard be active?
        guard_needed = any(
            e["minutes_away"] >= 0 and e["minutes_away"] <= GUARD_MINUTES
            for e in upcoming
        )
        # Also guard for 5 min after event (price spike settling)
        guard_needed = guard_needed or any(
            e["minutes_away"] >= -5 for e in recent
        )

        if guard_needed and not self.guard_active:
            trigger_event = (upcoming + recent)[0]
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

        status = {
            "active":        self.guard_active,
            "block_trading": self.guard_active,
            "event_name":    self._guarding_event.get("name") if self._guarding_event else None,
            "next_event":    next_event.get("name") if next_event else "None scheduled",
            "next_in_min":   next_event.get("minutes_away") if next_event else None,
            "next_time":     next_event.get("time_str") if next_event else None,
            "timestamp":     now.isoformat(),
        }
        self._write_status(status)
        try:
            get_scribe().heartbeat(
                component   = "SENTINEL",
                status      = "WARN" if self.guard_active else "OK",
                note        = f"Next: {status.get('next_event','?')} in {status.get('next_in_min','?')}min",
                last_action = "guard ACTIVE" if self.guard_active else "monitoring",
            )
        except Exception as e:
            log.debug(f"SENTINEL heartbeat error: {e}")
        return status

    def _activate_guard(self, event: dict, current_mode: str):
        log.warning(f"SENTINEL GUARD ON — {event['name']} in {event['minutes_away']}min")
        self.guard_active     = True
        self._guarding_event  = event
        self._event_id = self.scribe.log_news_event(
            event_name=event["name"],
            impact="HIGH",
            currency="USD",
            mode_before=current_mode,
        )
        from herald import get_herald
        get_herald().news_guard_on(event["name"], event["minutes_away"], current_mode)
        self.scribe.log_system_event(
            "NEWS_FILTER_ON", new_mode="WATCH",
            triggered_by="SENTINEL", reason=event["name"],
            news_event=event["name"],
        )

    def _deactivate_guard(self, current_mode: str):
        log.info(f"SENTINEL GUARD OFF — resuming {current_mode}")
        self.guard_active = False
        if self._event_id:
            self.scribe.close_news_event(self._event_id, current_mode)
        from herald import get_herald
        get_herald().news_guard_off(
            self._guarding_event.get("name","Event") if self._guarding_event else "Event",
            current_mode
        )
        self.scribe.log_system_event(
            "NEWS_FILTER_OFF", prev_mode="WATCH", new_mode=current_mode,
            triggered_by="SENTINEL",
        )
        self._guarding_event = None
        self._event_id = None

    # ── ForexFactory scraper ───────────────────────────────────────
    def _fetch_events(self) -> list:
        try:
            resp = requests.get(FF_URL, headers=HEADERS, timeout=10)
            return self._parse_ff(resp.text)
        except Exception as e:
            log.error(f"SENTINEL fetch error: {e}")
            return self._fallback_events()

    def _parse_ff(self, html: str) -> list:
        """Parse ForexFactory calendar HTML for today's USD events."""
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
            if currency.get_text(strip=True) != "USD":
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
