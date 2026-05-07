# Scalper config — defaults, sync, and runtime

This document is the **source of truth** for how native scalper JSON is produced and consumed. Use it when changing parameters or debugging “why doesn’t MT5 see my edit?”.

## Files and roles

| Path | Role |
|------|------|
| **`config/scalper_config.defaults.json`** | **Committed baseline** — edit this when adding keys or changing default strategy values. `version` here is a placeholder (`0.0.0`); it is **not** the runtime scalper version string. |
| **`scripts/sync_scalper_config_from_env.py`** | **Generator** — loads defaults, stamps `version` from repo **`VERSION`**, applies optional **`FORGE_*` / `forge*`** overrides from **`.env`** (see `MAPPING` in the script), writes **`config/scalper_config.json`**, copies to **`MT5/scalper_config.json`** when that directory exists. |
| **`config/scalper_config.json`** | **Generated artifact** — what **FORGE** (MT5), **BRIDGE**, **AURUM**, and tests read by path. **Do not edit by hand**; the next `make scalper-env-sync` or `make forge-compile` will overwrite it. |

## Make targets

| Target | What it does |
|--------|----------------|
| **`make scalper-env-sync`** | Runs **`sync_scalper_config_from_env.py`** (regenerate from defaults + `.env` + `VERSION`). |
| **`make forge-compile`** | Depends on **`scalper-env-sync`**, then compiles FORGE and copies JSON to MT5 Common Files (see `scripts/compile_forge_ea_macos.sh`). |
| **`make scalper-config-sync`** | **Copy-only:** pushes **existing** `config/scalper_config.json` → Wine **Common Files** (no regenerate). Use when the file is already correct but MT5 has a stale copy. |

## Runtime (FORGE)

- FORGE reads **`scalper_config.json`** via **`ReadTextFileDual`**: **Terminal Common Files** first, then terminal-local **Files** (optional **`FilesPath`** input).
- Hot reload: **`ReadScalperConfig()`** runs on a timer cadence (and **`InitScalperConfig()`** on **`OnInit`**).

## Python / repo consumers

- Code such as **`python/bridge.py`** and **`python/aurum.py`** use **`config/scalper_config.json`**. After changing defaults, run **`make scalper-env-sync`** (or **`make forge-compile`**) so the generated file matches what you expect.

## Is this the right design?

**Reasons it helps**

- **Single editable JSON shape** in **`defaults.json`**; avoids drift between “what we meant” and “what MT5 has”.
- **`VERSION`** and FORGE EA version stay aligned with the **`version`** field in the emitted scalper JSON automatically.
- **`.env`** can override a **subset** of keys without forking the whole file (**`MAPPING`**); good for machine-local tuning (legs, bounce flags) without committing secrets.

**Tradeoffs**

- **Not every JSON key has a `FORGE_*` env mapping** — unmapped keys are changed only in **`scalper_config.defaults.json`**.
- **Two files in git** (`defaults` + `generated`): the generated file is still committed so CI, BRIDGE, and clones work without running Python first; if you edit **`scalper_config.json`** only, the next sync **wipes** those edits.
- **`make scalper-config-sync`** does **not** run the generator — it only copies. If you edited **`defaults.json`** but forgot **`scalper-env-sync`**, copying will push an **old** generated file.

**Rule:** After editing **`scalper_config.defaults.json`** or **`.env`** (for mapped keys), run **`make scalper-env-sync`** or **`make forge-compile`**, then use **`scalper-config-sync`** only when you need a fast copy of an already-correct **`scalper_config.json`**.

## Verification

- **`pytest tests/scripts/test_sync_scalper_config_num_trades.py`** — env merge behaviour.
- Quick check: **`config/scalper_config.json`**’s **`version`** must equal **`VERSION`** after sync; full JSON should equal defaults with **`version`** replaced (when `.env` has no overrides for those paths).
