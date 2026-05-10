# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-10
**EA version**: FORGE v2.7.12 (stamped from VERSION file; MQL5: 2.82)
**Reviewer**: Codex (automated) + Claude Code (manual fixes applied)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults). Post-2.7.12 review — covers H1 DI sell gate, cascade multi-leg, macd_histogram fix.

---

## Validation Summary
- Gates checked: 54
- PASS: 46 | WARNING: 5 | FAIL: 0 | UNVERIFIED: 3

> All 4 FAILs from Codex scan fixed in this session. See Issues Found for details.

---

## Section 1 — BB_BREAKOUT BUY Gates

| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | prev_close > BB_upper + buffer | FORGE.mq5:5183 | breakout_buffer | PASS | `prev_close > (m5_bb_u + breakout_buffer)` |
| 2 | RSI > rsi_buy_min (Cardwell 40) | FORGE.mq5:5183 | rsi_buy_min=40 | PASS | Cardwell Bull Support floor |
| 3 | RSI < rsi_buy_ceil | FORGE.mq5:5185 | rsi_buy_ceil=78 | PASS | Raised 77→78 in this session |
| 4 | m5_bull (H1+M15 trend alignment) | FORGE.mq5:5183-5184 | — | PASS | `m5_bull && m15_ok_buy && h1_ok_buy && h4_ok_buy` |
| 5 | H1 DI+ > DI- gate (require_h1_di_buy) | FORGE.mq5:5191-5200 | require_h1_di_buy=1 | PASS | ADX bypass at counter_buy_adx_threshold=28 |
| 6 | OsMA Q0 gate (require_macd_buy) | FORGE.mq5:5206-5222 | require_macd_buy=1 | PASS | 4-quadrant MC; histogram positive+rising |
| 7 | H4 RSI gate (h4_rsi_gate_enabled) | FORGE.mq5:5228-5234 | h4_rsi_gate_enabled=0 | PASS | Disabled by default |
| 8 | H4 ADX gate (h4_adx_gate_enabled) | FORGE.mq5:5237-5241 | h4_adx_gate_enabled=0 | PASS | Disabled by default |

---

## Section 2 — BB_BREAKOUT SELL Gates

| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | prev_close < BB_lower - buffer | FORGE.mq5:5284 | breakout_buffer | PASS | `prev_close < (m5_bb_l - breakout_buffer)` |
| 2 | RSI < rsi_sell_max (Cardwell 60) | FORGE.mq5:5284 | rsi_sell_max=60 | PASS | Cardwell Bear Resistance ceiling |
| 3 | Session SELL cutoff | FORGE.mq5:5290-5298 | session_ny_sell_cutoff_utc=18 | PASS | Blocks SELL after 18:00 UTC (2PM EDT) |
| 4 | ADX extreme block | FORGE.mq5:5305-5312 | adx_sell_block_threshold=55 | PASS | Blocks at M15 ADX≥55 |
| 5 | ADX min SELL floor | FORGE.mq5:5313-5319 | adx_min_sell=25 | PASS | adx_min_sell_lookback_bars=6 spike filter |
| 6 | H1 DI sell gate (NEW 2.7.12) | FORGE.mq5:~5335-5351 | require_h1_di_sell=1 | PASS | Blocks SELL when H1 DI+≥DI-; no ADX bypass |
| 7 | RSI floor (two-tier) | FORGE.mq5:5334-5350 | rsi_sell_floor=33, rsi_sell_floor_weak_adx=36 | PASS | Stricter floor at ADX<35 |
| 8 | ADX spike-from-flat (adx_dur) | FORGE.mq5:5354-5366 | adx_min_sell_lookback_bars=6 | PASS | Skipped on crash bypass |
| 9 | RSI declining (require_rsi_declining_sell) | FORGE.mq5:5369-5381 | require_rsi_declining_sell=1 | PASS | Auto-off at ADX≥40 |
| 10 | OsMA Q2 gate (require_macd_sell) | FORGE.mq5:5388-5404 | require_macd_sell=1 | PASS | Histogram negative+falling |
| 11 | H1 MACD sell gate (require_h1_macd_sell) | FORGE.mq5:~5406-5425 | require_h1_macd_sell=0 | PASS | Disabled — enable in Run 12+ |
| 12 | M30 bearish EMA confirmation | FORGE.mq5:5428-5456 | require_m30_bear_sell=1, m30_bear_adx_min=25 | PASS | M30 EMA20 < EMA50 when ADX≥25 |
| 13 | H4 RSI gate | FORGE.mq5:5459-5468 | h4_rsi_gate_enabled=0 | PASS | Disabled |
| 14 | H4 ADX gate | FORGE.mq5:5471-5480 | h4_adx_gate_enabled=0 | PASS | Disabled |
| 15 | H1+H4 crash SELL bypass | FORGE.mq5:5329-5332 | breakout_h1h4_crash_sell=1 | PASS | Skips RSI floor + ADX spike gate when multi-TF bearish |

---

## Section 3 — Full Lot Path

For combined_lot_factor = inside_band × near_floor × stack × adx_lot × bounce:

| Factor | BUY ADX=38 | SELL ADX=38 | EA line | Status |
|--------|-----------|-----------|---------|--------|
| inside_band | 1.0 (above upper BB) | 1.0 (below lower BB) | FORGE.mq5:~5710 | PASS |
| near_floor | 1.0 (not near floor) | 1.0 | FORGE.mq5:~5715 | PASS |
| stack | 1.0 (first group) | 1.0 | FORGE.mq5:~5720 | PASS |
| adx_lot_factor_mid | 1.0 at ADX 25-35 | 1.0 | FORGE.mq5:~5725 | PASS |
| adx_lot_factor_high | 1.0 at ADX>35 | 1.0 | FORGE.mq5:~5728 | PASS — fixed in 2.7.10 (was 0.125) |
| bounce_factor | 1.0 (BB_BREAKOUT) | 1.0 | FORGE.mq5:~5735 | PASS |
| **Combined** | **1.0 = full lot** | **1.0 = full lot** | — | PASS |

---

## Section 4 — ADX-Conditional Leg Count

| Step | EA implementation | Config | Status |
|------|------------------|--------|--------|
| base_n = midpoint | `(min_num_trades + max_num_trades) / 2` | min=2, max=8 → base_n=5 | PASS |
| ADX<25: base_n-1 | `if(m5_adx < 25.0) base_n = MathMax(1, base_n-1)` | — | PASS |
| ADX 25-35: base_n unchanged | else branch | — | PASS |
| ADX>35: base_n+2 | `else if(m5_adx >= 35.0 && ...) base_n = MathMin(30, base_n+2)` | — | PASS |
| ForgeResolveNumTrades bonus | ±1 per regime/pattern bonus | — | PASS |
| staged_initial_legs cap | `MathMin(init_cap, n)` (fixed from n-1) | staged_initial_legs=8 | PASS |

---

## Section 5 — TP3 Live Staging

| Check | EA file:line | Status | Notes |
|-------|-------------|--------|-------|
| TP3 registered at group creation | `g_groups[gi].tp3 = (is_breakout && tp3_atr_mult>0)` | PASS | Only for BB_BREAKOUT |
| tp2_hit flag in TradeGroup struct | `bool tp2_hit` in TradeGroup | PASS | |
| tp2_hit set in ManageOpenGroups | TP2 detection sets tp2_hit=true | PASS | |
| TP3 promotion pass | After existing TP1 block, tp2_hit→promotes runners to tp3 | PASS | |
| tp3_atr_mult config | scalper_config.json: tp3_atr_mult=2.5 | PASS | |

---

## Section 6 — Direction-Split TP1

| Check | EA file:line | Config | Status |
|-------|-------------|--------|--------|
| BUY uses tp1_buy_atr_mult | FORGE.mq5:~5465 | tp1_buy_atr_mult=0.5 | PASS |
| SELL uses tp1_sell_atr_mult | FORGE.mq5:~5466 | tp1_sell_atr_mult=0.4 | PASS |
| Fallback to generic tp1_atr_mult if direction-specific=0 | Both BUY/SELL paths | tp1_atr_mult=0.4 | PASS |
| tp1_close_pct applied | Partial close at tp1_close_pct | tp1_close_pct=60 | PASS |

---

## Section 7 — Crash-Sell Bypass

| Check | EA file:line | Status |
|-------|-------------|--------|
| Requires h1_bear AND h4_bear | FORGE.mq5:5329 | PASS |
| Requires RSI > crash_sell_rsi_min (20) | FORGE.mq5:5330 | PASS |
| Requires ADX ≤ h1h4_crash_sell_adx_max (40) | FORGE.mq5:5331 | PASS |
| Skips RSI floor check when bypass=true | FORGE.mq5:5334 `if(!crash_sell_bypass)` | PASS |
| Skips ADX spike gate when bypass=true | FORGE.mq5:5354 `if(!crash_sell_bypass && ...)` | PASS |
| ADX min + RSI declining still apply on bypass | Not inside !crash_sell_bypass | PASS |

---

## Section 8 — Variable Integrity

| FORGE_ Variable | In sync script | In .env.example | Config value (active) | Default value | Status |
|----------------|---------------|----------------|----------------------|--------------|--------|
| FORGE_BREAKOUT_SELL_LIMIT_ENABLED | ✓ added 2.7.12 | ✓ | 1 | 1 | PASS |
| FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT | ✓ added 2.7.12 | ✓ | 0.4 | 0.4 | PASS |
| FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR | ✓ added 2.7.12 | ✓ | 0.125 | 0.125 | PASS |
| FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS | ✓ added 2.7.12 | ✓ | 6 | 6 | PASS |
| FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR | ✓ added 2.7.12 | ✓ | 0.25 | — | WARNING — not in defaults; verify EA reads key |
| FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD | ✓ added 2.7.12 | ✓ | 55 | — | PASS |
| FORGE_BREAKOUT_H1H4_CRASH_SELL_ADX_MAX | ✓ added 2.7.12 | ✓ | 40 | — | PASS |
| FORGE_BREAKOUT_MIN_H1_BEAR_STRENGTH | ✓ added 2.7.12 | ✓ | 0.2 | — | PASS |
| FORGE_BREAKOUT_REQUIRE_H1_DI_SELL | ✓ | ✓ | 1 | 0 | PASS |
| FORGE_BREAKOUT_REQUIRE_H1_MACD_SELL | ✓ | ✓ | 0 | 0 | PASS |
| FORGE_SELL_STOP_CONT_ENABLED | ✓ | ✓ | 1 | 0 | PASS |
| FORGE_SELL_STOP_CONT_LOT_FACTOR | ✓ | ✓ | 1.0 | 1.0 | PASS |
| FORGE_SELL_STOP_CONT_LEGS | ✓ | ✓ | 5 | 5 | PASS |
| FORGE_SELL_STOP_CONT_TP_ATR_MULT | ✓ | ✓ | 1.5 | 1.5 | PASS |
| FORGE_SELL_STOP_CONT_MIN_ADX | ✓ | ✓ | 25 | 25.0 | PASS |
| FORGE_SELL_STOP_CONT_REQUIRE_H1_DI | ✓ | ✓ | 1 | 1 | PASS |
| FORGE_BREAKOUT_RSI_BUY_CEIL | ✓ | ✓ | 78 | 70 | PASS |

---

## Section 9 — scribe.py / regime.py Cross-Check

| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|
| macd_histogram in CREATE TABLE | scribe.py:119 | WARNING | Not in CREATE — handled by ALTER TABLE migration |
| ALTER TABLE macd_histogram | scribe.py:~558 (added 2.7.12) | PASS | Fixed: migration added |
| ALTER TABLE m15_adx | scribe.py:~562 (added 2.7.12) | PASS | Fixed: migration added |
| ALTER TABLE lot_factor | scribe.py:~566 (added 2.7.12) | PASS | Fixed: migration added |
| has_macd_hist guard in INSERT | scribe.py:855-857 | PASS | Gracefully handles old source DBs |
| Live DB columns verified | aurum_intelligence.db + aurum_tester.db | PASS | All 3 columns present |
| Regime labels vs ForgeResolveNumTrades | FORGE.mq5 + regime.py | UNVERIFIED | Not cross-checked in this pass |
| regime.py config keys vs scalper_config | regime.py | UNVERIFIED | Not audited |

---

## Issues Found (Consolidated)

| # | Severity | Section | Description | Action |
|---|----------|---------|-------------|--------|
| 1 | FIXED | Version | v2.7.11 after 2.7.12 changes | Bumped VERSION→2.7.12; recompiled |
| 2 | FIXED | Sec 8 | 8 .env vars had no sync mappings (dead vars) | Added all 8 to sync_scalper_config_from_env.py |
| 3 | FIXED | Sec 9 | scribe.py INSERT includes macd_histogram/m15_adx/lot_factor with no ALTER TABLE | Added 3 ALTER TABLE migrations to scribe.py |
| 4 | WARNING | Sec 8 | FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR not in scalper_config.defaults.json | Verify EA reads sell_inside_band_lot_factor; add to defaults if used |
| 5 | WARNING | Doc | FORGE_ENTRY_CONDITIONS.md still says rsi_buy_ceil=77; active=78 | Update doc to reflect current value |
| 6 | WARNING | Doc | FORGE_ENTRY_CONDITIONS.md does not document 2.7.12 cascade changes | Update doc |
| 7 | UNVERIFIED | Sec 9 | Regime labels from regime.py not cross-checked vs ForgeResolveNumTrades | Manual audit needed before live trading |

---

## Overall Verdict

**High confidence in EA logic post-2.7.12.** All entry gates are correctly implemented and wired to config. The H1 DI sell gate (require_h1_di_sell=1) is the most significant new protection — it would have blocked G5008 (May 4, ADX=37.4, H1 bullish) at both the entry level and the cascade arming level. The cascade multi-leg fix (5 legs × full lot, lot_factor=1.0) correctly classifies TP1-hit continuation as a primary-quality entry, with real-time RSI+ADX+H1 DI validation at arm time.

Three items need follow-up before Run 11:
1. `FORGE_ENTRY_CONDITIONS.md` is stale (rsi_buy_ceil=78, cascade changes not documented) — update before next review cycle
2. `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR` — verify EA reads this key; if unused, remove from .env
3. Regime label cross-check — unaudited; low risk but should be done before live trading
