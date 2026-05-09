# FORGE Run 19 — Trend Scalp mode (implementation prompt)

**Reference analysis:** `docs/FORGE_RUN17_ANALYSIS.md` (Run 17, FORGE 2.7.3).

**Motivation from Run 17 (evidence-based):**

- **BUY** profit is strong but rally capture shows gaps when `rsi_buy_ceil` / `no_setup` dominate (Apr 30–May 1 in the Run 17 log).
- Dominant **BUY loss cluster** includes **G8** (BB_BREAKOUT BUY, multi-leg SL) — any loosening of stacking must **not** blindly repeat that regime.
- **SELL** side was improved with **`adx_min_sell`** etc.; **G7** documents **inside-band fractional lot** behavior. **Asymmetric** rules: trend stacking for **BUY** is the priority; **SELL** needs **extra bearish confirmation** before similar treatment.

This document is an **implementation spec**, not a guarantee of profitability.

---

## 1) Does this make mathematical and logical sense? (design review)

**What is sound:**

- **Conditional lift of `max_open_same_direction`** is **logically coherent** if and only if **effective exposure** is capped: three groups at **full** size ≈ **3×** risk versus one group. **Per-add-on lot multipliers** (or a hard notional cap) are **mathematically necessary**, not optional.
- **Separate `max_reentry_atr_ext` in trend mode** is **consistent** with pullback depth in trends vs chop: a **single** global `max_reentry_atr_ext` is a **distance constraint**, not a probability of win; widening it **increases** where re-entries are allowed — acceptable **only** while the **Trend Scalp gate** is true.
- **Directional cooldown after TP1** (e.g. **1 bar**) is **logically** a **time stagger**; it reduces **same-bar** pile-in. It does **not** by itself prevent **correlated** losses if the gate flips false late.
- **Trailing after TP1** (if implemented) **replaces fixed TP2–TP4** on *remaining* exposure: **logically** a **variance trade** (larger right tail, different left tail). It must be **explicitly** reconciled with existing **staged legs / MODIFY_TP** behavior to avoid **double management**.

**What needs care (avoid magical thinking):**

- The **four inputs** (H1 strength, M5 ADX, M5 RSI, BB width change) are **highly correlated** in real markets. **“All four true”** can still mean **late trend entries** — you are **not** independence-multiplying edge; you are **filtering**. **Backtest** is required.
- **BB width increasing bar-over-bar** is **noisy**. Without a **small hysteresis** (e.g. require **N of M** bars expanding, or min relative change ε), **mode** may **flicker** and churn `max_open` / re-entry limits.
- **`h1_trend_strength > 0.5`** is only meaningful **relative to how FORGE already defines** `h1_trend_strength` (see §3). Do **not** reinterpret the number in a second formula elsewhere.
- **`trend_scalp_m5_rsi_buy_max = 68`** vs **abort at 70** is a **narrow band**; logically fine as **“still room”** vs **“overbought exit”**, but it is **arbitrary** — treat defaults as **tunable**.
- **Option C (runner)** **compounds** management complexity. Prefer **config-gated** or **phase 2** unless the team accepts **merge risk** with the TP ladder.

**Bottom line:** The structure is **logically defensible** as a **gated risk expansion**, not as a **free edge**. **Math sanity** = enforce **exposure caps**, **avoid mode flicker**, and **prove with Run 19** vs baseline.

---

## 2) Feature spec — Option B first (Option C optional)

### 2.1 Combined “Trend Scalp” gate (BUY)

Activate **Trend Scalp** for **BUY** only when **all** of the following hold (evaluate on the **same M5 bar** as native scalper setup logic, using **completed** bars where applicable):

| # | Condition | Suggested config key | Default |
|---|-----------|----------------------|---------|
| 1 | **H1 bullish strength** | `trend_scalp_h1_strength_min` | `0.5` |
| 2 | **M5 ADX trend zone** | `trend_scalp_m5_adx_min` | `30` |
| 3 | **M5 RSI not at ceiling** | `trend_scalp_m5_rsi_buy_max` | `68` |
| 4 | **BB expanding** | `trend_scalp_bb_expand_bars` / `trend_scalp_bb_expand_epsilon` | define in code |

**Abort / drop out of mode** when any **fail** condition triggers (configurable), e.g. `m5_rsi >= trend_scalp_m5_rsi_buy_abort` (default `70`), **H1 no longer bullish**, **`m5_adx` below** exit threshold, or **BB expansion** fails **for K consecutive bars** (hysteresis).

**When ON (BUY):**

- **`effective_max_open_same_direction`** = `trend_scalp_max_open_same_direction` (default **`3`**) instead of baseline `max_open_same_direction` (default **`1`**).
- **`effective_max_reentry_atr_ext`** = `trend_scalp_max_reentry_atr_ext` (default **`3.0`**) instead of baseline `bb_breakout.max_reentry_atr_ext` (e.g. **`1.25`**).
- **`effective_direction_cooldown_bars`** = `trend_scalp_direction_cooldown_bars` (default **`1`**) after **TP1** events (define **detection** hook: group-level TP1 fill vs first partial close).
- **Stagger:** **G_n** at breakout; **G_{n+1}** only on **first qualifying pullback** (define **one** rule: e.g. first **M5 close** that dips to **touch / re-enter** band interior or **retest breakout level** — pick **one**, document, journal `stagger_ok` / skip reason).
- **Addon lot sizing:** new keys e.g. `trend_scalp_first_group_lot_mult`, `trend_scalp_addon_group_lot_mult` (or scale from existing auto-lot) — **must** prevent **3× full** exposure.

**When OFF:** revert all **effective\_\*** to **static config** defaults.

### 2.2 SELL asymmetry

- Default **`trend_scalp_sell_enabled`** = **`false`**.
- If enabled: require **mirror bearish** checks using **the same `h1_trend_strength` sign convention** as FORGE (negative = bear), **plus** existing SELL filters you trust (`adx_min_sell`, RSI floor logic, etc.).
- **Inside-band / weak-regime SELL:** keep **`sell_inside_band_lot_factor`** (or equivalent) as a **multiplier on base lot**: `final_lot = base_lot × factor` (e.g. `0.25` ⇒ quarter of base). **Do not** confuse multiplier with target lot.

### 2.3 Option C — Runner (secondary)

After **BB_BREAKOUT BUY** hits **TP1**, optional **smaller runner**: wide TP (e.g. **`8 × M5_ATR`**), **ATR trail**, only if **`h1_trend_strength > runner_h1_threshold`**. Gate with **`runner_mode_enabled`** default **`off`**. If not implementing in Run 19, add **config stubs + CHANGELOG “deferred”** only.

---

## 3) Internal routine — compute and track **every input point** (no hallucinated fields)

Implement a **single** function, e.g. **`UpdateTrendScalpTelemetry()`**, called **once per native scalper evaluation** (same cadence as `CheckNativeScalperSetups`), **before** gates consume “effective” limits.

### 3.1 Inputs (must match existing FORGE definitions)

Use **identical** series and bar indices as the current breakout path:

1. **`h1_trend_strength`** — already computed in native scalper block as  
   `(h1_ema20 - h1_ema50) / MathMax(h1_atr, point)` (see current `FORGE.mq5` — uses local `point`; do **not** invent a second formula).
2. **`m5_adx`** — same handle/buffer as existing breakout logic.
3. **`m5_rsi`** — same as existing breakout logic.
4. **BB upper/lower on M5** — same as existing; define width  
   `bb_width_cur = m5_bb_upper - m5_bb_lower` on bar **1** (last **completed**) vs **`bb_width_prev`** on bar **2** unless your code standard uses bar 0/1 differently — **document which bar index** you use and **stay consistent** with entry triggers.
5. **Baseline config** (non-effective):  
   `g_sc.max_open_same_direction`, `g_sc.breakout_max_reentry_atr_ext`, global / safety **`direction_cooldown_bars`** (whatever struct holds it today).

### 3.2 Per-evaluation derived booleans (store in globals or a small struct)

For **BUY**:

- `ts_g1 = (h1_trend_strength > +trend_scalp_h1_strength_min)`
- `ts_g2 = (m5_adx > trend_scalp_m5_adx_min)`
- `ts_g3 = (m5_rsi < trend_scalp_m5_rsi_buy_max)`
- `ts_g4 =` BB expansion rule (exact predicate in code)
- `ts_abort =` any fail rule (RSI >= abort, ADX < exit, etc.)

**Effective outputs** (these are what enforcement must read):

- `trend_scalp_active` = `ts_g1 && ts_g2 && ts_g3 && ts_g4 && !ts_abort` (final predicate as you define it)
- `effective_max_open_same_direction` = `trend_scalp_active ? trend_scalp_max_open_same_direction : g_sc.max_open_same_direction`
- `effective_max_reentry_atr_ext` = `trend_scalp_active ? trend_scalp_max_reentry_atr_ext : g_sc.breakout_max_reentry_atr_ext`
- `effective_direction_cooldown_bars` = … (only override **after TP1** if you implement that hook; else document **not applicable**)

### 3.3 Persistence / observability (at least one channel)

**Minimum (pick all that are cheap):**

1. **`mode_status.json`** — extend `WriteModeStatus()` with a nested object, e.g.  
   `trend_scalp: { "active": bool, "g1": … "g4": …, "h1_ts": …, "m5_adx": …, "m5_rsi": …, "bb_w": …, "bb_w_prev": …, "eff_max_open": …, "eff_reentry_atr": … }`  
   so **ATHENA / operators** can verify **live** without opening MT5 logs.
2. **`scalper_entry.json`** (optional) — only if you need per-entry snapshots; avoid bloating.
3. **Journal** — on **`trend_scalp_active` 0→1 and 1→0**, emit **one** row per transition with a dedicated **`gate_reason`** or `setup_type` convention **documented** in `docs/FORGE_JOURNAL_SQL.md` (e.g. `trend_scalp_enter` / `trend_scalp_exit` **only if** you add schema support; otherwise use **`PrintFormat`** with a **stable prefix** + **`mode_status`** as source of truth).

**Explicit non-goals:** Do **not** claim telemetry exists in `market_data.json` **unless** you actually add fields in `WriteMarketData()` and update **`docs/DATA_CONTRACT.md`**.

### 3.4 Enforcement wiring

- Replace **direct** reads of `g_sc.max_open_same_direction` in the direction-cap check with **`effective_max_open_same_direction`** **only after** telemetry runs.
- Replace **ATR re-entry** comparison with **`effective_max_reentry_atr_ext`**.
- **Cooldown**: if you implement TP1-based cooldown, **log both** the **canonical** cooldown counter and **`effective_direction_cooldown_bars`**.

---

## 4) Config / tooling / docs (required)

- `config/scalper_config.defaults.json` (+ generated `config/scalper_config.json` via `make scalper-env-sync`).
- `scripts/sync_scalper_config_from_env.py` — `FORGE_TREND_SCALP_*` mappings with **clamped** ranges.
- `VERSION` / `FORGE_VERSION`, `CHANGELOG.md`.
- `docs/FORGE_TRADING_RULES.md`, `docs/FORGE_JOURNAL_SQL.md` (if new journal labels), `docs/DATA_CONTRACT.md` **only** if file-bus JSON changes.
- `.env.example` comments.

---

## 5) Acceptance criteria

1. With **Trend Scalp disabled** or gate never true, behavior **matches** prior baseline on the same tester window (no accidental drift).
2. When gate **true**, **effective** max open / re-entry limits match **telemetry** in `mode_status.json` **on the same tick** as enforcement.
3. **No orphaned constants**: every threshold appears in **config** or **inputs**.
4. **SELL defaults** do **not** stack unless **`trend_scalp_sell_enabled`** is explicitly on and predicates are documented.

---

*Prompt version: 2026-05-08 — includes internal telemetry spec and explicit tie-in to current FORGE `h1_trend_strength` / `WriteModeStatus` / re-entry / max-open mechanisms.*
