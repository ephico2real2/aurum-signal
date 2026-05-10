# XAUUSD / Gold Pip Calculation in MetaTrader 5

## Key Facts

### SYMBOL_POINT vs pip for XAUUSD

| Property | Value | Notes |
|---|---|---|
| `SYMBOL_POINT` (MT5) | `0.01` | Smallest price increment, 2-decimal quote |
| `SYMBOL_DIGITS` (MT5) | `2` | Prices quoted as `####.##` (e.g. `2347.55`) |
| `SYMBOL_TRADE_TICK_SIZE` | `0.01` | Same as SYMBOL_POINT for gold |
| **1 pip = 1 point** | `0.01` USD | Unlike FX majors where 1 pip = 10 points |
| Contract size | `100 oz` | 1 standard lot = 100 troy ounces |

**Critical distinction from FX:** For EURUSD (5-digit broker), `SYMBOL_POINT = 0.00001`
and `1 pip = 0.0001 = 10 points`. For XAUUSD (2-digit broker), `SYMBOL_POINT = 0.01`
and `1 pip = 0.01 = 1 point`. There is no multiplier gap for gold.

### Pip Value Formula

```
pip_value_usd = lot_size × contract_size × pip_size × pips
              = lot_size × 100 oz × $0.01/oz × pips
              = lot_size × 1.0 × pips
```

So for XAUUSD: `pip_value_usd = lot_size × pips` (factor = 1.0).

### Practical Examples

| Entry | Exit | Direction | Pips | Formula |
|---|---|---|---|---|
| 4700.00 | 4710.00 | BUY | +1000 | (4710 - 4700) / 0.01 = 1000 |
| 4700.00 | 4710.00 | SELL | -1000 | -(4710 - 4700) / 0.01 = -1000 |
| 2347.55 | 2350.05 | BUY | +250 | (2350.05 - 2347.55) / 0.01 = 250 |

### Pip Value in USD by Lot Size

| Lot Size | Oz Traded | 1 pip move ($0.01) | Example: 250 pips |
|---|---|---|---|
| 0.01 | 1 oz | $0.01 | $2.50 |
| 0.08 | 8 oz | $0.08 | $20.00 |
| 0.10 | 10 oz | $0.10 | $25.00 |
| 1.00 | 100 oz | $1.00 | $250.00 |

Formula: `pip_value_usd = lot_size × pips` (for XAUUSD specifically).

---

## FORGE / bridge.py Implementation

### `_pip_size_for_symbol` (bridge.py ~line 639)

```python
def _pip_size_for_symbol(symbol, open_price, close_price) -> float:
    sym = (symbol or "").upper()
    if sym.startswith(("XAU", "XAG")):
        return 0.01   # SYMBOL_POINT — 1 pip = 1 point for gold
    ...
```

Status: **correct**. Uses `0.01` as pip_size = SYMBOL_POINT for XAUUSD.

### `_calc_pips` (bridge.py ~line 664)

```python
def _calc_pips(symbol, direction, open_price, close_price) -> float:
    raw = close_price - open_price
    if direction.upper() == "SELL":
        raw = -raw
    pip_size = _pip_size_for_symbol(symbol, open_price, close_price)
    return round(raw / pip_size, 1)
```

Status: **correct**. BUY: (close - open) / 0.01; SELL: (open - close) / 0.01.
Signed: positive = profit, negative = loss.

### `_ratchet_pip_size` (bridge.py ~line 766) — trader-style, different purpose

```python
def _ratchet_pip_size(symbol) -> float:
    # XAU/XAG: 0.10  (1 pip = $0.10 on 0.01 lot visible to operator)
    ...
```

This uses `0.10` deliberately for the profit ratchet UI so that the operator
sees "pip" values that match the $0.10/pip mental model at 0.01 lot (i.e.
LOCK_PIPS=10 means $1.00 protection). This is a separate trader-facing
convention and does NOT affect DB-stored pips.

### `_calc_pip_value_usd` (bridge.py — added by this implementation)

```python
def _calc_pip_value_usd(symbol, lot_size, pips) -> float:
    """USD value = lot_size × 100oz × $0.01/pip × pips = lot_size × pips"""
    if "XAU" in sym or "XAG" in sym:
        return round(lot_size * 1.0 * pips, 2)
    return 0.0
```

---

## Terminology Note

Some traders and forums use "pip" for gold to mean `$0.10` (a 10-point / $0.10
move). This is a trader-convention shorthand, not the MT5 technical definition.
This codebase stores `pips` in the MT5/technical sense (`pip_size=0.01`), so
a trade from 4700 → 4710 is **1000 pips** internally. The `pip_value_usd`
field converts this to a human-useful dollar amount:
- 1000 pips × 0.01 lot = $10.00 (entry 4700 → exit 4710, 0.01 lot)

---

## Sources

- [XAUUSD Pips and Lot Size Guide — DefcoFX](https://www.defcofx.com/xauusd-pips-and-lot-size/)
- [How many dollars is each gold pip? — MondFX](https://mondfx.com/how-many-dollars-is-each-gold-pip)
- [How to calculate pips in gold — DailyForex](https://www.dailyforex.com/forex-articles/how-to-calculate-pips-in-gold/206998)
- [MQL5 Pip Value Calculator — Medium](https://kritthanit-m.medium.com/mql5-pip-value-calculator-e121288d666d)
- [PIPS are killing me — MQL5 Forum](https://www.mql5.com/en/forum/431426)
- [Complete pip formula for XAUUSD — MQL5 Forum](https://www.mql5.com/en/forum/426270/page2)
- [How to calculate lot size for gold — Equiti](https://www.equiti.com/sc-en/news/trading-ideas/how-to-calculate-lot-size-in-gold-trading/)
