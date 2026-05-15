# QuestDB evaluation for FORGE telemetry

**Status (updated 2026-05-14)**: **ADOPT** — but via the MT5-Python-as-broker-ingress pattern, not via direct EA writes. See §12 for the winning architecture. §1-§11 below remain valid as the SQLite-vs-QuestDB analysis; §12 supersedes them with the **MT5 Python module + QuestDB API + Parquet archive** path, which solves the MQL5-can't-write-to-QuestDB constraint while still landing all the QuestDB wins.

## §1 TL;DR

- Today's pain has been **schema drift + dedup-crawl logic**, not SQLite I/O. QuestDB doesn't fix either.
- QuestDB IS the right tool if signal volume grows 10× (e.g., M1 tick-level capture, multi-symbol) or cross-run analytical queries start taking minutes.
- The MT5 EA cannot write to QuestDB natively — MQL5 has `<sqlite3.mqh>` but no QuestDB ILP client. Any migration is a **hybrid**: MT5 → SQLite journal → SCRIBE forwarder → QuestDB.
- Estimated migration cost (hybrid): **1-2 weeks engineering**. Estimated payoff at current load: **negligible**.

## §2 Current state (2026-05-14)

| Metric | Value | Headroom |
|---|---:|---|
| Source journal DB size | 1.05 GB / run | comfortable |
| Scribe DB (`aurum_tester.db`) | not measured | — |
| Live scribe DB (`aurum_intelligence.db`) | 142 MB / 6 weeks | comfortable |
| `forge_signals` column count | 117 | manageable, but drift-prone |
| Signal volume / tester run | 197k / 57h sim | low |
| Signal volume / 24h live | 8,239 | very low |
| Sync batch | 5,000 rows / 60s | bottlenecked by dedup-crawl, not I/O |
| Gate-breakdown query latency | sub-second | comfortable |
| Multi-run cross-comparison | not yet a workflow | n/a |

## §3 Pain → does QuestDB help?

| Today's pain | QuestDB helps? | Why / why not |
|---|---|---|
| `scribe.py` placeholder count drift | ❌ | Same bug class in any INSERT codegen — fix is schema-driven code generation, not storage |
| Dedup-crawl marking 656k rows synced (fixed today) | △ partial | Bulk UPDATE is already fast in SQLite; the bottleneck was application-loop logic |
| 5,000-row / 60s batch ingest | ✅ | QuestDB ILP ingests 100k+ rows/sec — batch size becomes irrelevant |
| Gate-breakdown aggregates over 200k rows | ✅ | Column-oriented `SAMPLE BY 5m` + native time bucketing is faster than SQLite `GROUP BY` |
| `database is locked` during WAL contention | ✅ | Single-writer + concurrent readers is QuestDB's home turf — but already mitigated by WAL+busy_timeout (commit 43d21b6) |
| 117-column schema drift across versions | ❌ | Column drift is a Python codegen problem, not a storage problem |
| Multi-month backtest cross-comparison | ✅ (future) | ASOF JOIN + `LATEST ON` queries are native; SQLite needs subqueries |
| Tick-level OHLC capture (not yet built) | ✅ (future) | Designed for this — ILP at line-rate, no INSERT-per-row overhead |
| **High-cardinality diagnostic columns** (30+ lot factors, 50+ atom snapshots, state-machine breakdowns) | ✅ | **Column-oriented storage = unused / always-1.0 columns are effectively free (compressed delta-encoding).** SQLite is row-oriented → every column adds bytes to every row even when constant. This is the structural reason for the operator-mandated "selective-column 12-of-30" tradeoff (codified in `.claude/skills/forge-monitor/SKILL.md`). QuestDB removes the tradeoff entirely. |

## §4 QuestDB facts relevant to FORGE

| Property | Value | Implication for FORGE |
|---|---|---|
| Storage model | Column-oriented, time-partitioned | Aggregates fast, point queries slower than SQLite |
| Ingest protocol | InfluxDB Line Protocol (ILP) over TCP/UDP/HTTP | SCRIBE needs an ILP client (Python `questdb` package exists) |
| Query protocol | PostgreSQL wire protocol + HTTP REST | ATHENA can query via `psycopg2` |
| Web UI | Built-in at `:9000` | Replaces some of the Athena debug surface |
| Schema | Append-mostly; UPDATE/DELETE limited | Fits signal/trade append model; problematic for `trade_groups` mutable state |
| Foreign keys / joins | No FK constraints; standard SQL JOINs | Relational integrity stays in SQLite |
| License | Apache 2.0, open source | No vendor lock |
| Deployment | Single binary, ~50 MB, macOS/Linux | One more launchd service |
| Maturity | Production at Bloomberg, Toggle, Razorpay | Battle-tested for our use case |

## §5 Proposed hybrid architecture (if migration is justified)

```
┌─────────────┐   SQLite write     ┌──────────────────────┐
│  MT5 EA     │ ─────────────────▶ │ FORGE_journal_*.db   │
│  (FORGE.mq5)│                    │ (source, per-agent)  │
└─────────────┘                    └──────────┬───────────┘
                                              │ tail
                                              ▼
                                  ┌───────────────────────┐
                                  │  SCRIBE (Python)      │
                                  │  - reads SQLite       │
                                  │  - splits the stream  │
                                  └────┬──────────────┬───┘
                              ILP write│              │SQLite write
                                       ▼              ▼
                            ┌──────────────────┐  ┌────────────────────────┐
                            │  QuestDB         │  │  aurum_intelligence.db │
                            │  - forge_signals │  │  (SQLite, relational)  │
                            │  - forge_trades  │  │  - aurum_tester_runs   │
                            │  - tick OHLC     │  │  - trade_groups        │
                            │  (time-series)   │  │  - trade_closures      │
                            └────────┬─────────┘  │  - market_regimes      │
                                     │            │  - system_events       │
                                     │            └─────────┬──────────────┘
                                     │ PG wire             │ SQLite read
                                     ▼                     ▼
                                 ┌───────────────────────────────┐
                                 │  ATHENA API + dashboard       │
                                 │  - time-series → QuestDB      │
                                 │  - relational → SQLite        │
                                 └───────────────────────────────┘
```

**Split rule**:
- Append-only, time-indexed, high-cardinality → **QuestDB** (`forge_signals`, `forge_journal_trades`, future tick data)
- Mutable, relational, low-cardinality → **SQLite** (`aurum_tester_runs`, `trade_groups`, `trade_closures`, `system_events`, `component_heartbeats`)

MT5 keeps writing to the per-agent SQLite journal — no change to the EA. SCRIBE becomes the fan-out point.

## §6 Migration cost estimate (hybrid path)

| Task | Effort | Risk |
|---|---|---|
| Add `questdb` to launchd via Makefile | 0.5 day | low |
| Define schema (forge_signals, forge_journal_trades) in QuestDB | 0.5 day | low |
| Rewrite `scribe.py::sync_forge_journal` to ILP-forward | 2-3 days | medium — needs same column-discipline as today |
| Add QuestDB connector to ATHENA (`psycopg2`) | 1 day | low |
| Migrate time-series queries in `python/athena_api.py` | 2-3 days | medium — SAMPLE BY syntax differs |
| Update `/forge-monitor` skill queries (both TESTER + LIVE modes) | 1 day | low |
| Backfill historical data from existing SQLite DBs | 1 day | low |
| Operator + dashboard validation | 1-2 days | medium |
| **Total** | **9-12 days** | — |

Full migration (drop SQLite entirely) is NOT recommended — relational tables don't belong in a time-series store.

## §7 Trip-wire metrics — when to re-open this

Open the evaluation when **any two** of the following are true for a sustained window (≥ 2 weeks):

| Metric | Trip-wire threshold | Current value |
|---|---:|---:|
| Signal volume / tester run | ≥ 2M | 197k (~10% of trip) |
| Signal volume / 24h live | ≥ 100k | 8.2k (~8% of trip) |
| Tester DB size / run | ≥ 5 GB | 1.05 GB (~21% of trip) |
| Gate-breakdown query latency (p95) | ≥ 5 sec | sub-second |
| Multi-run cross-comparison query | ≥ 30 sec | not run regularly |
| `database is locked` errors / 24h | ≥ 100 | 2 (last 24h, post-WAL fix) |
| `scribe.py` dedup-crawl backlog | ≥ 500k rows recurring weekly | one-time 656k (fixed) |
| Tick-level OHLC capture demanded | yes/no | no |
| Symbols tracked | ≥ 5 | 1 (XAUUSD) |

**Single-trip exceptions** (justify immediate re-open):
- Tick-level capture lands on the roadmap (per-tick ingest at 5+ ticks/sec/symbol = 1.5M rows/day, blows past SQLite's comfort zone)
- Multi-symbol expansion to 5+ symbols (5× signal volume + 5× cross-symbol query load)

## §8 What NOT to do (decided 2026-05-14)

- ❌ Migrate `aurum_tester_runs` or `trade_groups` to QuestDB — relational tables don't belong there
- ❌ Make the MT5 EA write directly to QuestDB — no MQL5 ILP client exists; bridge through SQLite first
- ❌ Run QuestDB and discard the SQLite journal — broker-side journal is the source of truth for fills
- ❌ Adopt QuestDB to fix schema-drift bugs — that's a Python codegen problem, not a storage problem (fix: generate the column tuple from a single schema source — see §9)

## §9 Better-than-QuestDB short-term fix for the recurring scribe drift bug

The scribe placeholder mismatch has bitten us repeatedly (v2.7.45, v2.7.47, v2.7.111-class). The structural fix is **single-source schema generation**, not a new DB:

- Add `schemas/forge_signals.yml` defining columns + types
- Codegen `scribe.py` INSERT tuple + placeholder count from the YAML
- Codegen `ea/FORGE.mq5` SIGNALS schema + `JournalRecordSignal` INSERT order from the same YAML
- Pre-commit hook validates the three are in lockstep

Cost: ~1 week. Eliminates the recurring "X values for Y columns" bug class entirely. **Higher ROI than QuestDB at current scale.**

## §10 References

- [QuestDB docs](https://questdb.io/docs/) — introduction + ILP protocol
- [QuestDB vs SQLite benchmark](https://questdb.io/blog/2021/05/10/questdb-release-6-0-tsbs-benchmark/) — time-series workload comparison
- [InfluxDB Line Protocol](https://github.com/influxdata/influxdb-client-python) — Python ILP client
- [PostgreSQL wire protocol](https://www.postgresql.org/docs/current/protocol.html) — same protocol QuestDB serves on `:8812`
- `commit 43d21b6` — WAL mode + busy_timeout on `aurum_tester.db` / `aurum_intelligence.db` (the SQLite mitigations already in place)
- `commit 1ba527a` — scribe fast-forward fix (this session)
- `.claude/skills/forge-monitor/SKILL.md` — LIVE MODE + TESTER MODE protocols against current SQLite

## §11 Changelog

- **2026-05-14** — Initial evaluation. Verdict: not adopted; trip-wire thresholds set at 10× current volume + tick-capture / multi-symbol exceptions. Short-term recurring scribe-drift bug is better fixed by single-source schema codegen (§9), not migration.
- **2026-05-14** — **Verdict flipped to ADOPT** after operator surfaced the MT5 Python module + Parquet pattern from [mql5.com article 19065](https://www.mql5.com/en/articles/19065) and the working reference at `~/Downloads/ai-signal-generator/market_ai_engine.py`. The constraint that killed adoption in §3 ("MT5 EA cannot write to QuestDB") is removed by inserting a Python ingress layer that uses the official `MetaTrader5` package. New architecture in §12.
- **2026-05-15** — **High-cardinality diagnostic argument added** (§3 + §12.7a). Operator surfaced during v2.7.121 ship: the just-codified "selective-column 12-of-30" lot-factor rule (in `.claude/skills/forge-monitor/SKILL.md`) is a SQLite-row-storage workaround, not a methodological preference. QuestDB's column-oriented storage makes always-1.0 columns effectively free (delta + run-length compression), removing the tradeoff. Strengthens the adopt verdict for the analytics layer (`forge_signals` + future per-atom/per-factor breakdowns); EA-side SQLite journal still constrained by Wine + MQL5 sqlite3.mqh.

---

## §12 Winning path — MT5 Python module + QuestDB API + Parquet archive

**Decision (2026-05-14)**: adopt QuestDB, but the ingress is **Python**, not the MQL5 EA. The MT5 Python module (`pip install MetaTrader5`) talks directly to the running MT5 terminal and returns broker data as pandas DataFrames. The Python ingress fans out to two stores:
- **QuestDB** (hot path) — live time-series, dashboard queries, real-time monitoring
- **Parquet** (cold path) — daily-partitioned zstd-compressed archives, training data, cross-version backtests

### §12.1 Reference implementation

`~/Downloads/ai-signal-generator/market_ai_engine.py` (Apr 2026, ~500 lines) is the canonical pattern. Key idioms to lift:

```python
import MetaTrader5 as mt5

mt5.initialize()                                    # attach to running terminal
mt5.symbol_select("XAUUSD", True)
bars = mt5.copy_rates_range("XAUUSD",
                            mt5.TIMEFRAME_M1,
                            int(start.timestamp()),
                            int(end.timestamp()))
df = pd.DataFrame(bars)
df['Date'] = pd.to_datetime(df['time'], unit='s', utc=True)
df.set_index('Date').to_parquet("hist.parquet.zst", compression='zstd')
```

Source: [mql5.com — Price Action Analysis Toolkit Part 36 (article 19065)](https://www.mql5.com/en/articles/19065)

### §12.2 Why this beats both prior options

| Approach | EA-side write | Python ingress | Hot store | Cold store | Operational | Verdict |
|---|---|---|---|---|---|---|
| **Current** (SQLite + SCRIBE sync) | SQLite journal | SCRIBE polls journal | `aurum_*.db` (SQLite) | none | 2 SQLite DBs + SCRIBE service | drifts, dedup-crawl bottleneck |
| **§1-§11 plan** (direct QuestDB) | ❌ MQL5 has no ILP client | — | QuestDB | none | not viable | rejected in §3 |
| **§12 plan** (MT5 Py + QuestDB API + Parquet) | optional audit-only SQLite | Python ILP push | QuestDB | Parquet zstd | QuestDB daemon + Python | **adopt** |

The pivot: MT5 Python module is **the universal adapter**. It works against the *same terminal* the EA runs in, so we get broker-authoritative data (ticks, OHLC, positions, deals, history) without depending on the EA's own SQLite write path.

### §12.3 Data split — what comes from where

| Data class | Source | Ingest path | Hot store | Cold store |
|---|---|---|---|---|
| OHLC bars (M1-MN) | `mt5.copy_rates_range()` | Python poll loop | QuestDB | Parquet (daily partition) |
| Ticks | `mt5.copy_ticks_range()` | Python poll loop | QuestDB | Parquet (daily, zstd) |
| Open positions | `mt5.positions_get()` | Python 5s poll | QuestDB (snapshot table) | — |
| Pending orders | `mt5.orders_get()` | Python 5s poll | QuestDB (snapshot table) | — |
| Closed deals | `mt5.history_deals_get()` | Python 30s poll, idempotent | QuestDB | Parquet |
| Symbol info | `mt5.symbol_info()` | Python on-demand | — (config) | — |
| **FORGE gate state** (PEMCG, DLV, DTC, ISS, h1_trend, etc.) | MQL5 EA computation | EA → JSON-drop or SQLite journal → Python tail | QuestDB `forge_signals` | Parquet |
| **FORGE trade events** (entries, fills, partial closes) | MQL5 EA | EA → SQLite journal → Python tail | QuestDB `forge_trades` | Parquet |
| `trade_groups`, `aurum_tester_runs` (relational) | Python aggregator | — | **SQLite** (stays — relational integrity) | — |

The 117-column `forge_signals` schema (PEMCG warnings, DTC state, ISS atoms, regime context) is **EA-computed** — `copy_rates_range` doesn't give you that. So the EA still needs to publish gate context. Three options:
- **A**: keep the SQLite journal as the EA's write target; Python tails it + forwards to QuestDB (low risk, drop-in)
- **B**: EA writes JSON drops to a watched directory; Python ingests files (avoids the SQLite-locking class entirely)
- **C**: EA exposes an HTTP endpoint Python polls (highest decoupling, most operational complexity)

Recommended: **A first** (no EA changes), migrate to **B** later if SQLite contention recurs.

### §12.4 Architecture

```
┌──────────────┐   broker fills, ticks, deals    ┌────────────────────┐
│  MT5 Terminal│ ◀──────────────────────────────▶│  Broker (Vantage)  │
│  (Wine)      │                                 └────────────────────┘
└──────┬───────┘
       │
       ├─[1] MQL5 EA writes own gate state ───▶  FORGE_journal_*.db (SQLite, audit)
       │
       │     ┌──────────────────────────────────────┐
       └─[2] │  Python ingress (mt5 module + pyarrow│
             │  + questdb client)                   │
             │  - mt5.copy_rates_range()  → ticks   │
             │  - mt5.positions_get()     → snapshot│
             │  - mt5.history_deals_get() → deals   │
             │  - tail SQLite journal     → gates   │
             └──┬──────────────────────────────┬────┘
                │ ILP TCP                      │ Parquet zstd append
                ▼                              ▼
        ┌───────────────┐                ┌─────────────────────┐
        │  QuestDB :9000│                │ data/parquet/       │
        │  - ohlc_m1    │                │  ohlc/2026-05-14/   │
        │  - ticks      │                │  ticks/2026-05-14/  │
        │  - forge_sigs │                │  signals/2026-05-14/│
        │  - forge_trd  │                │  deals/2026-05-14/  │
        │  - positions  │                └─────────────────────┘
        └───────┬───────┘                          ▲
                │ PG wire / REST                   │ DuckDB / polars
                ▼                                  │
        ┌────────────────────────────────────────────┐
        │  ATHENA API + dashboard                    │
        │  - live queries → QuestDB                  │
        │  - cross-run / training → Parquet via DuckDB│
        │  - relational (trade_groups) → SQLite      │
        └────────────────────────────────────────────┘
```

### §12.5 macOS / Wine consideration

The official `MetaTrader5` Python package is Windows-only at the binary level. On macOS the user's setup runs MT5 in Wine; two viable approaches:

| Approach | How | Pros | Cons |
|---|---|---|---|
| **Wine-Python** | Install Python *inside* the Wine bottle alongside MT5; run `wine python market_ai_engine.py` | Single host, single bottle | Wine Python tooling is awkward; pip installs into Wine-side site-packages |
| **Native-Python + Wine bridge** | Mac-side Python connects to a small Wine-side TCP shim that proxies MT5 calls | Use native pip/venv, modern Python | Need to write the shim; latency adds 1-5ms |
| **Dedicated Windows host** | Run Python + MT5 on a small Windows VM/box; QuestDB + Parquet on Mac | Cleanest separation, prod-grade | Hardware cost, additional ops |

The reference `market_ai_engine.py` notes `MetaTrader5 is Windows-only. Import lazily so the module still loads on macOS/Linux for offline tasks` — i.e., they handle the cross-platform case by deferring the import. That implies they're running it in Wine. Validate before committing to Phase 1.

### §12.6 Phased migration

| Phase | Scope | Effort | Risk |
|---|---|---|---|
| **Phase 0** | Validate MT5 Python module works in this Wine bottle (or set up the Windows-host alternative). Bootstrap one symbol's M1 history to Parquet. | 1 day | low |
| **Phase 1** | Add QuestDB to launchd. Python collector: poll `mt5.positions_get` + `mt5.history_deals_get` + tail SQLite journal → ILP push to QuestDB + Parquet append. SCRIBE stays running in parallel for safety. | 3-5 days | low |
| **Phase 2** | Migrate `/forge-monitor` LIVE-mode queries (and the Q3/Q9 gate breakdowns) to QuestDB. ATHENA dashboard switches to QuestDB for time-series panels. | 2-3 days | medium |
| **Phase 3** | Migrate TESTER-mode queries. Python tails the tester journal SQLite, forwards to QuestDB (separate table set per `aurum_run_id`). | 2-3 days | medium |
| **Phase 4** | Retire SCRIBE's signal/trade sync (relational tables stay in SQLite via a slimmer sync). Operator validation period. | 1-2 days | low |
| **Phase 5 (optional)** | Add tick-level capture via `mt5.copy_ticks_range()`. Parquet daily partitions become 100+ MB; QuestDB ingest stays sub-second. Now you have the data to evaluate sub-M1 setups. | 1 week | low |
| **Total** | | **9-15 days** spread over Phase 1-4 | — |

### §12.7 Wins over the rejected §1-§11 plan

- **MQL5-to-QuestDB constraint dissolved**: Python is the universal adapter
- **Two storage tiers**: hot (QuestDB, fast aggregates) + cold (Parquet, archive-friendly, DuckDB-queryable, git-ignorable per-day)
- **Schema drift solved differently**: Parquet column-by-name + QuestDB column-add API both tolerate adding columns without breaking existing data. The 117-column drift bug in scribe.py would not have a parallel here.
- **Training data is a first-class output**: Parquet daily partitions are exactly what scikit-learn / PyTorch / catboost want. No CSV exports needed.
- **No EA changes required for Phase 1**: the SQLite journal stays. SCRIBE may even stay (initially). Risk surface is small.
- **High-cardinality diagnostic columns become free**: see §12.7a below.

### §12.7a The high-cardinality diagnostic columns argument (operator-surfaced 2026-05-15)

**Why this matters for FORGE specifically**: as ICT atoms and lot-factor breakdowns scale, the EA has many state values worth persisting per-signal. Examples surfaced in this session:

| Data class | Underlying values | "Should be queryable" cut |
|---|---:|---:|
| Lot factor breakdown (v2.7.121) | 30 factors | 12 columns under selective-column rule |
| ICT atoms (Phase 1-5, full design) | ~50 atoms across MSS/FVG/ChoCH/OB/Breaker/Unicorn/CRT/Venom | 14 columns shipped so far (v2.7.119+120) |
| PEMCG composite atoms | 7 atoms × 2 directions = 14 | 0 columns today; would be valuable |
| DTC state breakdown (intraday + H4) | ~10 derived values | 0 columns today |
| Composite-score breakdowns (CES retired, future ISS-C, future Unicorn-score) | 5-7 components each | varies |

**Total potential diagnostic columns**: ~80-120 across the full FORGE state. SQLite can technically handle it, but:

1. **Storage cost** — every signal row carries every column. With ~200k signals per tester run, 80 REAL columns × 8 bytes = 640 bytes/row × 200k = 128 MB additional storage per run. Compounds across runs.
2. **Schema-parity ship cost** — every new diagnostic column requires the 5-layer touch (CREATE + ALTER + JournalRecordSignal + scribe CREATE/ALTER/SELECT/INSERT/placeholder count + sql file). Mechanical but error-prone (historical drift incidents in v2.7.45/47/112 cited above).
3. **Dashboard query latency** — every column adds to SELECT * footprint and JOIN cost.
4. **The operator-mandated "selective-column" tradeoff** — the 12-of-30 cut codified today in `.claude/skills/forge-monitor/SKILL.md` exists ENTIRELY because of these SQLite-row-storage constraints. It is not a methodological preference; it is a storage-cost workaround.

**Why QuestDB resolves this structurally**:

- **Column-oriented storage**: each column is stored independently in its own file. An always-1.0 column compresses to a near-zero footprint (delta + run-length encoding). Adding 18 always-1.0 columns to QuestDB's `forge_signals` table costs ~kilobytes total, not megabytes per run.
- **Schema add API**: `ALTER TABLE forge_signals ADD COLUMN lot_dump_pyramid_factor DOUBLE` is non-blocking, takes <1 sec, doesn't rewrite existing rows. No `CREATE TABLE IF NOT EXISTS` semantics to drift against.
- **Selective queries are free**: `SELECT lot_stack_factor, lot_dump_pyramid_factor FROM forge_signals WHERE ...` only reads the 2 column files, not the whole row. SQLite must scan every row's storage page.

**Practical impact**:

Under QuestDB, the operator-mandated selective-column rule **becomes obsolete for the analytical layer**. The text-log + 12-columns + grep-only-for-the-rest tradeoff was a SQLite tax. QuestDB removes it — log all 30+ factors as columns, query whichever subset matters per analysis, pay nothing in storage for the always-1.0 ones.

The selective-column rule **still applies to the source EA SIGNALS journal** (SQLite written by MQL5, can't be replaced — see §12.5 Wine constraints). But Python-side analytics + dashboard live in QuestDB and lose the constraint.

### §12.8 Open questions

- **Wine + MT5 Python verification**: does the package import + `mt5.initialize()` succeed in the operator's Wine bottle? Phase 0 settles this.
- **Latency budget**: how fresh does the dashboard need to be? QuestDB at 1-second polls is feasible; if 100ms is needed, Phase 1 ingress design changes.
- **Tick storage cost**: at 5+ ticks/sec on XAUUSD, 1 day = ~430k ticks = ~20MB Parquet zstd. 90 days = 1.8GB. Manageable.
- **Backfill strategy**: do we replay the existing `aurum_tester.db` into QuestDB, or start fresh? Probably start fresh; the existing data stays queryable in SQLite for cross-comparison.
- **Operator approval needed for**: launchd service for QuestDB daemon, disk budget for Parquet (estimate 10-50 GB for first year), Python ingress as a new long-running service.

### §12.9 First concrete step

Phase 0 (1 day) — write `python/mt5_ingress_probe.py` that does:
1. `mt5.initialize()` in the Wine bottle
2. Pull last 24h M1 bars on XAUUSD
3. Write to `data/probe.parquet.zst`
4. Read back with `pd.read_parquet` + DuckDB and confirm row count

Pass/fail determines whether we go Wine-Python (path 1) or set up the Windows-host alternative (path 3 in §12.5). Want me to scaffold that probe script?
