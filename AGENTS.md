# Agent / automation notes (signal_system)

## Scalper config — do not edit `config/scalper_config.json`

`config/scalper_config.json` is **generated**. Edits are overwritten by **`make scalper-env-sync`** and **`make forge-compile`**.

1. Change **`config/scalper_config.defaults.json`** (or **`.env`** keys mapped in **`scripts/sync_scalper_config_from_env.py`**).
2. Run **`make scalper-env-sync`** (or **`make forge-compile`**) to refresh **`config/scalper_config.json`** and optionally copy to **`MT5/`**.

Details: **`docs/SCALPER_CONFIG_PIPELINE.md`**.
