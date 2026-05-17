# FORGE Trade Conviction State Machine

**Shipped Phase 1**: 2026-05-13 (v2.7.75)
**Status**: Phase 1 = BUY-only state machine wired into BB_BREAKOUT BUY
**Author intent**: continuously-computed "trade quality meter" that pre-validates entries, replacing v2.7.74's tick-of-fire inline conviction check.

---

## Why this exists

v2.7.74 introduced inline conviction check at the BB_BREAKOUT BUY fire moment. It worked but had limits:
- **Single-tick snapshot** — one indicator briefly aligns then breaks, you get false positives
- **No visibility** — internal to fire path, you can't see "we're approaching HIGH conviction"
- **Binary** — either amplified (5 legs) or not (3 legs), no gradation
- **BUY-only and inline** — every setup would need its own conviction logic if we wanted SELL or MD_BUY amplification

v2.7.75 generalizes this into a **pre-computed state machine** that any setup can read.

---

## Concept summary

```
Every M5 tick:
  1. Compute weighted score for BUY direction (0-100, atoms with +/- weights)
  2. Compute weighted score for SELL direction (mirror)
  3. Update 5-bar ring buffer + running average
  4. Determine tier (LOW / EMERGING / HIGH / ULTRA) with hysteresis
  5. Expose to market_data.json for live visibility

When any setup fires:
  Read g_regime.trade_score.{buy|sell}_tier → size the trade accordingly
```

---

## Two designs explored

### Design A — Binary ConvictionState (initial proposal)

```mql5
struct ConvictionState {
    int    buy_score;            // 0-6 atoms aligned bullish this tick
    int    sell_score;           // 0-6 atoms aligned bearish (mirror)
    int    buy_high_bars;        // consecutive M5 bars where buy_score ≥ threshold
    int    sell_high_bars;       // same for SELL
    string buy_state;            // "LOW" / "EMERGING" / "HIGH" / "FADING"
    string sell_state;           // mirror
    datetime buy_entered_high_at;   // when we entered HIGH (for time-since-entry tracking)
    datetime sell_entered_high_at;
};

g_regime.conviction = ConvictionState{};
```

**State transitions**:

```
LOW state (default)
   │
   ▼ buy_score ≥ 4 for 1 bar
EMERGING (probe-allowed, no amplifier)
   │
   ▼ buy_score ≥ 4 for 3 consecutive bars
HIGH (full conviction — amplifier active, 5+ legs allowed)
   │
   ▼ buy_score drops below 4 for 1 bar
FADING (still allow open positions, no new amplifier fires)
   │
   ▼ buy_score < 4 for 2 consecutive bars
LOW
```

**Atoms** (6 atoms, count-based scoring 0-6):
- BOS direction == +1 → +1
- Signed velocity > 0 → +1
- (price − bb_upper) / ATR ≥ 0.5 → +1
- (price − VWAP) / ATR ≤ 1.5 → +1
- RSI ∈ [55, 70] → +1
- M15 ADX ≥ 20 → +1

**Trade-offs**: simpler scoring; coarse-grained binary tier; same setup behavior at HIGH regardless of how strongly atoms align.

### Design B — Weighted TradeScore (CHOSEN for Phase 1)

```mql5
struct TradeScore {
    int    buy_score;          // 0-100 (can go negative on bad atoms)
    int    sell_score;         // 0-100 (mirror)
    int    buy_score_5bar[5];  // ring buffer of last 5 M5 bar scores
    int    sell_score_5bar[5];
    int    buy_score_avg5;     // running average (smooths noise)
    int    sell_score_avg5;
    string buy_tier;           // "LOW" | "EMERGING" | "HIGH" | "ULTRA"
    string sell_tier;
    int    buy_tier_bars;      // consecutive bars at current tier (hysteresis)
    int    sell_tier_bars;
};

g_regime.trade_score = TradeScore{};
```

**BUY atoms with weights**:

| Atom | Condition | Weight | Rationale |
|---|---|---|---|
| BOS direction | == +1 (bullish break) | **+20** | Most important structural confirmation |
| Signed velocity | > 0 (climbing) | +10 | Direction continuation |
| Signed velocity | > +0.5×ATR (fast climb) | +10 bonus | Strong momentum |
| (price − bb_upper) / ATR | ≥ 0.5 (strong impulse) | +15 | True breakout vs fake touch |
| (price − VWAP) / ATR | ≤ 1.5 (within value) | +15 | Not overextended |
| (price − VWAP) / ATR | > 2.5 (overextended) | **−20** | Mean-reversion zone |
| RSI | ∈ [55, 72] (sweet spot) | +15 | Confirmed but not exhausted |
| RSI | > 72 (exhaustion) | **−15** | Second-leg trap zone |
| M15 ADX | ≥ 20 (M15 confirms) | +10 | Multi-TF alignment |
| macd_slope_5bar | > 0 (momentum positive) | +5 | Bonus alignment |

**Tier thresholds (with 2-bar hysteresis)**:

| Score range | Tier | Setup behavior (BB_BREAKOUT BUY) |
|---|---|---|
| ≤ 30 | **LOW** | Probe — 1 leg, tight TP1, narrow TP3 |
| 31-55 | **EMERGING** | Standard — 3 legs (default) |
| 56-75 | **HIGH** | Amplified — 5 legs, TP1 close 50%, TP3 5×ATR |
| 76-100 | **ULTRA** | Maximum — 7 legs, TP1 close 30%, TP3 7×ATR |

**SELL mirror** — same atom weights inverted:
- BOS = −1 → +20 (bearish break)
- Signed velocity < 0 → +10 (falling)
- (VWAP − price) / ATR ≤ 1.5 → +15 (within value below VWAP)
- RSI ∈ [28, 45] → +15 (sweet spot for shorts)
- RSI < 28 → −15 (exhaustion oversold)
- etc.

**Trade-offs vs Design A**: finer-grained sizing (4 tiers vs binary HIGH); accurate proportional response (ULTRA score means full deployment, HIGH means moderate); slightly more code but more useful behavior.

---

## Live visibility — `market_data.json`

```json
"entry_atoms": {
  "trade_score_buy": 67,
  "trade_score_buy_avg5": 62,
  "trade_score_buy_tier": "HIGH",
  "trade_score_buy_tier_bars": 4,
  "trade_score_buy_5bar": [45, 52, 58, 67, 67],
  "trade_score_sell": 12,
  "trade_score_sell_avg5": 15,
  "trade_score_sell_tier": "LOW"
}
```

ATHENA dashboard can render this as a live "BUY Strength: 67 (HIGH, 4 bars)" indicator. Operator can anticipate the next BB_BREAKOUT BUY fire confidently — "score rising toward HIGH, expect 5-leg deployment in next 5min."

---

## How setup triggers consume the tier

```mql5
// Universal setup wrapper:
switch (g_regime.trade_score.buy_tier) {
    case "ULTRA":    init_cap = 7;  tp1_pct = 30;  tp3_mult = 7.0;  break;
    case "HIGH":     init_cap = 5;  tp1_pct = 50;  tp3_mult = 5.0;  break;
    case "EMERGING": init_cap = 3;  tp1_pct = 70;  tp3_mult = 2.5;  break;
    case "LOW":      init_cap = 1;  tp1_pct = 90;  tp3_mult = 1.5;  break;
}
```

Every setup (BB_BREAKOUT BUY, MD_BUY, TC_BUY, etc.) reads the same tier — no per-setup duplication of conviction logic.

---

## Industry research (per operator memory rule: always Google MQL5+topic before designing)

The weighted-multi-atom + tiered-sizing pattern is industry-canonical for algorithmic scalping. Confirmed via WebSearch 2026-05-13:

### MQL5 multi-factor confidence scores
- **Nyao Scalper EA** uses confidence score 0.0-10.0 aggregating Trend + Momentum + Impulse + Volatility + Price Action. RSI "sweet spots," breakout detection, candle body momentum, ATR-based chop/trend classification, opposing wick penalty. [Source: nyao_scalper_mt5 GitHub](https://github.com/elrizwiraswara/nyao_scalper_mt5)
- **Machine Learning Supertrend (MQL5 article 72110)** writes Confidence Score 0-100 to a hidden 5th buffer. Components: regime grid cell confidence + RSI confirmation boost + volume surge boost + regime alignment boost. [Source: MQL5 article 72110](https://www.mql5.com/en/code/72110)

### Conviction × position sizing (algorithmic trading literature)
- "Conviction scores 0 to 100 are generated for each candidate, multiplying the composite quantitative score to promote high-conviction setups and demote low-conviction ones. Raw strategy signals are classified into a 5-tier system: Strong Buy, Buy, Neutral, Sell, Strong Sell." — [Position Sizing Strategies for Algo-Traders](https://medium.com/@jpolec_72972/position-sizing-strategies-for-algo-traders-a-comprehensive-guide-c9a8fc2443c8)
- "Base size factors vary by regime (1.8 in strong-trend, 2.5 in breakout, 0.7 in sideways, 0.8 in high-vol), with increases up to 30% when momentum scores higher than 70% of past values." — [International Trading Institute: Dynamic Position Sizing](https://internationaltradinginstitute.com/blog/dynamic-position-sizing-and-risk-management-in-volatile-markets/)

### Hysteresis / consecutive-bar pattern (canonical)
- "MovingFlatBreakout monitors the market for a flat state, detected as a predefined number of consecutive bars during which price fluctuates inside a small range." — confirms N-consecutive-bar state-detection pattern. [Source: MovingFlatBreakout](https://www.mql5.com/en/market/product/4685)
- "Stochastic with Noise Reduction reduces false signals using sensitivity tuning and threshold mechanism." — confirms multi-bar smoothing for noise rejection. [Source: Stochastic with Noise Reduction](https://www.mql5.com/en/code/9279)

### Drawdown / safety throttle pattern (informs future Phase 5+)
- "Three-tiered drawdown protocols: down 5% reduces risk 25%; down 10-15% reduces risk 50% + A-setups only; down >15% halts trading 24-72h." — pattern to apply on top of trade score when account equity decays. Phase 5+ idea.

**Citation in EA code comments**: When the conviction logic ships, file-line comments reference these sources so future analysts can trace the design lineage.

---

## Full implementation plan

### Phase 1 — BUY-only state machine + BB_BREAKOUT BUY (v2.7.75 — THIS SHIP)

**Components**:
1. `TradeScore` struct + global instance (~25 LOC)
2. Score computation in `ForgeEvalAtoms` — BUY atoms + weights (~50 LOC)
3. Tier transition with hysteresis — helper function `UpdateTradeScoreTier()` (~30 LOC)
4. `market_data.json` exposure (~10 LOC)
5. BB_BREAKOUT BUY trigger reads tier (replaces v2.7.74 inline check) (~15 LOC)
6. Sync mappings + `.env` knobs + gate legend entries (~15 LOC)

**New env knobs**:
- `FORGE_SCORE_BUY_TIER_LOW_MAX=30`
- `FORGE_SCORE_BUY_TIER_EMERGING_MAX=55`
- `FORGE_SCORE_BUY_TIER_HIGH_MAX=75`
- `FORGE_SCORE_BUY_TIER_HYSTERESIS_BARS=2`
- `FORGE_SCORE_BREAKOUT_BUY_ULTRA_LEGS=7` (was 5 in conviction)
- `FORGE_SCORE_BREAKOUT_BUY_HIGH_LEGS=5` (matches v2.7.74)
- `FORGE_SCORE_BREAKOUT_BUY_EMERGING_LEGS=3`
- `FORGE_SCORE_BREAKOUT_BUY_LOW_LEGS=1`

**Total**: ~145 LOC. Single ship.

**Validation**: next tester run — read live `trade_score_buy_tier` from market_data.json, confirm it rises during Apr 1 NY rally to HIGH/ULTRA. Cross-check setup leg counts against tier.

### Phase 2 — SELL mirror (v2.7.76)

Mirror score computation + tier logic for SELL direction. Wire into:
- BB_BREAKOUT SELL
- MOMENTUM_DUMP SELL
- NY_SESSION_BEARISH_BREAKOUT_SELL

**~80 LOC. Independent ship.**

### Phase 3 — Wire all setups to read tier (v2.7.77)

One-line changes per setup to consult `g_regime.trade_score.{dir}_tier`:
- MOMENTUM_DUMP BUY: amplify when tier ≥ HIGH
- TREND_CONTINUATION_BUY: require tier ≥ EMERGING
- BB_LOWER_REVERSION_BUY: require tier == EMERGING or LOW (mean-reversion needs counter-direction)
- FRACTIONAL_SELL_IN_BULL: require buy_tier ≥ HIGH (counter-trend probe only when bullish strong)

**~50 LOC. Independent ship.**

### Phase 4 — Score history persistence + ATHENA visibility (v2.7.78)

- Persist score + tier into SIGNALS table per signal (forensic)
- ATHENA dashboard widget: "BUY Strength" + "SELL Strength" gauges
- Score history chart (last 30 bars) in dashboard

**~30 LOC EA + frontend work. Independent ship.**

### Phase 5 — Dedicated `trade_conviction` section in `market_data.json` + killzone correlation (future)

**Operator directive (2026-05-13)**: trade score should live under a dedicated top-level
section in `market_data.json` and be correlated with killzone for analytical purposes.
Currently in v2.7.75 the fields live inside `entry_atoms` for shipping speed.

**Scope**:
1. Move `trade_score_buy*` fields from `entry_atoms` to a new top-level `trade_conviction` block
2. Add `killzone` and `minutes_into_kz` fields to that block (correlation data already in g_regime)
3. Add a `tier_history_5bar` parallel array next to score_5bar — tier value at each of last 5 bars
4. ATHENA/dashboard consumers read from `trade_conviction` directly

**Proposed JSON structure**:

```json
"trade_conviction": {
  "killzone": "NY_OPEN_KZ",
  "minutes_into_kz": 23,
  "buy": {
    "score": 67,
    "score_avg5": 62,
    "tier": "HIGH",
    "tier_bars": 4,
    "score_5bar": [45, 52, 58, 67, 67],
    "tier_5bar": ["EMERGING","EMERGING","HIGH","HIGH","HIGH"]
  },
  "sell": {
    "score": 12,
    "score_avg5": 15,
    "tier": "LOW",
    "tier_bars": 2,
    "score_5bar": [25, 22, 18, 15, 12],
    "tier_5bar": ["LOW","LOW","LOW","LOW","LOW"]
  }
}
```

**Why this matters**:
- Analyst can query `trade_conviction` directly without parsing all entry_atoms
- Killzone correlation enables future analysis like "buy_tier=HIGH during NY_OPEN_KZ = 78% win rate; during ASIAN_KZ = 41%"
- Tier history reveals trend direction (rising tier sequence vs oscillating)
- ATHENA dashboard can render a compact "Conviction Panel" widget by reading just this object

**Critical: score must compute in ALL sessions** (including those skipped for trading like ASIAN). This is already the case in v2.7.75 because `ForgeEvalAtoms()` runs at line 9119 BEFORE the session_off gate at line 9147. So the score updates every tick regardless of whether trades are allowed. This is preserved in Phase 5.

**Effort**: ~30 LOC EA (JSON restructure) + ~50 LOC ATHENA dashboard widget if added.

### Phase 6 — Account-equity safety throttle (future v2.7.80+)

Add an equity-drawdown overlay that throttles tier sizing when account is down:
- Equity down 5% from peak: clamp legs to ½ of tier value
- Equity down 10% from peak: clamp to ¼ + only ULTRA tier fires
- Equity down 15%+: halt new trades 24-72h

Based on the canonical [3-tiered drawdown protocol](https://medium.com/@jpolec_72972/position-sizing-strategies-for-algo-traders-a-comprehensive-guide-c9a8fc2443c8).

---

## Tradeoffs vs v2.7.74 inline check

| Aspect | v2.7.74 (inline) | v2.7.75 (state machine) |
|---|---|---|
| Latency | 0 (tick-of-fire) | 0 (pre-computed each tick) |
| Noise filter | None | 5-bar avg + 2-bar tier hysteresis |
| Visibility | None in JSON | Live score + tier + 5-bar history in JSON |
| Code reuse | BUY-only, inline at one site | Universal — any setup reads tier |
| Tier granularity | Binary (4-of-6 or not) | 4 tiers (LOW/EMERGING/HIGH/ULTRA) |
| SELL mirror | Manual to add per setup | Generic — mirror score auto-computed |
| Forensic logging | Atom count in log only | Full score + history in SIGNALS |
| Per-tier sizing nuance | Single boost (5 legs) | 1 / 3 / 5 / 7 legs by tier |

---

## What changes vs Design A (binary ConvictionState)

The binary ConvictionState (initial proposal) was simpler — count atoms 0-6, threshold ≥4 = HIGH. The Trade Score (chosen for ship) refines this:

| Aspect | Binary ConvictionState | Weighted TradeScore |
|---|---|---|
| Scoring | Count-based 0-6 | Weighted 0-100 with penalties |
| Penalties | Implicit (binary fail) | Explicit negative weights (e.g. −20 for VWAP overextended) |
| Tiers | 3 (LOW/EMERGING/HIGH) + FADING | 4 (LOW/EMERGING/HIGH/ULTRA) |
| Bad-setup signal | Atoms just fail to count | Atoms can ACTIVELY subtract — surfaces danger |
| Cross-day comparability | Atom count not informative | Score number directly comparable (67 > 45) |

The weighted approach is canonical for algorithmic trading (per industry research above). Adopted.

---

## EA implementation reference (post-ship)

| Component | File:line (post-v2.7.75) |
|---|---|
| `TradeScore` struct | EA struct definitions (search `struct TradeScore`) |
| `g_regime.trade_score` field declaration | `RegimeState` struct in FORGE.mq5 |
| Score computation | `ForgeEvalAtoms()` — new section after ICT atom block |
| Tier transition helper | `UpdateTradeScoreTier()` function |
| BB_BREAKOUT BUY consumer | Replaces v2.7.74 inline check at FORGE.mq5:12022+ |
| `market_data.json` exposure | `WriteMarketData()` entry_atoms block |
| Sync mappings | `scripts/sync_scalper_config_from_env.py` |

---

## Validation plan for next tester run

1. **Live visibility check** — read `market_data.json` while tester runs; confirm `trade_score_buy_tier` updates each M5 bar
2. **Pre-fire signal** — before any BB_BREAKOUT BUY fires, score should already be in EMERGING or HIGH tier
3. **Apr 1 NY rally** — score should climb from LOW (overnight) → EMERGING (08:30 pre-NY) → HIGH (NY open rally) → ULTRA on G5013 fire window
4. **Apr 2 morning crash** — buy_score should drop sharply (BOS=-1, falling velocity); sell_score should rise (Phase 2 will validate)
5. **Per-tier leg count** — TRADES table should show legs_planned varying with tier:
   - LOW: 1 leg
   - EMERGING: 3 legs
   - HIGH: 5 legs
   - ULTRA: 7 legs

---

## References

- Run 30 analysis: `docs/FORGE_RUN30_ANALYSIS.md`
- v2.7.74 inline conviction predecessor: `docs/FORGE_BB_BREAKOUT_BUY_AMPLIFICATION_v2.7.74.md`
- Indicator atlas: `docs/FORGE_INDICATOR_ATLAS.md` (atoms used in scoring)
- Setup playbook: `FORGE_SETUP_PLAYBOOK.md` §10 (boolean composite design pattern)
- Industry research citations: see Industry research section above

---

## How to test the state machine

### Tier 1 — Static code-trace validation (do BEFORE next tester run)

Walk through known Run 30 entries by hand and verify expected scores:

**Run 30 entry: G5004 +$354 (04/01 08:40 4700.70)**
- Atoms (Run 30 values): BOS=+1 (overnight rally → +20), velocity>0 (+10), bb_ext +2.64×ATR (+15), VWAP_dist 2.41 (no points — between 1.5 and 2.5), RSI 73.32 (>72 → −15), m15_adx 24.95 (+10), macd_slope −2.23 (no points)
- Expected score: **40**
- Expected tier: **EMERGING** (3 legs)

**Run 30 entry: G5005 −$1,694 (04/01 08:45 4702.29)**
- Atoms (Run 30 values): BOS=+1 (+20), velocity>0 (+10), bb_ext 0.30 (no points — below 0.5), VWAP_dist 2.76 (>2.5 → −20), RSI 74.54 (>72 → −15), m15_adx 26.39 (+10), macd_slope −2.12 (no points)
- Expected score: **5**
- Expected tier: **LOW** (1 leg — probe)

**Run 30 entry: G5013 +$985 (04/01 17:46 4753.70)**
- Atoms (Run 30 values): BOS=+1 (+20), velocity>0 (+10), bb_ext −0.02 (no), VWAP_dist 1.81 (no — between 1.5 and 2.5), RSI 59.01 (∈[55,72] → +15), m15_adx 21.19 (+10), macd_slope −1.01 (no)
- Expected score: **55**
- Expected tier: **EMERGING borderline → could be HIGH**

**Reality check**: weights give G5005 a LOW tier (5/100), so it would fire 1 leg instead of 3 — even less damage when it loses. G5004 lands at EMERGING (40, fires 3 legs) which is conservative — maybe should be HIGH. G5013 hits 55 (EMERGING borderline) — should arguably be HIGH given +$985 outcome.

**Adjustment candidates** based on this trace:
- VWAP_dist 1.5-2.5 zone should give SOME points (currently zero) — winners G5004/G5013 fall here
- macd_slope penalty needed (negative macd = trend lagging — currently no points awarded either way)
- Or simply lower tier thresholds: LOW ≤25, EMERGING ≤45, HIGH ≤65, ULTRA >65

### Tier 2 — Live JSON observation (during next tester run)

Read `market_data.json` continuously and watch:

```bash
watch -n 2 'python3 -c "
import json
md = json.load(open(\"/Users/olasumbo/Library/Application Support/.../market_data.json\"))
ea = md[\"entry_atoms\"]
print(f\"score={ea[\\\"trade_score_buy\\\"]} avg5={ea[\\\"trade_score_buy_avg5\\\"]} tier={ea[\\\"trade_score_buy_tier\\\"]} bars={ea[\\\"trade_score_buy_tier_bars\\\"]} 5bar={ea[\\\"trade_score_buy_5bar\\\"]}\")
"'
```

**Validate**:
- Score updates every tick (not just bar close — score itself is per-tick; ring buffer is per-bar)
- Avg5 lags real-time score (smoothing visible)
- Tier transitions happen ONLY on M5 bar close (not intra-bar)
- After tier change, `tier_bars` resets to 1, increments each subsequent bar
- During Apr 1 NY rally 13:30-17:46: score should rise from LOW → EMERGING → HIGH

### Tier 3 — Cross-run A/B comparison (the real test)

Run 31 (v2.7.75) on identical Mar 31 → Apr 13 sim period as Run 30 (v2.7.70). Compare:

| Metric | Run 30 | Run 31 (expected) |
|---|---|---|
| Total TAKEN | 15 (paused) | should be similar count |
| BB_BREAKOUT BUY leg distribution | All 3 legs (v2.7.74 amplifier disabled in paused run before tier was active) | Mix of 1/3/5/7 legs by tier |
| G5005 outcome | −$1,694 | LOW tier → 1 leg → −$300 ish (capped) |
| G5013 outcome | +$985 | HIGH/ULTRA tier → 5-7 legs → potentially +$1,500-2,500 |
| Net P&L (partial run to Apr 2) | +$304 | hoped +$1,500+ |

### Tier 4 — Forensic validation (post-run)

```sql
-- For every TAKEN BB_BREAKOUT BUY in Run 31, what tier was it?
-- (requires Phase 4 — score persistence in SIGNALS)
-- For now: cross-reference market_data.json snapshots with TAKEN timestamps

-- Win rate by tier:
SELECT tier, COUNT(*) deals, AVG(profit) avg_pnl, SUM(profit) net
FROM trades_with_tier
GROUP BY tier;
```

**Expected gradient**:
- ULTRA tier WR > 80%, avg_pnl > $300
- HIGH tier WR > 70%, avg_pnl > $200
- EMERGING tier WR > 55%, avg_pnl > $100
- LOW tier WR < 50%, avg_pnl < $50 (probe should rarely win)

If reality doesn't match this gradient → atom weights need tuning.

---

## Is this a great design? — honest assessment

### ✅ Strengths

1. **Industry-aligned pattern** — weighted multi-factor + tier classification is canonical (Nyao Scalper, ML Supertrend, algo-trading literature consensus)
2. **Decoupled** — state machine independent of setups; one source of truth
3. **Live visibility** — in `market_data.json`, operator can observe pre-fire
4. **Hysteresis** — 5-bar avg smooths the score; 2-bar persistence on tier prevents flicker
5. **Universal extensibility** — Phase 2 (SELL) and Phase 3 (other setups) are mechanical extensions
6. **Backward-compatible** — LOW tier = probe (1 leg), preserves conservative behavior when atoms misalign

### ⚠️ Honest weaknesses

1. **Weights are educated guesses** — derived from 4 trades, not statistically validated. The G5004 trace above shows my weights give it only 40 (EMERGING) when intuitively it deserved HIGH
2. **Tier thresholds are arbitrary** — 30/55/75 cutoffs are guesses, not optimized via gradient descent or grid search
3. **Negative weights can dominate** — −20 for VWAP overextended + −15 for RSI exhausted = −35, swamps positive atoms
4. **Score = right-now snapshot per tick** — no "is the score rising or falling?" signal (could add slope)
5. **No SELL mirror** — half the directional space is unscored (Phase 2)
6. **No SIGNALS persistence** — Q9 gate-precision analysis can't validate tier performance forensically until Phase 4
7. **5-bar warmup at run start** — first 25min of every tester run, ring buffer is empty (zeros); score is artificially low. Fine for backtest, but means first 5 bars have no useful tier
8. **No cross-direction consistency** — if BUY tier=HIGH and SELL tier=HIGH at same tick (contradiction), nothing flags it
9. **Per-tick recompute is expensive** — 1 CopyBuffer call to BB upper, 1 to RSI, 1 to M15 ADX every tick × ~1000 ticks/M5 bar = ~3000 buffer reads per bar. Likely fine on M5 but should profile
10. **Won't help on Mar 31 chop days** — atoms designed for trend; chop will keep score perpetually around 0-30 (LOW); BB_BREAKOUT will probe 1 leg = correct behavior actually

### 🟡 Real verdict

**Solid foundation, unproven specifics.** The pattern is right; the numbers need real-data tuning.

**What would make it GREAT** (Phase 4+ work):
1. Persist tier into SIGNALS (forensic gate-precision validation)
2. Run grid search across atom weights on Mar 31 → Apr 13 data: find weight combo maximizing per-tier P&L gradient
3. Add score slope (rising vs falling) as a derivative signal
4. Add consistency check (buy_tier + sell_tier shouldn't both be HIGH)
5. Profile compute cost — may need to cache buffer reads if profile shows hotspot

**Right move from here**: ship + observe + tune. Don't trust the weights until Run 31 data validates them.

---

## Nyao Scalper cheatsheet comparison (2026-05-13)

Reference: `/Users/olasumbo/Downloads/nyao_scalper.mq5` (4591 lines, production-grade scalper EA). Read in full to extract canonical patterns.

### What v2.7.75 ALREADY matches (validates direction)

| Pattern | Nyao | v2.7.75 |
|---|---|---|
| Multi-factor weighted score | ✅ 0-10 with 5 components | ✅ 0-100 with weighted atoms |
| Tier classification | ✅ `MinSignalScore 5.5` threshold | ✅ LOW/EMERGING/HIGH/ULTRA |
| Velocity tracking | ✅ score − prevScore | ⚠️ NOT computed (gap) |
| Cached per tick | ✅ `_buyStrengthValid` flag | ❌ recomputes (perf gap) |
| 5-bar smoothing | ✅ N-bar weighted (linear decay) | ⚠️ simple average (less responsive) |
| Threshold for lot increase | ✅ `MinSignalStrengthForLot=8.0` | ✅ tier→legs mapping |

### What Nyao does that v2.7.75 SHOULD adopt

**1. Component breakdown (5 components, not flat score)**
Nyao splits the score into TREND (0-3) + MOMENTUM (0-3) + CHOP (0-2) + PEAK (0-1) + VOLATILITY (0-1). Lets analyst see WHY a score is 6/10 — "trend 3, momentum 2.5, chop 0.5 = top in trend but choppy ATR." Currently FORGE has a flat 0-100 — can't distinguish "strong trend but weak momentum" from "average everywhere."

**2. Impulse detection (canonical formula)**
```mql5
double rawImpulse = (0.5 × bodyAccel + 0.3 × rangeAccel + 0.2 × continuity) / 2.0;
```
- `bodyAccel` = current candle body / avg-of-last-N bodies (capped 3.0)
- `rangeAccel` = current range / avg range (capped 3.0)
- `continuity` = consecutive same-direction candles / lookback
- Combined into 0-1 impulse strength, then `momentumScore *= (1 + ImpulseBoostWeight × impulse)`

This is much richer than my single signed velocity atom. Captures **acceleration** + **direction continuity** in one number.

**3. Wick rejection penalty**
```mql5
penaltyWick = (upperWick / safeBody) × WickRejectionWeight;
rawScore -= penaltyWick;
```
For BUY: upper wick is bad (sellers rejecting price). My v2.7.75 has no wick penalty — easy to add given FORGE already computes `g_eval_long_upper_wick`.

**4. N-bar weighted average with linear decay**
Nyao weights: `candle[1] = N`, `candle[2] = N−1`, ..., `candle[N] = 1`. Recent bars matter MORE. My simple 5-bar average treats all 5 bars equally — laggier.

```mql5
// Nyao approach
double weightedSum = 0, weightTotal = 0;
for (int i=1; i<=N; i++) {
    double weight = (double)(N - i + 1);
    weightedSum += score[i] * weight;
    weightTotal += weight;
}
double baseScore = weightedSum / weightTotal;
```

**5. Current-candle blend**
```mql5
double finalScore = baseScore × (1.0 − blend) + currentScore × blend;
```
With `blend=0.3`: 70% from smoothed history + 30% from live tick. Smooth but responsive. v2.7.75 only uses bar-close average (laggier).

**6. Velocity (score derivative)**
```mql5
double velocity = strength.finalScore - prevScore;            // signed: rising vs falling
double normalizedVelocity = (vel + window) / (2.0 × window);  // maps to 0-1
```
Critical signal: setup entering on SCORE RISING (gaining strength) >> entering on score FALLING (losing strength). My v2.7.75 has the 5-bar buffer but doesn't compute slope.

### Incremental upgrade roadmap (Nyao-inspired)

| Version | Scope | LOC | Result |
|---|---|---|---|
| **v2.7.76** | Adopt Nyao validations (highest value): velocity + normalized velocity + wick penalty + rising-only tier entry + reasoning string | ~80 | Big jump in score quality |
| **v2.7.77** | Component breakdown — split into TREND / MOMENTUM / CHOP / VOLATILITY / STRUCTURE; expose each in JSON | ~150 | Forensic visibility |
| **v2.7.78** | Impulse detection — bodyAccel + rangeAccel + continuity composite. Most expensive change but highest signal quality | ~120 | Better momentum capture |
| **v2.7.79+** | N-bar weighted decay + current-candle blend formula. Linear decay weights, 0.3 blend factor | ~60 | Smoother + more responsive |

### Is v2.7.75 a great design? — UPDATED answer with Nyao reference

**Yes for the architectural pattern, partial for the implementation.**

- ✅ State machine concept — Nyao validates it (4591 lines, production-grade EA uses it)
- ✅ Tier-based sizing — Nyao uses `MinSignalStrengthForLot=8.0` (matches our ULTRA threshold concept)
- ✅ Hysteresis approach — Nyao uses N-bar smoothing for the same noise-rejection goal
- ⚠️ Atom weights — ours are educated guesses; Nyao has each weight as a separate `input double` for tuning
- ⚠️ Missing velocity — Nyao computes signed score derivative; ours doesn't
- ⚠️ Flat score — Nyao breaks into components; ours doesn't
- ⚠️ Missing impulse/wick penalty — Nyao has both; ours doesn't

**Net**: v2.7.75 is a SOLID v1 implementation of an industry-validated pattern. Nyao gives us a roadmap for v2.7.76-79.

### Tuning approach (3 options)

1. **Ship v2.7.76 now** — adopt the highest-value Nyao patterns (velocity + wick penalty + rising-only tier entry). ~80 LOC, big jump in score quality.
2. **Ship v2.7.76 + v2.7.77** — also add component breakdown for forensic visibility. ~150 LOC.
3. **Hold v2.7.75 as-is, validate with Run 31 first** — see what the basic implementation does before refining. Lets data drive tuning rather than borrowing weights from a different EA. **(Recommended.)**

Reasoning for Option 3: Nyao's weights are tuned for Nyao's setups (which may differ from BB_BREAKOUT/MD/BLR), so cloning blind isn't optimal. Ship + observe → THEN iterate with informed weight changes.

---

## Changelog

- 2026-05-13 — v2.7.75 ships Phase 1: BUY-only TradeScore state machine + BB_BREAKOUT BUY consumer. Replaces v2.7.74 inline conviction check with cleaner pre-computed approach. Industry research validates pattern (Nyao Scalper, ML Supertrend, weighted multi-factor scoring).
- 2026-05-13 — Doc extended: testing plan (4-tier validation), honest design assessment (strengths + 10 weaknesses), Nyao Scalper comparison from `/Users/olasumbo/Downloads/nyao_scalper.mq5` cheatsheet (4591-line production EA), upgrade roadmap v2.7.76-v2.7.79.
- 2026-05-13 — **v2.7.76 SHIPPED**: score velocity gate. Run 31 G5005 loss diagnosed (avg5 fell 76→63 in 6min, amplifier deployed 5 legs and lost $2,934). Fix: cap tier at EMERGING when velocity ≤ -5. Aligns FORGE with Nyao Scalper canonical pattern.

## Run 31 diagnosis — score velocity is the missing piece

### Empirical evidence (sim Mar 31 → Apr 7, 15 TAKEN, net -$1,659)

**TRADE-SCORE log entries from MT5 log show the smoking gun**:

| Time | Setup | Tier | Score | Avg5 | Legs | Outcome |
|---|---|---|---|---|---|---|
| 04/01 08:40 G5004 | BB_BREAKOUT BUY | **ULTRA** | 40 | **76** | 7 | +$556 ✓ |
| 04/01 08:46 G5005 | BB_BREAKOUT BUY | **HIGH** | 20 | **63** | 5 | **−$2,934 ❌** |
| 04/01 17:46 G5013 | BB_BREAKOUT BUY | EMERGING | 50 | 35 | 3 | +$536 ✓ |

**Avg5 fell 76 → 63 between 08:40 and 08:46** — velocity = −13 (massive decay). But the 5-bar smoothing kept tier=HIGH, so amp deployed 5 legs into a fading wave.

### TC_BUY (separate loss, same pattern)

Run 31 also had TC_BUY at 04/06 17:36 @ 4693.33 RSI 63.3 → lost $1,152.

M5 price trail around fire time:
- 17:34 RSI 61.8 climbing
- **17:35:31 RSI 65.9** ← peak
- 17:36 RSI 63.3 ← TC_BUY fired 1 minute AFTER peak (RSI already declining)
- 17:40 RSI 55.0 ← reversal accelerating
- 17:45 SL hit

Same exhausting-rally pattern. TC_BUY doesn't currently consume the trade_score state (Phase 3+ extension), but the same velocity signal would catch it.

### Fix shipped in v2.7.76

```mql5
// In BB_BREAKOUT BUY conviction amplifier (FORGE.mq5:12035+):
if (g_sc.breakout_buy_score_velocity_check_enabled
    && (_bb_tier == "ULTRA" || _bb_tier == "HIGH")
    && g_regime.trade_score_buy_velocity <= g_sc.breakout_buy_score_velocity_threshold) {
    // Velocity ≤ -5 (avg5 fell 5+ from prior bar) → cap tier at EMERGING
    PrintFormat("FORGE 2.7.76 SCORE-VELOCITY-CAP: ...");
    _bb_tier = "EMERGING";
}
```

**Hypothetical replay on Run 31 G5005**:
- prev_avg5 = 76, avg5 = 63, velocity = −13
- velocity (−13) ≤ threshold (−5) → tier "HIGH" capped to "EMERGING"
- Legs deployed: 3 (was 5) → projected loss ≈ −$1,760 (vs actual −$2,934) = **saves $1,174**

**Backward compatibility**: ships behind `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK_ENABLED=1` (default ON). Set to 0 to revert to v2.7.75 behavior.

### Config knobs (v2.7.76)

| FORGE_* env var | Default | Effect |
|---|---|---|
| `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK_ENABLED` | `1` | Enable velocity cap |
| `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_THRESHOLD` | `-5` | Cap tier when velocity ≤ this |

### New JSON fields in market_data.json

```json
"entry_atoms": {
  ...existing trade_score_buy*...
  "trade_score_buy_velocity": -13,   // <0 = falling, >0 = rising
  "trade_score_buy_avg5_prev": 76    // previous bar's avg5 (for verification)
}
```

### What v2.7.76 does NOT do (Phase 3 / v2.7.77+)

- TC_BUY trigger doesn't consume trade_score yet (Run 31 04/06 TC_BUY loss unfixed)
- SELL mirror of trade_score not built (Phase 2)
- No score persistence in SIGNALS (Phase 4)

These remain in the roadmap from earlier in this doc.
