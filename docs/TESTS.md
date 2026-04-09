# Signal System — Test Documentation

> 100+ tests across API integration, unit, contract, and Playwright UI suites.

---

## Running Tests

```bash
make test              # All tests (API + UI)
make test-api          # All API tests (pytest, excludes slow)
make test-ui           # Playwright UI tests (headed browser)
make test-ui-silent    # Playwright UI tests (headless)
make test-contracts    # Unit tests: contracts, schemas, scoping
make test-closures     # SL/TP closure endpoint tests
make test-mgmt-scoping # Channel management scoping tests
make test-live         # /api/live endpoint tests
make test-components   # /api/components tests
```

---

## API Tests — `/api/live` (`test_live.py`)

| Test | What it verifies |
|------|-----------------|
| `test_live_returns_200` | Endpoint responds |
| `test_live_has_required_keys` | All 20+ required fields present (mode, session, account, execution, tradingview, closures, etc.) |
| `test_live_has_components` | Component heartbeats dict present |
| `test_live_has_aegis_state` | AEGIS scale_factor, streak, pnl_day_reset_hour_utc |
| `test_live_has_broker_info` | account_type is DEMO/LIVE/UNKNOWN |
| `test_live_has_circuit_breaker` | circuit_breaker boolean present |
| `test_live_has_reconciler` | Reconciler block present (can be null) |
| `test_live_mode_valid` | Mode is one of OFF/WATCH/SIGNAL/SCALPER/HYBRID/AUTO_SCALPER/UNKNOWN/DISCONNECTED |
| `test_live_mt5_connected_bool` | mt5_connected is boolean |
| `test_live_execution_shape` | Execution block has stale, usable, bid, ask, age_sec |
| `test_live_tradingview_shape` | TradingView block is dict |
| `test_live_account_has_fields` | Account is a dict |
| `test_live_open_groups_list` | open_groups, open_groups_queued, pending_orders are lists |
| `test_live_performance_has_fields` | Performance is a dict |

---

## API Tests — `/api/closures` + `/api/closure_stats` (`test_closures.py`)

| Test | What it verifies |
|------|-----------------|
| `test_closures_returns_200` | Endpoint responds |
| `test_closures_is_list` | Returns a list |
| `test_closures_with_days_param` | days + limit query params work |
| `test_closures_row_shape` | Each row has id, timestamp, ticket, trade_group_id, direction, close_reason, pnl, pips |
| `test_closures_close_reason_valid` | close_reason is one of SL_HIT/TP1_HIT/TP2_HIT/TP3_HIT/MANUAL_CLOSE/CLOSE_ALL/PARTIAL_CLOSE/RECONCILER/UNKNOWN |
| `test_closure_stats_returns_200` | Stats endpoint responds |
| `test_closure_stats_structure` | Has total, sl_hits, tp1_hits, tp2_hits, tp3_hits, manual, sl_rate, tp_rate, total_pnl, avg_pnl, avg_pips, avg_duration_sec |
| `test_closure_stats_rates_are_numbers` | sl_rate and tp_rate are 0-100 |
| `test_closure_stats_with_days_param` | days query param works |
| `test_closure_stats_total_consistent` | Sum of parts does not exceed total |
| `test_live_has_recent_closures` | /api/live includes recent_closures list |
| `test_live_has_closure_stats` | /api/live includes closure_stats with sl_hits, tp_rate |

---

## API Tests — Misc Endpoints (`test_endpoints.py`)

| Test | What it verifies |
|------|-----------------|
| `test_health_returns_200` | /api/health responds |
| `test_health_structure` | status=ok, timestamp present |
| `test_sessions_returns_200` | /api/sessions responds |
| `test_sessions_is_list` | Returns a list |
| `test_events_returns_200` | /api/events responds |
| `test_events_is_list` | Returns a list |
| `test_events_newest_first_when_multiple` | Events sorted DESC by timestamp |
| `test_performance_returns_200` | /api/performance responds |
| `test_performance_has_fields` | Returns a dict |
| `test_mode_invalid_returns_400` | POST /api/mode with bad mode returns 400 |
| `test_mode_valid_returns_200` | POST /api/mode with WATCH returns 200 + ok=true |

---

## API Tests — `/api/components` (`test_components.py`)

| Test | What it verifies |
|------|-----------------|
| `test_components_returns_200` | Endpoint responds |
| `test_components_structure` | Has components, total, healthy, timestamp |
| `test_components_has_all_expected` | All 11 components present (BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS, SCRIBE, HERALD, AURUM, RECONCILER, ATHENA) |
| `test_each_component_has_required_fields` | Each has name, status, ok, timestamp, note |
| `test_component_status_valid_values` | Status is OK/WARN/ERROR/UNKNOWN/STARTING |
| `test_component_ok_matches_status` | ok=true when status=OK |
| `test_healthy_count_matches` | Reported healthy count matches actual |
| `test_reconciler_endpoint_200` | /api/reconciler responds |
| `test_reconciler_structure` | Has status and issue_count or issues |
| `test_heartbeat_post_rejects_unknown_component` | POST with bad component returns 400 |
| `test_heartbeat_post_accepts_scribe` | POST with SCRIBE returns 200 + ok=true |

---

## API Tests — AURUM Chat (`test_aurum.py`)

| Test | What it verifies |
|------|-----------------|
| `test_aurum_empty_query_400` | Empty query returns 400 |
| `test_aurum_missing_query_400` | Missing query field returns 400 |
| `test_aurum_responds` | Real Claude API call returns response (slow, requires API key) |

---

## Unit Tests — Channel Management Scoping (`test_mgmt_channel_scoping.py`)

| Test | What it verifies |
|------|-----------------|
| `test_channel_close_all_only_closes_signal_groups` | LISTENER CLOSE_ALL skips AURUM + FORGE groups |
| `test_channel_close_all_does_not_send_global_close_all` | Never sends FORGE CLOSE_ALL from channel |
| `test_athena_close_all_still_closes_everything` | Dashboard CLOSE_ALL still works globally |
| `test_channel_move_be_does_not_send_global_move_be_all` | Channel MOVE_BE doesn't affect AURUM trades |
| `test_athena_move_be_still_moves_all` | Dashboard MOVE_BE still global |
| `test_channel_close_all_with_group_id_scopes_to_group` | Explicit group_id targets only that group |
| `test_resolve_channel_group_by_signal_id` | Finds correct group from signal_id |
| `test_resolve_channel_group_fallback_to_latest_signal` | Falls back to newest SIGNAL group |
| `test_resolve_channel_group_returns_none_if_no_signal_groups` | No SIGNAL groups returns None (safe) |
| `test_listener_source_detected_as_channel` | Various LISTENER source values detected correctly |

---

## Unit Tests — AURUM/BRIDGE/FORGE Contracts (`test_aurum_forge_contract.py`)

| Test | What it verifies |
|------|-----------------|
| `test_mode_change_valid` | Valid MODE_CHANGE validates clean |
| `test_mode_change_invalid_mode` | Invalid mode caught |
| `test_close_all_valid` | CLOSE_ALL validates clean |
| `test_open_group_valid` | OPEN_GROUP with all fields validates |
| `test_open_group_bad_direction` | Bad direction caught |
| `test_valid_modes_matches_bridge` | contracts.VALID_MODES matches bridge.VALID_MODES |
| `test_open_group_canonical_passes` | FORGE OPEN_GROUP command validates |
| `test_close_all_passes` | FORGE CLOSE_ALL validates |
| `test_open_group_missing_keys_fails` | Missing keys caught |
| `test_json_roundtrip_stable` | JSON serialize/deserialize stays valid |
| `test_market_entry_uses_mid` | OPEN_TRADE with entry=market uses MT5 mid |
| `test_numeric_entry` | OPEN_TRADE with numeric entry maps correctly |
| `test_tp_alias_and_lots` | tp alias to tp1, lots alias to lot_per_trade |
| `test_normalize_delegates_to_contracts` | Bridge uses contracts module |
| `test_schema_bundle_version_matches_manifest` | Python SCHEMA_BUNDLE_VERSION matches manifest.json |
| `test_verify_script_exists_and_mentions_off` | verify_scribe_mode_writes.py exists and covers OFF mode |

---

## Unit Tests — BRIDGE aurum_cmd.json (`test_bridge_aurum_cmd.py`)

| Test | What it verifies |
|------|-----------------|
| `test_aurum_cmd_file_deleted_after_mode_change` | BRIDGE removes aurum_cmd.json after handling MODE_CHANGE |
| `test_aurum_cmd_duplicate_timestamp_skips_and_does_not_delete` | Same timestamp = early return, file kept |
| `test_aurum_cmd_missing_file_no_crash` | Missing file doesn't crash BRIDGE |

---

## Unit Tests — Management API (`test_athena_management_api.py`)

| Test | What it verifies |
|------|-----------------|
| `test_management_rejects_bad_intent` | Bad intent returns 400 |
| `test_management_close_all_writes_json` | CLOSE_ALL writes management_cmd.json correctly |
| `test_management_close_pct` | CLOSE_PCT writes with pct field |

---

## Unit Tests — ATHENA Groups Partition (`test_athena_groups_partition.py`)

| Test | What it verifies |
|------|-----------------|
| `test_partition_confirms_only_matching_magic` | Only groups with MT5-matching magic show as confirmed |
| `test_partition_pending_order_magic_counts` | Pending order magics count as confirmed |
| `test_partition_empty_mt5_queues_everything` | No MT5 data = all groups queued |
| `test_api_live_exposes_partition_fields` | /api/live has open_groups, open_groups_queued, open_groups_policy |

---

## Unit Tests — ATHENA /api/live (`test_athena_live_unit.py`)

| Test | What it verifies |
|------|-----------------|
| `test_api_live_has_execution_and_tradingview` | execution, tradingview, mt5_quote_stale, session_utc, aegis.pnl_day_reset_hour_utc, performance_window present |

---

## Unit Tests — SCRIBE Query (`test_athena_scribe_query_limits.py`)

| Test | What it verifies |
|------|-----------------|
| `test_scribe_query_401_when_secret_and_no_header` | Missing auth returns 401 |
| `test_scribe_query_ok_with_bearer` | Bearer token accepted, returns rows + count + truncated |
| `test_scribe_query_ok_with_x_header` | X-ATHENA-SCRIBE-TOKEN header accepted |
| `test_scribe_query_truncated_flag_in_payload` | Truncated flag true when rows exceed max |

---

## Unit Tests — SCRIBE Query Examples (`test_scribe_query_examples.py`)

| Test | What it verifies |
|------|-----------------|
| `test_scribe_example_queries_execute_on_empty_db` | Every example SQL from scribe_query_examples.json runs without syntax error |
| `test_scribe_query_limited_truncates` | query_limited correctly truncates and sets flag |

---

## Unit Tests — JSON Schemas (`test_json_schemas.py`)

| Test | What it verifies |
|------|-----------------|
| `test_forge_close_all` | FORGE CLOSE_ALL validates against schema |
| `test_forge_open_group` | FORGE OPEN_GROUP validates against schema |
| `test_aurum_mode_change` | AURUM MODE_CHANGE validates against schema |
| `test_aurum_open_group` | AURUM OPEN_GROUP validates against schema |
| `test_status_minimal` | status.json minimal shape validates |
| `test_market_data_minimal` | market_data.json minimal shape validates |

---

## Unit Tests — Schema Bundle Integrity (`test_schema_bundle_integrity.py`)

| Test | What it verifies |
|------|-----------------|
| `test_manifest_version_and_paths` | manifest.json version set, all listed files exist and parse |
| `test_openapi_spec_covers_http_api` | OpenAPI YAML mentions /api/live, /api/openapi.yaml |
| `test_data_contract_doc_exists` | DATA_CONTRACT.md exists with file bus + API references |
| `test_sync_openapi_scribe_script_idempotent` | Sync script produces no diff on re-run |

---

## Unit Tests — Swagger UI (`test_swagger_ui.py`)

| Test | What it verifies |
|------|-----------------|
| `test_openapi_yaml_served` | /api/openapi.yaml returns OpenAPI with key operationIds |
| `test_health_includes_scribe_query_caps` | /api/health includes scribe_query limits |
| `test_get_mode_and_heartbeat_help` | GET /api/mode returns mode + hint; GET /api/components/heartbeat returns help |
| `test_swagger_ui_shell_served` | /api/docs/ returns Swagger UI HTML |
| `test_swagger_ui_references_openapi_path` | Swagger UI references /api/openapi.yaml |

---

## Unit Tests — Trading Sessions (`test_trading_session.py`)

| Test | What it verifies |
|------|-----------------|
| `test_london_window` | 08:00-12:59 UTC = LONDON |
| `test_new_york_then_asian_wrap` | 17:00-21:59 = NEW_YORK, 22:00-07:59 = ASIAN (wrap) |
| `test_london_opens_after_asian` | 08:00 = LONDON (boundary) |
| `test_london_ny_mid_window` | 14:00 = LONDON_NY |
| `test_trading_day_reset_hour_defaults_to_london` | Default reset hour = London start |
| `test_trading_day_reset_hour_aegis_override` | AEGIS_SESSION_RESET_HOUR overrides default |

---

## Unit Tests — Service Python Resolution (`test_resolve_signal_python.py`)

| Test | What it verifies |
|------|-----------------|
| `test_resolve_prefers_signal_python_env` | SIGNAL_PYTHON env var takes priority |
| `test_resolve_prefers_venv_when_no_env` | .venv/bin/python used when no env var |
| `test_inject_signal_python_replaces_placeholder` | __SIGNAL_PYTHON__ placeholder replaced correctly |

---

## Playwright UI Tests — Dashboard (`test_dashboard.spec.js`)

| Test | What it verifies |
|------|-----------------|
| `dashboard loads without error` | No error title, root visible |
| `ATHENA header is visible` | ATHENA text visible |
| `mode badge is visible` | One of OFF/WATCH/SIGNAL/SCALPER/HYBRID visible |
| `left column panels are visible` | Account + Mode Control panels |
| `LENS panel is visible` | LENS text visible |
| `system health panel is visible` | System Health text visible |
| `tab navigation exists` | Groups + Activity tabs visible |
| `no JavaScript errors on load` | No console errors (excludes network) |

---

## Playwright UI Tests — Panels (`test_panels.spec.js`)

| Test | What it verifies |
|------|-----------------|
| `Activity tab switches content` | Activity tab click shows filter buttons (INFO) |
| `Activity pause toggles live tail` | PAUSE/RESUME buttons toggle, footer updates |
| `Mode control buttons are clickable` | WATCH button visible and clickable |
| `AURUM chat input is present` | Chat input or AURUM text visible |
| `Performance tab shows stats` | Performance tab shows Win Rate |
| `Groups tab shows open groups or empty state` | Groups or "No open groups" visible |
| `SENTINEL panel shows status` | CLEAR TO TRADE or TRADING PAUSED visible |

---

## Playwright UI Tests — Closures (`test_closures.spec.js`)

| Test | What it verifies |
|------|-----------------|
| `Closures tab is visible in tab bar` | data-testid tab-closures visible |
| `Closures tab switches content on click` | Shows closure rows or empty state |
| `Closures tab shows API help text` | "Full history" footer text visible |
| `Closures stats tiles render when data exists` | SL Hits tiles or empty state |
| `Can switch between Groups and Closures tabs` | Tab switching doesn't crash |

---

## Playwright UI Tests — Audit (`test_athena_audit.spec.js`)

| Test | What it verifies |
|------|-----------------|
| `walk tabs, screenshots, JSON report for Claude` | Walks all 4 tabs, takes screenshots, writes JSON audit report, checks for mock/static data |

---

## Test Categories

| Category | Count | How to run |
|----------|-------|------------|
| API integration (live server) | ~40 | `make test-api` |
| Unit tests (no server) | ~55 | `make test-contracts` |
| Playwright UI | ~18 | `make test-ui-silent` |
| **Total** | **~113** | `make test` |

---

## Notes

- Tests marked `@pytest.mark.slow` (e.g., `test_aurum_responds`) call real Claude API — excluded by default
- Tests marked `@pytest.mark.unit` run without a live server (use Flask test_client or mocks)
- API integration tests require ATHENA running on `ATHENA_URL` (default `http://localhost:7842`)
- Playwright tests require `npx playwright install` and ATHENA running
- `make test-contracts` includes channel scoping, JSON schema, AURUM/FORGE contract, and SCRIBE query tests
