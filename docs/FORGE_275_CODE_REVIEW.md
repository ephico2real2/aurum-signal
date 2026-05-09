# FORGE 2.7.4 / 2.7.5 — Code Review
**Date:** 2026-05-08 | **Reviewer:** Codex (automated) | **Status:** REVIEWED

---

## Overall Verdict

**No CRITICAL or HIGH bugs. One LOW-severity risk in the H1 DI read path — fixed in same session.**

---

## Summary Table

| # | Checklist item | Result |
|---|----------------|--------|
| 1 | DI+/DI- buffer indices (buffer 0=ADX, 1=DI+, 2=DI-) | ✅ PASS |
| 2 | `h1_di_buy` gate flow / brace matching | ✅ PASS |
| 3 | SELL gate sequencing (`adx_dur_ok` guards `rsi_decl_ok`) | ✅ PASS |
| 4 | `breakout_rsi_decl_sell_adx_threshold` separation | ✅ PASS |
| 5 | `g_scalper_prev_session_blocked` set on both paths | ✅ PASS |
| 6 | CopyBuffer invalid-handle / zero-value risk (DI reads) | ⚠️ LOW — **FIXED** |
| 7 | Bar shift off-by-one in new CopyBuffer calls | ✅ PASS |

---

## Findings

### 1. DI+/DI- Buffer Indices — PASS (externally verified)

**Online research confirmed** via MQL5 official docs, `ENUM_ADX_LINE` constants, and community articles:

| Buffer | Index | ENUM constant | Value |
|--------|-------|---------------|-------|
| ADX main line | 0 | `MAIN_LINE` | trend strength |
| **DI+ (Plus DI)** | **1** | `PLUSDI_LINE` | upward force |
| **DI- (Minus DI)** | **2** | `MINUSDI_LINE` | downward force |

Official MQL5 reference pattern:
```mql5
CopyBuffer(adx_handle, 0, 0, 3, adx_buf);  // ADX main
CopyBuffer(adx_handle, 1, 0, 3, dip_buf);  // DI+  ← buffer 1
CopyBuffer(adx_handle, 2, 0, 3, dim_buf);  // DI-  ← buffer 2
```

FORGE implementation:
```mql5
h1_di_read_ok = (CopyBuffer(g_h_adx, 1, h1_bias_shift, 1, buf)==1);  // DI+
if(h1_di_read_ok) h1_di_plus = buf[0];
h1_di_read_ok = (CopyBuffer(g_h_adx, 2, h1_bias_shift, 1, buf)==1);  // DI-
if(h1_di_read_ok) h1_di_minus = buf[0];
```

Indices match the spec. No platform-level DI swap bug exists. `ArraySetAsSeries` is irrelevant here — reading `count=1` into a 1-element array, so `buf[0]` is always the single value regardless of series flag. ✅

**Note:** `g_h_adx = iADX(_Symbol, PERIOD_H1, 14)` uses EMA smoothing (standard ADX, not Wilder SMMA). Both `iADX` and `iADXWilder` share identical buffer indices — only the smoothing method differs. Either is valid for DI directional gating.

---

### 2. `h1_di_buy` Gate Flow / Brace Matching — PASS

Gate pattern (BUY breakout path):
```mql5
bool h1_di_ok = true;
if(g_sc.breakout_require_h1_di_buy && m5_adx < g_sc.breakout_counter_buy_adx_threshold) {
    if(h1_di_plus <= h1_di_minus) {
        // journal SKIP, h1_di_ok = false
    }
}
if(!h1_di_ok) { /* blocked */ } else {
    direction = "BUY";
    ...
} // end h1_di_ok block
```
The `else` branch is the only path setting `direction="BUY"`. Brace depth balanced. ✅

---

### 3. SELL Gate Sequencing — PASS

`adx_dur_ok` is evaluated first. `rsi_decl_ok` is only evaluated inside the body guarded by `adx_dur_ok && g_sc.breakout_require_rsi_declining_sell`. No path checks `rsi_decl_ok` without `adx_dur_ok` being true. ✅

---

### 4. `breakout_rsi_decl_sell_adx_threshold` Separation — PASS

All uses of `breakout_rsi_decl_sell_adx_threshold` (value 28) are confined to the `rsi_rising_sell` gate condition. The two-tier RSI floor check consistently uses `breakout_adx_sell_floor_threshold` (value 35). Not cross-contaminated. ✅

---

### 5. Session-Start Log State — PASS

Both paths update `g_scalper_prev_session_blocked`:
- `session_blocked = true` path: flag set to `true` before `return`
- `session_blocked = false` path: log fires, flag set to `false`

State is always updated. ✅

---

### 6. CopyBuffer Invalid-Handle Risk — ⚠️ LOW — FIXED

**Original issue:** If `CopyBuffer` fails (invalid handle, insufficient bars during warmup), `h1_di_plus` and `h1_di_minus` default to `0.0`. Gate evaluates `0.0 <= 0.0` → `h1_di_ok = false`, falsely blocking all BUY entries.

**When this occurs:**
- Strategy tester warmup (first H1 bars before indicator is primed)
- Broker reconnect events
- Any tick before the ADX handle has 2+ H1 bars of history

**Fix applied:** Changed inline ternary reads to CopyBuffer-guarded block that defaults to `h1_di_ok = true` on failure:
```mql5
// Before (vulnerable):
double h1_di_plus  = (CopyBuffer(g_h_adx, 1, h1_bias_shift, 1, buf)==1) ? buf[0] : 0.0;
double h1_di_minus = (CopyBuffer(g_h_adx, 2, h1_bias_shift, 1, buf)==1) ? buf[0] : 0.0;
// ... later: if(h1_di_plus <= h1_di_minus)  ← false-blocks on 0.0==0.0

// After (safe):
// DI read happens inside the gate block; on failure h1_di_ok stays true (no block)
double h1_di_p = 0.0, h1_di_m = 0.0;
bool di_read_ok = (CopyBuffer(g_h_adx, 1, h1_bias_shift, 1, buf)==1);
if(di_read_ok) h1_di_p = buf[0];
di_read_ok = di_read_ok && (CopyBuffer(g_h_adx, 2, h1_bias_shift, 1, buf)==1);
if(di_read_ok) h1_di_m = buf[0];
if(di_read_ok && h1_di_p <= h1_di_m) { /* block */ }
```

**Note:** The same 0.0-default vulnerability exists in other existing H1 reads (e.g. `h1_ema20`, `h1_ema50`) — this is a systemic LOW risk in the codebase, not introduced by 2.7.5. The fix applied here is more defensive than the existing pattern.

---

### 7. Bar Shift Off-by-One — PASS

New DI reads use `h1_bias_shift` (0 in tester, 1 in live) — identical to all other H1 reads in `CheckNativeScalperSetups()`. The `adx_spike_sell` 6-bar lookback uses offset=6 in `CopyBuffer(..., 6, 1, buf)` — reads the single bar at position 6 (30 min ago). Zero-based, correct. ✅

---

## Risks and Edge Cases

| Risk | Severity | Status |
|------|----------|--------|
| CopyBuffer false-block during warmup (DI reads) | LOW | **Fixed in 2.7.5** |
| `bounce_adx_max` 50→40 silently blocks ADX 40-50 bounces | INFO | Intentional — monitor in Run 18 |
| `rsi_rising_sell` may block G17/G18/G19-class wins (RSI recovering from extreme low) | INFO | Mitigated by `rsi_decl_sell_adx_threshold=28` (auto-off at ADX≥28) |

---

## Recommendations Applied

1. ✅ Added CopyBuffer return-value check for DI reads — fail-safe to `h1_di_ok = true` (no false-block)
2. ✅ No other code changes required

---

*Review generated by Codex automated pass. Fixed immediately per findings. EA recompiled as FORGE 2.7.5.*
