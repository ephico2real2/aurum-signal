# FORGE 2.7.6 — Run 20 Analysis (Tester DB Agent-3000, run_id=1)
**Date:** 2026-05-09 | **Period:** Short range (Apr 29–TBD) | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** IN PROGRESS | **EA:** 2.7.6 | **Balance:** 10,000

---

## Key Changes vs Run 19 (2.7.5)

| Feature | Config | Purpose |
|---------|--------|---------|
| Native news filter | `news_filter_enabled: 1` | MT5 Calendar API — no SENTINEL dependency |
| Per-impact windows | LOW:5/5, MED:10/15, HIGH:20/30 | Separate before/after per impact level |
| Keyword overrides | `"Non-Farm:30,60+FOMC:40,45+CPI:50,55"` | Wider windows for major events |
| Sliding proximity | `tighten_pct:0.5, block_pct:0.85` | RSI tightens 70→65 BUY / 33→38 SELL near news |
| Hard floor | `hard_floor_min:5` | Absolute 5-min post-news block (chaos zone) |
| `ScalperMode = "DUAL"` | Input default changed | Tester auto-uses DUAL without manual override |
| `NewsFilterInputsOverride` | `input bool = false` | Input can override config JSON when set |
| `NewsFilterEnabled` | `input bool = true` | EA-level toggle, enabled by default |

**TESTER_RUNS confirmation:**
- `ea_version: 2.7.6` ✅
- `scalper_mode: DUAL` ✅
- `magic: 202401` ✅

---

## Gate Validation Targets

| Gate | journal reason | Expected |
|------|---------------|----------|
| News hard block | `entry_quality_news_filter` | Fires within news window at block_pct proximity |
| News RSI tighten | `entry_quality_news_rsi_tighten` | Fires when RSI exceeds tightened threshold near news |
| Existing gates | all prior reasons | Must continue firing correctly (no regression) |

---

## Monitoring Log

| Wall time | Sim time | Signals | TAKEN | Deals | W | L | P&L | Notes |
|-----------|----------|---------|-------|-------|---|---|-----|-------|
| 01:00 | Apr 29 05:38 | 100,761 | 0 | 0 | 0 | 0 | $0 | All session_off (overnight Asian); EA 2.7.6/DUAL confirmed ✅ |
| 01:08 | Apr 29 16:40 | 143,870 | 5 | 10 | 10 | 0 | **+$323.92** | **news_rsi_tighten: 3,319 fires ✅** at 15:55 UTC (BB_BREAKOUT SELL blocked RSI 26-27, floor tightened to 38); 5 TAKEN all SELL; 10W/0L |
| 01:16 | Apr 30 01:32 | 301,930 | 5 | 10 | 10 | 0 | **+$323.92** | **news_rsi_tighten 3,319→7,075** (+3,756 more fires across Apr 29 full session); overnight session_off; rr_too_low first fire; no hard news_filter block yet |
| 01:24 | Apr 30 08:00 | 440,594 | 5 | 10 | 10 | 0 | **+$323.92** | **news_rsi_tighten 7,075→9,573**; London open; ADX 42-62 high (no_setup); RSI 24-35 oversold; bb_contraction 695; Apr 29-30 crash phase — no new entries |
| 01:32 | Apr 30 16:25 | 455,036 | 6 | 13 | 13 | 0 | **+$468.32** | **G6(R20) BUY +$144.40** Apr30 16:07 4636.83 ADX23 RSI54.6 ✅; news_rsi_tighten flat (9,573) — filter ALLOWED correctly; body gate 3,413→10,352 (crash recovery dojis) |
| 01:40 | Apr 30 22:53 | 547,820 | 7 | 13W/**2L** | — | — | **+$312.56** | **G7(R20) SELL LOSS -$155.76** Apr30 19:20 4607.67 ADX28.8 RSI33.1 → SL 4617.12 (+9.45pts); no news window at 19:20 — filter ALLOWED (correct); cooldown fired |
| 01:48 | May 1 10:26 | 664,168 | 7 | 13W/2L | — | — | **+$312.56** | Run extended into May 1; overnight session_off + May 1 morning no_setup (ADX ranging); news_rsi_tighten flat at 9,573; no new entries |
| 01:57 | May 1 18:20 | 685,475 | 8 | 13W/**4L** | — | — | **+$178.24** | **G8(R20) SELL LOSS -$134.32** May1 12:55 4563.11 ADX33.3 RSI33.0 → SL 4571.21; news_rsi_tighten 9,573→9,775 (+202 May1 events); filter ALLOWED correctly (ALLOW zone at 12:55) |
| 02:05 | May 1 23:57 | 766,892 | 8 | 13W/4L | — | — | **+$178.24** | End-of-day session_off; no new trades; news_rsi_tighten flat at 9,775; hard news_filter 0; run nearing completion |
| 02:13 | May 4 04:32 | 842,972 | 8 | 13W/4L | — | — | **+$178.24** | Weekend jump (May 2-3) — all session_off; sim extended past May 1; May 4 London open ahead |

---

## News Filter Validation Log

| Sim time | Gate | Count | Notes |
|----------|------|-------|-------|
| Apr 29 15:55 | `entry_quality_news_rsi_tighten` | **3,319** | **✅ CONFIRMED** — BB_BREAKOUT SELL blocked; RSI 26-27 below tightened SELL floor (38 vs normal 33); news proximity active at 15:55 UTC; MT5 Calendar API working in tester |
| — | `entry_quality_news_filter` | 0 | Hard BLOCK not yet triggered (proximity in TIGHTEN zone, not BLOCK zone) |

---

*Last updated: 2026-05-09 CDT — Run 20 near-complete; 7 groups, 13W/2L, +$312.56; news_rsi_tighten 9,573 fires confirmed ✅; hard news_filter block not triggered in this date range*
