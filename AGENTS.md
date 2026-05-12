# Agent / automation notes (signal_system)

## Claude skills ↔ Cursor

Repo workflows for Claude Code live under **`.claude/skills/`**. **Cursor agents should follow the same files** when the task matches:

| Skill | Path |
|--------|------|
| FORGE EA review / codex validation | `.claude/skills/forge-ea-review/SKILL.md` |
| FORGE tester journal monitor | `.claude/skills/forge-monitor/SKILL.md` |
| Trading / MQL5 research | `.claude/skills/research/SKILL.md` |

**Cursor:** project rule **`.cursor/rules/claude-skills-bridge.mdc`** (`alwaysApply: true`) instructs the agent to **read** the matching `SKILL.md` and comply. **`.claude/commands/*.md`** are only for Claude Code slash commands; use **`SKILL.md`** in Cursor.

## Scalper config — do not edit `config/scalper_config.json`

`config/scalper_config.json` is **generated**. Edits are overwritten by **`make scalper-env-sync`** and **`make forge-compile`**.

1. Change **`config/scalper_config.defaults.json`** (or **`.env`** keys mapped in **`scripts/sync_scalper_config_from_env.py`**).
2. Run **`make scalper-env-sync`** (or **`make forge-compile`**) to refresh **`config/scalper_config.json`** and optionally copy to **`MT5/`**.

Details: **`docs/SCALPER_CONFIG_PIPELINE.md`**.
