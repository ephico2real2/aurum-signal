"""
lens.py — LENS TradingView MCP Market Intelligence
===================================================
Build order: #5 — depends on SCRIBE.
Wraps the LewisWJackson/tradingview-mcp-jackson MCP server.
Caches results for LENS_CACHE_SEC (default 60s). Validates signal entries. Checks TP1 momentum.
"""

import os, json, logging, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

from scribe import get_scribe
from status_report import report_component_status

log = logging.getLogger("lens")

SNAPSHOT_FILE  = os.environ.get("LENS_SNAPSHOT", "config/lens_snapshot.json")
CACHE_SECONDS  = int(os.environ.get("LENS_CACHE_SEC", "60"))
MCP_SERVER_CMD = os.environ.get(
    "LENS_MCP_CMD",
    "npx tradingview-mcp-jackson"
)
SYMBOL         = os.environ.get("LENS_SYMBOL", "XAUUSD")
EXCHANGE       = os.environ.get("LENS_EXCHANGE", "FX_IDC")
TIMEFRAMES     = os.environ.get("LENS_TIMEFRAMES", "1m,5m,1h").split(",")

# Squeeze threshold
BBW_SQUEEZE = float(os.environ.get("LENS_BBW_SQUEEZE", "0.035"))
# Conflict thresholds
MAX_RSI_DIFF  = float(os.environ.get("LENS_MAX_RSI_DIFF", "15.0"))
MAX_PRICE_DIFF = float(os.environ.get("LENS_MAX_PRICE_DIFF", "5.0"))  # pips


class LensSnapshot:
    """Holds one TradingView data snapshot."""
    def __init__(self, data: dict):
        self.data         = data
        self.timestamp    = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        self.price        = data.get("close", 0)
        self.rsi          = data.get("RSI", 50)
        self.macd_hist    = data.get("MACD.hist", 0)
        self.bb_upper     = data.get("BB.upper", 0)
        self.bb_mid       = data.get("BB.basis", 0)
        self.bb_lower     = data.get("BB.lower", 0)
        self.bb_width     = (self.bb_upper - self.bb_lower) / self.bb_mid if self.bb_mid else 0
        self.adx          = data.get("ADX", 0)
        self.ema_20       = data.get("EMA20", 0)
        self.ema_50       = data.get("EMA50", 0)
        self.tv_recommend = data.get("Recommend.All", 0)
        self.timeframe    = data.get("timeframe", "5m")

        # Derived
        self.bb_rating    = self._bb_rating()
        self.bb_squeeze   = self.bb_width < BBW_SQUEEZE
        self.age_seconds  = self._age()

    def _bb_rating(self) -> int:
        if not self.price or not self.bb_upper:
            return 0
        if self.price >= self.bb_upper:      return 3
        if self.price >= (self.bb_upper + self.bb_mid) / 2: return 2
        if self.price >= self.bb_mid:        return 1
        if self.price >= (self.bb_lower + self.bb_mid) / 2: return -1
        if self.price >= self.bb_lower:      return -2
        return -3

    def _age(self) -> float:
        try:
            ts = datetime.fromisoformat(self.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts).total_seconds()
        except:
            return 9999

    def to_dict(self) -> dict:
        return {
            "price": self.price, "rsi": self.rsi,
            "macd_hist": self.macd_hist,
            "bb_upper": self.bb_upper, "bb_mid": self.bb_mid,
            "bb_lower": self.bb_lower, "bb_width": round(self.bb_width, 5),
            "bb_rating": self.bb_rating, "bb_squeeze": self.bb_squeeze,
            "adx": self.adx, "ema_20": self.ema_20, "ema_50": self.ema_50,
            "tv_recommend": self.tv_recommend, "timeframe": self.timeframe,
            "timestamp": self.timestamp, "age_seconds": round(self.age_seconds, 1),
        }

    def validate_entry(self, direction: str, entry_low: float,
                       entry_high: float, max_slippage_pips: float = 20.0) -> dict:
        """Check if current price is still within acceptable entry range."""
        current = self.price
        if direction == "BUY":
            distance = current - entry_high
            if distance > max_slippage_pips:
                return {"valid": False, "reason": f"SLIPPAGE: price ${current:.2f} is {distance:.0f} pips above entry zone ${entry_low:.2f}–${entry_high:.2f}"}
        else:  # SELL
            distance = entry_low - current
            if distance > max_slippage_pips:
                return {"valid": False, "reason": f"SLIPPAGE: price ${current:.2f} is {distance:.0f} pips below entry zone ${entry_low:.2f}–${entry_high:.2f}"}
        return {"valid": True, "reason": "Entry zone valid"}

    def check_tp1_momentum(self, direction: str) -> dict:
        """At TP1 hit — is momentum still running or fading?"""
        bullish = self.macd_hist > 0 and self.rsi < 75 and self.ema_20 > self.ema_50
        bearish = self.macd_hist < 0 and self.rsi > 25 and self.ema_20 < self.ema_50

        if direction == "BUY":
            running = bullish
            msg = "Momentum RUNNING — hold for TP2" if running else "Momentum FADING — consider closing all"
        else:
            running = bearish
            msg = "Momentum RUNNING — hold for TP2" if running else "Momentum FADING — consider closing all"

        return {"running": running, "message": msg,
                "rsi": self.rsi, "macd_hist": self.macd_hist}

    def conflict_with_mt5(self, mt5_rsi: float, mt5_price: float) -> dict:
        """Detect conflicts between LENS and MT5 data."""
        conflicts = []
        if abs(self.rsi - mt5_rsi) > MAX_RSI_DIFF:
            conflicts.append(f"RSI gap: LENS={self.rsi:.1f} MT5={mt5_rsi:.1f}")
        if abs(self.price - mt5_price) > MAX_PRICE_DIFF:
            conflicts.append(f"Price gap: LENS=${self.price:.2f} MT5=${mt5_price:.2f}")
        return {
            "conflict": len(conflicts) > 0,
            "details": conflicts,
            "score": len(conflicts),
        }


class Lens:
    def __init__(self):
        self.scribe    = get_scribe()
        self._cache:   LensSnapshot | None = None
        self._cache_ts: float = 0
        Path(SNAPSHOT_FILE).parent.mkdir(parents=True, exist_ok=True)
        log.info("LENS initialised")

    def get(self, mode: str, mt5_data: dict = None) -> LensSnapshot | None:
        """Get snapshot, using cache if fresh."""
        if self._is_fresh():
            return self._cache
        return self.fetch_fresh(mode, mt5_data)

    def fetch_fresh(self, mode: str, mt5_data: dict = None) -> LensSnapshot | None:
        """Force a fresh fetch from TradingView MCP."""
        try:
            raw = self._call_mcp()
            if not raw:
                return self._cache  # return stale if available
            snap = LensSnapshot(raw)
            self._cache    = snap
            self._cache_ts = time.time()
            self._write_snapshot(snap, mode)
            # Log to SCRIBE
            d = snap.to_dict()
            if mt5_data:
                d.update({
                    "bid": mt5_data.get("bid"),
                    "ask": mt5_data.get("ask"),
                    "spread": mt5_data.get("spread"),
                    "open_m1": mt5_data.get("open_m1"),
                    "close_m1": mt5_data.get("close_m1"),
                    "session": mt5_data.get("session"),
                })
            self.scribe.log_market_snapshot(d, mode, "LENS_MCP")
            log.debug(f"LENS fresh: RSI={snap.rsi:.1f} BB={snap.bb_rating} ADX={snap.adx:.1f}")
            try:
                report_component_status(
                    "LENS",
                    "OK",
                    mode=mode,
                    note=f"RSI={snap.rsi:.1f} BB={snap.bb_rating:+d}",
                    last_action=f"fetched {snap.timeframe} from TradingView",
                )
            except Exception as _he:
                log.debug(f"LENS heartbeat error: {_he}")
            return snap
        except Exception as e:
            log.error(f"LENS fetch error: {e}")
            try:
                report_component_status(
                    "LENS",
                    "ERROR",
                    error_msg=str(e)[:200],
                    note="MCP fetch failed",
                )
            except Exception:
                pass
            return self._cache

    def _mcp_argv(self) -> list:
        """Resolve npx/node to absolute paths when possible (launchd-safe)."""
        parts = MCP_SERVER_CMD.split()
        if not parts:
            return parts
        exe = shutil.which(parts[0]) or parts[0]
        return [exe] + parts[1:]

    def _run_mcp(self, tool: str) -> dict:
        """Spawn MCP server, send one request, read response, kill process."""
        req = {"jsonrpc":"2.0","id":1,"method":"tools/call",
               "params":{"name": tool, "arguments":{}}}
        proc = subprocess.Popen(
            self._mcp_argv(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
        proc.stdin.write((json.dumps(req) + "\n").encode())
        proc.stdin.flush()

        result = {}
        deadline = time.time() + 55

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                try:
                    resp = json.loads(line)
                    if "result" in resp:
                        for block in resp["result"].get("content", []):
                            if block.get("type") == "text":
                                result = json.loads(block["text"])
                                break
                        break
                except json.JSONDecodeError:
                    continue

        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        return result

    def _call_mcp(self) -> dict | None:
        """Fetch price + indicator data from TradingView via MCP."""
        try:
            quote        = self._run_mcp("quote_get")
            studies_resp = self._run_mcp("data_get_study_values")
            studies = studies_resp.get("studies", [])

            # 3. Parse studies — values is a dict of {label: "string_value"}
            def to_float(v):
                try:
                    return float(str(v).replace(",","").replace("\u2212","-").replace("−","-"))
                except:
                    return 0.0

            def find_study(name_fragment, value_key):
                for s in studies:
                    if name_fragment.lower() in s.get("name","").lower():
                        vals = s.get("values", {})
                        for k, v in vals.items():
                            if value_key.lower() in k.lower():
                                return to_float(v)
                return 0.0

            # EMA — first occurrence = 20, second = 50
            ema_vals = [to_float(list(s["values"].values())[0])
                        for s in studies
                        if "exponential" in s.get("name","").lower() and s.get("values")]

            data = {
                "close":         quote.get("last", quote.get("close", 0)),
                "RSI":           find_study("Relative Strength", "RSI"),
                "MACD.hist":     find_study("MACD", "Histogram"),
                "BB.upper":      find_study("Bollinger", "Upper"),
                "BB.basis":      find_study("Bollinger", "Basis"),
                "BB.lower":      find_study("Bollinger", "Lower"),
                "ADX":           find_study("ADX", "ADX"),
                "EMA20":         ema_vals[0] if len(ema_vals) > 0 else 0.0,
                "EMA50":         ema_vals[1] if len(ema_vals) > 1 else 0.0,
                "Recommend.All": 0.0,
                "timeframe":     TIMEFRAMES[0],
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            }
            log.debug(f"LENS parsed: RSI={data['RSI']} BB={data['BB.basis']:.0f} EMA20={data['EMA20']:.0f}")
            return data

        except subprocess.TimeoutExpired:
            log.error("LENS MCP timeout (>55s) — TradingView CDP may be slow")
            return None
        except Exception as e:
            log.error(f"LENS MCP call error: {e}")
            return None

    def _is_fresh(self) -> bool:
        return (self._cache is not None and
                (time.time() - self._cache_ts) < CACHE_SECONDS)

    def _write_snapshot(self, snap: LensSnapshot, mode: str):
        data = snap.to_dict()
        data["mode"] = mode
        try:
            with open(SNAPSHOT_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"LENS write error: {e}")

    @staticmethod
    def read_snapshot() -> dict:
        """Read last saved snapshot (used by AURUM/ATHENA without running LENS)."""
        try:
            with open(SNAPSHOT_FILE) as f:
                return json.load(f)
        except:
            return {}


# ── Singleton ─────────────────────────────────────────────────────
_instance: Lens = None

def get_lens() -> Lens:
    global _instance
    if _instance is None:
        _instance = Lens()
    return _instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    lens = Lens()
    snap = lens.fetch_fresh("WATCH")
    if snap:
        print("LENS OK:", json.dumps(snap.to_dict(), indent=2))
    else:
        print("LENS: No data (MCP server not running?)")
        print("Start with: npx tradingview-mcp-jackson")
