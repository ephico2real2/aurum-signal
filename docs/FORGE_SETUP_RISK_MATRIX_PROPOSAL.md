# FORGE — setup risk matrix (proposal)

**Status:** proposal — not implemented until reviewed against `config/scalper_config.defaults.json`, `.env` / `FORGE_*`, and `ea/FORGE.mq5`.

**Legend**

| Col | Meaning |
|-----|--------|
| **R** | Risk / priority tier (1 = tightest; higher = more defensive). Not the same as strategy R:R. |
| **Legs** | Native leg envelope `min–max` per group (resolver + caps). |
| **Max** | Concurrent exposure cap for this row (exact FORGE field TBD — e.g. `gold_native_max_sell_legs`, `max_open_same_direction`, or dedicated cap). |
| **Cool** | Cooldown policy vs baseline for that setup class (`default` = keep current; `×n` / `÷n` = multiply / divide baseline; `new` = new key; `n/a` = not applicable). |

**Overlap:** Rows 3 and 4 (inside band vs ADX≥45) can both apply — define **precedence** in implementation.

---

## Matrix (current vs proposed)

| # | Setup | Dir | R | Legs (cur) | Legs (new) | Max (cur) | Max (new) | Cool (cur) | Cool (new) |
|---|--------|-----|---|------------|------------|-----------|-----------|------------|------------|
| 1 | BB_BREAKOUT | BUY | 2 | 2–5 | 3–5 | 30 | 30 | default | default |
| 2 | BB_BREAKOUT | SELL (below band) | 3 | 2–5 | 2–4 | 10 | 16 | default | default |
| 3 | BB_BREAKOUT | SELL (inside band) | 4 | 2–5 | 1–2 | 10 | 3 | default | ×2 |
| 4 | BB_BREAKOUT | SELL (ADX ≥ 45) | 4 | 2–5 | 1–2 | 10 | 3 | default | ×2 |
| 5 | BB_BREAKOUT_RETEST | BUY | 1 | 2–5 | 3–5 | 30 | 30 | default | ÷2 |
| 6 | BB_BREAKOUT_RETEST | SELL | 3 | 2–5 | 2–4 | 10 | 10 | default | default |
| 7 | BB_BOUNCE | BUY | 3 | 2–3 | 2–3 | 5 | 5 | default | default |
| 8 | BB_BOUNCE | SELL | 5 | 2–3 | 1 | 5 | 2 | default | ×3 |
| 9 | BB_PULLBACK_SCALP | BUY | 2 | 1–2 | 2–3 | 3 | 5 | default | ÷2 |
| 10 | BB_PULLBACK_SCALP | SELL | 3 | 1–2 | 1–2 | 3 | 3 | default | default |
| 11 | MOMENTUM_DUMP | BUY | 3 | 2–3 | 2–3 | 5 | 5 | default | default |
| 12 | MOMENTUM_DUMP | SELL (composite OFF) | 4 | 2–3 | 1–2 | 10 | 4 | default | ×2 |
| 13 | MOMENTUM_DUMP | SELL + reversal | 1 | 2–3 | 3–4 | 10 | 10 | default | ÷2 |
| 14 | FRACTIONAL_SELL_IN_BULL | SELL | 5 | 1 | 1 | 1 | 1 | — | new |
| 15 | BULL_DAY_DIP_BUY | BUY | 3 | 1–2 | 1–2 | 3 | 3 | — | new |
| 16 | SELL_STOP_CONT (cascade) | SELL | 2 | 5 | 5 | 5 | 5 | — | n/a |
| 17 | BUY_LIMIT_RECOVERY | BUY | 1 | 1 | 1 | 1 | 3–5 ⚠️ | — | n/a |

⚠️ **Row 17:** Confirm whether **Max (new)** is max **concurrent recovery groups**, **legs** elsewhere, or a different knob — `Legs (new)` stays 1 in this proposal.

---

## Plain “proposed only” view (for diffs)

| # | Legs | Max | Cool |
|---|------|-----|------|
| 1 | 3–5 | 30 | default |
| 2 | 2–4 | 16 | default |
| 3 | 1–2 | 3 | ×2 |
| 4 | 1–2 | 3 | ×2 |
| 5 | 3–5 | 30 | ÷2 |
| 6 | 2–4 | 10 | default |
| 7 | 2–3 | 5 | default |
| 8 | 1 | 2 | ×3 |
| 9 | 2–3 | 5 | ÷2 |
| 10 | 1–2 | 3 | default |
| 11 | 2–3 | 5 | default |
| 12 | 1–2 | 4 | ×2 |
| 13 | 3–4 | 10 | ÷2 |
| 14 | 1 | 1 | new |
| 15 | 1–2 | 3 | new |
| 16 | 5 | 5 | n/a |
| 17 | 1 | 3–5 ⚠️ | n/a |

---

## Next steps

1. Map **Max** and **Cool** to concrete `scalper_config` keys and `FORGE_*` env names.
2. Align **Legs (cur)** / **Max (cur)** with a snapshot from `scalper_config.defaults.json` + active `.env` (date the snapshot in the doc).
3. Resolve row **3 vs 4** and row **17 ⚠️** before implementation.

---

*Document version: 2026-05-12 — table split into explicit current / proposed columns for git review.*
