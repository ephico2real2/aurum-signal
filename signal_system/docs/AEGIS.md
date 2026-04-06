# AEGIS — risk gate decision logic

**AEGIS** (`python/aegis.py`) validates every trade **before** FORGE sees an `OPEN_GROUP`. BRIDGE calls `get_aegis().validate(signal, account, current_price)` for:

- AURUM-queued commands (`aurum_cmd.json` → `_dispatch_aurum_open_group`)
- Internal / scalper paths that build the same signal shape

If validation fails, BRIDGE logs a rejection (e.g. `TRADE_REJECTED · LOW_RR:1.04<1.2`) and does not write a FORGE command.

---

## 1. Signal shape AEGIS expects

| Field | Meaning |
|--------|---------|
| `direction` | `BUY` or `SELL` |
| `entry_low`, `entry_high` | Entry zone (may be equal for single price) |
| `sl` | Stop loss price |
| `tp1` | First take-profit price |

`account` (from MT5 / bridge context):

| Field | Meaning |
|--------|---------|
| `balance` | Account balance (required for sizing + loss cap) |
| `open_groups_count` | Open trade groups (SCRIBE/bridge) |

Optional **`current_price`**: used only for the **slippage** check (see §3).

---

## 2. Decision order (guards run in sequence)

AEGIS evaluates **Guards 1 → 6** in order. The **first** failure wins; later checks are skipped.

### Guard 1 — Completeness

- Reject **`INCOMPLETE_SIGNAL`** if any of: `direction`, `entry_low`, `sl`, `tp1`, or `balance` is missing/zero in a way that breaks validation.

### Guard 2 — Max open groups

- Reject **`MAX_GROUPS:{n}/{max}`** if `open_groups_count >= MAX_OPEN_GROUPS` (default **3**).

### Guard 3 — Session daily loss limit

- Computes **session P&L** since the last **trading-day boundary** (see §6).
- If session P&L is negative and `|session_pnl| >= balance * (MAX_DAILY_LOSS / 100)`, reject **`DAILY_LOSS_LIMIT:$…/$…`**.
- Default **MAX_DAILY_LOSS** = **5%** of balance.

### Guard 4 — Slippage (only if `current_price` is passed)

- **BUY:** `slippage = current_price - entry_high` (price “above” your zone).
- **SELL:** `slippage = entry_low - current_price`.
- If `slippage > MAX_SLIPPAGE` (default **20**), reject **`SLIPPAGE:{x}>{max}pips`**.

> Note: For XAUUSD these values are **price deltas in the same units as your quotes** (dollars), consistent with how BRIDGE passes the number.

### Guard 5 — Stop distance and direction sanity

Define **entry mid**:

```text
mid = (entry_low + entry_high) / 2
```

**Stop distance** (must be **positive**):

- **BUY:**  `sl_pips = mid - sl`  (SL below entry)
- **SELL:** `sl_pips = sl - mid`  (SL above entry)

- Reject **`INVALID_SL:SL_BEYOND_ENTRY`** if `sl_pips <= 0`.
- Reject **`SL_TOO_TIGHT:{x}pips`** if `sl_pips < 3` (minimum **3** price units).

### Guard 6 — Take-profit direction and risk–reward

**TP distance** (must be **positive**):

- **BUY:**  `tp_pips = tp1 - mid`  (TP above entry)
- **SELL:** `tp_pips = mid - tp1`  (TP below entry)

- Reject **`INVALID_TP1:TP_BEYOND_ENTRY`** if `tp_pips <= 0`.

**Risk–reward ratio:**

```text
R:R = tp_pips / sl_pips
```

- Reject **`LOW_RR:{rr}<{MIN_RR}`** if `R:R < MIN_RR` (default **1.2**).

---

## 3. After approval: lot size and ladder

If all guards pass:

1. **Scale factor** from recent closed trades (§5): normal, reduced after consecutive losses, or increased after consecutive wins.
2. **Effective risk %** = `RISK_PCT * scale_factor` (capped by scaling logic; wins can scale up toward `MAX_RISK_PCT`).
3. **Lot per trade** (approximate intent in code):

   ```text
   risk_amount = balance * (effective_risk_pct / 100)
   lot_per_trade = risk_amount / (NUM_TRADES * sl_pips * PIP_VALUE_PER_LOT)
   ```

   then clamped to at least **MIN_LOT** (0.01) and so that `lot_per_trade * NUM_TRADES <= MAX_LOT_TOTAL`.

4. **`PIP_VALUE_PER_LOT`** is fixed at **100.0** in code (XAUUSD assumption: **$100 per 1.0 lot per $1.00 adverse move** in the simplified model — align your mental model with your broker’s contract specs).

5. **Entry ladder**: if `entry_high > entry_low` and `NUM_TRADES > 1`, entries are spaced linearly between low and high; otherwise the ladder repeats `entry_low`.

---

## 4. Rejection codes (Activity / logs)

| Reason prefix | Meaning |
|----------------|---------|
| `INCOMPLETE_SIGNAL` | Missing/invalid fields |
| `INVALID_DIRECTION` | Not BUY/SELL |
| `MAX_GROUPS` | Too many open groups |
| `DAILY_LOSS_LIMIT` | Session loss exceeded % of balance |
| `SLIPPAGE` | Current price too far vs entry zone |
| `INVALID_SL` | SL on wrong side of mid |
| `SL_TOO_TIGHT` | SL closer than 3 price units |
| `INVALID_TP1` | TP1 on wrong side of mid |
| `LOW_RR` | R:R below `MIN_RR` |

---

## 5. Gradual lot scaling (recent closes)

Reads the most recent closed positions from SCRIBE (`trade_positions`, `status='CLOSED'`, ordered by `close_time`).

- If **≥ `AEGIS_SCALE_DOWN_LOSSES`** (default **3**) consecutive **negative** P&L closes → scale factor = **`AEGIS_SCALE_DOWN_FACTOR`** (default **0.5**).
- Else if **≥ `AEGIS_SCALE_UP_WINS`** (default **3**) consecutive **positive** closes → scale factor up, capped (see code: `min(MAX_RISK_PCT / RISK_PCT, 1.5)`).
- Else → factor **1.0** (`NORMAL`).

This only changes **risk % used for sizing**, not the R:R or SL guards.

---

## 6. Session P&L window (daily loss guard)

Session start = **today at `trading_day_reset_hour_utc():00` UTC**, or **yesterday** if current time is still before that hour.

- **`AEGIS_SESSION_RESET_HOUR`** (optional, `0`–`23`): if set, defines that UTC hour.
- If unset, uses **`SESSION_LONDON_START`** (default **8**) — same idea as kill-zone config in `trading_session.py`.

Closed trades with `close_time >= session_start` are summed for the **DAILY_LOSS_LIMIT** check.

---

## 7. Environment variables (complete list)

Set these in **repo root `.env`** (or the environment of **bridge** / launchd plist). After changes, **restart BRIDGE** (or `make restart`) so the process reloads env.

| Variable | Default | Role |
|----------|---------|------|
| `AEGIS_RISK_PCT` | `2.0` | Base risk % of balance for sizing |
| `AEGIS_MAX_RISK_PCT` | `5.0` | Ceiling used when scaling **up** after wins |
| `AEGIS_NUM_TRADES` | `8` | Trades in the group ladder; divisor in lot formula |
| `AEGIS_MAX_SLIPPAGE` | `20.0` | Max allowed slippage vs entry zone |
| `AEGIS_MIN_RR` | `1.2` | Minimum **tp_pips / sl_pips** |
| `AEGIS_MAX_DAILY_LOSS` | `5.0` | Max session loss as **% of balance** |
| `AEGIS_MAX_OPEN_GROUPS` | `3` | Max concurrent open groups |
| `AEGIS_MAX_LOT_TOTAL` | `5.0` | Cap on `lot_per_trade * NUM_TRADES` |
| `AEGIS_SCALE_DOWN_LOSSES` | `3` | Consecutive losses to halve (by default) risk |
| `AEGIS_SCALE_UP_WINS` | `3` | Consecutive wins to scale risk up |
| `AEGIS_SCALE_DOWN_FACTOR` | `0.5` | Multiplier on `RISK_PCT` when scaled down |
| `AEGIS_SESSION_RESET_HOUR` | *(unset)* | UTC hour for session P&L window; else `SESSION_LONDON_START` |

### New guards (v1.2.4+)

| Variable | Default | Role |
|----------|---------|------|
| `AEGIS_MIN_LOT` | `0.01` | Minimum lot per trade |
| `AEGIS_PIP_VALUE_PER_LOT` | `100.0` | Pip value per standard lot (XAUUSD) |
| `AEGIS_MIN_SL_PIPS` | `3.0` | Minimum SL distance in price units |
| `AEGIS_H1_TREND_FILTER` | `true` | Multi-TF trend cascade (M5→M15→H1 for SIGNAL, H1→M15 for AURUM) |
| `AEGIS_H1_FLAT_THRESHOLD` | `1.0` | EMA20-EMA50 diff below this = FLAT (either direction OK) |
| `DD_FLOATING_BLOCK_PCT` | `2.0` | Block new groups if floating loss ≥ this % of balance |
| `DD_EQUITY_CLOSE_ALL_PCT` | `3.0` | CLOSE ALL + WATCH if equity drops this % from session peak |
| `DD_LOSS_COOLDOWN_SEC` | `300` | AUTO_SCALPER pauses this long after a losing close |

### Lot sizing mode

| `AEGIS_LOT_MODE` | Behaviour |
|---|---|
| `fixed` (default) | Uses the source's `lot_per_trade` directly (e.g. `SIGNAL_LOT_SIZE`, `AUTO_SCALPER_LOT_SIZE`, AURUM JSON). Capped by `MAX_LOT_TOTAL`. |
| `risk_based` | Computes lot dynamically: `(balance × risk% × scale_factor) / (num_trades × SL_pips × PIP_VALUE_PER_LOT)`. Ignores source lot_per_trade. |

Risk-based computation always runs internally for logging (`total_risk` in approval). The toggle only controls which value goes to FORGE.

### Per-signal overrides

- `num_trades` or `trades` in the signal/command — overrides `AEGIS_NUM_TRADES` (clamped 1–20)
- `lot_per_trade` from any source — used when `AEGIS_LOT_MODE=fixed` (still capped by MAX_LOT_TOTAL)

---

## 8. Tuning for your risk and style

### Tighter / more selective

- **Raise** `AEGIS_MIN_RR` (e.g. **1.5**–**2.0**) — fewer marginal setups pass.
- **Lower** `AEGIS_MAX_DAILY_LOSS` or **`AEGIS_MAX_OPEN_GROUPS`** — stricter capital exposure.
- **Lower** `AEGIS_MAX_SLIPPAGE` — stricter entry vs market.

### More permissive (e.g. demo learning)

- **Lower** `AEGIS_MIN_RR` slightly (e.g. **1.0**–**1.15**) — same logic as live, but allows smaller R:R (use with care).
- **Raise** `AEGIS_MAX_OPEN_GROUPS` if you run multiple strategies (watch total exposure).

### Scalping vs wider swings

- **Scalping** often hits **`SL_TOO_TIGHT`** or **`LOW_RR`** if TP1 is too close; either widen TP1 (or SL within structure) so **`R:R ≥ MIN_RR`** and **`sl_pips ≥ 3`**, or lower **`AEGIS_MIN_RR`** only if you accept the edge trade-off.
- **Wider SL/TP** increases **dollar risk per pip**; lot sizing will shrink if risk % is fixed — that is intentional.

### AURUM / manual `OPEN_GROUP`

Teach the model to pre-check the formulas in **§2 Guard 5–6** (see **SKILL.md** and prompts). AEGIS does not read “demo”; for different demo vs live **numeric** policy, use **separate `.env` profiles** or different machines — there is no `DEMO` branch in AEGIS today.

---

## 9. Code references

- Implementation: `python/aegis.py`
- Call sites: `python/bridge.py` (`validate` on signals)
- Session boundary: `python/trading_session.py` → `trading_day_reset_hour_utc()`
- Heartbeat / component card: `status_report.report_component_status("AEGIS", ...)`

---

## 10. Related docs

- [OPERATIONS.md](OPERATIONS.md) — restart services after `.env` changes  
- [SETUP.md](SETUP.md) — first-time env and services  
- [SKILL.md](../SKILL.md) (repo root) — AURUM must emit SL/TP that satisfy these gates  
