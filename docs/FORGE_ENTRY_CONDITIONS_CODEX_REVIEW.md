# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-12
**EA version**: FORGE v2.7.37 (from scalper_config.json; #property "2.107")
**Reviewer**: Codex (automated, read-only)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults).

## Validation Summary
- Gates checked: 60 literal SKIP gate codes from mandatory grep pattern
- PASS: 214  |  WARNING: 6  |  FAIL: 1  |  UNVERIFIED: 0
- Mandatory Check A (dead env vars): PASS (0 issues)
- Mandatory Check B (gate legend): PASS (0 issues)

## Section 1 — BB_BREAKOUT BUY Gates [carry over from v2.7.36 review with updated line cites]
| # | Gate | Evidence | Active config | Status |
|---|------|----------|---------------|--------|
| 1 | Breakout trigger uses prior M5 close above upper band plus buffer | ea/FORGE.mq5:6907 | bb_breakout.adx_min=20 at config/scalper_config.json:35 | PASS |
| 2 | BUY RSI ceiling blocks overbought entries | ea/FORGE.mq5:6924-6926 | rsi_buy_ceil=78 at config/scalper_config.json:63 | PASS |
| 3 | H1 DI BUY gate reads DI+/DI- and can block weak-DI buys | ea/FORGE.mq5:6433-6441, ea/FORGE.mq5:6933-6937 | require_h1_di_buy=1, counter_buy_adx_threshold=28 at config/scalper_config.json:72-73 | PASS |
| 4 | OsMA BUY gate maps non-Q0 quadrants to dynamic `_qreason` SKIPs | ea/FORGE.mq5:6952-6957 | require_macd_buy=1 at config/scalper_config.json:89 | PASS |
| 5 | H4 RSI/ADX BUY supplemental gates exist but are inactive in active config | ea/FORGE.mq5:6967-6979 | h4_rsi_gate_enabled=0, h4_adx_gate_enabled=0 at config/scalper_config.json:111-116 | PASS |
| 6 | Failed-breakout, cooldown, PSAR, and news-tighten checks run before assigning BUY | ea/FORGE.mq5:7010-7088 | failed_gate_enabled=1, same_dir_cooldown_seconds=900, require_psar_align=1 at config/scalper_config.json:77-83 | PASS |

## Section 2 — BB_BREAKOUT SELL Gates
| # | Gate | Evidence | Active config | Status |
|---|------|----------|---------------|--------|
| 1 | Breakout trigger uses prior M5 close below lower band plus buffer | ea/FORGE.mq5:7126 | adx_min=20 and adx_min_sell=25 at config/scalper_config.json:35,70 | PASS |
| 2 | Session sell cutoff gate exists but active config disables it with zero-hour cutoffs | ea/FORGE.mq5:7146-7152 | session_ny_sell_cutoff_utc=0, session_london_sell_cutoff_utc=0 at config/scalper_config.json:243-244 | WARNING |
| 3 | Extreme ADX and minimum SELL ADX gates are implemented | ea/FORGE.mq5:7160-7173 | adx_sell_block_threshold=55 and adx_min_sell=25 at config/scalper_config.json:125,70 | PASS |
| 4 | H1 DI SELL gate is before crash bypass and explicitly has no ADX bypass | ea/FORGE.mq5:7184-7194 | require_h1_di_sell=1 at config/scalper_config.json:74 | PASS |
| 5 | Crash-sell bypass requires H1/H4 bear, RSI floor, ADX cap, and M15 ADX confirmation | ea/FORGE.mq5:7199-7212 | h1h4_crash_sell=1, rsi_min=20, adx_max=40, min_m15_adx=25 at config/scalper_config.json:65-69 | PASS |
| 6 | RSI floor, ADX duration, RSI rising, HID_BULL, OsMA, H1 MACD, M30, H4, cooldown, PSAR, and news gates run before SELL assignment | ea/FORGE.mq5:7213-7435 | key toggles at config/scalper_config.json:77-123 | PASS |

## Section 3 — Full Lot Path
| Factor | Evidence | Active config | Status |
|---|---|---|---|
| `inside_band_factor` | ea/FORGE.mq5:7904-7911 | sell_inside_band_lot_factor=0.25 at config/scalper_config.json:124 | PASS |
| `near_floor_factor` | ea/FORGE.mq5:7912-7920 | breakout_near_floor_lot_factor=0.25 at config/scalper_config.json:241 | PASS |
| `stack_factor` | ea/FORGE.mq5:7922-7929 | same_direction_stack_lot_factor=0.25 at config/scalper_config.json:242 | PASS |
| `adx_lot_factor` | ea/FORGE.mq5:7930-7945 | M15 ADX tiers enabled at config/scalper_config.json:245-249 | PASS |
| bounce/dump/pullback factors | ea/FORGE.mq5:7947-7962 | active dump/pullback factors at config/scalper_config.json:268,272-273,278 | PASS |
| combined factor and base lot | ea/FORGE.mq5:7963-7969 | fixed_lot=0.25 at config/scalper_config.json:302 | PASS |

## Section 4 — ADX-Conditional Leg Count
| Check | Evidence | Active config | Status |
|---|---|---|---|
| Base leg count comes from config unless inputs override | ea/FORGE.mq5:7808-7814 | min/max trades 2/30 at config/scalper_config.json:303-304 | PASS |
| Breakout ADX <25 trims one leg; ADX 35..sell-block boosts two | ea/FORGE.mq5:7839-7850 | sell block threshold=55 at config/scalper_config.json:250 | PASS |
| Unclear HTF and XAU SELL caps apply after resolver | ea/FORGE.mq5:7887-7899 | unclear cap=5, XAU SELL cap=10 at config/scalper_config.json:313-314 | PASS |

## Section 5 — TP3 Live Staging
| Check | Evidence | Active config | Status |
|---|---|---|---|
| TP1 handling arms post-TP1 ladder and moves remaining legs | ea/FORGE.mq5:1884-1904 | move_be_on_tp1=true at config/scalper_config.json:60 | PASS |
| TP2 reached promotes runners to TP3 and optionally ratchets SL to TP1 | ea/FORGE.mq5:1947-2001 | tp3_atr_mult=2.5, tp2_sl_ratchet_enabled=1 at config/scalper_config.json:42,54 | PASS |
| TP4/TP5 staging code exists but active config disables both | ea/FORGE.mq5:2005 | tp4_staging_enabled=0, tp5_staging_enabled=0 at config/scalper_config.json:45-46 | PASS |

## Section 6 — Direction-Split TP1
| Check | Evidence | Active config | Status |
|---|---|---|---|
| BUY uses direction-specific TP1 multiplier when set | ea/FORGE.mq5:7101-7102 | tp1_buy_atr_mult=0.5 at config/scalper_config.json:51 | PASS |
| SELL uses direction-specific TP1 multiplier when set | ea/FORGE.mq5:7417-7418 | tp1_sell_atr_mult=0.4 at config/scalper_config.json:52 | PASS |
| Shared fallback remains available | ea/FORGE.mq5:7417 | tp1_atr_mult=0.4 at config/scalper_config.json:50 | PASS |

## Section 7 — Crash-Sell Bypass
| Check | Evidence | Status |
|---|---|---|
| Bypass conditions include H1/H4 bear, RSI > floor, ADX <= cap, M15 ADX >= floor | ea/FORGE.mq5:7203-7212 | PASS |
| Does not bypass H1 DI SELL | ea/FORGE.mq5:7184-7199 | PASS |
| Bypasses only RSI floor and ADX-duration gate | ea/FORGE.mq5:7219-7240 | PASS |
| Near-floor lot reducer applies to SELL crash region | ea/FORGE.mq5:7912-7920 | PASS |

## Section 8 — Variable Integrity (FORGE_* env)
All 146 active uppercase `FORGE_*` variables in `.env` are mapped by `scripts/sync_scalper_config_from_env.py` or whitelisted by `tests/api/test_forge_27x_gates.py`; no lowercase config-looking keys were found (`grep -nE` returned empty). See Mandatory Check A for the full table. Status: PASS.

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Check | Evidence | Status |
|---|---|---|
| `forge_signals` top declarative schema contains v2.7.37 atom columns | python/scribe.py:119-207 | PASS |
| In-init `CREATE TABLE IF NOT EXISTS forge_signals` contains v2.7.37 atom columns | python/scribe.py:594-626 | PASS |
| Additive `ALTER TABLE forge_signals ADD COLUMN` migration loops cover v37 + Group 3 atoms | python/scribe.py:675-724 | PASS |
| `regime.py` has no direct `forge_signals` schema dependency in this review | python/regime.py:94-118,551-632 | PASS |
| schemas query examples reference `forge_signals` generically and do not conflict with additive columns | schemas/scribe_query_examples.json:75-82 | PASS |

## Section 10 — Dashboard / API Consistency
| Check | Evidence | Status |
|---|---|---|
| `/api/backtest/run/:id` reads `forge_signals` for signals, gate breakdown, and taken entries | python/athena_api.py:1745-1778 | PASS |
| Dashboard backtest detail consumes API `signals`, `gates`, and `entries` fields without hard-coded v2.7.37 atom assumptions | dashboard/app.js:1591-1603,1723-1780 | PASS |
| Gate legend endpoint serves `config/gate_legend.json` and dashboard maps returned gate_reason labels | python/athena_api.py:1979-1984, dashboard/app.js:610-611,1774-1780 | PASS |
| OpenAPI/query examples use `forge_signals` additive-safe selects | schemas/openapi.yaml:828-835 | PASS |

## Section 11 — Scripts / Tests Consistency
| Check | Evidence | Status |
|---|---|---|
| Dead env var test whitelist contains only `FORGE_SCALPER_MODE` | tests/api/test_forge_27x_gates.py:260-261 | PASS |
| Gate legend test still uses a literal-string regex and does not see dynamic `_qreason`/`floor_gate` emissions | tests/api/test_forge_27x_gates.py:188, ea/FORGE.mq5:7229-7231,7296-7303 | WARNING |
| scribe journal sync tests passed | tests/services/test_scribe_forge_journal.py:119-217; pytest: 4 passed | PASS |
| bridge tester journal sync tuple mocks passed | tests/api/test_bridge_tester_journal_sync.py:86-238; pytest: 4 passed | PASS |

## Section 12 — v2.7.37 Layer-4 Atom Telemetry (NEW — 69 cols)
Tier counts requested: Tier A=13, Tier B=11, Group 3=45, total=69. Declarations: 69 `g_eval_*` atom globals at ea/FORGE.mq5:246-315; `g_eval_last_tick` guard at ea/FORGE.mq5:316.

| Column | EA SIGNALS CREATE | EA ALTER migration | scribe declarative | scribe in-init | scribe ALTER | Status |
|---|---|---|---|---|---|---|
| `h4_trend` | ea/FORGE.mq5:5210 | ea/FORGE.mq5:5316 | python/scribe.py:153 | python/scribe.py:606 | python/scribe.py:670 | PASS |
| `m15_trend` | ea/FORGE.mq5:5211 | ea/FORGE.mq5:5317 | python/scribe.py:154 | python/scribe.py:606 | python/scribe.py:671 | PASS |
| `h1_di_balance` | ea/FORGE.mq5:5212 | ea/FORGE.mq5:5318 | python/scribe.py:155 | python/scribe.py:606 | python/scribe.py:672 | PASS |
| `day_open` | ea/FORGE.mq5:5213 | ea/FORGE.mq5:5319 | python/scribe.py:156 | python/scribe.py:607 | python/scribe.py:673 | PASS |
| `day_high` | ea/FORGE.mq5:5214 | ea/FORGE.mq5:5320 | python/scribe.py:157 | python/scribe.py:607 | python/scribe.py:674 | PASS |
| `day_low` | ea/FORGE.mq5:5215 | ea/FORGE.mq5:5321 | python/scribe.py:158 | python/scribe.py:607 | python/scribe.py:675 | PASS |
| `m5_open_1` | ea/FORGE.mq5:5216 | ea/FORGE.mq5:5322 | python/scribe.py:159 | python/scribe.py:608 | python/scribe.py:676 | PASS |
| `m5_high_1` | ea/FORGE.mq5:5217 | ea/FORGE.mq5:5323 | python/scribe.py:160 | python/scribe.py:608 | python/scribe.py:677 | PASS |
| `m5_low_1` | ea/FORGE.mq5:5218 | ea/FORGE.mq5:5324 | python/scribe.py:161 | python/scribe.py:608 | python/scribe.py:678 | PASS |
| `m5_close_1` | ea/FORGE.mq5:5219 | ea/FORGE.mq5:5325 | python/scribe.py:162 | python/scribe.py:608 | python/scribe.py:679 | PASS |
| `m5_lh_cascade` | ea/FORGE.mq5:5220 | ea/FORGE.mq5:5326 | python/scribe.py:163 | python/scribe.py:609 | python/scribe.py:680 | PASS |
| `m5_hl_cascade` | ea/FORGE.mq5:5221 | ea/FORGE.mq5:5327 | python/scribe.py:164 | python/scribe.py:609 | python/scribe.py:681 | PASS |
| `m5_body_pct` | ea/FORGE.mq5:5222 | ea/FORGE.mq5:5328 | python/scribe.py:165 | python/scribe.py:609 | python/scribe.py:682 | PASS |
| `h1_di_plus` | ea/FORGE.mq5:5223 | ea/FORGE.mq5:5329 | python/scribe.py:166 | python/scribe.py:610 | python/scribe.py:683 | PASS |
| `h1_di_minus` | ea/FORGE.mq5:5224 | ea/FORGE.mq5:5330 | python/scribe.py:167 | python/scribe.py:610 | python/scribe.py:684 | PASS |
| `h4_rsi` | ea/FORGE.mq5:5225 | ea/FORGE.mq5:5331 | python/scribe.py:168 | python/scribe.py:610 | python/scribe.py:685 | PASS |
| `h4_adx` | ea/FORGE.mq5:5226 | ea/FORGE.mq5:5332 | python/scribe.py:169 | python/scribe.py:610 | python/scribe.py:686 | PASS |
| `m30_trend` | ea/FORGE.mq5:5227 | ea/FORGE.mq5:5333 | python/scribe.py:170 | python/scribe.py:610 | python/scribe.py:687 | PASS |
| `d1_open` | ea/FORGE.mq5:5228 | ea/FORGE.mq5:5334 | python/scribe.py:171 | python/scribe.py:611 | python/scribe.py:688 | PASS |
| `d1_close` | ea/FORGE.mq5:5229 | ea/FORGE.mq5:5335 | python/scribe.py:172 | python/scribe.py:611 | python/scribe.py:689 | PASS |
| `h1_atr` | ea/FORGE.mq5:5230 | ea/FORGE.mq5:5336 | python/scribe.py:173 | python/scribe.py:611 | python/scribe.py:690 | PASS |
| `h4_atr` | ea/FORGE.mq5:5231 | ea/FORGE.mq5:5337 | python/scribe.py:174 | python/scribe.py:611 | python/scribe.py:691 | PASS |
| `m15_atr` | ea/FORGE.mq5:5232 | ea/FORGE.mq5:5338 | python/scribe.py:175 | python/scribe.py:611 | python/scribe.py:692 | PASS |
| `m1_atr` | ea/FORGE.mq5:5233 | ea/FORGE.mq5:5339 | python/scribe.py:176 | python/scribe.py:611 | python/scribe.py:693 | PASS |
| `h1_rsi` | ea/FORGE.mq5:5235 | ea/FORGE.mq5:5341 | python/scribe.py:178 | python/scribe.py:613 | python/scribe.py:701 | PASS |
| `h1_adx` | ea/FORGE.mq5:5235 | ea/FORGE.mq5:5342 | python/scribe.py:179 | python/scribe.py:613 | python/scribe.py:701 | PASS |
| `h1_bb_u` | ea/FORGE.mq5:5235 | ea/FORGE.mq5:5343 | python/scribe.py:180 | python/scribe.py:613 | python/scribe.py:702 | PASS |
| `h1_bb_m` | ea/FORGE.mq5:5235 | ea/FORGE.mq5:5344 | python/scribe.py:181 | python/scribe.py:613 | python/scribe.py:702 | PASS |
| `h1_bb_l` | ea/FORGE.mq5:5235 | ea/FORGE.mq5:5345 | python/scribe.py:182 | python/scribe.py:613 | python/scribe.py:702 | PASS |
| `h4_bb_u` | ea/FORGE.mq5:5236 | ea/FORGE.mq5:5346 | python/scribe.py:183 | python/scribe.py:614 | python/scribe.py:703 | PASS |
| `h4_bb_m` | ea/FORGE.mq5:5236 | ea/FORGE.mq5:5347 | python/scribe.py:184 | python/scribe.py:614 | python/scribe.py:703 | PASS |
| `h4_bb_l` | ea/FORGE.mq5:5236 | ea/FORGE.mq5:5348 | python/scribe.py:185 | python/scribe.py:614 | python/scribe.py:703 | PASS |
| `m15_rsi` | ea/FORGE.mq5:5237 | ea/FORGE.mq5:5349 | python/scribe.py:186 | python/scribe.py:615 | python/scribe.py:704 | PASS |
| `m15_ema20` | ea/FORGE.mq5:5237 | ea/FORGE.mq5:5350 | python/scribe.py:187 | python/scribe.py:615 | python/scribe.py:704 | PASS |
| `m15_ema50` | ea/FORGE.mq5:5237 | ea/FORGE.mq5:5351 | python/scribe.py:188 | python/scribe.py:615 | python/scribe.py:704 | PASS |
| `m30_rsi` | ea/FORGE.mq5:5238 | ea/FORGE.mq5:5352 | python/scribe.py:189 | python/scribe.py:616 | python/scribe.py:705 | PASS |
| `m30_adx` | ea/FORGE.mq5:5238 | ea/FORGE.mq5:5353 | python/scribe.py:190 | python/scribe.py:616 | python/scribe.py:705 | PASS |
| `m30_atr` | ea/FORGE.mq5:5238 | ea/FORGE.mq5:5354 | python/scribe.py:191 | python/scribe.py:616 | python/scribe.py:705 | PASS |
| `m30_ema20` | ea/FORGE.mq5:5238 | ea/FORGE.mq5:5355 | python/scribe.py:192 | python/scribe.py:616 | python/scribe.py:706 | PASS |
| `m30_ema50` | ea/FORGE.mq5:5238 | ea/FORGE.mq5:5356 | python/scribe.py:193 | python/scribe.py:616 | python/scribe.py:706 | PASS |
| `m1_ema20` | ea/FORGE.mq5:5239 | ea/FORGE.mq5:5357 | python/scribe.py:194 | python/scribe.py:617 | python/scribe.py:707 | PASS |
| `m1_ema50` | ea/FORGE.mq5:5239 | ea/FORGE.mq5:5358 | python/scribe.py:195 | python/scribe.py:617 | python/scribe.py:707 | PASS |
| `m5_open_0` | ea/FORGE.mq5:5240 | ea/FORGE.mq5:5359 | python/scribe.py:196 | python/scribe.py:618 | python/scribe.py:708 | PASS |
| `m5_high_0` | ea/FORGE.mq5:5240 | ea/FORGE.mq5:5360 | python/scribe.py:197 | python/scribe.py:618 | python/scribe.py:708 | PASS |
| `m5_low_0` | ea/FORGE.mq5:5240 | ea/FORGE.mq5:5361 | python/scribe.py:198 | python/scribe.py:618 | python/scribe.py:708 | PASS |
| `m5_close_0` | ea/FORGE.mq5:5240 | ea/FORGE.mq5:5362 | python/scribe.py:199 | python/scribe.py:618 | python/scribe.py:708 | PASS |
| `m15_open` | ea/FORGE.mq5:5241 | ea/FORGE.mq5:5363 | python/scribe.py:200 | python/scribe.py:619 | python/scribe.py:709 | PASS |
| `m15_high` | ea/FORGE.mq5:5241 | ea/FORGE.mq5:5364 | python/scribe.py:201 | python/scribe.py:619 | python/scribe.py:709 | PASS |
| `m15_low` | ea/FORGE.mq5:5241 | ea/FORGE.mq5:5365 | python/scribe.py:202 | python/scribe.py:619 | python/scribe.py:709 | PASS |
| `m15_close` | ea/FORGE.mq5:5241 | ea/FORGE.mq5:5366 | python/scribe.py:203 | python/scribe.py:619 | python/scribe.py:709 | PASS |
| `m30_open` | ea/FORGE.mq5:5242 | ea/FORGE.mq5:5367 | python/scribe.py:204 | python/scribe.py:620 | python/scribe.py:710 | PASS |
| `m30_high` | ea/FORGE.mq5:5242 | ea/FORGE.mq5:5368 | python/scribe.py:205 | python/scribe.py:620 | python/scribe.py:710 | PASS |
| `m30_low` | ea/FORGE.mq5:5242 | ea/FORGE.mq5:5369 | python/scribe.py:206 | python/scribe.py:620 | python/scribe.py:710 | PASS |
| `m30_close` | ea/FORGE.mq5:5242 | ea/FORGE.mq5:5370 | python/scribe.py:207 | python/scribe.py:620 | python/scribe.py:710 | PASS |
| `h1_open` | ea/FORGE.mq5:5243 | ea/FORGE.mq5:5371 | python/scribe.py:208 | python/scribe.py:621 | python/scribe.py:711 | PASS |
| `h1_high` | ea/FORGE.mq5:5243 | ea/FORGE.mq5:5372 | python/scribe.py:209 | python/scribe.py:621 | python/scribe.py:711 | PASS |
| `h1_low` | ea/FORGE.mq5:5243 | ea/FORGE.mq5:5373 | python/scribe.py:210 | python/scribe.py:621 | python/scribe.py:711 | PASS |
| `h1_close` | ea/FORGE.mq5:5243 | ea/FORGE.mq5:5374 | python/scribe.py:211 | python/scribe.py:621 | python/scribe.py:711 | PASS |
| `h4_open` | ea/FORGE.mq5:5244 | ea/FORGE.mq5:5375 | python/scribe.py:212 | python/scribe.py:622 | python/scribe.py:712 | PASS |
| `h4_high` | ea/FORGE.mq5:5244 | ea/FORGE.mq5:5376 | python/scribe.py:213 | python/scribe.py:622 | python/scribe.py:712 | PASS |
| `h4_low` | ea/FORGE.mq5:5244 | ea/FORGE.mq5:5377 | python/scribe.py:214 | python/scribe.py:622 | python/scribe.py:712 | PASS |
| `h4_close` | ea/FORGE.mq5:5244 | ea/FORGE.mq5:5378 | python/scribe.py:215 | python/scribe.py:622 | python/scribe.py:712 | PASS |
| `m5_inside_bar` | ea/FORGE.mq5:5245 | ea/FORGE.mq5:5379 | python/scribe.py:216 | python/scribe.py:623 | python/scribe.py:713 | PASS |
| `m5_outside_bar` | ea/FORGE.mq5:5245 | ea/FORGE.mq5:5380 | python/scribe.py:217 | python/scribe.py:623 | python/scribe.py:714 | PASS |
| `m5_doji` | ea/FORGE.mq5:5246 | ea/FORGE.mq5:5381 | python/scribe.py:218 | python/scribe.py:624 | python/scribe.py:715 | PASS |
| `m5_strong_bar` | ea/FORGE.mq5:5246 | ea/FORGE.mq5:5382 | python/scribe.py:219 | python/scribe.py:624 | python/scribe.py:716 | PASS |
| `long_lower_wick` | ea/FORGE.mq5:5247 | ea/FORGE.mq5:5383 | python/scribe.py:220 | python/scribe.py:625 | python/scribe.py:717 | PASS |
| `long_upper_wick` | ea/FORGE.mq5:5247 | ea/FORGE.mq5:5384 | python/scribe.py:221 | python/scribe.py:625 | python/scribe.py:718 | PASS |
| `m5_range_expanding` | ea/FORGE.mq5:5248 | ea/FORGE.mq5:5385 | python/scribe.py:222 | python/scribe.py:626 | python/scribe.py:719 | PASS |

## Section 13 — ForgeEvalAtoms helper integrity (NEW)
| Check | File:line | Status |
|---|---|---|
| Function defined | ea/FORGE.mq5:4308 | PASS |
| `g_eval_last_tick` idempotency guard | ea/FORGE.mq5:4310-4311 | PASS |
| All 69 atom globals assigned/read into telemetry paths | ea/FORGE.mq5:4323-4478 plus insert values at ea/FORGE.mq5:5576-5645 | PASS |
| Called at top of native entry evaluation before `ScalperOnePerBar()` | call is after `ScalperOnePerBar()` at ea/FORGE.mq5:6402-6407 | FAIL |
| Called before any `JournalRecordSignal` in `CheckNativeScalperSetups` | earlier guard logs exist at ea/FORGE.mq5:6320,6347,6355,6365,6375,6389 before call at ea/FORGE.mq5:6407 | FAIL |
| H1 ADX DI+/DI- buffers read from buffers 1 and 2 | ea/FORGE.mq5:4353-4357 and ea/FORGE.mq5:6433-6441 | PASS |
| Current OHLC uses bar 0 and prior M5 uses bar 1+ | current at ea/FORGE.mq5:4431-4452; prior/cascade at ea/FORGE.mq5:4376-4388 | PASS |

## Section 14 — Scribe sync integrity (NEW)
| Check | File:line | Status |
|---|---|---|
| `has_v37` detects all 24 v37 cols on source SIGNALS | python/scribe.py:1042 | PASS |
| `has_v37g3` detects all 45 Group 3 cols on source SIGNALS | python/scribe.py:1058; tuple build comment confirms 45 at python/scribe.py:1208 | PASS |
| SELECT appends 24 + 45 cols conditionally | python/scribe.py:1168-1170 | PASS |
| INSERT placeholder count = 37 + 24 + 45 = 106 | python/scribe.py:1251 | PASS |
| insert_params tuple size = 37 + 24 + 45 = 106 | python/scribe.py:1206-1212 | PASS |
| Migration is idempotent when run twice on tmp DB | `PYTHONPATH=python python3 ... Scribe(path); Scribe(path)` completed; resulting table had 107 columns | PASS |
| Group 3 comments still say 46 cols in several places although code lists 45 | ea/FORGE.mq5:5234,5550; python/scribe.py:170,705,1059,1170,1239 | WARNING |
| v37 scribe indexes are not created on a fresh table because index creation is gated by columns missing from the pre-migration `fs_cols` snapshot | python/scribe.py:727-731; tmp fresh DB index_list was empty | WARNING |

## Section 15 — Init order fix verification (carryover from v2.7.36 #1)
| Check | File:line | Status |
|---|---|---|
| `InitScalperConfig()` precedes `WriteBrokerInfo()` in OnInit | ea/FORGE.mq5:977-982 | PASS |
| Comment explains the dependency | ea/FORGE.mq5:977-980 | PASS |

## Section 16 — Inventory + atlas cross-refs (NEW)
| Check | File:line | Status |
|---|---|---|
| `FORGE_DECISION_STACK.md` §10 references `docs/FORGE_DECISION_STACK_INVENTORY.md` | FORGE_DECISION_STACK.md:192-194 | PASS |
| Decision Stack §8 references logging extension design | FORGE_DECISION_STACK.md:179-187 | PASS |
| Atlas §3 mentions “Decision Stack Inventory §6” | docs/FORGE_INDICATOR_ATLAS.md:326-328 | PASS |
| Atlas §3.4 has atom-level deficit table | docs/FORGE_INDICATOR_ATLAS.md:364 | PASS |
| Inventory file exists and is non-empty | docs/FORGE_DECISION_STACK_INVENTORY.md:1; `wc -l` = 551 | PASS |

## Mandatory Check A — Dead FORGE_* env vars
**Status**: PASS

| FORGE_ Variable | .env file:line | In sync script / whitelist | In .env.example | Status |
|---|---|---|---|---|
| `FORGE_SCALPER_MODE` | .env:145 | tests/api/test_forge_27x_gates.py:261 | .env.example:203 | PASS |
| `FORGE_BOUNCE_RECLAIM_PCT` | .env:146 | scripts/sync_scalper_config_from_env.py:28 | .env.example:246 | PASS |
| `FORGE_BOUNCE_REQUIRE_REJECTION_CANDLE` | .env:147 | scripts/sync_scalper_config_from_env.py:29 | .env.example:248 | PASS |
| `FORGE_FAST_LOCK_MIN_HOLD_SEC_BOUNCE` | .env:148 | scripts/sync_scalper_config_from_env.py:30 | .env.example:250 | PASS |
| `FORGE_FAST_LOCK_MIN_HOLD_SEC_BREAKOUT` | .env:149 | scripts/sync_scalper_config_from_env.py:31 | .env.example:295 | PASS |
| `FORGE_FAST_LOCK_MIN_PROFIT_POINTS` | .env:150 | scripts/sync_scalper_config_from_env.py:33 | .env.example:254 | PASS |
| `FORGE_BOUNCE_MIN_TP1_ATR_MULT` | .env:151 | scripts/sync_scalper_config_from_env.py:34 | .env.example:256 | PASS |
| `FORGE_BOUNCE_MIN_TP2_ATR_MULT` | .env:152 | scripts/sync_scalper_config_from_env.py:35 | .env.example:258 | PASS |
| `FORGE_BREAKOUT_TP1_ATR_MULT` | .env:154 | scripts/sync_scalper_config_from_env.py:249 | .env.example:484 | PASS |
| `FORGE_BREAKOUT_TP1_BUY_ATR_MULT` | .env:157 | scripts/sync_scalper_config_from_env.py:250 | .env.example:490 | PASS |
| `FORGE_BREAKOUT_TP1_SELL_ATR_MULT` | .env:158 | scripts/sync_scalper_config_from_env.py:251 | .env.example:491 | PASS |
| `FORGE_BREAKOUT_TP1_CLOSE_PCT` | .env:159 | scripts/sync_scalper_config_from_env.py:252 | .env.example:495 | PASS |
| `FORGE_LOT_SIZING_SOURCE` | .env:160 | scripts/sync_scalper_config_from_env.py:60 | .env.example:211 | PASS |
| `FORGE_INPUTS_OVERRIDE_LOT_SIZING` | .env:161 | scripts/sync_scalper_config_from_env.py:59 | .env.example:213 | PASS |
| `FORGE_FIXED_LOT` | .env:162 | scripts/sync_scalper_config_from_env.py:61 | .env.example:215 | PASS |
| `FORGE_MIN_NUM_TRADES` | .env:169 | scripts/sync_scalper_config_from_env.py:62 | .env.example:219 | PASS |
| `FORGE_MAX_NUM_TRADES` | .env:171 | scripts/sync_scalper_config_from_env.py:63 | .env.example:220 | PASS |
| `FORGE_GOLD_NATIVE_MAX_SELL_LEGS` | .env:173 | scripts/sync_scalper_config_from_env.py:64 | .env.example:226 | PASS |
| `FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR` | .env:175 | scripts/sync_scalper_config_from_env.py:65 | .env.example:230 | PASS |
| `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | .env:188 | scripts/sync_scalper_config_from_env.py:70 | .env.example:241 | PASS |
| `FORGE_WAVE_CONFIRMATION_LOT_MULT` | .env:194 | scripts/sync_scalper_config_from_env.py:71 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR` | .env:197 | scripts/sync_scalper_config_from_env.py:139 | .env.example:534 | PASS |
| `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT` | .env:198 | scripts/sync_scalper_config_from_env.py:116 | .env.example:541 | PASS |
| `FORGE_BREAKOUT_ADX_MIN` | .env:200 | scripts/sync_scalper_config_from_env.py:78 | .env.example:288 | PASS |
| `FORGE_BREAKOUT_ADX_MIN_SELL` | .env:202 | scripts/sync_scalper_config_from_env.py:92 | .env.example:293 | PASS |
| `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL` | .env:204 | scripts/sync_scalper_config_from_env.py:119 | .env.example:305 | PASS |
| `FORGE_BREAKOUT_BLOCK_HID_BULL_SELL` | .env:207 | scripts/sync_scalper_config_from_env.py:120 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_RSI_DECL_SELL_ADX_THRESHOLD` | .env:209 | scripts/sync_scalper_config_from_env.py:121 | .env.example:308 | PASS |
| `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS` | .env:211 | scripts/sync_scalper_config_from_env.py:94 | .env.example:314 | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY` | .env:213 | scripts/sync_scalper_config_from_env.py:96 | .env.example:319 | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_SELL` | .env:215 | scripts/sync_scalper_config_from_env.py:98 | .env.example:324 | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_MACD_SELL` | .env:217 | scripts/sync_scalper_config_from_env.py:100 | .env.example:330 | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY` | .env:222 | scripts/sync_scalper_config_from_env.py:102 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS` | .env:226 | scripts/sync_scalper_config_from_env.py:104 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_FAILED_GATE_ENABLED` | .env:231 | scripts/sync_scalper_config_from_env.py:106 | .env.example:460 | PASS |
| `FORGE_BREAKOUT_FAILED_LOOKBACK_BARS` | .env:232 | scripts/sync_scalper_config_from_env.py:107 | .env.example:461 | PASS |
| `FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI` | .env:236 | scripts/sync_scalper_config_from_env.py:108 | .env.example:462 | PASS |
| `FORGE_BREAKOUT_FAILED_MIN_RSI_DROP` | .env:237 | scripts/sync_scalper_config_from_env.py:109 | .env.example:463 | PASS |
| `FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK` | .env:241 | scripts/sync_scalper_config_from_env.py:111 | .env.example:467 | PASS |
| `FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN` | .env:245 | scripts/sync_scalper_config_from_env.py:112 | .env.example:471 | PASS |
| `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD` | .env:247 | scripts/sync_scalper_config_from_env.py:114 | .env.example:317 | PASS |
| `FORGE_SESSION_NY_SELL_CUTOFF_UTC` | .env:255 | scripts/sync_scalper_config_from_env.py:191 | .env.example:621 | PASS |
| `FORGE_SESSION_LONDON_SELL_CUTOFF_UTC` | .env:256 | scripts/sync_scalper_config_from_env.py:192 | .env.example:623 | PASS |
| `FORGE_BREAKOUT_RSI_SELL_FLOOR` | .env:261 | scripts/sync_scalper_config_from_env.py:87 | .env.example:303 | PASS |
| `FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL` | .env:264 | scripts/sync_scalper_config_from_env.py:118 | .env.example:506 | PASS |
| `FORGE_BREAKOUT_M30_BEAR_ADX_MIN` | .env:265 | scripts/sync_scalper_config_from_env.py:122 | .env.example:508 | PASS |
| `FORGE_BREAKOUT_REQUIRE_MACD_SELL` | .env:266 | scripts/sync_scalper_config_from_env.py:124 | .env.example:512 | PASS |
| `FORGE_BREAKOUT_REQUIRE_MACD_BUY` | .env:268 | scripts/sync_scalper_config_from_env.py:125 | .env.example:514 | PASS |
| `FORGE_BREAKOUT_MACD_FAST` | .env:269 | scripts/sync_scalper_config_from_env.py:126 | .env.example:516 | PASS |
| `FORGE_BREAKOUT_MACD_SLOW` | .env:270 | scripts/sync_scalper_config_from_env.py:127 | .env.example:517 | PASS |
| `FORGE_BREAKOUT_MACD_SIGNAL` | .env:271 | scripts/sync_scalper_config_from_env.py:128 | .env.example:518 | PASS |
| `FORGE_BREAKOUT_ADX_LOT_USE_M15` | .env:273 | scripts/sync_scalper_config_from_env.py:263 | .env.example:522 | PASS |
| `FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD` | .env:274 | scripts/sync_scalper_config_from_env.py:259 | .env.example:524 | PASS |
| `FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD` | .env:275 | scripts/sync_scalper_config_from_env.py:260 | .env.example:526 | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID` | .env:279 | scripts/sync_scalper_config_from_env.py:261 | .env.example:528 | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH` | .env:280 | scripts/sync_scalper_config_from_env.py:262 | .env.example:530 | PASS |
| `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD` | .env:282 | scripts/sync_scalper_config_from_env.py:140 | .env.example:532 | PASS |
| `FORGE_BREAKOUT_RSI_BUY_CEIL` | .env:284 | scripts/sync_scalper_config_from_env.py:86 | .env.example:301 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_ENABLED` | .env:286 | scripts/sync_scalper_config_from_env.py:130 | .env.example:545 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT` | .env:287 | scripts/sync_scalper_config_from_env.py:131 | .env.example:547 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR` | .env:288 | scripts/sync_scalper_config_from_env.py:132 | .env.example:549 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS` | .env:289 | scripts/sync_scalper_config_from_env.py:133 | .env.example:551 | PASS |
| `FORGE_SELL_STOP_CONT_ENABLED` | .env:292 | scripts/sync_scalper_config_from_env.py:146 | .env.example:561 | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_ENABLED` | .env:297 | scripts/sync_scalper_config_from_env.py:160 | .env.example:577 | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_MIN_RSI` | .env:298 | scripts/sync_scalper_config_from_env.py:161 | .env.example:579 | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR` | .env:299 | scripts/sync_scalper_config_from_env.py:162 | .env.example:581 | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS` | .env:300 | scripts/sync_scalper_config_from_env.py:163 | .env.example:583 | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_SL_ATR_MULT` | .env:301 | scripts/sync_scalper_config_from_env.py:164 | .env.example:585 | PASS |
| `FORGE_SELL_STOP_CONT_ATR_MULT` | .env:302 | scripts/sync_scalper_config_from_env.py:147 | .env.example:563 | PASS |
| `FORGE_SELL_STOP_CONT_SL_ATR_MULT` | .env:307 | scripts/sync_scalper_config_from_env.py:148 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_BUY_SL_ATR_MULT` | .env:313 | scripts/sync_scalper_config_from_env.py:198 | .env.example:350 | PASS |
| `FORGE_BREAKOUT_BE_CUSHION_ATR_MULT` | .env:322 | scripts/sync_scalper_config_from_env.py:200 | .env.example:355 | PASS |
| `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED` | .env:328 | scripts/sync_scalper_config_from_env.py:202 | .env.example:360 | PASS |
| `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | .env:334 | scripts/sync_scalper_config_from_env.py:204 | .env.example:364 | PASS |
| `FORGE_BREAKOUT_ATR_TRAIL_MULT` | .env:335 | scripts/sync_scalper_config_from_env.py:205 | .env.example:365 | PASS |
| `FORGE_SELL_STOP_CONT_LOT_FACTOR` | .env:336 | scripts/sync_scalper_config_from_env.py:149 | .env.example:565 | PASS |
| `FORGE_SELL_STOP_CONT_LEGS` | .env:337 | scripts/sync_scalper_config_from_env.py:150 | missing from .env.example | PASS |
| `FORGE_SELL_STOP_CONT_EXPIRY_BARS` | .env:339 | scripts/sync_scalper_config_from_env.py:151 | .env.example:567 | PASS |
| `FORGE_SELL_STOP_CONT_TP_ATR_MULT` | .env:341 | scripts/sync_scalper_config_from_env.py:152 | .env.example:573 | PASS |
| `FORGE_SELL_STOP_CONT_MIN_RSI` | .env:342 | scripts/sync_scalper_config_from_env.py:153 | .env.example:569 | PASS |
| `FORGE_SELL_STOP_CONT_MIN_ADX` | .env:343 | scripts/sync_scalper_config_from_env.py:154 | missing from .env.example | PASS |
| `FORGE_SELL_STOP_CONT_REQUIRE_H1_DI` | .env:344 | scripts/sync_scalper_config_from_env.py:155 | missing from .env.example | PASS |
| `FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME` | .env:348 | scripts/sync_scalper_config_from_env.py:157 | .env.example:476 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_ENABLED` | .env:351 | scripts/sync_scalper_config_from_env.py:135 | .env.example:553 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_ATR_MULT` | .env:352 | scripts/sync_scalper_config_from_env.py:136 | .env.example:555 | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_LOT_FACTOR` | .env:353 | scripts/sync_scalper_config_from_env.py:137 | .env.example:557 | PASS |
| `FORGE_H4_RSI_GATE_ENABLED` | .env:358 | scripts/sync_scalper_config_from_env.py:168 | .env.example:592 | PASS |
| `FORGE_H4_RSI_SELL_MAX` | .env:359 | scripts/sync_scalper_config_from_env.py:169 | .env.example:594 | PASS |
| `FORGE_H4_RSI_BUY_MIN` | .env:360 | scripts/sync_scalper_config_from_env.py:170 | .env.example:596 | PASS |
| `FORGE_H4_ADX_GATE_ENABLED` | .env:363 | scripts/sync_scalper_config_from_env.py:172 | .env.example:598 | PASS |
| `FORGE_H4_ADX_MIN_SELL` | .env:364 | scripts/sync_scalper_config_from_env.py:173 | .env.example:600 | PASS |
| `FORGE_H4_ADX_MIN_BUY` | .env:365 | scripts/sync_scalper_config_from_env.py:174 | .env.example:602 | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL` | .env:366 | scripts/sync_scalper_config_from_env.py:88 | .env.example:339 | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_RSI_MIN` | .env:368 | scripts/sync_scalper_config_from_env.py:89 | .env.example:341 | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_ADX_MAX` | .env:370 | scripts/sync_scalper_config_from_env.py:142 | .env.example:343 | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX` | .env:374 | scripts/sync_scalper_config_from_env.py:143 | missing from .env.example | PASS |
| `FORGE_BREAKOUT_MIN_H1_BEAR_STRENGTH` | .env:376 | scripts/sync_scalper_config_from_env.py:144 | .env.example:345 | PASS |
| `FORGE_BOUNCE_ADX_MAX` | .env:378 | scripts/sync_scalper_config_from_env.py:194 | .env.example:260 | PASS |
| `FORGE_BOUNCE_LOT_FACTOR` | .env:380 | scripts/sync_scalper_config_from_env.py:195 | .env.example:265 | PASS |
| `FORGE_ADX_HYSTERESIS_ENABLED` | .env:386 | scripts/sync_scalper_config_from_env.py:36 | .env.example:607 | PASS |
| `FORGE_ADX_TREND_ENTER` | .env:387 | scripts/sync_scalper_config_from_env.py:55 | .env.example:611 | PASS |
| `FORGE_ADX_TREND_EXIT` | .env:388 | scripts/sync_scalper_config_from_env.py:56 | .env.example:613 | PASS |
| `FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER` | .env:389 | scripts/sync_scalper_config_from_env.py:37 | .env.example:609 | PASS |
| `FORGE_MIN_ENTRY_ATR` | .env:421 | scripts/sync_scalper_config_from_env.py:186 | .env.example:635 | PASS |
| `FORGE_MIN_DIRECTIONAL_BARS` | .env:424 | scripts/sync_scalper_config_from_env.py:189 | .env.example:641 | PASS |
| `FORGE_MIN_BODY_RATIO` | .env:426 | scripts/sync_scalper_config_from_env.py:188 | .env.example:639 | PASS |
| `FORGE_REQUIRE_BB_EXPANSION` | .env:428 | scripts/sync_scalper_config_from_env.py:190 | .env.example:643 | PASS |
| `FORGE_NEWS_FILTER_ENABLED` | .env:433 | scripts/sync_scalper_config_from_env.py:39 | .env.example:781 | PASS |
| `FORGE_NEWS_FILTER_CURRENCIES` | .env:434 | scripts/sync_scalper_config_from_env.py:40 | .env.example:783 | PASS |
| `FORGE_NEWS_FILTER_LOW_BEFORE` | .env:436 | scripts/sync_scalper_config_from_env.py:41 | .env.example:785 | PASS |
| `FORGE_NEWS_FILTER_LOW_AFTER` | .env:437 | scripts/sync_scalper_config_from_env.py:42 | .env.example:787 | PASS |
| `FORGE_NEWS_FILTER_MEDIUM_BEFORE` | .env:438 | scripts/sync_scalper_config_from_env.py:43 | .env.example:789 | PASS |
| `FORGE_NEWS_FILTER_MEDIUM_AFTER` | .env:439 | scripts/sync_scalper_config_from_env.py:44 | .env.example:791 | PASS |
| `FORGE_NEWS_FILTER_HIGH_BEFORE` | .env:440 | scripts/sync_scalper_config_from_env.py:45 | .env.example:793 | PASS |
| `FORGE_NEWS_FILTER_HIGH_AFTER` | .env:441 | scripts/sync_scalper_config_from_env.py:46 | .env.example:795 | PASS |
| `FORGE_NEWS_FILTER_SPECIAL` | .env:443 | scripts/sync_scalper_config_from_env.py:47 | .env.example:797 | PASS |
| `FORGE_NEWS_FILTER_HARD_FLOOR_MIN` | .env:445 | scripts/sync_scalper_config_from_env.py:48 | .env.example:799 | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_PCT` | .env:446 | scripts/sync_scalper_config_from_env.py:49 | .env.example:801 | PASS |
| `FORGE_NEWS_FILTER_BLOCK_PCT` | .env:447 | scripts/sync_scalper_config_from_env.py:50 | .env.example:803 | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_RSI_BUY` | .env:448 | scripts/sync_scalper_config_from_env.py:51 | .env.example:805 | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_RSI_SELL` | .env:449 | scripts/sync_scalper_config_from_env.py:52 | .env.example:807 | PASS |
| `FORGE_NEWS_FILTER_REFRESH_SEC` | .env:451 | scripts/sync_scalper_config_from_env.py:53 | .env.example:809 | PASS |
| `FORGE_NEWS_FILTER_APPLY_IN_TESTER` | .env:452 | scripts/sync_scalper_config_from_env.py:54 | .env.example:812 | PASS |
| `FORGE_DAILY_DIRECTION_GATE_ENABLED` | .env:453 | scripts/sync_scalper_config_from_env.py:213 | .env.example:375 | PASS |
| `FORGE_DAILY_CANCEL_PENDING_ON_FLIP` | .env:454 | scripts/sync_scalper_config_from_env.py:219 | .env.example:381 | PASS |
| `FORGE_REGIME_H1_OVERRIDE_FACTOR` | .env:456 | scripts/sync_scalper_config_from_env.py:247 | .env.example:426 | PASS |
| `FORGE_REGIME_H1_OVERRIDE_ADX_MIN` | .env:457 | scripts/sync_scalper_config_from_env.py:248 | .env.example:427 | PASS |
| `FORGE_DUMP_CATCH_ENABLED` | .env:458 | scripts/sync_scalper_config_from_env.py:222 | .env.example:404 | PASS |
| `FORGE_DUMP_REQUIRE_D1_BIAS` | .env:459 | scripts/sync_scalper_config_from_env.py:229 | .env.example:410 | PASS |
| `FORGE_DUMP_LOT_FACTOR` | .env:460 | scripts/sync_scalper_config_from_env.py:231 | .env.example:412 | PASS |
| `FORGE_DUMP_MIN_ADX` | .env:464 | scripts/sync_scalper_config_from_env.py:227 | .env.example:408 | PASS |
| `FORGE_DUMP_ATR_MULT` | .env:469 | scripts/sync_scalper_config_from_env.py:224 | .env.example:406 | PASS |
| `FORGE_DUMP_MAX_RSI` | .env:474 | scripts/sync_scalper_config_from_env.py:225 | .env.example:407 | PASS |
| `FORGE_DUMP_SELL_H1_MAX` | .env:478 | scripts/sync_scalper_config_from_env.py:234 | missing from .env.example | PASS |
| `FORGE_DUMP_BUY_LOT_FACTOR` | .env:482 | scripts/sync_scalper_config_from_env.py:232 | missing from .env.example | PASS |
| `FORGE_DUMP_SELL_LOT_FACTOR` | .env:483 | scripts/sync_scalper_config_from_env.py:233 | missing from .env.example | PASS |
| `FORGE_DUMP_MAX_RSI_BUY` | .env:488 | scripts/sync_scalper_config_from_env.py:226 | missing from .env.example | PASS |
| `FORGE_PULLBACK_SCALP_ENABLED` | .env:491 | scripts/sync_scalper_config_from_env.py:238 | .env.example:436 | PASS |
| `FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS` | .env:492 | scripts/sync_scalper_config_from_env.py:239 | .env.example:437 | PASS |
| `FORGE_PULLBACK_SCALP_LOT_FACTOR` | .env:493 | scripts/sync_scalper_config_from_env.py:240 | .env.example:438 | PASS |
| `FORGE_PULLBACK_SCALP_SL_ATR_MULT` | .env:494 | scripts/sync_scalper_config_from_env.py:241 | .env.example:439 | PASS |
| `FORGE_DUMP_REQUIRE_BAR_CONFIRM` | .env:500 | scripts/sync_scalper_config_from_env.py:236 | .env.example:455 | PASS |
| `FORGE_PULLBACK_SCALP_TP1_ATR_MULT` | .env:501 | scripts/sync_scalper_config_from_env.py:242 | .env.example:440 | PASS |
| `FORGE_PULLBACK_SCALP_TP2_ATR_MULT` | .env:502 | scripts/sync_scalper_config_from_env.py:243 | .env.example:441 | PASS |
| `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS` | .env:503 | scripts/sync_scalper_config_from_env.py:244 | .env.example:442 | PASS |
| `FORGE_PULLBACK_SCALP_MAX_ADX` | .env:504 | scripts/sync_scalper_config_from_env.py:245 | .env.example:443 | PASS |

Lowercase config-looking `.env` keys: none.

## Mandatory Check B — Gate legend completeness
**Status**: PASS

| Gate code | EA evidence | Legend / pattern | Status |
|---|---|---|---|
| `cooldown` | ea/FORGE.mq5:6375 | config/gate_legend.json:219 | PASS |
| `direction_cooldown` | ea/FORGE.mq5:7657 | config/gate_legend.json:229 | PASS |
| `dump_adx_block` | ea/FORGE.mq5:7531 | config/gate_legend.json:309 | PASS |
| `dump_bar_confirm_missing` | ea/FORGE.mq5:7498 | config/gate_legend.json:334 | PASS |
| `dump_chop_block` | ea/FORGE.mq5:7559 | config/gate_legend.json:329 | PASS |
| `dump_cooldown` | ea/FORGE.mq5:7551 | config/gate_legend.json:324 | PASS |
| `dump_d1_bias_block` | ea/FORGE.mq5:7543 | config/gate_legend.json:319 | PASS |
| `dump_h1_trend_block_sell` | ea/FORGE.mq5:7517 | config/gate_legend.json:304 | PASS |
| `dump_psar_block` | ea/FORGE.mq5:7537 | config/gate_legend.json:314 | PASS |
| `dump_rsi_block` | ea/FORGE.mq5:7524 | config/gate_legend.json:294 | PASS |
| `dump_rsi_buy_ceil` | ea/FORGE.mq5:7587 | config/gate_legend.json:299 | PASS |
| `entry_quality_adx_extreme_sell` | ea/FORGE.mq5:7165 | config/gate_legend.json:74 | PASS |
| `entry_quality_adx_min_sell` | ea/FORGE.mq5:7172 | config/gate_legend.json:69 | PASS |
| `entry_quality_adx_spike_sell` | ea/FORGE.mq5:7247 | config/gate_legend.json:79 | PASS |
| `entry_quality_atr` | ea/FORGE.mq5:6222 | config/gate_legend.json:34 | PASS |
| `entry_quality_atr_ext` | ea/FORGE.mq5:7721 | config/gate_legend.json:39 | PASS |
| `entry_quality_bb_contraction` | ea/FORGE.mq5:6280 | config/gate_legend.json:44 | PASS |
| `entry_quality_body` | ea/FORGE.mq5:6253 | config/gate_legend.json:29 | PASS |
| `entry_quality_breakout_cooldown` | ea/FORGE.mq5:7015 | config/gate_legend.json:124 | PASS |
| `entry_quality_breakout_failed` | ea/FORGE.mq5:7059 | config/gate_legend.json:129 | PASS |
| `entry_quality_breakout_failed_samebar` | ea/FORGE.mq5:7039 | config/gate_legend.json:134 | PASS |
| `entry_quality_daily_bear_block_buy` | ea/FORGE.mq5:6732 | config/gate_legend.json:284 | PASS |
| `entry_quality_daily_bull_block_sell` | ea/FORGE.mq5:6810 | config/gate_legend.json:289 | PASS |
| `entry_quality_direction` | ea/FORGE.mq5:6265 | config/gate_legend.json:19 | PASS |
| `entry_quality_direction_cap` | ea/FORGE.mq5:6214 | config/gate_legend.json:24 | PASS |
| `entry_quality_h1_di_buy` | ea/FORGE.mq5:6936 | config/gate_legend.json:104 | PASS |
| `entry_quality_h1_di_sell` | ea/FORGE.mq5:7193 | config/gate_legend.json:109 | PASS |
| `entry_quality_h1_macd_buy` | ea/FORGE.mq5:6997 | config/gate_legend.json:119 | PASS |
| `entry_quality_h1_macd_sell` | ea/FORGE.mq5:7322 | config/gate_legend.json:114 | PASS |
| `entry_quality_h4_adx_buy_blocked` | ea/FORGE.mq5:6979 | config/gate_legend.json:169 | PASS |
| `entry_quality_h4_adx_sell_blocked` | ea/FORGE.mq5:7370 | config/gate_legend.json:159 | PASS |
| `entry_quality_h4_rsi_buy_blocked` | ea/FORGE.mq5:6970 | config/gate_legend.json:164 | PASS |
| `entry_quality_h4_rsi_sell_blocked` | ea/FORGE.mq5:7358 | config/gate_legend.json:154 | PASS |
| `entry_quality_hid_bull_div_sell` | ea/FORGE.mq5:7281 | config/gate_legend.json:149 | PASS |
| `entry_quality_m30_not_bearish` | ea/FORGE.mq5:7344 | config/gate_legend.json:174 | PASS |
| `entry_quality_news_filter` | ea/FORGE.mq5:6202 | config/gate_legend.json:184 | PASS |
| `entry_quality_news_rsi_tighten` | ea/FORGE.mq5:6641 | config/gate_legend.json:189 | PASS |
| `entry_quality_psar_misalign_buy` | ea/FORGE.mq5:6771 | config/gate_legend.json:139 | PASS |
| `entry_quality_psar_misalign_sell` | ea/FORGE.mq5:6844 | config/gate_legend.json:144 | PASS |
| `entry_quality_rsi_buy_ceil` | ea/FORGE.mq5:6925 | config/gate_legend.json:49 | PASS |
| `entry_quality_rsi_rising_sell` | ea/FORGE.mq5:7265 | config/gate_legend.json:64 | PASS |
| `entry_quality_session_sell_cutoff` | ea/FORGE.mq5:7152 | config/gate_legend.json:179 | PASS |
| `execution_failed` | ea/FORGE.mq5:8050 | config/gate_legend.json:244 | PASS |
| `m1` | ea/FORGE.mq5:7668 | config/gate_legend.json:234 | PASS |
| `no_setup` | ea/FORGE.mq5:7702 | config/gate_legend.json:14 | PASS |
| `open_group_` | ea/FORGE.mq5:8743 | config/gate_legend.json:11 | PASS |
| `open_group_bad_stoplimit_price` | ea/FORGE.mq5:8866 | config/gate_legend.json:11 | PASS |
| `open_group_bad_stoplimit_trigger` | ea/FORGE.mq5:8861 | config/gate_legend.json:11 | PASS |
| `open_group_invalid_stops` | ea/FORGE.mq5:8800 | config/gate_legend.json:279 | PASS |
| `open_group_missing_stoplimit` | ea/FORGE.mq5:8855 | config/gate_legend.json:11 | PASS |
| `open_group_rr_below_floor` | ea/FORGE.mq5:8793 | config/gate_legend.json:274 | PASS |
| `open_group_unsupported_order_type` | ea/FORGE.mq5:8755 | config/gate_legend.json:11 | PASS |
| `open_groups` | ea/FORGE.mq5:6355 | config/gate_legend.json:194 | PASS |
| `post_sl_cooldown` | ea/FORGE.mq5:7661 | config/gate_legend.json:224 | PASS |
| `regime_countertrend` | ea/FORGE.mq5:7676 | config/gate_legend.json:239 | PASS |
| `rr_too_low` | ea/FORGE.mq5:7797 | config/gate_legend.json:214 | PASS |
| `session_off` | ea/FORGE.mq5:6320 | config/gate_legend.json:204 | PASS |
| `session_trade_cap` | ea/FORGE.mq5:6365 | config/gate_legend.json:199 | PASS |
| `spread` | ea/FORGE.mq5:6347 | config/gate_legend.json:209 | PASS |
| `warmup_` | ea/FORGE.mq5:6389 | config/gate_legend.json:10 | PASS |

## Issues Found (Consolidated)
1. FAIL — `ForgeEvalAtoms()` is not at the requested top-of-entry position. It runs after early native-scalper guard SKIPs and after `ScalperOnePerBar()` (ea/FORGE.mq5:6320-6407), so early SKIP rows can carry stale/zero atom telemetry.
2. WARNING — Group 3 comments still say 46 columns even though the code correctly lists and syncs 45 columns (ea/FORGE.mq5:5234,5550; python/scribe.py:170,705,1059,1170,1239).
3. WARNING — scribe’s v37 helper indexes are not created on a fresh table because `fs_cols` is captured before the additive column loop; tmp fresh init left `PRAGMA index_list(forge_signals)` empty for the v37 indexes (python/scribe.py:727-731).
4. WARNING — Gate legend test regex remains literal-only and misses dynamic gate sources such as `floor_gate` and `_qreason` (tests/api/test_forge_27x_gates.py:188; ea/FORGE.mq5:7229-7231,7296-7303).
5. WARNING — `docs/FORGE_ENTRY_CONDITIONS.md` remains stale relative to active v2.7.37 behavior; this was the known carryover doc-refresh item from v2.7.36.
6. WARNING — 13 active `FORGE_*` variables are mapped/whitelisted but absent from `.env.example`, so the cheat sheet is not fully synchronized with `.env`.

## Recommendations & Proposed Fixes
1. Move `ForgeEvalAtoms();` to immediately after indicator setup in `CheckNativeScalperSetups()` and before any guard that can call `JournalRecordSignal()`. Backward-compat flag: none needed; telemetry-only and idempotent.

```mql5
void CheckNativeScalperSetups() {
   EnsureIndicators();
   EnsureMTFIndicators();
   ForgeEvalAtoms();
   ...
}
```

2. Replace all “46 cols” comments with “45 cols”. Backward-compat flag: none, comment-only.
3. In scribe migration, refresh `fs_cols` after ALTER loops or always run `CREATE INDEX IF NOT EXISTS` unconditionally. Backward-compat flag: none; SQLite `IF NOT EXISTS` is safe.
4. Harden the gate legend regex test to include dynamic literal assignments or assert expected dynamic gate families explicitly. Backward-compat flag: none, test-only.
5. Refresh `docs/FORGE_ENTRY_CONDITIONS.md` from current `ea/FORGE.mq5` gates and active `config/scalper_config.json`. Backward-compat flag: none, docs-only.

## Overall Verdict
WARNING/FAIL. The 69-column v2.7.37 atom telemetry schema and scribe sync are present and tests pass, but the helper call-order contract is not satisfied: early SKIP rows can be recorded before `ForgeEvalAtoms()` runs for the tick.
