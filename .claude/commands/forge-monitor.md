Read and follow all instructions in /Users/olasumbo/signal_system/.claude/skills/forge-monitor/SKILL.md exactly.

**Mode selection** (check the invocation args / surrounding message):

- If the invocation was `/forge-monitor live` (or contains the word `live` anywhere — e.g. `live /forge-monitor`, `live forge-monitor`, `live mon`, `live monitor`, `live monitors`, `live-mon`, `monitor live`, "watch the live broker") → enter **LIVE MODE**: read the "LIVE MODE — monitor the live broker EA instead of the tester" section of the skill, query the scribe DB at `python/data/aurum_intelligence.db` + `market_data.json`, and write the per-day analysis doc at `docs/FORGE_LIVE_<YYYY-MM-DD>_ANALYSIS.md`.

- Otherwise → default **TESTER MODE**: find the active tester journal DB at `$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/.../FORGE_journal_*_tester.db`, capture the baseline snapshot, and begin the 45s polling loop. Per-run analysis doc at `docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md`.

Both modes share the same housekeeping checks (A/B/C), PEMCG asymmetry audit, GFM-mandatory markdown rules, recommendations pattern, and operator Q&A log structure — only the data sources and time-windowing differ. The SKILL.md is the canonical reference for both.
