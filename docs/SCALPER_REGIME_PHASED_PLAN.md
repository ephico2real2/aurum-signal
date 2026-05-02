# Scalper + regime enhancement — phased plan & execution prompts

> **Purpose:** Step-by-step phases (with copy-paste **execution prompts** for humans or coding agents), testing/restart discipline via the **Makefile**, MT5 Strategy Tester orientation, and documentation touch-points. Aligns with existing code comment style and project docs (`README.md`, `docs/ARCHITECTURE.md`, `DATA_CONTRACT.md`, `SOUL.md`, `SKILL.md`, `CHANGELOG.md`).

---

## 0. Review — scope, risks, and lot scaling

### 0.1 What we are fixing (baseline)

- **BRIDGE LENS scalper** (`_scalper_logic`) historically queued **`OPEN_GROUP` without `Aegis.validate()`**, so trend cascade, floating DD caps, R:R, and regime context did not apply. Phased work should route self-scalp candidates through the same **risk envelope** as other entry paths where appropriate.
- **FORGE native scalper** decides inside **MQL5**; Python regime/trend must either be **mirrored into `MT5/config.json`** or duplicated judiciously in the EA.
- **SCRIBE** already has `regime_*` columns on `trade_groups`; many self-scalp rows may not populate them until we wire BRIDGE consistently.

### 0.2 Lot size — “multiply during DD to recover” vs safer patterns

**Plain increasing of lot size after losses to “recover” drawdown faster is martingale-like behaviour.** It raises tail risk (a losing streak wipes the account faster). Industry practice and this codebase’s posture:

| Approach | Role in Signal System | Risk note |
|----------|------------------------|-----------|
| **Fixed / risk-based sizing** | Default (`AEGIS_*`, `AEGIS_LOT_MODE`) | Baseline. |
| **Scale down after consecutive losses** | Already present in AEGIS (`AEGIS_SCALE_DOWN_*`) | Reduces size when wrong. |
| **Scale up after consecutive wins** | Already present (`AEGIS_SCALE_UP_*`) | Anti-martingale — sizes up when edge appears to work. |
| **Regime / trend-conditioned bump** | *Proposed phased feature*: modest multiplier **only when** regime confidence + MTF alignment pass, with **hard caps** (`max_lot`, `max_multiplier`) | Targets “ride strong trend, scalp repeatedly” without tying size to *recent loss*. |
| **Post-DD “recovery multiplier”** | If ever implemented: must be **opt-in**, **capped**, **session-limited**, and **documented as high risk** — not recommended as default. | Treat as experimental; demo first. |

**Phase prompts below** use **regime-aligned scaling** and **optional capped recovery assist** as *separate*, env-gated features. Do not conflate “recover DD faster” with unlimited lot growth.

### 0.3 Documentation standard

When changing behaviour:

- **Python/MQL5:** Match surrounding docstrings and section headers (`# ── Section ──`).
- **Operator-facing:** Update `.env.example` for every new env var; cross-link `docs/AEGIS.md`, `docs/FORGE_BRIDGE.md`, `docs/DATA_CONTRACT.md` as appropriate.
- **AI layer:** Update `SOUL.md` (identity/constraints) and `SKILL.md` (actionable rules); keep bullets truthful to real gates.
- **Release notes:** `CHANGELOG.md` under the next version with migration/testing notes.
- **Architecture diagram:** Update `docs/assets/trading-system-architecture.drawio` (and export PNG/HTML) **when data flow or components change** — not for typo-only edits.

---

## 1. MT5 Strategy Tester — backtesting FORGE (no project CI today)

The repo does **not** run MQL5 backtests in CI. You run them **inside MetaTrader 5** on your machine.

### 1.1 Prerequisites

- `FORGE.mq5` compiled to **`FORGE.ex5`** (`make forge-compile` or MetaEditor F7).
- Symbol **XAUUSD** (or your broker’s name) available in Tester.
- EA inputs: set **FilesPath** / use **FILE_COMMON** consistent with how you export JSON in live (Tester uses a sandbox — see MT5 docs for **Tester “Every tick based on real ticks”** vs coarse models).

### 1.2 Steps (classic MT5 flow)

1. Open **MetaTrader 5** → **View → Strategy Tester** (or `Ctrl+R`).
2. **Expert Advisor:** select **FORGE**.
3. **Symbol:** XAUUSD (broker suffix if any).
4. **Period / dates:** choose range with sufficient ticks (gold: prefer **M5 or M15** initial exploration; native scalper logic lives in the EA — confirm timeframe in `ea/FORGE.mq5` inputs).
5. **Model:** **Every tick based on real ticks** when available for realism; otherwise note results are indicative only.
6. **Inputs:** align **scalper mode**, SL/TP, session filters with `config/scalper_config.json` / `.env`-driven philosophy you use live.
7. **Start** — inspect graph, **Journal**, **Experts** tab for errors.
8. Export or screenshot summary for regression comparison after code changes.

### 1.3 Limitations (document honestly)

- **LENS / TradingView / Telegram / BRIDGE** do not exist in isolated EA Tester runs unless you simulate or stub file feeds. Native scalper + OPEN_GROUP mechanics are testable; **full-stack** behaviour requires **demo forward testing** or **Python integration tests** (file-bus mocks).

### 1.4 Makefile alignment after EA changes

| Goal | Command |
|------|---------|
| Copy EA to MT5 Experts + compile | `make forge-compile` |
| Compile + open MT5 + poll `forge_version` | `make forge-refresh-verify` |
| Python-only change | `make reload-bridge` or `make reload` |
| `.env` change | `make restart` |

---

## 2. Global verification commands (run frequently)

```bash
cd /path/to/signal_system

# Contracts + schemas (after JSON/env contract edits)
make test-contracts

# API regression (after BRIDGE/AEGIS/ATHENA changes)
make test-api

# Focused suites (examples — adjust as tests are added per phase)
python3 -m pytest tests/api/test_modify_scope.py -q --tb=short
python3 -m pytest tests/services/test_regime_engine.py -q --tb=short

# Full API suite when close to merge
make test-api
```

---

## Phase A — BRIDGE LENS scalper through Aegis + regime snapshot on group rows

**Status:** implemented — see **`[1.5.7] — 2026-05-03`** in `CHANGELOG.md` (`python/bridge.py`, `python/aegis.py`, `tests/api/test_scalper_aegis_gate.py`). Deploy: `make reload-bridge`.

### Goals

- Call **`Aegis.validate()`** from `_scalper_logic` before any `OPEN_GROUP`.
- Pass **`mt5_data`**, **`regime_context`** from **`_regime_context_for_trade(direction)`**, **`current_price`** from LENS.
- Persist **`regime_*`** on `trade_groups` for **`SCALPER_SUBPATH_DIRECT`** (mirror SIGNAL/AURUM field population pattern).
- Remove or downgrade **`DIRECT_NO_AEGIS`** audit path when superseded.

### Tests to add or extend

- New: `tests/api/test_scalper_aegis_gate.py` (or extend `test_bridge_*`): mock `mt5` + lens_snap → assert reject when trend cascade fails; assert approve when aligned.
- Run: `make test-api`, `make test-contracts` if JSON examples change.

### Restart / compile

- `make reload-bridge` after Python edits (no EA change).

### Doc updates (Phase A)

- `CHANGELOG.md` — user-visible behaviour change.
- `docs/ARCHITECTURE.md` — Trade Lifecycle / safety layers: LENS scalper passes AEGIS.
- `docs/FORGE_BRIDGE.md` or `AEGIS.md` — note scalper path now gated.
- `SKILL.md` / `SOUL.md` — one bullet each on scalper + regime alignment.
- `.env.example` — only if new toggles (e.g. `SCALPER_USE_AEGIS=true` default on).

### Execution prompt — Phase A

```
You are working in the Signal System repo. Implement Phase A of docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Read python/bridge.py _scalper_logic and python/aegis.py validate / _check_trend_cascade.
2. Refactor _scalper_logic to build the candidate signal dict, then call self.aegis.validate(signal, account, current_price=..., mt5_data=mt5, regime_context=self._regime_context_for_trade(direction)). Only write OPEN_GROUP when TradeApproval.approved is True; log reject_reason to bridge activity / debug.
3. Populate trade_groups regime_* fields when logging the group (follow _process_signal / AURUM OPEN_GROUP patterns in bridge.py).
4. Add pytest coverage under tests/api/ with mocked mt5 and lens snapshots for approve/reject paths.
5. Update CHANGELOG.md, SKILL.md, SOUL.md, docs/ARCHITECTURE.md, docs/AEGIS.md per the plan; match existing comment and section style.
6. Run: make test-contracts && make test-api && make reload-bridge (document for operator).

Do not change FORGE.mq5 in Phase A unless unavoidable.
```

---

## Phase B — Regime-aware entry gate for self-scalp sources

**Status:** implemented — **`[1.5.7] — 2026-05-03`** in `CHANGELOG.md`; code: `python/aegis.py` (`_regime_countertrend_reject`), `tests/services/test_aegis_regime_countertrend.py`, `.env.example`, `docs/AEGIS.md`. Deploy: `make reload-bridge` (restart after changing `REGIME_*` + AEGIS env: `make restart`).

### Goals

- When **`REGIME_ENTRY_MODE=active`** and **`apply_entry_policy`** is true, optionally **reject** counter-trend scalps (e.g. BUY when label `TREND_BEAR` above confidence threshold), configurable per source class (`SCALPER_*` vs `FORGE_NATIVE` logged path).
- Keep **shadow** mode logging-only.

### Tests

- Extend `tests/services/` or `tests/api/` for regime reject matrix (label × direction × confidence).

### Restart

- `make reload-bridge`; restart after `.env` regime toggles: `make restart`.

### Doc updates

- `docs/AEGIS.md`, `.env.example`, `DATA_CONTRACT.md` if new rejection codes surface in SCRIBE.

### Execution prompt — Phase B

```
Implement Phase B from docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Read python/regime.py RegimeSnapshot fields and python/aegis.py validate().
2. Add optional guard: when regime_context indicates apply_entry_policy and label conflicts with direction (define matrix TREND_BULL/TREND_BEAR vs BUY/SELL), return TradeApproval(False, REASON_CODE) with stable machine-readable strings for SCRIBE/skip_reason logging.
3. Gate with new env vars (e.g. AEGIS_SCALPER_REGIME_BLOCK=true, AEGIS_SCALPER_REGIME_MIN_CONFIDENCE=0.55) documented in .env.example.
4. Tests for pass/block/shadow; run make test-api && make test-contracts.
5. Update AEGIS.md, CHANGELOG.md, SKILL.md (one paragraph).
```

---

## Phase C — FORGE EA: trend / regime alignment + Makefile compile discipline

**Status:** implemented — **`[1.6.0] — 2026-05-04`** in `CHANGELOG.md`; code: `ea/FORGE.mq5` (H4 alignment, `NativeScalperH4Align` / `NativeScalperRegimeGate`, `indicators_h4`, `forge_version` **1.6.0**), `python/bridge.py` (`config.json` **`regime_*`** + refresh on each `_write_status`), `tests/api/test_bridge_config_regime.py`. Deploy: **`make forge-compile`** + reattach EA; **`make reload-bridge`**.

### Goals

- **MQL5:** Native setups (BB bounce/breakout) require **H1** (existing) plus optional **H4** EMA/ATR alignment; **`market_data.json`** exports **`indicators_h4`**.
- **`MT5/config.json`:** BRIDGE writes **`regime_label`**, **`regime_confidence`**, **`regime_apply_entry_policy`** (0/1), **`regime_countertrend_min_confidence`** for the FORGE counter-trend gate (mirrors Python AEGIS Phase B when policy applies).

### Tests

- **Tester:** manual backtest runs + journal checks (document baseline metrics before/after).
- **Python:** if BRIDGE writes new config keys, extend `tests/api/` or contract tests for `config.json` shape.

### Restart / compile

```bash
make forge-compile
make forge-refresh-verify   # or forge-reload per README
make reload-bridge          # when BRIDGE writes new config keys
```

### Doc updates

- `ea/FORGE.mq5` header architecture comment block.
- `docs/FORGE_TRADING_RULES.md`, `docs/FORGE_BRIDGE.md`.
- **Architecture diagram** if file-bus adds fields.

### Execution prompt — Phase C

```
Implement Phase C from docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Read ea/FORGE.mq5 native scalper sections and docs/FORGE_TRADING_RULES.md.
2. Add trend-alignment guards using existing indicator buffers (document which TF and thresholds in FORGE.mq5 header).
3. If adding BRIDGE→MT5/config.json fields for regime_hint, update bridge.py write path, schemas/files if applicable, python/contracts, tests, and DATA_CONTRACT.md in one PR.
4. Run make forge-compile; manual Strategy Tester pass; make test-contracts if JSON changed.
5. Update FORGE_TRADING_RULES.md, FORGE_BRIDGE.md, CHANGELOG.md; refresh docs/assets/trading-system-architecture.drawio only if data flow changes.
```

---

## Phase D — SCRIBE & observability for all self-scalp sources

### Goals

- Ensure **`FORGE_NATIVE_SCALP`** rows receive **`regime_*`** and optional **`skip_reason`** / audit when BRIDGE blocks duplicate or unhealthy entries.
- Add **queries** to `docs/SCRIBE_QUERY_EXAMPLES.md` for “self-scalp by regime label”.

### Tests

- Scribe migration tests if new columns (prefer using existing regime columns).

### Restart

- `make reload-bridge`; `make scribe-gui` for manual DB checks.

### Execution prompt — Phase D

```
Phase D per docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Wire regime snapshot from bridge._regime_snapshot into _check_forge_scalper_entry group_data / log_trade_group kwargs matching scribe.py schema.
2. Add SCRIBE_QUERY_EXAMPLES.md examples filtering trade_groups WHERE source IN ('FORGE_NATIVE_SCALP','SCALPER_SUBPATH_DIRECT').
3. Tests for scribe.log_trade_group regime fields; make test-api.
4. Update SCRIBE_QUERY_EXAMPLES.md, DATA_CONTRACT.md snippet if needed, CHANGELOG.md.
```

---

## Phase E — Intelligent lot scaling (regime + streak; not raw martingale)

### Goals

- **Primary:** Increase **`lot_per_trade`** (within **hard caps**) when **regime confidence** and **MTF alignment** support aggressive intraday scalping; optional **reduce** when regime is RANGE/VOLATILE or floating DD pressure high.
- **Secondary (optional, high risk):** Session-capped “recovery assist” multiplier after equity DD — **default off**, strongly warned in docs.

### Tests

- Unit tests for multiplier math with mocked regime + account state; enforce caps never exceeded.

### Restart

- `make restart` after `.env` changes.

### Doc updates

- `docs/AEGIS.md`, `.env.example`, `SOUL.md` / `SKILL.md` — honest capability bounds.

### Execution prompt — Phase E

```
Implement Phase E from docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Design env-gated multipliers (e.g. AEGIS_REGIME_SCALE_MAX=1.5) applied inside aegis.validate or a small helper; never exceed MAX_LOT_TOTAL / broker constraints.
2. Wire consecutive-win streak + regime confidence only for upsize; do NOT tie upsize directly to “recover last loss” unless AEGIS_RECOVERY_ASSIST_ENABLED=true with explicit caps documented.
3. Full pytest coverage; run make test-api.
4. Update AEGIS.md, SOUL.md, SKILL.md, CHANGELOG.md — disclose tail risks for any recovery assist.
```

---

## Phase F — AURUM AUTO_SCALPER + prompts & context

### Goals

- Inject **full `regime` block** into AUTO_SCALPER prompt and **`_build_context`** consistently.
- **`SKILL.md`:** scalping discipline synchronized with Phase B/E gates.

### Tests

- `tests/api/` for context builder if extractable; manual Telegram checks.

### Restart

- `make reload` (aurum + bridge).

### Execution prompt — Phase F

```
Phase F per docs/SCALPER_REGIME_PHASED_PLAN.md:

1. Update python/bridge.py _auto_scalper_tick prompt and python/aurum.py _build_context to include regime snapshot + feature_shape_mismatch warning.
2. Update SKILL.md and SOUL.md so AURUM never advises counter-policy trades when gates forbid them.
3. make test-api; make reload.
4. CHANGELOG.md user-facing note.
```

---

## 3. Checklist template (per phase — copy into PR description)

- [ ] Code + comments follow existing style
- [ ] `make test-contracts` (if schemas/contracts touched)
- [ ] `make test-api` (Python behaviour)
- [ ] `make forge-compile` + manual Tester **if EA touched**
- [ ] `.env.example` updated
- [ ] `CHANGELOG.md` updated
- [ ] `README.md` / `docs/ARCHITECTURE.md` link or section if user-visible
- [ ] `SOUL.md` / `SKILL.md` if AURUM behaviour or constraints change
- [ ] Architecture drawio + PNG export **if architecture changed**

---

## 4. Related files (quick index)

| Area | Files |
|------|--------|
| BRIDGE scalper | `python/bridge.py` (`_scalper_logic`, `_check_forge_scalper_entry`) |
| AEGIS | `python/aegis.py` |
| Regime | `python/regime.py`, BRIDGE `_refresh_regime_snapshot` |
| FORGE | `ea/FORGE.mq5`, `config/scalper_config.json` |
| SCRIBE | `python/scribe.py` |
| Docs | `README.md`, `docs/ARCHITECTURE.md`, `docs/AEGIS.md`, `docs/FORGE_TRADING_RULES.md`, `docs/DATA_CONTRACT.md`, `SOUL.md`, `SKILL.md`, `CHANGELOG.md` |

---

*Last updated: aligns with roadmap discussion (scalper + regime + testing discipline). Implement phases in order A→F unless a hotfix dictates otherwise.*
