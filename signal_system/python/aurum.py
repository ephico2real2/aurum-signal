"""
aurum.py — AURUM AI Agent
=========================
Build order: #8 — depends on SCRIBE, HERALD, LENS.
Claude-powered conversational agent.
Accessible via Telegram bot AND ATHENA dashboard API.
SOUL.md + SKILL.md define identity and capabilities.
Writes aurum_cmd.json for BRIDGE to execute commands.
"""

import os, json, logging, asyncio, time
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from telethon import TelegramClient, events

from scribe import get_scribe
from herald import get_herald
from status_report import report_component_status
from market_data import build_execution_quote, fmt_age_short, safe_float
from trading_session import get_trading_session_utc, session_clock_summary

log = logging.getLogger("aurum")

_PY   = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_PY, ".."))


def _py_rel(rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    return os.path.join(_PY, rel)


def _root_rel(rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    return os.path.join(_ROOT, rel)


# ── Config ──────────────────────────────────────────────────────────
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
BOT_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AURUM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")  # your personal chat
API_ID          = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH        = os.environ.get("TELEGRAM_API_HASH", "")
PHONE           = os.environ.get("TELEGRAM_PHONE", "")

CMD_FILE        = _py_rel(os.environ.get("AURUM_CMD_FILE",    "config/aurum_cmd.json"))
STATUS_FILE     = _py_rel(os.environ.get("BRIDGE_STATUS_FILE","config/status.json"))
MARKET_FILE     = _root_rel(os.environ.get("MT5_MARKET_FILE",   "MT5/market_data.json"))
BROKER_FILE     = _root_rel(os.environ.get("MT5_BROKER_FILE",   "MT5/broker_info.json"))
LENS_FILE       = _py_rel(os.environ.get("LENS_SNAPSHOT_FILE","config/lens_snapshot.json"))
SENTINEL_FILE   = _py_rel(os.environ.get("SENTINEL_STATUS_FILE","config/sentinel_status.json"))
SOUL_FILE       = _root_rel(os.environ.get("SOUL_FILE",         "SOUL.md"))
SKILL_FILE      = _root_rel(os.environ.get("SKILL_FILE",        "SKILL.md"))
SESSION_FILE    = _py_rel(os.environ.get("TELEGRAM_SESSION_FILE", "config/aurum_session"))

MAX_TOKENS      = int(os.environ.get("AURUM_MAX_TOKENS", "1000"))
MODEL           = os.environ.get("AURUM_MODEL", "claude-sonnet-4-6")

Path(_PY, "config").mkdir(parents=True, exist_ok=True)


def _read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""

def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


# Max conversation turns to send to Claude (user+assistant = 1 turn).
# Higher = better continuity but more tokens per call.
MAX_CONV_TURNS = int(os.environ.get("AURUM_MAX_CONV_TURNS", "10"))


class Aurum:
    def __init__(self):
        self.scribe  = get_scribe()
        self.herald  = get_herald()
        self.claude  = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
        self._soul   = _read_file(SOUL_FILE)
        self._skill  = _read_file(SKILL_FILE)
        self._mode   = "SIGNAL"
        # Per-source conversation buffers: {source: [{role, content}, ...]}
        self._conversations: dict[str, list[dict]] = {}
        if not self.claude:
            log.warning("AURUM: ANTHROPIC_API_KEY not set")
        log.info("AURUM initialised")

    def set_mode(self, mode: str):
        self._mode = mode

    # ── Core query handler ─────────────────────────────────────────
    def ask(self, query: str, source: str = "TELEGRAM") -> str:
        """
        Answer a query. Returns response string.
        Injects last 5 conversations from SCRIBE for continuity.
        If query triggers live-search keywords, injects web search results.
        """
        if not self.claude:
            return "AURUM: Claude API not configured. Set ANTHROPIC_API_KEY in .env"

        context  = self._build_context()

        # On-demand web search: inject fresh results when query asks about live events
        web_context = self._maybe_web_search(query)
        if web_context:
            context += "\n\n" + web_context

        memory   = self._build_memory()
        system   = self._build_system_prompt(context, memory)

        # Build multi-turn messages (user/assistant pairs for continuity)
        messages = self._get_conversation_messages(query, source)

        try:
            resp = self.claude.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
            )
            answer = resp.content[0].text.strip()
            tokens = resp.usage.input_tokens + resp.usage.output_tokens

            # Append assistant response to conversation buffer
            self._append_to_conversation(source, "assistant", answer)

            # Log to SCRIBE
            self.scribe.log_aurum_conversation(
                query=query, response=answer,
                mode=self._mode, source=source, tokens=tokens
            )

            try:
                report_component_status(
                    "AURUM",
                    "OK",
                    mode=self._mode,
                    note=f"tokens={tokens}",
                    last_action=f"answered: {query[:80]}",
                )
            except Exception as _he:
                log.debug(f"AURUM heartbeat error: {_he}")

            # Check if response contains a command
            self._check_for_command(answer)
            self._extract_json_commands_from_response(answer)

            return answer

        except Exception as e:
            log.error(f"AURUM query error: {e}")
            return f"AURUM: Error — {str(e)[:100]}"

    def _build_system_prompt(self, context: str, memory: str = "") -> str:
        # Re-read SOUL + SKILL from disk so edits take effect without restart
        soul  = _read_file(SOUL_FILE)  or self._soul
        skill = _read_file(SKILL_FILE) or self._skill
        parts = [soul, skill, "---", "## CURRENT SYSTEM STATE (live data)", context]
        if memory:
            parts += ["---", "## RECENT CONVERSATION HISTORY (from SCRIBE)", memory]
        parts += [
            "---",
            "## BRIDGE / FORGE command contract (critical)",
            "Trades are executed only when BRIDGE writes MT5/command.json with action OPEN_GROUP (FORGE EA).",
            "You queue work by writing **config/aurum_cmd.json** — done automatically when you:",
            "- Say **Switching to SCALPER mode.** / **Switching to WATCH mode.** etc. (exact phrase → MODE_CHANGE), OR",
            "- Put **one** ```json code fence in your reply with a supported action (parsed after each answer).",
            "Supported JSON actions:",
            '- MODE_CHANGE: {"action":"MODE_CHANGE","new_mode":"SCALPER","reason":"..."}',
            '- OPEN_GROUP (preferred): {"action":"OPEN_GROUP","direction":"SELL","entry_low":4610.7,"entry_high":4610.9,"sl":4614.0,"tp1":4607.0,"tp2":null,"lot_per_trade":0.01,"reason":"..."}',
            '- MODIFY_TP: {"action":"MODIFY_TP","tp":4648.50,"group_id":15,"reason":"..."}',
            '- MODIFY_SL: {"action":"MODIFY_SL","sl":4660.00,"group_id":15,"reason":"..."}',
            '- CLOSE_GROUP: {"action":"CLOSE_GROUP","group_id":15,"reason":"..."}',
            '- CLOSE_GROUP_PCT: {"action":"CLOSE_GROUP_PCT","group_id":15,"pct":70,"reason":"..."}',
            '- CLOSE_ALL, MOVE_BE, CLOSE_PROFITABLE, CLOSE_LOSING (no group_id needed)',
            '- OPEN_TRADE is accepted as an alias for OPEN_GROUP; map numeric "entry" or entry=market uses MT5 mid from context.',
            "Do **not** use action OPEN_TRADE as a separate protocol — it is normalized to OPEN_GROUP.",
            "**Multiple commands**: If you need to modify MULTIPLE groups, put each as a SEPARATE ```json block in your reply. "
            "BRIDGE processes them sequentially (6s delay between each). All blocks in one reply are fine.",
            "Never tell the user a trade was written unless you included a valid JSON fence or the mode-change phrase above.",
            "BRIDGE runs AEGIS on every OPEN_GROUP; if AEGIS rejects, FORGE never sees the order.",
            "Automatic SCALPER entries from BRIDGE (without AURUM) only fire when ADX>20 and RSI/MACD/BB align — low ADX means no *auto* scalp from BRIDGE.",
            "That ADX rule does NOT apply to **you**: if the user **explicitly** asks you to place a trade / act / buy or sell with size, you MUST output a valid OPEN_GROUP JSON (sl, tp1, lot, entry from MT5+structure) and state risks in reason — do not refuse solely because ADX is 0 or session is thin. Still skip OPEN_GROUP if MT5 price missing or SENTINEL clearly blocks.",
            "If **CURRENT SYSTEM STATE** shows **ACCOUNT_TYPE: DEMO**, treat explicit execution requests as practice: still use SL/TP and AEGIS, but **never** refuse those orders only for 'hard filter' / trendless / ADX=0 — put the caveat in `reason` and issue the JSON.",
            "---",
            "## MT5 vs SCRIBE vs order types (do not confuse these)",
            "- **Open positions** (MT5 `open_positions_count` in context): **filled** deals only. Working **Buy/Sell Limit** or **Stop** orders that are not filled are **not** counted there.",
            "- **OPEN TRADE GROUPS** in context come from **SCRIBE** (`trade_groups` status OPEN/PARTIAL). That is **internal bookkeeping** after BRIDGE queued FORGE — not a guaranteed mirror of the broker's Order tab. Do **not** call them 'pending orders' or 'working limits' as fact; say they *may* correspond to resting limits or may be stale vs MT5 if reconciliation lagged.",
            "- If **positions = 0** but **open groups > 0**, list possibilities: (1) FORGE placed **limit** entries still waiting, (2) orders filled and closed already while SCRIBE still OPEN, (3) mismatch — recommend checking MT5 **Trade**: Positions vs **Orders** (pendings).",
            "- **session_pnl** (MT5): **realized** P&L vs session-start balance from the EA — includes closed trades, fees, spread on closes; it is **not** the same as summing SCRIBE group lines (those may show $0 until positions exist or close).",
            "- **OPEN_GROUP / entry ladder**: FORGE may use **market** or **limit** from ladder vs live bid/ask; 'SELL with entries above bid' often becomes **Sell Limit**. Use correct terms when explaining risk.",
            "---",
            "Always refer to this context when answering. "
            "If data seems stale or missing, say so rather than guessing.",
        ]
        return "\n\n".join(parts)

    # ── Conversation buffer (multi-turn continuity) ───────────────
    def _get_conversation_messages(self, query: str, source: str) -> list[dict]:
        """
        Build the messages array for Claude with conversation history.
        Appends the new user query and returns the full list.
        On first call for a source, seeds from SCRIBE for restart continuity.
        """
        if source not in self._conversations:
            self._seed_conversation_from_scribe(source)

        # Append current user query
        self._append_to_conversation(source, "user", query)

        return list(self._conversations[source])

    def _append_to_conversation(self, source: str, role: str, content: str):
        """Append a message and trim to MAX_CONV_TURNS."""
        if source not in self._conversations:
            self._conversations[source] = []
        self._conversations[source].append({"role": role, "content": content})
        # Trim: keep last MAX_CONV_TURNS * 2 messages (user+assistant pairs)
        max_msgs = MAX_CONV_TURNS * 2
        if len(self._conversations[source]) > max_msgs:
            self._conversations[source] = self._conversations[source][-max_msgs:]
            # Ensure conversation starts with a user message (Claude requirement)
            while (self._conversations[source]
                   and self._conversations[source][0]["role"] != "user"):
                self._conversations[source].pop(0)

    def _seed_conversation_from_scribe(self, source: str):
        """
        On first call after restart, load recent conversations from SCRIBE
        so AURUM remembers what was discussed before the restart.
        """
        self._conversations[source] = []
        try:
            rows = self.scribe.query(
                """SELECT query, response FROM aurum_conversations
                   WHERE source = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (source, MAX_CONV_TURNS),
            )
        except Exception as e:
            log.warning("AURUM conversation seed failed: %s", e)
            return
        if not rows:
            return
        # Reverse to chronological order
        for r in reversed(rows):
            q = r.get("query", "")
            a = r.get("response", "")
            if q:
                self._conversations[source].append({"role": "user", "content": q})
            if a:
                self._conversations[source].append({"role": "assistant", "content": a})
        log.info("AURUM: seeded %d messages for %s from SCRIBE",
                 len(self._conversations[source]), source)

    def _build_memory(self) -> str:
        """
        Brief summary of recent conversation topics for the system prompt.
        Full conversation history is now in the messages array; this is
        a lightweight supplement for cross-source awareness.
        """
        try:
            rows = self.scribe.query(
                """SELECT timestamp, source, query, response
                   FROM aurum_conversations
                   ORDER BY timestamp DESC
                   LIMIT 5"""
            )
        except Exception as e:
            log.warning(f"AURUM memory query failed: {e}")
            return ""

        if not rows:
            return ""

        rows = list(reversed(rows))
        lines = []
        for r in rows:
            ts  = r.get("timestamp","")[:16]
            src = r.get("source","?")
            q   = r.get("query","")[:120]
            a   = r.get("response","")[:200]
            lines.append(f"[{ts} via {src}]\nYou: {q}\nAURUM: {a}")

        return "\n\n".join(lines)

    def _build_context(self) -> str:
        lines = []

        # Mode + time (session from UTC kill zones — same logic as BRIDGE/trading_session.py)
        status   = _read_json(STATUS_FILE)
        mode     = status.get("mode", self._mode)
        now_utc  = datetime.now(timezone.utc)
        session  = get_trading_session_utc(now_utc)
        lines.append(f"MODE: {mode}  SESSION: {session}")
        lines.append(f"TIME: {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(session_clock_summary())

        broker = _read_json(BROKER_FILE)
        acct_type = (broker.get("account_type") or "UNKNOWN").upper()
        if acct_type == "DEMO":
            lines.append(
                "\n**ACCOUNT_TYPE: DEMO** (FORGE `broker_info.json`) — practice capital, not live money. "
                "When the operator explicitly requests a trade, emit OPEN_GROUP with SL/TP per SKILL; "
                "do **not** refuse solely because ADX is low or the session is thin (that caution is for unsolicited live advice, not for demo execution orders)."
            )
        elif acct_type == "LIVE":
            lines.append(
                "\n**ACCOUNT_TYPE: LIVE** — real broker capital. Unsolicited entries deserve extra scrutiny; "
                "operator-directed OPEN_GROUP still follows SKILL §5 (SL/TP required)."
            )
        else:
            lines.append(
                f"\n**ACCOUNT_TYPE: {acct_type}** (if this is demo, ensure FORGE writes broker_info.json)."
            )

        # Account from MT5
        mt5 = _read_json(MARKET_FILE)
        if mt5:
            acc = mt5.get("account", {})
            br = broker.get("broker") or ""
            srv = broker.get("server") or ""
            tag = f" ({acct_type}" + (f" · {br}" if br else "") + (f" · {srv}" if srv else "") + ")"
            lines.append(f"\nACCOUNT (MT5){tag}:")
            lines.append(f"  Balance:  ${acc.get('balance',0):,.2f}")
            lines.append(f"  Equity:   ${acc.get('equity',0):,.2f}")
            lines.append(f"  Floating: ${acc.get('total_floating_pnl',0):+.2f}")
            lines.append(f"  Session P&L: ${acc.get('session_pnl',0):+.2f}")
            opc = int(acc.get("open_positions_count") or 0)
            lines.append(f"  Open positions (filled only, MT5): {opc}")

        # Open groups from SCRIBE
        groups = self.scribe.get_open_groups()
        if groups:
            lines.append(
                f"\nOPEN TRADE GROUPS — SCRIBE bookkeeping ({len(groups)}), not the broker order list:"
            )
            for g in groups[:5]:
                lines.append(
                    f"  [{g['id']}] {g['direction']} ×{g['num_trades']} "
                    f"@ {g['entry_low']:.0f}–{g['entry_high']:.0f} "
                    f"SL:{g['sl']:.0f} TP1:{g['tp1']:.0f} "
                    f"Status:{g['status']} P&L:${g.get('total_pnl',0) or 0:.2f}"
                )
            if mt5:
                opc = int((mt5.get("account") or {}).get("open_positions_count") or 0)
                if opc == 0:
                    lines.append(
                        "  → MT5 shows 0 **filled** positions while SCRIBE still has open groups — "
                        "possible resting **limit/stop** orders, or SCRIBE/MT5 out of sync; "
                        "check MT5 Trade tab (Orders vs Positions). Do not assert 'pending sells' as fact."
                    )

        # LENS: indicators from TradingView MCP snapshot; gold execution price from MT5 when fresh
        lens = _read_json(LENS_FILE)
        ex = build_execution_quote(mt5)
        tv_last = safe_float(lens.get("price")) if lens else None
        age_tv = lens.get("age_seconds")
        age_tv_s = f"{fmt_age_short(float(age_tv))} ago" if age_tv is not None else "age unknown"

        if lens:
            lines.append(f"\nLENS (TradingView chart — {lens.get('timeframe','?')}, snapshot {age_tv_s}):")
            lines.append(
                "  **Use MT5 prices below for XAUUSD execution.** "
                "TradingView 'last' can be another symbol, CFD, or delayed — do not call it gold if it disagrees with MT5 by >$2."
            )
            if tv_last is not None:
                lines.append(f"  Chart last (indicator context only): ${tv_last:.2f}")
            lines.append(f"  RSI: {lens.get('rsi',0):.1f}  "
                         f"MACD hist: {lens.get('macd_hist',0):+.5f}  "
                         f"BB rating: {lens.get('bb_rating',0):+d}  "
                         f"ADX: {lens.get('adx',0):.1f}")
            # Full indicator levels for SL/TP calculation
            bb_u = lens.get('bb_upper')
            bb_m = lens.get('bb_mid')
            bb_l = lens.get('bb_lower')
            bb_w = lens.get('bb_width')
            if bb_u and bb_m and bb_l:
                lines.append(f"  BB bands: upper ${bb_u:.2f}  mid ${bb_m:.2f}  lower ${bb_l:.2f}  width {bb_w:.4f}")
                if lens.get('bb_squeeze'):
                    lines.append("  ⚠ BB SQUEEZE — volatility compressed, breakout likely")
            ema20 = lens.get('ema_20')
            ema50 = lens.get('ema_50')
            if ema20 and ema50:
                trend = "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "FLAT"
                lines.append(f"  EMA20: ${ema20:.2f}  EMA50: ${ema50:.2f}  ({trend})")
            if ex.get("usable") and ex.get("mid") is not None and tv_last is not None:
                diff = abs(float(tv_last) - float(ex["mid"]))
                if diff > 2.0:
                    lines.append(
                        f"  ⚠ TV vs MT5 mid mismatch: ${diff:.2f} — trust MT5 for gold level, TV for momentum shape only."
                    )

        # MT5 indicators from FORGE (H1 + multi-timeframe M5/M15/M30)
        if mt5:
            h1 = mt5.get("indicators_h1", {})
            atr = h1.get("atr_14")
            mt5_rsi = h1.get("rsi_14")
            mt5_ma20 = h1.get("ma_20")
            mt5_ma50 = h1.get("ma_50")
            if atr:
                lines.append(f"\nMT5 H1 (FORGE):")
                lines.append(f"  ATR(14): ${atr:.2f} — use 1.5×ATR for SL distance, 2×ATR for TP minimum")
                if mt5_rsi:
                    lines.append(f"  RSI(14): {mt5_rsi:.1f}")
                if mt5_ma20 and mt5_ma50:
                    lines.append(f"  EMA20: ${mt5_ma20:.2f}  EMA50: ${mt5_ma50:.2f}")

            # Multi-timeframe scalping data (M5, M15, M30)
            mtf_labels = [("indicators_m5", "M5"), ("indicators_m15", "M15"), ("indicators_m30", "M30")]
            mtf_found = []
            for key, label in mtf_labels:
                tf = mt5.get(key, {})
                if not tf or not tf.get("rsi_14"):
                    continue
                rsi_v = tf.get("rsi_14", 0)
                atr_v = tf.get("atr_14", 0)
                ema20_v = tf.get("ema_20", 0)
                ema50_v = tf.get("ema_50", 0)
                bb_u = tf.get("bb_upper", 0)
                bb_m = tf.get("bb_mid", 0)
                bb_l = tf.get("bb_lower", 0)
                trend = "BULL" if ema20_v > ema50_v else "BEAR" if ema20_v < ema50_v else "FLAT"
                mtf_found.append(
                    f"  {label}: RSI {rsi_v:.1f} | ATR ${atr_v:.2f} | "
                    f"EMA20 ${ema20_v:.2f} EMA50 ${ema50_v:.2f} ({trend}) | "
                    f"BB [{bb_l:.2f} / {bb_m:.2f} / {bb_u:.2f}]"
                )
            if mtf_found:
                lines.append(f"\nMT5 MULTI-TIMEFRAME (FORGE — scalping context):")
                lines.extend(mtf_found)
                lines.append(
                    "  Use M5 for entry timing, M15 for structure, M30 for bias. "
                    "BB bands are target zones; ATR sizes your SL."
                )
        if ex.get("usable"):
            sym = ex.get("symbol") or "XAUUSD"
            lines.append(
                f"\nMT5 EXECUTION (fresh): {sym} bid ${ex['bid']:.2f} ask ${ex['ask']:.2f} "
                f"mid ${ex['mid']:.2f} (file age {fmt_age_short(ex.get('age_sec'))})"
            )
        elif lens and tv_last is not None:
            lines.append(
                f"\nMT5 quote stale or missing — do not size trades on price; "
                f"TV chart last ${tv_last:.2f} is not verified as broker XAUUSD."
            )

        # Sentinel
        sent = _read_json(SENTINEL_FILE)
        if sent:
            active = sent.get("active", False)
            lines.append(f"\nSENTINEL: {'⚠ ACTIVE — TRADING PAUSED' if active else 'Clear'}")
            if sent.get("next_event"):
                lines.append(
                    f"  Next: {sent['next_event']} in {sent.get('next_in_min','?')}min "
                    f"({sent.get('next_time','?')})"
                )
            cals = sent.get("calendar_currencies")
            if cals:
                lines.append(f"  Calendar currencies monitored: {', '.join(cals)}")
            nf = sent.get("news_feeds") or {}
            if isinstance(nf, dict):
                heads: list[str] = []
                for key in ("fxstreet", "google_news", "investing_forex", "dailyfx", "extra"):
                    for row in nf.get(key) or []:
                        t = (row.get("title") or "").strip()
                        if not t:
                            continue
                        src = row.get("source", key)
                        heads.append(f"[{src}] {t[:100]}")
                        if len(heads) >= 6:
                            break
                    if len(heads) >= 6:
                        break
                if heads:
                    lines.append("  RSS headlines (FXStreet / Google News / Investing / DailyFX / extras):")
                    for h in heads:
                        lines.append(f"    · {h}")

        # Performance
        perf = self.scribe.get_performance(days=7)
        wr = perf.get("win_rate")
        wr_s = f"{wr:.0f}%" if wr is not None else "n/a (no closes in window)"
        lines.append(f"\nPERFORMANCE (last 7d UTC, SCRIBE closed trades):")
        lines.append(f"  P&L: ${perf.get('total_pnl',0):+.2f}  "
                     f"Trades: {perf.get('total',0)}  "
                     f"Win rate: {wr_s}  "
                     f"Avg pips: {perf.get('avg_pips',0):+.1f}")

        # Recent closures (SL/TP hits)
        try:
            closures = self.scribe.get_recent_closures(limit=5, days=1)
            if closures:
                lines.append(f"\nRECENT CLOSURES (last 24h):")
                for c in closures:
                    lines.append(
                        f"  [{c.get('close_reason','?')}] #{c.get('ticket','?')} "
                        f"G{c.get('trade_group_id','?')} {c.get('direction','?')} "
                        f"pnl=${c.get('pnl',0):+.2f} pips={c.get('pips',0):+.1f}")
            cstats = self.scribe.get_closure_stats(days=7)
            if cstats.get("total", 0) > 0:
                lines.append(
                    f"  7d stats: SL hit rate {cstats['sl_rate']}% "
                    f"TP hit rate {cstats['tp_rate']}% "
                    f"({cstats['sl_hits']} SL, {cstats['tp1_hits']} TP1, "
                    f"{cstats['tp2_hits']} TP2, {cstats['manual']} manual)")
        except Exception as e:
            log.debug("AURUM closure context error: %s", e)

        return "\n".join(lines)

    # ── On-demand web search ──────────────────────────────────────
    @staticmethod
    def _maybe_web_search(query: str) -> str | None:
        """
        If the query contains trigger keywords and Google CSE is configured,
        run a live web search and return formatted context. Otherwise None.
        """
        try:
            from web_search import needs_search, is_available, search_and_format
        except ImportError:
            return None
        if not is_available() or not needs_search(query):
            return None
        try:
            return search_and_format(query, num_results=3)
        except Exception as e:
            log.debug("AURUM web_search failed: %s", e)
            return None

    def _extract_json_commands_from_response(self, text: str) -> None:
        """Parse ```json ... ``` fences and write actionable commands to aurum_cmd.json.

        IMPORTANT: aurum_cmd.json holds ONE command at a time. If the response
        contains multiple JSON blocks, they are queued sequentially with a
        small delay so BRIDGE can process each before the next overwrites.
        """
        if not text or "```" not in text:
            return
        chunks = text.split("```")
        valid_actions = (
            "MODE_CHANGE", "CLOSE_ALL", "OPEN_GROUP", "OPEN_TRADE",
            "MODIFY_TP", "MODIFY_SL", "CLOSE_GROUP", "CLOSE_GROUP_PCT",
            "MOVE_BE", "CLOSE_PROFITABLE", "CLOSE_LOSING",
            "SENTINEL_OVERRIDE",
        )
        commands_found: list[dict] = []
        for i in range(1, len(chunks), 2):
            block = chunks[i].strip()
            if block.lower().startswith("json"):
                block = block[4:].lstrip("\n\r")
            block = block.strip()
            if not block.startswith("{"):
                continue
            try:
                obj = json.loads(block)
            except json.JSONDecodeError:
                continue
            act = (obj.get("action") or "").upper()
            if act == "OPEN_TRADE":
                obj["action"] = "OPEN_GROUP"
                act = "OPEN_GROUP"
            if act in valid_actions:
                obj["timestamp"] = datetime.now(timezone.utc).isoformat()
                commands_found.append(obj)

        if not commands_found:
            return

        if len(commands_found) > 1:
            log.warning(
                "AURUM: %d JSON commands in one reply — processing sequentially "
                "(aurum_cmd.json holds one at a time)",
                len(commands_found),
            )

        # Write commands sequentially with delay between them
        for idx, cmd in enumerate(commands_found):
            if idx > 0:
                # Wait for BRIDGE to consume previous command (~6s > BRIDGE_LOOP_SEC)
                import time as _time
                _time.sleep(6)
            self.write_command(cmd)
            log.info("AURUM: queued %s from response JSON (%d/%d)",
                     cmd.get("action"), idx + 1, len(commands_found))

    def _check_for_command(self, response: str):
        """Check if AURUM's response contains a system command to execute."""
        resp_lower = response.lower()
        cmd = None

        if "switching to watch" in resp_lower or "mode → watch" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "WATCH", "reason": "AURUM"}
        elif "switching to hybrid" in resp_lower or "mode → hybrid" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "HYBRID", "reason": "AURUM"}
        elif "switching to signal" in resp_lower or "mode → signal" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "SIGNAL", "reason": "AURUM"}
        elif "switching to scalper" in resp_lower or "mode → scalper" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "SCALPER", "reason": "AURUM"}

        if cmd:
            cmd["timestamp"] = datetime.now(timezone.utc).isoformat()
            self.write_command(cmd)
            log.info(f"AURUM wrote command: {cmd}")

    def write_command(self, cmd: dict):
        """Write a command for BRIDGE to execute."""
        cmd["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(CMD_FILE, "w") as f:
                json.dump(cmd, f, indent=2)
        except Exception as e:
            log.error(f"AURUM write command error: {e}")

    # ── Telegram bot handler ───────────────────────────────────
    async def start_telegram(self):
        """Start Telegram bot that listens for messages in your personal chat."""
        if not all([API_ID, API_HASH]):
            log.warning("AURUM: Telegram not configured")
            return

        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start(phone=PHONE)

        # Resolve who we are and the target chat
        me = await client.get_me()
        my_id = me.id
        target_chat = int(AURUM_CHAT_ID) if AURUM_CHAT_ID else None
        log.info(f"AURUM: logged in as user {my_id}, listening on chat {target_chat}")

        @client.on(events.NewMessage(chats=target_chat))
        async def on_message(event):
            # Only respond to messages FROM us (not bot replies)
            if event.message.sender_id != my_id:
                return
            text = event.message.message or ""
            if not text.strip() or text.startswith("/system"):
                return
            log.info(f"AURUM query from Telegram: {text[:60]}")
            reply = self.ask(text, source="TELEGRAM")
            await event.respond(reply)

        log.info("AURUM Telegram bot listening")
        await client.run_until_disconnected()

    # ── Flask API endpoint (called by ATHENA) ─────────────────────
    def flask_ask(self, query: str) -> dict:
        """Used by athena_api.py for the dashboard chat panel."""
        response = self.ask(query, source="ATHENA")
        return {"response": response, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Singleton ─────────────────────────────────────────────────────
_instance: Aurum = None

def get_aurum() -> Aurum:
    global _instance
    if _instance is None:
        _instance = Aurum()
    return _instance


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    a = Aurum()
    if "--telegram" in sys.argv:
        asyncio.run(a.start_telegram())
    else:
        # Interactive test
        print("AURUM interactive test (type 'quit' to exit)")
        while True:
            q = input("\nYou: ").strip()
            if q.lower() in ("quit","exit","q"):
                break
            print(f"\nAURUM: {a.ask(q, source='TEST')}")
