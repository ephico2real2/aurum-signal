"""
lens.py — LENS TradingView MCP Market Intelligence
===================================================
Build order: #5 — depends on SCRIBE.
Wraps the LewisWJackson/tradingview-mcp-jackson MCP server.
Caches results for LENS_CACHE_SEC (default 60s). Validates signal entries. Checks TP1 momentum.
"""

import os, json, logging, shutil, subprocess, time, shlex
from datetime import datetime, timezone
from pathlib import Path

from scribe import get_scribe
from status_report import report_component_status
from mcp_client import MCPSession
from freshness import DATA_FRESHNESS_WINDOWS

log = logging.getLogger("lens")

SNAPSHOT_FILE  = os.environ.get(
    "LENS_SNAPSHOT_FILE",
    os.environ.get("LENS_SNAPSHOT", "config/lens_snapshot.json"),
)
BRIEF_FILE     = os.environ.get("LENS_BRIEF_FILE", "config/lens_brief.json")
CACHE_SECONDS  = int(os.environ.get("LENS_CACHE_SEC", str(DATA_FRESHNESS_WINDOWS["LENS"])))
MCP_SERVER_CMD = os.environ.get(
    "LENS_MCP_CMD",
    "npx tradingview-mcp-jackson"
)
ENABLE_TV_BRIEF = os.environ.get("LENS_ENABLE_TV_BRIEF", "true").lower() in ("1", "true", "yes")
TV_BRIEF_INTERVAL_SEC = int(os.environ.get("LENS_TV_BRIEF_INTERVAL_SEC", "1800"))
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
        self.di_plus      = data.get("DI.plus", 0)
        self.di_minus     = data.get("DI.minus", 0)
        self.dmi_present  = bool(data.get("DMI.present", False))
        self.dmi_study    = data.get("DMI.study")
        self.ema_20       = data.get("EMA20", 0)
        self.ema_50       = data.get("EMA50", 0)
        self.order_block_present = bool(data.get("OrderBlock.present", False))
        self.order_block_study   = data.get("OrderBlock.study")
        self.order_block_values  = data.get("OrderBlock.values", {}) or {}
        self.tv_recommend = data.get("Recommend.All")
        self.tv_recommend_source = data.get("Recommend.Source", "UNAVAILABLE")
        self.tv_brief = data.get("TV.Brief")
        self.tv_brief_source = data.get("TV.Brief.Source")
        self.tv_brief_timestamp = data.get("TV.Brief.Timestamp")
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
            "adx": self.adx, "di_plus": self.di_plus, "di_minus": self.di_minus,
            "dmi_present": self.dmi_present, "dmi_study": self.dmi_study,
            "ema_20": self.ema_20, "ema_50": self.ema_50,
            "order_block_present": self.order_block_present,
            "order_block_study": self.order_block_study,
            "order_block_values": self.order_block_values,
            "tv_recommend": self.tv_recommend,
            "tv_recommend_source": self.tv_recommend_source,
            "tv_brief": self.tv_brief,
            "tv_brief_source": self.tv_brief_source,
            "tv_brief_timestamp": self.tv_brief_timestamp,
            "timeframe": self.timeframe,
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
        self._last_tv_brief_ts: float = 0
        self._last_tv_brief: dict | None = None
        Path(SNAPSHOT_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(BRIEF_FILE).parent.mkdir(parents=True, exist_ok=True)
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
            if raw.get("stale"):
                if self._cache:
                    self._cache.data["stale"] = True
                return self._cache
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
                    "pending_entry_threshold_points": mt5_data.get("pending_entry_threshold_points"),
                    "trend_strength_atr_threshold": mt5_data.get("trend_strength_atr_threshold"),
                    "breakout_buffer_points": mt5_data.get("breakout_buffer_points"),
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

    def _stale_lens_data(self) -> dict:
        data = self._cache.to_dict() if self._cache else {}
        data["stale"] = True
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return data

    def _mcp_argv(self) -> list:
        """Resolve npx/node to absolute paths when possible (launchd-safe)."""
        cmd = (MCP_SERVER_CMD or "").strip().strip('"').strip("'")
        parts = shlex.split(cmd)
        if not parts:
            return parts
        exe = shutil.which(parts[0]) or parts[0]
        return [exe] + parts[1:]

    def _run_mcp(self, tool: str, arguments: dict | None = None) -> dict:
        """Spawn MCP server, send one request, read response, kill process."""
        req = {"jsonrpc":"2.0","id":1,"method":"tools/call",
               "params":{"name": tool, "arguments": arguments or {}}}
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

    def _tv_brief_due(self) -> bool:
        return ENABLE_TV_BRIEF and (
            self._last_tv_brief is None or
            (time.time() - self._last_tv_brief_ts) >= TV_BRIEF_INTERVAL_SEC
        )

    def _tv_brief_from_cli(self) -> dict | None:
        tv = shutil.which("tv")
        if not tv:
            return None
        try:
            proc = subprocess.run(
                [tv, "brief", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
                env=os.environ.copy(),
            )
            if proc.returncode != 0:
                return None
            payload = (proc.stdout or "").strip()
            if not payload:
                return None
            try:
                return json.loads(payload)
            except Exception:
                # Non-JSON CLI output fallback
                return {"summary": payload[:1500]}
        except subprocess.TimeoutExpired:
            log.warning("LENS tv brief subprocess timed out; returning stale lens data")
            return self._stale_lens_data()
        except Exception as e:
            log.warning("LENS tv brief subprocess failed: %s", e)
            return None

    def _extract_tv_brief(self, resp: dict | None, source: str) -> dict | None:
        if not isinstance(resp, dict) or not resp:
            return None
        out = {
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for k in ("bias", "summary", "session_bias", "overall", "market_bias"):
            if k in resp and resp.get(k) not in (None, ""):
                out["bias"] = resp.get(k)
                break
        for k in ("brief", "notes", "analysis", "message", "report"):
            if k in resp and resp.get(k) not in (None, ""):
                v = resp.get(k)
                out["summary"] = v if isinstance(v, str) else str(v)
                break
        # keep compact raw for debugging/use by UI/AURUM if needed
        out["raw"] = resp
        return out

    def _write_tv_brief(self, brief: dict):
        try:
            with open(BRIEF_FILE, "w") as f:
                json.dump(brief, f, indent=2)
        except Exception as e:
            log.error(f"LENS brief write error: {e}")

    def _call_mcp(self) -> dict | None:
        """Fetch price + indicator data from TradingView via MCP."""
        try:
            # Preferred path: proper MCP initialize/initialized handshake + persistent session.
            quote = {}
            studies_resp = {}
            chart_state = {}
            ob_boxes_resp = {}
            tv_brief_obj = self._last_tv_brief
            try:
                with MCPSession(timeout=30) as session:
                    quote = session.call("quote_get", {})
                    studies_resp = session.call("data_get_study_values", {})
                    chart_state = session.call("chart_get_state", {})
                    ob_boxes_resp = session.call(
                        "data_get_pine_boxes",
                        {"study_filter": "Order Block Detector", "verbose": False},
                    )
                    if self._tv_brief_due():
                        brief_resp = session.call("morning_brief", {})
                        tv_brief_obj = self._extract_tv_brief(brief_resp, "MCP_TOOL")
                        if tv_brief_obj:
                            self._last_tv_brief = tv_brief_obj
                            self._last_tv_brief_ts = time.time()
                            self._write_tv_brief(tv_brief_obj)
            except Exception as e:
                log.warning(f"LENS MCP session path failed, falling back to legacy one-shot calls: {e}")
                quote = self._run_mcp("quote_get")
                studies_resp = self._run_mcp("data_get_study_values")
                chart_state = self._run_mcp("chart_get_state")
                ob_boxes_resp = self._run_mcp(
                    "data_get_pine_boxes",
                    {"study_filter": "Order Block Detector", "verbose": False},
                )
                if self._tv_brief_due():
                    brief_resp = self._run_mcp("morning_brief")
                    tv_brief_obj = self._extract_tv_brief(brief_resp, "MCP_TOOL_LEGACY")
                    if not tv_brief_obj:
                        tv_brief_obj = self._extract_tv_brief(self._tv_brief_from_cli(), "TV_CLI")
                    if tv_brief_obj:
                        self._last_tv_brief = tv_brief_obj
                        self._last_tv_brief_ts = time.time()
                        self._write_tv_brief(tv_brief_obj)

            studies = studies_resp.get("studies", []) if isinstance(studies_resp, dict) else []
            chart_studies = chart_state.get("studies", []) if isinstance(chart_state, dict) else []

            # 3. Parse studies — values is a dict of {label: "string_value"}
            def to_float(v):
                try:
                    return float(str(v).replace(",","").replace("\u2212","-").replace("−","-"))
                except:
                    return 0.0
            def norm_key(v: str) -> str:
                s = str(v).lower().replace("+", "plus").replace("-", "minus")
                return "".join(ch for ch in s if ch.isalnum())

            def find_study_by_fragments(fragments: list[str]):
                for frag in fragments:
                    frag_l = frag.lower()
                    for s in studies:
                        if frag_l in s.get("name", "").lower():
                            return s
                return None

            def find_value_from_study(study: dict | None, key_candidates: list[str]) -> float:
                if not study:
                    return 0.0
                vals = study.get("values", {}) or {}
                norm_vals = {norm_key(k): v for k, v in vals.items()}
                for cand in key_candidates:
                    nk = norm_key(cand)
                    if nk in norm_vals:
                        return to_float(norm_vals[nk])
                for cand in key_candidates:
                    nk = norm_key(cand)
                    for k, v in norm_vals.items():
                        if nk in k:
                            return to_float(v)
                return 0.0
            def find_value_with_presence(study: dict | None, key_candidates: list[str]) -> tuple[bool, float]:
                if not study:
                    return False, 0.0
                vals = study.get("values", {}) or {}
                norm_vals = {norm_key(k): v for k, v in vals.items()}
                for cand in key_candidates:
                    nk = norm_key(cand)
                    if nk in norm_vals:
                        return True, to_float(norm_vals[nk])
                for cand in key_candidates:
                    nk = norm_key(cand)
                    for k, v in norm_vals.items():
                        if nk in k:
                            return True, to_float(v)
                return False, 0.0

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
            close = to_float(quote.get("last", quote.get("close", 0)) if isinstance(quote, dict) else 0)
            if close <= 0:
                log.warning("LENS MCP returned invalid quote payload (close<=0)")
                return None
            if len(studies) == 0:
                log.warning("LENS MCP returned quote but no studies; keeping previous snapshot")
                return None
            dmi_study = find_study_by_fragments(
                ["adx and di", "directional movement index", "directional movement"]
            )
            dmi_name = dmi_study.get("name") if dmi_study else None
            adx = find_value_from_study(dmi_study, ["ADX"])
            di_plus = find_value_from_study(dmi_study, ["DI+", "+DI", "Plus DI", "PlusDI"])
            di_minus = find_value_from_study(dmi_study, ["DI-", "-DI", "Minus DI", "MinusDI"])

            ob_name = None
            for s in chart_studies:
                nm = s.get("name", "")
                if "order block detector" in nm.lower():
                    ob_name = nm
                    break

            ob_values = {}
            ob_data_study = find_study_by_fragments(["order block detector"])
            if ob_data_study:
                raw_vals = ob_data_study.get("values", {}) or {}
                ob_values = {k: to_float(v) for k, v in raw_vals.items()}
            ob_studies = ob_boxes_resp.get("studies", []) if isinstance(ob_boxes_resp, dict) else []
            ob_zones = []
            if ob_studies:
                try:
                    for s in ob_studies:
                        for z in s.get("zones", []) or []:
                            hi = to_float(z.get("high"))
                            lo = to_float(z.get("low"))
                            if hi > 0 and lo > 0:
                                ob_zones.append({"high": round(hi, 2), "low": round(lo, 2)})
                except Exception:
                    pass
            if ob_zones:
                # Keep a compact payload for API/UI
                ob_values = {
                    "zone_count": len(ob_zones),
                    "zones": ob_zones[:6],
                }
            tv_recommend = None
            tv_recommend_source = "UNAVAILABLE"
            # Try to extract a native recommendation value if available on-chart
            rec_study = find_study_by_fragments(["technical ratings", "recommend"])
            if rec_study:
                rec_found, rec_val = find_value_with_presence(
                    rec_study,
                    ["Recommend.All", "Recommendation", "recommendall", "all"],
                )
                if rec_found:
                    tv_recommend = rec_val
                    tv_recommend_source = "TECHNICAL_RATINGS"
            if tv_recommend is None:
                # Fallback: derive a compact directional score from available indicators.
                score = 0.0
                score += 0.35 if (ema_vals[0] if len(ema_vals) > 0 else 0.0) > (ema_vals[1] if len(ema_vals) > 1 else 0.0) else -0.35
                score += 0.25 if find_study("MACD", "Histogram") > 0 else -0.25
                score += 0.25 if di_plus > di_minus else -0.25
                rsi_now = find_study("Relative Strength", "RSI")
                if rsi_now > 55:
                    score += 0.15
                elif rsi_now < 45:
                    score -= 0.15
                tv_recommend = round(max(-1.0, min(1.0, score)), 2)
                tv_recommend_source = "DERIVED_FROM_INDICATORS"

            data = {
                "close":         close,
                "RSI":           find_study("Relative Strength", "RSI"),
                "MACD.hist":     find_study("MACD", "Histogram"),
                "BB.upper":      find_study("Bollinger", "Upper"),
                "BB.basis":      find_study("Bollinger", "Basis"),
                "BB.lower":      find_study("Bollinger", "Lower"),
                "ADX":           adx,
                "DI.plus":       di_plus,
                "DI.minus":      di_minus,
                "DMI.present":   bool(dmi_study),
                "DMI.study":     dmi_name,
                "EMA20":         ema_vals[0] if len(ema_vals) > 0 else 0.0,
                "EMA50":         ema_vals[1] if len(ema_vals) > 1 else 0.0,
                "OrderBlock.present": bool(ob_name),
                "OrderBlock.study":   ob_name,
                "OrderBlock.values":  ob_values,
                "Recommend.All": tv_recommend,
                "Recommend.Source": tv_recommend_source,
                "TV.Brief": (tv_brief_obj or {}).get("summary"),
                "TV.Brief.Source": (tv_brief_obj or {}).get("source"),
                "TV.Brief.Timestamp": (tv_brief_obj or {}).get("timestamp"),
                "timeframe":     TIMEFRAMES[0],
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            }
            log.debug(f"LENS parsed: RSI={data['RSI']} BB={data['BB.basis']:.0f} EMA20={data['EMA20']:.0f}")
            return data

        except subprocess.TimeoutExpired:
            log.warning("LENS MCP timeout; returning stale lens data")
            return self._stale_lens_data()
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
