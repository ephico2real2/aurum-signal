from __future__ import annotations
import json

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
import aurum as aurum_mod

from aurum import Aurum, MCP_RESULT_STALE_SEC, MCP_RESULT_RETENTION_SEC
from herald import Herald


@pytest.mark.unit
class TestHeraldAlertTemplates:
    def test_mcp_failure_template_contains_core_fields(self):
        h = Herald(token="", chat_id="")
        msg = h._render_alert_template(
            "MCP_CALL_FAILED",
            {"tool": "data_get_study_values", "error": "timeout"},
        )
        assert "MCP CALL FAILED" in msg
        assert "data_get_study_values" in msg
        assert "timeout" in msg

    def test_webhook_failure_template_contains_retry_signal(self):
        h = Herald(token="", chat_id="")
        msg = h._render_alert_template(
            "WEBHOOK_ALERT_FAILED",
            {"alert_kind": "TP1_HIT", "failure": "endpoint timeout", "retryable": True},
        )
        assert "WEBHOOK ALERT FAILED" in msg
        assert "TP1_HIT" in msg
        assert "Retryable" in msg


@pytest.mark.unit
class TestAurumMcpNormalization:
    def test_normalize_study_values_detects_cvd_and_delta(self):
        a = Aurum.__new__(Aurum)
        out = a._normalize_study_values_result(
            {
                "studies": [
                    {"name": "RSI", "values": {"RSI": "52.1"}},
                    {
                        "name": "Cumulative Volume Delta",
                        "values": {"CVD": "124.5"},
                        "history": ["100.0", "124.5"],
                    },
                ]
            }
        )
        assert out["cvd_available"] is True
        assert out["cvd_last"] == 124.5
        assert out["cvd_prev"] == 100.0
        assert out["cvd_divergence_hint"] == "BUYING_PRESSURE_RISING"

    def test_normalize_study_values_computes_cvd_proxy_when_native_missing(self):
        a = Aurum.__new__(Aurum)
        out = a._normalize_study_values_result(
            {
                "studies": [
                    {
                        "name": "Order Flow Proxy",
                        "values": {"Buy Volume": "1500", "Sell Volume": "900"},
                    }
                ]
            }
        )
        assert out["cvd_available"] is False
        assert out["cvd_proxy_available"] is True
        assert out["cvd_proxy_method"] == "BUY_SELL_VOLUME_DELTA"
        assert out["cvd_proxy_last"] == 600.0

    def test_normalize_study_values_computes_proxy_from_up_down_k_suffix(self):
        a = Aurum.__new__(Aurum)
        out = a._normalize_study_values_result(
            {
                "studies": [
                    {
                        "name": "Session Volume Profile HD",
                        "values": {"Up": "1.92 K", "Down": "1.77 K", "Total": "3.68 K"},
                    }
                ]
            }
        )
        assert out["cvd_available"] is False
        assert out["cvd_proxy_available"] is True
        assert out["cvd_proxy_method"] == "UP_DOWN_VOLUME_DELTA"
        assert out["cvd_proxy_last"] == 150.0
        assert out["cvd_proxy_source_keys"] == ["up", "down"]

    def test_to_float_parses_metric_suffixes(self):
        a = Aurum.__new__(Aurum)
        assert a._to_float("1.5K") == 1500.0
        assert a._to_float("2.0 M") == 2000000.0
        assert a._to_float("0.75B") == 750000000.0

    def test_reconcile_loopback_answer_promotes_success_when_chart_payloads_succeed(self):
        a = Aurum.__new__(Aurum)
        answer = (
            "LOOPBACK_CHECK\n"
            "- TOOL_STATUS:\n"
            "  - quote_get: FAIL\n"
            "  - chart_get_state: FAIL\n"
            "  - data_get_study_values: FAIL\n"
            "- FEEDBACK_LOOP:\n"
            "  - mcp_context_updated: NO\n"
            "- FINAL_STATUS: FAIL\n"
        )
        chart_result = (
            'quote_get: {"success": true, "symbol": "OANDA:XAUUSD"}\n'
            'chart_get_state: {"success": true, "symbol": "OANDA:XAUUSD"}\n'
            'data_get_study_values: {"success": true, "study_count": 8}'
        )
        out = a._reconcile_loopback_answer(answer, chart_result)
        assert "quote_get: SUCCESS" in out
        assert "chart_get_state: SUCCESS" in out
        assert "data_get_study_values: SUCCESS" in out
        assert "mcp_context_updated: YES" in out
        assert "FINAL_STATUS: PASS" in out

    def test_mcp_context_lines_include_freshness_and_cvd_flags(self):
        a = Aurum.__new__(Aurum)
        a._mcp_last_results = [
            {
                "tool": "data_get_study_values",
                "timestamp_unix": time.time() - (MCP_RESULT_STALE_SEC + 10),
                "summary": "studies=8 cvd=unavailable",
                "normalized": {
                    "cvd_available": False,
                    "cvd_last": None,
                    "cvd_divergence_hint": "UNKNOWN",
                },
            }
        ]
        lines = a._build_mcp_context_lines()
        joined = "\n".join(lines)
        assert "stale" in joined
        assert "CVD: available=False" in joined

    def test_mcp_cache_persists_and_loads(self, tmp_path):
        a = Aurum.__new__(Aurum)
        a._mcp_results_file = str(tmp_path / "aurum_mcp_results.json")
        a._mcp_last_results = [{"tool": "quote_get", "timestamp_unix": time.time(), "summary": "ok"}]
        a._persist_mcp_results()
        raw = json.loads(Path(a._mcp_results_file).read_text())
        assert "results" in raw

        b = Aurum.__new__(Aurum)
        b._mcp_results_file = a._mcp_results_file
        b._mcp_last_results = []
        b._load_mcp_results()
        assert b._mcp_last_results
        assert b._mcp_last_results[0]["tool"] == "quote_get"

    def test_mcp_cache_prunes_entries_older_than_retention(self, tmp_path):
        a = Aurum.__new__(Aurum)
        a._mcp_results_file = str(tmp_path / "aurum_mcp_results.json")
        a._mcp_last_results = [
            {
                "tool": "stale",
                "timestamp_unix": time.time() - (MCP_RESULT_RETENTION_SEC + 100),
                "summary": "old",
            },
            {
                "tool": "fresh",
                "timestamp_unix": time.time(),
                "summary": "new",
            },
        ]
        a._persist_mcp_results()

        b = Aurum.__new__(Aurum)
        b._mcp_results_file = a._mcp_results_file
        b._mcp_last_results = []
        b._load_mcp_results()
        assert len(b._mcp_last_results) == 1
        assert b._mcp_last_results[0]["tool"] == "fresh"


@pytest.mark.unit
class TestAurumFinalResponseLogging:
    def test_ask_logs_final_post_mcp_response(self, monkeypatch):
        class _Scribe:
            def __init__(self):
                self.logged = []

            def log_aurum_conversation(self, **kwargs):
                self.logged.append(kwargs)

        class _RespObj:
            class _Usage:
                input_tokens = 10
                output_tokens = 5

            usage = _Usage()
            content = [type("_Block", (), {"text": "LOOPBACK_CHECK\n- FINAL_STATUS: FAIL"})()]

        class _Claude:
            class _Messages:
                @staticmethod
                def create(**_kwargs):
                    return _RespObj()

            messages = _Messages()

        scribe = _Scribe()
        appended = []

        a = Aurum.__new__(Aurum)
        a.claude = _Claude()
        a.scribe = scribe
        a._mode = "SIGNAL"
        a._build_context = lambda: "ctx"
        a._maybe_web_search = lambda _q: None
        a._build_memory = lambda: ""
        a._build_system_prompt = lambda _ctx, _mem="": "sys"
        a._get_conversation_messages = lambda _q, _s: [{"role": "user", "content": "q"}]
        a._append_to_conversation = lambda _src, _role, content: appended.append(content)
        a._check_for_command = lambda _a: None
        a._extract_json_commands_from_response = lambda _a: None
        a._execute_chart_commands = lambda _a: 'quote_get: {"success": true}'
        a._reconcile_loopback_answer = lambda ans, _cr: ans.replace("FAIL", "PASS")
        monkeypatch.setattr(aurum_mod, "report_component_status", lambda *args, **kwargs: None)

        out = a.ask("q", source="TELEGRAM")
        assert "FINAL_STATUS: PASS" in out
        assert "📊 Chart result:" in out
        assert appended and appended[-1] == out
        assert scribe.logged and scribe.logged[-1]["response"] == out
