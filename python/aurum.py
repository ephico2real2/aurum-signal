"""
aurum.py — AURUM AI Agent
=========================
Build order: #8 — depends on SCRIBE, HERALD, LENS.
Claude-powered conversational agent.
Accessible via Telegram bot AND ATHENA dashboard API.
SOUL.md + SKILL.md define identity and capabilities.
Writes aurum_cmd.json for BRIDGE to execute commands.
"""

import os, json, logging, asyncio, time, tempfile, re, signal
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from telethon import TelegramClient, events

from scribe import get_scribe
from herald import get_herald
from status_report import report_component_status
from market_data import build_execution_quote, fmt_age_short, safe_float
from trading_session import get_trading_session_utc, session_clock_summary
from mcp_client import MCPSession
from vision import Vision

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
SCALPER_CFG     = os.path.join(_ROOT, "config", "scalper_config.json")
SESSION_FILE    = _py_rel(os.environ.get("TELEGRAM_SESSION_FILE", "config/aurum_session"))
MCP_RESULTS_FILE = _py_rel(os.environ.get("AURUM_MCP_RESULTS_FILE", "config/aurum_mcp_results.json"))

MAX_TOKENS      = int(os.environ.get("AURUM_MAX_TOKENS", "1000"))
MODEL           = os.environ.get("AURUM_MODEL", "claude-sonnet-4-6")
VISION_ENABLED  = os.environ.get("VISION_ENABLED", "true").lower() in ("1", "true", "yes")
MCP_RESULT_STALE_SEC = int(os.environ.get("AURUM_MCP_RESULT_STALE_SEC", "300"))
MCP_RESULT_MAX_ITEMS = int(os.environ.get("AURUM_MCP_RESULT_MAX_ITEMS", "10"))
MCP_RESULT_RETENTION_SEC = int(os.environ.get("AURUM_MCP_RESULT_RETENTION_SEC", "86400"))
MCP_ALERTS_ENABLED = os.environ.get("AURUM_MCP_ALERTS_ENABLED", "true").lower() in ("1", "true", "yes")

Path(_PY, "config").mkdir(parents=True, exist_ok=True)


def _read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""


_SOUL_CACHE = ""
_SKILL_CACHE = ""


def _reload_prompt_cache(signum=None, frame=None) -> None:
    global _SOUL_CACHE, _SKILL_CACHE
    _SOUL_CACHE = _read_file(SOUL_FILE)
    _SKILL_CACHE = _read_file(SKILL_FILE)
    if signum is not None:
        log.info("AURUM: reloaded SOUL/SKILL prompt cache via SIGHUP")


_reload_prompt_cache()
try:
    signal.signal(signal.SIGHUP, _reload_prompt_cache)
except (AttributeError, ValueError):
    log.debug("AURUM: SIGHUP prompt reload unavailable in this runtime")

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
        self.vision  = Vision(self.claude)
        self._soul   = _SOUL_CACHE
        self._skill  = _SKILL_CACHE
        self._mode   = "SIGNAL"
        # Per-source conversation buffers: {source: [{role, content}, ...]}
        self._conversations: dict[str, list[dict]] = {}
        self._mcp_results_file = MCP_RESULTS_FILE
        self._mcp_last_results: list[dict] = []
        self._load_mcp_results()
        if not self.claude:
            log.warning("AURUM: ANTHROPIC_API_KEY not set")
        log.info("AURUM initialised")

    def set_mode(self, mode: str):
        self._mode = mode

    @staticmethod
    def _message_has_media(message) -> bool:
        if not message:
            return False
        return bool(
            getattr(message, "photo", None)
            or getattr(message, "document", None)
            or getattr(message, "effective_attachment", None)
            or getattr(message, "animation", None)
            or getattr(message, "video", None)
        )

    # ── Core query handler ─────────────────────────────────────────
    def ask(self, query: str, source: str = "TELEGRAM", extra_context: str = "") -> str:
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

        if extra_context:
            context += "\n\n" + extra_context
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
            try:
                self._extract_json_commands_from_response(answer, source=source)
            except TypeError as e:
                if "unexpected keyword argument 'source'" in str(e):
                    self._extract_json_commands_from_response(answer)
                else:
                    raise

            # Execute chart commands via TradingView MCP
            chart_result = self._execute_chart_commands(answer)
            if chart_result:
                answer = self._reconcile_loopback_answer(answer, chart_result)
                answer += f"\n\n📊 Chart result: {chart_result}"

            # Append FINAL assistant response (post-MCP reconciliation)
            self._append_to_conversation(source, "assistant", answer)

            # Log FINAL response to SCRIBE
            self.scribe.log_aurum_conversation(
                query=query, response=answer,
                mode=self._mode, source=source, tokens=tokens
            )

            return answer

        except Exception as e:
            log.error(f"AURUM query error: {e}")
            return f"AURUM: Error — {str(e)[:100]}"

    def _build_system_prompt(self, context: str, memory: str = "") -> str:
        soul  = _SOUL_CACHE or self._soul
        skill = _SKILL_CACHE or self._skill
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
            '- SCRIBE_QUERY: {"action":"SCRIBE_QUERY","sql":"SELECT id,status,timestamp FROM trade_groups ORDER BY id DESC LIMIT 5","reply_to":"TELEGRAM"}',
            '- SHELL_EXEC (preferred): {"action":"SHELL_EXEC","program":"python3","args":["scripts/analyse_performance.py","--days","7"],"timeout_sec":30,"reply_to":"TELEGRAM"}',
            '- SHELL_EXEC (legacy): {"action":"SHELL_EXEC","cmd":"python3 scripts/analyse_performance.py --days 7","reply_to":"TELEGRAM"}',
            '- AURUM_EXEC (HTTP bridge): {"action":"AURUM_EXEC","payload":{"action":"SCRIBE_QUERY","sql":"SELECT COUNT(*) AS n FROM trade_positions"},"reply_to":"TELEGRAM"}',
            '- ANALYSIS_RUN (deferred async analysis, results posted to Telegram by query_id): '
            '{"action":"ANALYSIS_RUN","kind":"trade_group_review","params":{"group_id":56},"notify":{"telegram":true},"reason":"..."}',
            '- MODIFY_TP: {"action":"MODIFY_TP","tp":4648.50,"group_id":15,"tp_stage":1,"reason":"..."}  (also accepts "ticket":<int>)',
            '- MODIFY_SL: {"action":"MODIFY_SL","sl":4660.00,"group_id":15,"tp_stage":2,"reason":"..."}  (also accepts "ticket":<int>)',
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
            "## TradingView chart control (via MCP)",
            "You can interact with the live TradingView Desktop chart. To execute a chart action, "
            "include a ```chart_command code fence with a JSON object: {\"tool\": \"tool_name\", \"args\": {...}}",
            "Available tools:",
            '- chart_set_symbol: {"tool":"chart_set_symbol","args":{"symbol":"XAUUSD"}} — change ticker',
            '- chart_set_timeframe: {"tool":"chart_set_timeframe","args":{"timeframe":"60"}} — 1/5/15/60/D/W',
            '- chart_manage_indicator: {"tool":"chart_manage_indicator","args":{"action":"add","indicator":"Bollinger Bands"}} — add/remove indicator',
            '- indicator_set_inputs: {"tool":"indicator_set_inputs","args":{"entity_id":"...","inputs":"{\\"length\\":20}"}}',
            '- data_get_study_values: {"tool":"data_get_study_values","args":{}} — read all indicator values',
            '- data_get_pine_boxes: {"tool":"data_get_pine_boxes","args":{"study_filter":"Order Block"}} — read OB/FVG zones',
            '- data_get_pine_lines: {"tool":"data_get_pine_lines","args":{}} — read drawn price levels',
            '- quote_get: {"tool":"quote_get","args":{}} — current price/OHLC',
            '- chart_get_state: {"tool":"chart_get_state","args":{}} — symbol, timeframe, all studies',
            '- capture_screenshot: {"tool":"capture_screenshot","args":{}} — screenshot the chart',
            "You may use multiple ```chart_command blocks in one reply. Results are appended to your response.",
            "If the user asks about chart state, levels, or indicators — read them via MCP rather than guessing.",
            "---",
            "## MT5 vs SCRIBE vs order types (do not confuse these)",
            "- **Open positions** (MT5 `open_positions_count` in context): **filled** deals only. Working **Buy/Sell Limit** or **Stop** orders that are not filled are **not** counted there.",
            "- **OPEN TRADE GROUPS** in context come from **SCRIBE** (`trade_groups` status OPEN/PARTIAL). That is **internal bookkeeping** after BRIDGE queued FORGE — not a guaranteed mirror of the broker's Order tab. Do **not** call them 'pending orders' or 'working limits' as fact; say they *may* correspond to resting limits or may be stale vs MT5 if reconciliation lagged.",
            "- If **positions = 0** but **open groups > 0**, list possibilities: (1) FORGE placed **limit** entries still waiting, (2) orders filled and closed already while SCRIBE still OPEN, (3) mismatch — recommend checking MT5 **Trade**: Positions vs **Orders** (pendings).",
            "- **session_pnl** (MT5): **realized** P&L vs session-start balance from the EA — includes closed trades, fees, spread on closes; it is **not** the same as summing SCRIBE group lines (those may show $0 until positions exist or close).",
            "- **OPEN_GROUP / entry ladder**: FORGE may use **market** or **limit** from ladder vs live bid/ask; 'SELL with entries above bid' often becomes **Sell Limit**. Use correct terms when explaining risk.",
            "---",
            "## DEFERRED ANALYSIS RUNS (ANALYSIS_RUN)",
            "Use this when the operator asks for an analysis/report that takes time or that you want delivered to Telegram as a self-contained message.",
            "Emit a JSON command:",
            '  {"action":"ANALYSIS_RUN","kind":"<registered_kind>","params":{...},"notify":{"telegram":true},"reason":"..."}',
            "Behaviour:",
            "- BRIDGE returns immediately with a `query_id` and `status:PENDING`. Do NOT poll or block; the run is async.",
            "- The handler writes `logs/analysis/<query_id>.{json,md}` and the result body is posted to the existing Telegram channel via Herald (no new bot, no extra config).",
            "- On your **next** turn, the CURRENT SYSTEM STATE will list pending and recent runs by `query_id` in the `Pending analysis runs` / `Recent analysis runs` sections. Reference runs by their query_id.",
            "Registered kinds (built-in):",
            "- `trade_group_review` — params `{\"group_id\": <int>}`. Reads SCRIBE + bridge.log, returns markdown review (signal text, AEGIS decision, fills, fill ratio, PnL).",
            "You may pass an optional client `query_id` for idempotency; while a run is PENDING, re-submitting the same query_id is rejected with `ANALYSIS_RUN duplicate query_id`.",
            "**STRONG PREFERENCE — trade group reviews:** When the operator asks to *review*, *break down*, *explain*, or *audit* a specific trade group (\"review G56\", \"why didn’t G47 fill\", \"break down group 12\", etc.), emit **exactly one** `ANALYSIS_RUN` JSON with `kind=trade_group_review` and `params.group_id=<int>`. Do **NOT** craft `SCRIBE_QUERY` SQL by hand for these requests — the handler already loads the right tables and bridge.log lines. Tell the operator: \"Queued review for G<id>; results will land in Telegram with query_id <the id we sent>\".",
            "**ALWAYS RE-EMIT ON REQUEST:** If a prior `ANALYSIS_RUN` for the same group is already DONE in your context, you MUST still emit a brand-new `ANALYSIS_RUN` JSON when the operator asks again. The operator needs the report delivered to Telegram on this turn — prior runs in context do NOT mean the operator already saw the report. Generate a fresh `query_id` (e.g. include a timestamp suffix like `REVIEW-G<id>-<HHMMSS>`) so it's distinguishable, and emit the JSON. Do NOT reply with \"already queued\" / \"see prior report\" / \"check Telegram\" — always queue a new run.",
            "---",
            "## PER-STAGE / PER-TICKET MODIFY (critical — don't collapse stages)",
            "FORGE places legs on different TP stages (e.g. 70% on TP1, 30% on TP2). A bare `MODIFY_TP` with only `tp` + `group_id` rewrites EVERY leg's TP to the same value, collapsing TP2/TP3 onto TP1. Use these scope fields whenever the operator's intent is stage-specific:",
            "- `tp_stage` (1/2/3): apply to legs whose FORGE comment ends with `|TP<n>` (matches the original placement bucket).",
            "- `ticket` (int): apply to exactly one position/pending. Wins over `tp_stage` when both are set.",
            "- Omit both → legacy whole-magic behaviour (use only when the operator literally says 'all legs').",
            "**Required precondition for multi-leg modifications:** before emitting a MODIFY command, run a SCRIBE_QUERY to inspect the legs and their stages, e.g. "
            '```json\n{"action":"SCRIBE_QUERY","sql":"SELECT id,ticket,direction,entry_price,sl,tp,tp_stage,lot_size FROM trade_positions WHERE trade_group_id=15 AND status=\'OPEN\' ORDER BY id","reply_to":"TELEGRAM"}\n```. '
            "On the next turn, decide which legs to touch. To move TP1 and TP2 separately, emit TWO `MODIFY_TP` blocks (one per stage) in the same reply — the multi-block dispatcher already serialises them.",
            "Example pair (move TP1 to 4648, leave TP2 at 4655):",
            '```json\n{"action":"MODIFY_TP","tp":4648.0,"group_id":15,"tp_stage":1,"reason":"tighten TP1 only"}\n```',
            "and a separate fence to leave TP2 untouched (or to move only TP2):",
            '```json\n{"action":"MODIFY_TP","tp":4655.0,"group_id":15,"tp_stage":2,"reason":"keep runner"}\n```',
            "If `trade_positions.tp_stage` is NULL for some rows (legacy fills logged before the stage backfill), the leg's FORGE comment still encodes the stage — BRIDGE will backfill on the next tick. In the meantime prefer `ticket` scope to avoid affecting unrelated stages.",
            "---",
            "## ENTRY ZONE / FILL-RATE AWARENESS",
            "- Wide signal zones (`entry_zone_pips > AEGIS_MAX_ENTRY_ZONE_PIPS`, default 8) carry inherent fill-rate risk. When a provider says \"enter slowly / layer / don't rush\", price must sweep the full zone for all legs to fill — and on directional moves it often won't.",
            "- When `trades_filled < num_trades` and the group closed at TP1, that is **NOT** a system failure; it is normal limit-ladder behaviour. Frame it that way to the operator and reference the **Configuration** section in `trade_group_review` output.",
            "- When AEGIS `scale_factor > 1.0` AND `entry_zone_pips > 5`, surface `scale_zone_risk=true` to the operator (more capital deployed across legs that may never fill while the filled leg carries elevated size).",
            "- Operators can adjust placement via `SIGNAL_ENTRY_TYPE` (`limit`|`market`), `SIGNAL_ENTRY_ZONE_CLUSTER` (bool, clusters legs near the directional zone edge), `SIGNAL_ENTRY_CLUSTER_PIPS` (band width, default 2.0). TP routing override per source: `SIGNAL_TP1_CLOSE_PCT`. Pending cancel-on-group-close: `PENDING_CANCEL_ON_GROUP_CLOSE` (default true) emits `CANCEL_GROUP_PENDING` to FORGE when the group's positions drain.",
            "---",
            "## SCRIBE schema cheatsheet (use these EXACT column names if you must SCRIBE_QUERY)",
            "Mistakes here cause `no such column` failures — verify against this list before hand-crafting SQL.",
            "`trade_groups`: id, timestamp, mode, session, **source** (NOT `reason`), signal_id, direction, entry_low, entry_high, sl, tp1, tp2, tp3, num_trades, **lot_per_trade**, status, **close_reason**, total_pnl, pips_captured, trades_opened, trades_closed, magic_number, regime_label, regime_confidence, regime_policy.",
            "`trade_positions`: id, **trade_group_id** (NOT `group_id`), timestamp, mode, session, ticket, magic_number, direction, **lot_size** (NOT `lot`), entry_price, sl, tp, status, close_price, close_time, close_reason, pnl, pips, **tp_stage** (1/2/3, populated at OPEN time from FORGE comment when available; may be NULL on legacy rows). There is **no** `open_time` column — the row's `timestamp` is the open time.",
            "`trade_closures`: id, timestamp, ticket, **trade_group_id**, direction, **lot_size**, entry_price, close_price, sl, tp, close_reason, pnl, pips, duration_seconds, session, mode.",
            "`signals_received`: id, timestamp, mode, session, raw_text, channel_name, message_id, signal_type, direction, entry_low, entry_high, sl, tp1, tp2, tp3, action_taken, skip_reason, trade_group_id, regime_label, regime_confidence. There is **no** `parsed_json` column.",
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

        # Scalper config (shared with FORGE native scalper)
        try:
            sc = _read_json(SCALPER_CFG)
            if sc:
                bounce = sc.get("bb_bounce", {})
                breakout = sc.get("bb_breakout", {})
                lines.append(f"\nSCALPER CONFIG (shared with FORGE native):")
                lines.append(
                    f"  BB Bounce (ADX<{bounce.get('adx_max',20)}): "
                    f"BUY if RSI<{bounce.get('rsi_buy_max',35)} + near BB lower, "
                    f"SELL if RSI>{bounce.get('rsi_sell_min',65)} + near BB upper. "
                    f"SL: {bounce.get('sl_atr_mult',1.2)}x ATR. TP1: BB mid.")
                lines.append(
                    f"  BB Breakout (ADX>{breakout.get('adx_min',25)}): "
                    f"BUY if RSI>{breakout.get('rsi_buy_min',55)} + close above BB upper + M5+M15 aligned. "
                    f"SL: {breakout.get('sl_atr_mult',1.5)}x ATR. "
                    f"TP: {breakout.get('tp1_atr_mult',1.0)}/{breakout.get('tp2_atr_mult',1.5)}/"
                    f"{breakout.get('tp3_atr_mult',2.5)}/{breakout.get('tp4_atr_mult',4.0)}x ATR.")
                lines.append(
                    f"  Use these SAME rules for AUTO_SCALPER decisions (consistency with FORGE backtest).")
        except Exception as e:
            log.debug("AURUM scalper config context error: %s", e)

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
        mcp_ctx = self._build_mcp_context_lines()
        if mcp_ctx:
            lines.append("\nAURUM CHART_COMMAND MCP CACHE (not LENS feed):")
            lines.extend(mcp_ctx)

        # ── Deferred Analysis Runs (pending + recent) ────────────────
        try:
            import analysis_runner
            pending = analysis_runner.list_pending() or []
            recent = analysis_runner.list_recent(limit=5) or []
        except Exception as e:
            log.debug("AURUM analysis_runner context error: %s", e)
            pending, recent = [], []

        if pending or recent:
            ar_lines: list[str] = []
            if pending:
                ar_lines.append("Pending analysis runs:")
                for row in pending[:10]:
                    ar_lines.append(
                        f"  - {row.get('query_id')}  kind={row.get('kind')}  age={row.get('age_sec')}s"
                    )
            if recent:
                ar_lines.append("Recent analysis runs (last 5):")
                for row in recent[:5]:
                    qid = row.get("query_id")
                    kind = row.get("kind")
                    status = row.get("status")
                    finished = (row.get("finished_at") or "")[:19]
                    summary = (row.get("summary") or "").strip().replace("\n", " ")[:120]
                    ar_lines.append(
                        f"  - {qid}  kind={kind}  status={status}  finished={finished}  summary={summary}"
                    )
            # Cap total appended lines at 20 to keep the prompt lean.
            ar_lines = ar_lines[:20]
            lines.append("\nDEFERRED ANALYSIS RUNS:")
            lines.extend(ar_lines)

        return "\n".join(lines)

    def _load_mcp_results(self):
        try:
            data = _read_json(self._mcp_results_file)
            rows = data.get("results", []) if isinstance(data, dict) else []
            if isinstance(rows, list):
                self._mcp_last_results = rows[-MCP_RESULT_MAX_ITEMS:]
            self._prune_mcp_results()
        except Exception as e:
            log.debug("AURUM mcp cache load failed: %s", e)
    def _prune_mcp_results(self):
        now = time.time()
        kept: list[dict] = []
        for row in self._mcp_last_results:
            if not isinstance(row, dict):
                continue
            tsu = self._to_float(row.get("timestamp_unix"))
            if tsu is None:
                continue
            age = now - tsu
            if age < 0:
                age = 0
            if age <= MCP_RESULT_RETENTION_SEC:
                kept.append(row)
        self._mcp_last_results = kept[-MCP_RESULT_MAX_ITEMS:]

    def _persist_mcp_results(self):
        try:
            self._prune_mcp_results()
            _write = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": self._mcp_last_results[-MCP_RESULT_MAX_ITEMS:],
            }
            with open(self._mcp_results_file, "w") as f:
                json.dump(_write, f, indent=2, default=str)
        except Exception as e:
            log.debug("AURUM mcp cache persist failed: %s", e)

    def _build_mcp_context_lines(self) -> list[str]:
        out: list[str] = []
        now = time.time()

        def _age_from_iso(ts_raw) -> float | None:
            if not ts_raw:
                return None
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
            except Exception:
                return None

        lens = _read_json(LENS_FILE)
        lens_age = None
        if isinstance(lens, dict):
            lens_age = self._to_float(lens.get("age_seconds"))
            if lens_age is None:
                lens_age = _age_from_iso(lens.get("timestamp"))
        lens_fresh = lens_age is not None and lens_age <= MCP_RESULT_STALE_SEC
        if not self._mcp_last_results:
            if lens_age is None:
                out.append("  No recent chart_command MCP results captured in this runtime.")
            else:
                state = "fresh" if lens_fresh else "stale"
                out.append(
                    f"  No recent chart_command MCP results captured in this runtime. "
                    f"LENS TradingView snapshot is {state} ({int(lens_age)}s old)."
                )
            return out
        stale_count = 0
        for row in self._mcp_last_results[-5:]:
            tsu = float(row.get("timestamp_unix", 0) or 0)
            age = max(0.0, now - tsu) if tsu else 9999.0
            freshness = "fresh" if age <= MCP_RESULT_STALE_SEC else "stale"
            if freshness == "stale":
                stale_count += 1
            tool = row.get("tool", "?")
            summary = row.get("summary", "")
            out.append(f"  - {tool}: {freshness} ({int(age)}s old) — {summary}")
            norm = row.get("normalized")
            if isinstance(norm, dict) and "cvd_available" in norm:
                out.append(
                    f"    CVD: available={norm.get('cvd_available')} "
                    f"last={norm.get('cvd_last')} divergence={norm.get('cvd_divergence_hint')}"
                )
                if norm.get("cvd_proxy_available"):
                    out.append(
                        f"    CVD proxy: method={norm.get('cvd_proxy_method')} "
                        f"last={norm.get('cvd_proxy_last')}"
                    )
        if stale_count > 0 and lens_fresh:
            out.append(
                "  Note: stale items above are from prior AURUM chart_command cache; "
                "live LENS TradingView snapshot is currently fresh."
            )
        return out

    @staticmethod
    def _to_float(v):
        try:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip()
            if not s:
                return None
            s = (
                s.replace("\u2212", "-")
                .replace("−", "-")
                .replace("\u202f", "")
                .replace("\xa0", "")
                .replace(",", "")
                .replace(" ", "")
            )
            mult = 1.0
            if s[-1:] in ("K", "k"):
                mult = 1_000.0
                s = s[:-1]
            elif s[-1:] in ("M", "m"):
                mult = 1_000_000.0
                s = s[:-1]
            elif s[-1:] in ("B", "b"):
                mult = 1_000_000_000.0
                s = s[:-1]
            return float(s) * mult
        except Exception:
            return None

    def _compute_cvd_proxy_from_studies(self, studies: list[dict]) -> dict:
        """
        Fallback proxy when native CVD study is unavailable.
        Priority:
          1) buy/sell volume or up/down volume keys => delta
          2) signed_volume = volume * sign(close-open)
        """
        out = {
            "cvd_proxy_available": False,
            "cvd_proxy_method": None,
            "cvd_proxy_last": None,
            "cvd_proxy_source_keys": [],
        }
        for s in studies:
            vals = s.get("values", {}) or {}
            if not isinstance(vals, dict) or not vals:
                continue
            buy = sell = up = down = vol = o = c = None
            for k, v in vals.items():
                kl = str(k).lower()
                fv = self._to_float(v)
                if fv is None:
                    continue
                if buy is None and ("buy" in kl and "vol" in kl):
                    buy = fv
                if sell is None and ("sell" in kl and "vol" in kl):
                    sell = fv
                if up is None and (("up" in kl and "vol" in kl) or kl in ("up", "buy", "buyers")):
                    up = fv
                if down is None and (("down" in kl and "vol" in kl) or kl in ("down", "sell", "sellers")):
                    down = fv
                if vol is None and "volume" in kl:
                    vol = fv
                if vol is None and kl in ("total", "tot"):
                    vol = fv
                if o is None and kl in ("open", "o"):
                    o = fv
                if c is None and kl in ("close", "c"):
                    c = fv
            if buy is not None and sell is not None:
                out["cvd_proxy_available"] = True
                out["cvd_proxy_method"] = "BUY_SELL_VOLUME_DELTA"
                out["cvd_proxy_last"] = round(buy - sell, 4)
                out["cvd_proxy_source_keys"] = ["buy_volume", "sell_volume"]
                return out
            if up is not None and down is not None:
                out["cvd_proxy_available"] = True
                out["cvd_proxy_method"] = "UP_DOWN_VOLUME_DELTA"
                out["cvd_proxy_last"] = round(up - down, 4)
                out["cvd_proxy_source_keys"] = ["up", "down"]
                return out
            if vol is not None and o is not None and c is not None:
                sign = 1.0 if c >= o else -1.0
                out["cvd_proxy_available"] = True
                out["cvd_proxy_method"] = "SIGNED_VOLUME_FROM_CLOSE_OPEN"
                out["cvd_proxy_last"] = round(vol * sign, 4)
                out["cvd_proxy_source_keys"] = ["volume", "open", "close"]
                return out
        return out

    def _normalize_study_values_result(self, result: dict) -> dict:
        studies = result.get("studies", []) if isinstance(result, dict) else []
        payload = {
            "cvd_available": False,
            "cvd_study_name": None,
            "cvd_last": None,
            "cvd_prev": None,
            "cvd_delta": None,
            "cvd_divergence_hint": "UNKNOWN",
            "cvd_proxy_available": False,
            "cvd_proxy_method": None,
            "cvd_proxy_last": None,
            "cvd_proxy_source_keys": [],
        }
        if not isinstance(studies, list):
            return payload
        target = None
        for s in studies:
            name = (s.get("name") or "").lower()
            if "cumulative volume delta" in name or re.search(r"\bcvd\b", name):
                target = s
                break
        if not target:
            payload.update(self._compute_cvd_proxy_from_studies(studies))
            return payload

        payload["cvd_available"] = True
        payload["cvd_study_name"] = target.get("name")
        vals = target.get("values", {}) or {}
        nums: list[float] = []
        preferred = None
        for k, v in vals.items():
            k_l = str(k).lower()
            f = self._to_float(v)
            if f is None:
                continue
            nums.append(f)
            if preferred is None and ("cvd" in k_l or "delta" in k_l or "value" in k_l):
                preferred = f
        if preferred is not None:
            payload["cvd_last"] = round(preferred, 4)
        elif nums:
            payload["cvd_last"] = round(nums[0], 4)

        hist = target.get("history")
        if isinstance(hist, list) and len(hist) >= 2:
            prev = self._to_float(hist[-2])
            last = self._to_float(hist[-1])
            if prev is not None:
                payload["cvd_prev"] = round(prev, 4)
            if last is not None:
                payload["cvd_last"] = round(last, 4)

        if payload["cvd_last"] is not None and payload["cvd_prev"] is not None:
            delta = float(payload["cvd_last"]) - float(payload["cvd_prev"])
            payload["cvd_delta"] = round(delta, 4)
            if delta > 0:
                payload["cvd_divergence_hint"] = "BUYING_PRESSURE_RISING"
            elif delta < 0:
                payload["cvd_divergence_hint"] = "SELLING_PRESSURE_RISING"
            else:
                payload["cvd_divergence_hint"] = "FLAT"
        return payload

    def _summarize_mcp_result(self, tool: str, result: dict, normalized: dict | None = None) -> str:
        if tool == "quote_get":
            last = result.get("last") if isinstance(result, dict) else None
            symbol = result.get("symbol") if isinstance(result, dict) else None
            return f"symbol={symbol or '?'} last={last if last is not None else 'n/a'}"
        if tool == "chart_get_state":
            symbol = result.get("symbol") if isinstance(result, dict) else None
            timeframe = result.get("timeframe") if isinstance(result, dict) else None
            studies = result.get("studies", []) if isinstance(result, dict) else []
            return f"symbol={symbol or '?'} tf={timeframe or '?'} studies={len(studies) if isinstance(studies, list) else 0}"
        if tool == "data_get_study_values":
            studies = result.get("studies", []) if isinstance(result, dict) else []
            if normalized and normalized.get("cvd_available"):
                return (
                    f"studies={len(studies) if isinstance(studies, list) else 0} "
                    f"cvd={normalized.get('cvd_last')} hint={normalized.get('cvd_divergence_hint')}"
                )
            if normalized and normalized.get("cvd_proxy_available"):
                return (
                    f"studies={len(studies) if isinstance(studies, list) else 0} "
                    f"cvd=proxy:{normalized.get('cvd_proxy_last')} "
                    f"method={normalized.get('cvd_proxy_method')}"
                )
            return f"studies={len(studies) if isinstance(studies, list) else 0} cvd=unavailable"
        return f"keys={','.join(sorted(result.keys())[:6])}" if isinstance(result, dict) else "result captured"

    def _capture_mcp_result(self, *, tool: str, args: dict, result: dict) -> dict:
        ts_iso = datetime.now(timezone.utc).isoformat()
        tsu = time.time()
        normalized = self._normalize_study_values_result(result) if tool == "data_get_study_values" else {}
        summary = self._summarize_mcp_result(tool, result, normalized)
        row = {
            "tool": tool,
            "args": args,
            "timestamp": ts_iso,
            "timestamp_unix": tsu,
            "result": result,
            "normalized": normalized,
            "summary": summary,
        }
        self._mcp_last_results.append(row)
        self._prune_mcp_results()
        self._persist_mcp_results()
        try:
            self.scribe.log_system_event(
                event_type="AURUM_MCP_RESULT_CAPTURED",
                triggered_by="AURUM",
                reason=tool,
                notes=json.dumps(
                    {
                        "tool": tool,
                        "args": args,
                        "summary": summary,
                        "normalized": normalized,
                    },
                    default=str,
                )[:2000],
            )
        except Exception:
            pass
        if MCP_ALERTS_ENABLED:
            try:
                self.herald.send_alert(
                    "MCP_RESULT_CAPTURED",
                    {
                        "tool": tool,
                        "freshness": "fresh",
                        "timestamp": ts_iso,
                        "summary": summary,
                    },
                )
            except Exception:
                pass
        return row

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

    def _vision_prompt_context(self, vr) -> str:
        sd = vr.structured_data if isinstance(vr.structured_data, dict) else {}
        return (
            "## IMAGE EXTRACTION (VISION)\n"
            f"confidence: {vr.confidence}\n"
            f"image_type: {vr.image_type}\n"
            f"action_hint: {vr.caller_action}\n"
            f"summary: {vr.extracted_text}\n"
            f"structured_data: {json.dumps(sd, default=str)}"
        )

    @staticmethod
    def _response_claims_no_image(text: str) -> bool:
        t = (text or "").lower()
        patterns = (
            "no image attached",
            "no image coming through",
            "i don't see an image",
            "still no image",
            "image not attached",
            "no image in your message",
        )
        return any(p in t for p in patterns)

    def _log_vision(self, *, caller: str, source_channel: str, context_hint: str, vr) -> int:
        sd = vr.structured_data if isinstance(vr.structured_data, dict) else {}
        return self.scribe.log_vision_extraction({
            "caller": caller,
            "source_channel": source_channel,
            "context_hint": context_hint,
            "image_type": vr.image_type,
            "confidence": vr.confidence,
            "extracted_text": vr.extracted_text,
            "structured_data": sd,
            "direction": sd.get("direction"),
            "entry_price": sd.get("entry_low") or sd.get("entry_high"),
            "sl_price": sd.get("sl"),
            "tp1_price": sd.get("tp1"),
            "tp2_price": sd.get("tp2"),
            "caller_action": vr.caller_action,
            "downstream_result": "USED_FOR_CHAT",
            "image_hash": vr.image_hash,
            "file_size_kb": vr.file_size_kb,
            "processing_ms": vr.processing_ms,
            "error": vr.error,
        })

    def _reply_with_optional_image(self, *, query: str, caption: str,
                                   image_path: str | None,
                                   source: str = "TELEGRAM",
                                   context_hint: str = "GENERAL",
                                   source_channel: str = "direct") -> str:
        if image_path and VISION_ENABLED:
            vr = self.vision.extract(
                image_path=image_path,
                caption=caption,
                context_hint=context_hint,
                caller="HERALD",
            )
            try:
                self.scribe.log_system_event(
                    event_type="AURUM_UPLOAD_VISION_PARSED",
                    triggered_by="AURUM",
                    reason="TELEGRAM_DIRECT_MEDIA",
                    notes=f"confidence={vr.confidence} image_type={vr.image_type} source={source_channel}",
                )
            except Exception:
                pass
            vid = self._log_vision(
                caller="HERALD",
                source_channel=source_channel,
                context_hint=context_hint,
                vr=vr,
            )
            if vr.confidence == "LOW":
                self.scribe.update_vision_extraction_result(vid, "LOW_CONFIDENCE")
                return (
                    "I received the image but confidence is LOW, so I may misread key levels. "
                    "Please resend as a clearer file or include entry/SL/TP in text."
                )
            guard_ctx = (
                "## IMAGE DELIVERY CONFIRMATION\n"
                "The image WAS successfully received and parsed by VISION for this same user message.\n"
                "Do NOT claim that no image was attached. Use the extraction below as primary evidence.\n"
            )
            answer = self.ask(
                query,
                source=source,
                extra_context=guard_ctx + "\n" + self._vision_prompt_context(vr),
            )
            if self._response_claims_no_image(answer):
                return (
                    f"Image received and parsed ({vr.confidence}).\n"
                    f"Extraction: {vr.extracted_text}\n"
                    "Reply with your intended action (analyze / trade setup / levels), and I’ll proceed from this extraction."
                )
            return answer
        return self.ask(query, source=source)
    @staticmethod
    def _parse_chart_result_success_map(chart_result: str) -> dict[str, bool]:
        out: dict[str, bool] = {}
        if not chart_result:
            return out
        for line in chart_result.splitlines():
            if ":" not in line:
                continue
            tool, payload = line.split(":", 1)
            tool = tool.strip()
            payload = payload.strip()
            if not tool or not payload.startswith("{"):
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if isinstance(obj, dict) and "success" in obj:
                out[tool] = bool(obj.get("success"))
        return out

    def _reconcile_loopback_answer(self, answer: str, chart_result: str) -> str:
        """
        If LOOPBACK_CHECK claims FAIL while MCP execution payloads clearly succeeded,
        reconcile statuses so operator output matches hard tool evidence.
        """
        if not answer or "LOOPBACK_CHECK" not in answer:
            return answer
        success_map = self._parse_chart_result_success_map(chart_result)
        expected = ("quote_get", "chart_get_state", "data_get_study_values")
        if not all(success_map.get(t) is True for t in expected):
            return answer

        fixed = answer
        for tool in expected:
            fixed = re.sub(
                rf"({re.escape(tool)}\s*:\s*)(FAIL|MISSING|UNKNOWN)",
                r"\1SUCCESS",
                fixed,
                flags=re.IGNORECASE,
            )
        fixed = re.sub(
            r"(mcp_context_updated:\s*)(NO|FALSE)",
            r"\1YES",
            fixed,
            flags=re.IGNORECASE,
        )
        fixed = re.sub(
            r"(FINAL_STATUS:\s*)FAIL",
            r"\1PASS",
            fixed,
            flags=re.IGNORECASE,
        )
        fixed += (
            "\n\nAuthoritative reconciliation: MCP tool payloads show SUCCESS for "
            "quote_get, chart_get_state, and data_get_study_values in this same response."
        )
        return fixed

    def _execute_chart_commands(self, text: str) -> str | None:
        """Parse ```chart_command ... ``` fences, execute via MCP, return results."""
        if not text or "```" not in text:
            return None

        chunks = text.split("```")
        commands: list[dict] = []
        for i in range(1, len(chunks), 2):
            block = chunks[i].strip()
            if not block.lower().startswith("chart_command"):
                continue
            block = block[len("chart_command"):].lstrip("\n\r").strip()
            if not block.startswith("{"):
                continue
            try:
                commands.append(json.loads(block))
            except json.JSONDecodeError:
                continue

        if not commands:
            return None

        results = []
        try:
            with MCPSession(timeout=20) as mcp:
                for cmd in commands:
                    tool = cmd.get("tool", "")
                    args = cmd.get("args", {})
                    if not tool:
                        continue
                    log.info("AURUM: MCP call %s(%s)", tool, json.dumps(args, default=str)[:100])
                    result = mcp.call(tool, args)
                    self._capture_mcp_result(
                        tool=tool,
                        args=args if isinstance(args, dict) else {},
                        result=result if isinstance(result, dict) else {},
                    )
                    # Truncate large results (e.g. 73 FVG zones)
                    result_str = json.dumps(result, default=str)
                    if len(result_str) > 2000:
                        result_str = result_str[:2000] + "...(truncated)"
                    results.append(f"{tool}: {result_str}")
        except ConnectionError:
            if MCP_ALERTS_ENABLED:
                try:
                    self.herald.send_alert(
                        "MCP_RESULT_MISSING",
                        {"tool": "session", "reason": "TradingView not connected"},
                    )
                except Exception:
                    pass
            return "TradingView not connected — run: make start-tradingview"
        except Exception as e:
            log.error("AURUM MCP error: %s", e)
            if MCP_ALERTS_ENABLED:
                try:
                    self.herald.send_alert(
                        "MCP_CALL_FAILED",
                        {"tool": "unknown", "error": str(e)[:180]},
                    )
                except Exception:
                    pass
            return f"MCP error: {str(e)[:100]}"

        return "\n".join(results) if results else None

    def _extract_json_commands_from_response(self, text: str, source: str = "") -> None:
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
            "SENTINEL_OVERRIDE", "SCRIBE_QUERY", "SHELL_EXEC", "AURUM_EXEC",
            "ANALYSIS_RUN",
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
                if source and not obj.get("origin_source"):
                    obj["origin_source"] = str(source).upper().strip()
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

    @staticmethod
    def _is_telegram_health_check_request(text: str) -> bool:
        t = re.sub(r"\s+", " ", (text or "").strip().lower())
        if not t:
            return False
        # Ignore raw JSON payload pastes; those are handled by normal JSON extraction.
        if "\"action\"" in t and "{" in t:
            return False
        if "health status" in t:
            return True
        if "health check" in t:
            return True
        if "system health" in t and any(k in t for k in ("check", "status", "run", "report", "show")):
            return True
        return False

    @staticmethod
    def _telegram_health_check_command(source: str = "TELEGRAM") -> dict:
        return {
            "action": "AURUM_EXEC",
            "payload": {"action": "HEALTH_CHECK"},
            "reply_to": "TELEGRAM",
            "origin_source": str(source or "TELEGRAM").upper().strip(),
        }

    def _handle_telegram_natural_language_command(self, text: str, source: str = "TELEGRAM") -> str | None:
        if not self._is_telegram_health_check_request(text):
            return None
        cmd = self._telegram_health_check_command(source=source)
        self.write_command(cmd)
        log.info("AURUM: mapped Telegram NL health request to %s", json.dumps(cmd, default=str))
        try:
            self.scribe.log_system_event(
                event_type="AURUM_NL_HEALTH_CHECK_QUEUED",
                triggered_by="AURUM",
                reason="TELEGRAM_NL_INTENT",
                notes=f"source={source}",
            )
        except Exception:
            pass
        return (
            "Running system health check now. "
            "Queued via AURUM_EXEC HEALTH_CHECK; results will be posted shortly."
        )

    def write_command(self, cmd: dict):
        """Write a command for BRIDGE to execute."""
        cmd["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(CMD_FILE, "w") as f:
                json.dump(cmd, f, indent=2)
        except Exception as e:
            log.error(f"AURUM write command error: {e}")

    # ── Telegram bot handler ───────────────────────────────
    async def start_telegram(self):
        """Start Telegram bot listener.

        Uses Bot API (python-telegram-bot) so users message the bot directly.
        Only responds to messages from TELEGRAM_CHAT_ID (your user ID).
        Falls back to Telethon user client if Bot API fails.
        """
        # Try Bot API first (preferred — users message the bot directly)
        if BOT_TOKEN and AURUM_CHAT_ID:
            try:
                await self._start_bot_api()
                return  # Bot API running — don't start Telethon
            except Exception as e:
                log.warning("AURUM: Bot API failed (%s), falling back to Telethon", e)

        # Fallback: Telethon user client (message yourself in Saved Messages)
        if not all([API_ID, API_HASH]):
            log.warning("AURUM: Telegram not configured (no bot token or API credentials)")
            return
        await self._start_telethon()

    async def _start_bot_api(self):
        """Listen for messages via Bot API — user messages the bot directly.

        Messages are queued and processed sequentially (FIFO) so responses
        always arrive in the same order they were sent. A typing indicator
        is shown while AURUM thinks.
        """
        from telegram import Update, Bot
        from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
        import asyncio as _aio

        allowed_chat = int(AURUM_CHAT_ID)
        msg_queue: _aio.Queue = _aio.Queue()

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            if update.message.chat_id != allowed_chat:
                log.warning("AURUM bot: rejected message from chat %s (allowed: %s)",
                            update.message.chat_id, allowed_chat)
                return
            text = (update.message.text or update.message.caption or "").strip()
            has_media = self._message_has_media(update.message)
            if not text and not has_media:
                return
            if text.startswith("/system"):
                return
            if has_media:
                try:
                    self.scribe.log_system_event(
                        event_type="AURUM_UPLOAD_RECEIVED",
                        triggered_by="AURUM",
                        reason="TELEGRAM_DIRECT_MEDIA",
                        notes=(
                            f"chat={update.message.chat_id} msg={update.message.message_id} "
                            f"photo={bool(update.message.photo)} document={bool(update.message.document)} "
                            f"caption_len={len(text)}"
                        ),
                    )
                except Exception:
                    pass
            image_path = None
            if has_media and VISION_ENABLED:
                try:
                    image_path = await self.herald.download_inbound_media(update.message, prefix="aurum_img_")
                    if not image_path:
                        self.scribe.log_system_event(
                            event_type="AURUM_UPLOAD_DOWNLOAD_FAILED",
                            triggered_by="AURUM",
                            reason="TELEGRAM_DIRECT_MEDIA",
                            notes=f"chat={update.message.chat_id} msg={update.message.message_id}",
                        )
                except Exception as e:
                    try:
                        self.scribe.log_system_event(
                            event_type="AURUM_UPLOAD_DOWNLOAD_FAILED",
                            triggered_by="AURUM",
                            reason="TELEGRAM_DIRECT_MEDIA",
                            notes=f"chat={update.message.chat_id} msg={update.message.message_id} err={str(e)[:180]}",
                        )
                    except Exception:
                        pass
                    log.warning("AURUM bot: failed to download image: %s", e)
            # Queue the message for sequential processing
            await msg_queue.put((update, text, image_path))

        async def process_queue():
            """Process messages one at a time in FIFO order."""
            while True:
                update, text, image_path = await msg_queue.get()
                try:
                    query = text or "Analyze this image in context of the current trading session."
                    if text and not image_path:
                        nl_reply = self._handle_telegram_natural_language_command(text, source="TELEGRAM")
                        if nl_reply:
                            await update.message.reply_text(nl_reply)
                            continue
                    log.info(f"AURUM query from Telegram (bot): {query[:60]}")
                    # Show typing indicator while thinking
                    await update.message.chat.send_action("typing")
                    reply = self._reply_with_optional_image(
                        query=query,
                        caption=text,
                        image_path=image_path,
                        source="TELEGRAM",
                        context_hint="GENERAL",
                        source_channel="direct",
                    )
                    # Telegram has 4096 char limit per message
                    if len(reply) <= 4096:
                        await update.message.reply_text(reply)
                    else:
                        # Split long replies
                        for i in range(0, len(reply), 4096):
                            await update.message.reply_text(reply[i:i+4096])
                except Exception as e:
                    log.error("AURUM bot message handler error: %s", e)
                    try:
                        await update.message.reply_text(f"AURUM error: {str(e)[:200]}")
                    except Exception:
                        pass
                finally:
                    if image_path:
                        try:
                            os.remove(image_path)
                        except Exception:
                            pass
                    msg_queue.task_done()

        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(
            MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_message)
        )
        log.info("AURUM: Bot API listening (message the bot directly in Telegram, queued FIFO)")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # Start the sequential queue processor
        import asyncio
        queue_task = asyncio.create_task(process_queue())
        try:
            await asyncio.Event().wait()
        finally:
            queue_task.cancel()
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    async def _start_telethon(self):
        """Fallback: Telethon user client (listen on Saved Messages)."""
        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start(phone=PHONE)

        me = await client.get_me()
        my_id = me.id
        target_chat = int(AURUM_CHAT_ID) if AURUM_CHAT_ID else None
        log.info(f"AURUM: Telethon fallback — logged in as user {my_id}, listening on chat {target_chat}")

        @client.on(events.NewMessage(chats=target_chat))
        async def on_message(event):
            if event.message.sender_id != my_id:
                return
            text = (event.message.message or "").strip()
            has_media = self._message_has_media(event.message)
            if not text and not has_media:
                return
            if text.startswith("/system"):
                return
            if has_media:
                try:
                    self.scribe.log_system_event(
                        event_type="AURUM_UPLOAD_RECEIVED",
                        triggered_by="AURUM",
                        reason="TELETHON_DIRECT_MEDIA",
                        notes=(
                            f"chat={target_chat} msg={event.message.id} "
                            f"photo={bool(getattr(event.message, 'photo', None))} "
                            f"document={bool(getattr(event.message, 'document', None))} "
                            f"caption_len={len(text)}"
                        ),
                    )
                except Exception:
                    pass
            query = text or "Analyze this image in context of the current trading session."
            if text and not has_media:
                nl_reply = self._handle_telegram_natural_language_command(text, source="TELEGRAM")
                if nl_reply:
                    await event.respond(nl_reply)
                    return
            reply = None
            image_path = None
            if has_media and VISION_ENABLED:
                try:
                    with tempfile.NamedTemporaryFile(prefix="aurum_tel_", suffix=".img", delete=False) as tmp:
                        image_path = tmp.name
                    out = await event.message.download_media(file=image_path)
                    image_path = out or image_path
                    if not image_path:
                        self.scribe.log_system_event(
                            event_type="AURUM_UPLOAD_DOWNLOAD_FAILED",
                            triggered_by="AURUM",
                            reason="TELETHON_DIRECT_MEDIA",
                            notes=f"chat={target_chat} msg={event.message.id}",
                        )
                    vr = self.vision.extract(
                        image_path=image_path,
                        caption=text,
                        context_hint="GENERAL",
                        caller="HERALD",
                    )
                    vid = self._log_vision(
                        caller="HERALD",
                        source_channel="direct",
                        context_hint="GENERAL",
                        vr=vr,
                    )
                    if vr.confidence == "LOW":
                        self.scribe.update_vision_extraction_result(vid, "LOW_CONFIDENCE")
                        reply = (
                            "I received the image but confidence is LOW, so I may misread key levels. "
                            "Please resend as a clearer file or include entry/SL/TP in text."
                        )
                    else:
                        reply = self.ask(
                            query,
                            source="TELEGRAM",
                            extra_context=self._vision_prompt_context(vr),
                        )
                except Exception as e:
                    try:
                        self.scribe.log_system_event(
                            event_type="AURUM_UPLOAD_DOWNLOAD_FAILED",
                            triggered_by="AURUM",
                            reason="TELETHON_DIRECT_MEDIA",
                            notes=f"chat={target_chat} msg={event.message.id} err={str(e)[:180]}",
                        )
                    except Exception:
                        pass
                    log.warning("AURUM telethon: failed to process media upload: %s", e)
                finally:
                    if image_path:
                        try:
                            os.remove(image_path)
                        except Exception:
                            pass
            if reply is None:
                reply = self.ask(query, source="TELEGRAM")
            log.info(f"AURUM query from Telegram (telethon): {query[:60]}")
            await event.respond(reply)

        log.info("AURUM Telegram (Telethon) listening")
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
