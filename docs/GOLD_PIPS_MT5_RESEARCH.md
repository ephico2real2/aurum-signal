# XAUUSD / Gold Pip Calculation — Broker Standard

## Correct Rule (broker-confirmed)

For XAUUSD, discard the decimal portion of each price (floor to integer), then
each whole-number move = **10 pips**.

```
pips = (int(close_price) - int(entry_price)) × 10   # BUY
pips = (int(entry_price) - int(close_price)) × 10   # SELL
```

`int()` in Python truncates toward zero, which equals floor for positive prices.
Signed output: positive = win, negative = loss.

### Examples

| Entry | Exit | Direction | Calculation | Pips |
|---|---|---|---|---|
| 2037.12 | 2038.50 | BUY | (int(2038) - int(2037)) × 10 | **10** |
| 2037.00 | 2042.00 | BUY | (2042 - 2037) × 10 | **50** |
| 4700.00 | 4715.75 | BUY | (int(4715) - int(4700)) × 10 | **150** |
| 4700.00 | 4715.75 | SELL | (int(4700) - int(4715)) × 10 | **-150** |

---

## Pip Value in USD

```
pip_value_usd = pips × lot_size × 10
```

Derivation:
- 1 pip = 1 whole-dollar move on gold price (after floor)
- 1 whole-dollar move per oz × 100 oz contract = $100 per standard lot per $1 move
- But 1 pip = 0.10 USD price move (since 10 pips per $1), so per pip per standard lot = $10
- pip_value_usd = pips × lot_size × $10/pip/lot

### Verification: entry 4700, exit 4715.75, BUY, 0.08 lot

```
pips          = (int(4715) - int(4700)) × 10 = 150 pips
pip_value_usd = 150 × 0.08 × 10 = $120.00

Cross-check actual P&L:
  actual_pnl = (4715.75 - 4700.00) × 0.08 lot × 100 oz = $126.00
  (the $6 difference = 0.75 decimal move × 0.08 × 100, which the floor formula discards by design)
```

### Pip value by lot size

| Lot Size | Oz Traded | 1 pip value | 50 pips | 150 pips |
|---|---|---|---|---|
| 0.01 | 1 oz | $0.10 | $5.00 | $15.00 |
| 0.08 | 8 oz | $0.80 | $40.00 | $120.00 |
| 0.10 | 10 oz | $1.00 | $50.00 | $150.00 |
| 1.00 | 100 oz | $10.00 | $500.00 | $1,500.00 |

---

## Why This Differs from SYMBOL_POINT = 0.01

The previous implementation used `SYMBOL_POINT = 0.01` as pip size:

```python
# WRONG — old formula
pips = (close_price - entry_price) / 0.01
```

For a $5 move (e.g. 4700 → 4705): `5.00 / 0.01 = 500 pips` — 10x too many.

The corresponding pip_value_usd used factor 1.0:
```python
# WRONG — old formula
pip_value_usd = lot_size × pips × 1.0
# e.g. 500 pips × 0.08 lot × 1.0 = $40.00
```

By coincidence, the old pip_value_usd could appear correct in spot checks because
the two errors cancelled out (10x too many pips, 10x too small per-pip value).
However, the stored `pips` column was wrong (e.g. 500 instead of 50 for a $5 move),
and the formula breaks down with fractional prices (e.g. 2037.12 → 2038.50 gives
138 pips via old formula vs. the correct 10 pips broker-standard).

---

## Correct bridge.py Implementation (post-fix)

### `_calc_pips`

```python
def _calc_pips(symbol, direction, open_price, close_price) -> float:
    ep = float(open_price or 0)
    cp = float(close_price or 0)
    if ep <= 0 or cp <= 0:
        return 0.0
    sym = (symbol or "").upper()
    if "XAU" in sym:
        raw = (int(cp) - int(ep)) * 10
        return float(raw if direction == "BUY" else -raw)
    # Forex fallback: 4-decimal pairs, 1 pip = 0.0001
    raw = (cp - ep) / 0.0001
    return round(raw if direction == "BUY" else -raw, 1)
```

### `_calc_pip_value_usd`

```python
def _calc_pip_value_usd(symbol, lot_size, pips) -> float:
    """XAUUSD: 1 pip = $10/lot. pip_value_usd = pips × lot_size × 10"""
    lot = float(lot_size or 0)
    p   = float(pips or 0)
    if lot <= 0:
        return 0.0
    sym = (symbol or "").upper()
    if "XAU" in sym:
        return round(p * lot * 10, 2)
    return 0.0
```

---

## Sources

- [XAUUSD Pips and Lot Size Guide — DefcoFX](https://www.defcofx.com/xauusd-pips-and-lot-size/)
- [How many dollars is each gold pip? — MondFX](https://mondfx.com/how-many-dollars-is-each-gold-pip)
- [How to calculate pips in gold — DailyForex](https://www.dailyforex.com/forex-articles/how-to-calculate-pips-in-gold/206998)
- [MQL5 Pip Value Calculator — Medium](https://kritthanit-m.medium.com/mql5-pip-value-calculator-e121288d666d)
- [PIPS are killing me — MQL5 Forum](https://www.mql5.com/en/forum/431426)
- [Complete pip formula for XAUUSD — MQL5 Forum](https://www.mql5.com/en/forum/426270/page2)
- [How to calculate lot size for gold — Equiti](https://www.equiti.com/sc-en/news/trading-ideas/how-to-calculate-lot-size-in-gold-trading/)
