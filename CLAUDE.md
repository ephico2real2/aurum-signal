## FORGE backtest monitoring

When the user asks to "monitor the forge tester", "watch the backtest", "tail the
journal", or similar, invoke `/forge-monitor`. The full instruction is at
`.claude/commands/forge-monitor.md`.

Key paths:
- Journal DB: `$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/.../FORGE_journal_*_tester.db`
- Query reference (writable): `docs/FORGE_TESTER_JOURNAL_QUERIES.md`
- Per-run analysis output: `docs/FORGE_RUN<run_id>_ANALYSIS.md`

The cheat sheet is a living document. New tables and refined queries discovered
during monitoring sessions are auto-appended under
`## Discovered Queries (auto-added by /forge-monitor)` and
`## Query revisions (auto-added by /forge-monitor)`. Hand-curated entries above
those sections are never modified.
