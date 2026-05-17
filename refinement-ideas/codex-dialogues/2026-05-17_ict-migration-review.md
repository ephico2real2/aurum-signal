# ICT migration design review: 8679ac3..ac58237

## 1. Critical issues (would break live trading) — file:line refs required

- **Changing `MagicNumber` while positions/orders are open orphans existing groups and defeats the v2.7.131 seed fix.** `RebuildGroups()` only accepts positions whose magic is in `[MagicNumber, MagicNumber+10000)` and drops everything else (`ea/FORGE.mq5:16150-16152`). `SeedScalperGroupCounter()` computes `off = pm - MagicNumber` from the current input, then only recognizes offsets in the primary/cascade/recovery bands (`ea/FORGE.mq5:16230-16236`, `ea/FORGE.mq5:16245-16251`). Code path: operator changes `MagicNumber` during an open XAUUSD session, EA reloads, old positions have broker magics based on the previous base, `RebuildGroups()` does not rebuild them, `SeedScalperGroupCounter()` does not seed from them, and management/cascade/recovery logic no longer sees them as FORGE groups. This is a live-trading break, not just a logging issue.

## 2. Design concerns (works but architecturally suspect) — rationale required

- **§B.8.2 is not matched verbatim for killzone atoms.** The spec says MSS continuation favors `{LONDON_OPEN_KZ, NY_AM_KZ}` (`docs/FORGE_SETUP_ICT_MAP.md:625`), while `Atom_KillzoneFavorable(1,*)` checks `LONDON_OPEN_KZ || NY_OPEN_KZ` (`ea/include/Forge/IctScoring.mqh:144-147`). The spec says liquidity-sweep reversal favors `{LONDON_OPEN_KZ, NY_PM_KZ}` (`docs/FORGE_SETUP_ICT_MAP.md:649`), while code checks `LONDON_OPEN_KZ || LONDON_CLOSE_KZ` and comments it as a NY_PM proxy (`ea/include/Forge/IctScoring.mqh:152-155`). Maybe `NY_OPEN_KZ`/`NY_AM_KZ` is intended aliasing, and maybe London Close is intentional until NY_PM ships, but the requested verbatim alignment is false.

- **Cat 3 wick-quality scoring collapses the documented 0/1/2 magnitude tier into an all-or-nothing threshold.** §B.8.2 says `atom_sweep_wick_quality` is weight 2 and should threshold-tier `g_ict_last_sweep_wick_atr_mult` into `0/1/2` (`docs/FORGE_SETUP_ICT_MAP.md:645-647`). `ComputeCategoryScore(3,*)` awards the full 2 points whenever `g_ict_last_sweep_rejection_score >= 0.5` (`ea/include/Forge/IctScoring.mqh:330-340`). That is a design drift: weak acceptable sweeps and high-quality sweeps become indistinguishable.

- **OB ring rebuild keeps the oldest 16 candidates, not the newest 16.** `Forge_DetectOrderBlocks()` scans `for(int i = lookback_bars; i >= 3; i--)` and breaks as soon as `g_ob_ring_count >= 16` (`ea/include/Forge/IctOrderBlock.mqh:107-108`). Because MQL shifts get newer as `i` decreases, a fast 50-bar window with more than 16 qualifying OBs keeps older zones and never evaluates the newer ones. The retained zones then feed `g_ict_last_atom_ob_broken` and breaker/confluence atoms (`ea/include/Forge/IctOrderBlock.mqh:251-260`). This is not a buffer overflow, but it loses the most relevant OBs in exactly the high-volatility regime where breaker logic matters.

- **“Last opposite candle before displacement” is implemented as “immediately previous candle only.”** The detector sets `ob_shift = i + 1` and tests only that one candle for opposite color (`ea/include/Forge/IctOrderBlock.mqh:115-124`). If the intended ICT rule is strictly the adjacent candle before the displacement candle, this is fine. If the intended rule is the last opposite candle before a multi-candle impulse leg, this misses valid OBs where one or more same-direction candles precede the large displacement candle. The comments say “last opposite-direction candle BEFORE a displacement leg” (`ea/include/Forge/IctOrderBlock.mqh:16-19`), which is broader than the code.

- **Current comment length can exceed the documented budget because legacy setup names are passed through.** The doc’s length table says worst case is 63 chars using compact ICT category codes (`docs/FORGE_ICT_COMMENT_CODES.md:273-285`), but rollout explicitly says legacy `setup_type` strings still appear in field 1 during transition (`docs/FORGE_ICT_COMMENT_CODES.md:300-304`). The builder appends legacy names as-is unless they end in `_BUY`/`_SELL` (`ea/include/Forge/IctComment.mqh:108-116`, `ea/include/Forge/IctComment.mqh:162-169`), and live call sites pass values like `g_groups[gi].scalper_setup` (`ea/FORGE.mq5:16496-16498`, `ea/FORGE.mq5:16623-16625`). A long legacy name plus `SK_BUY_LIMIT_RECOV` can exceed 63 before broker truncation is considered.

- **`PlaceMarketBatch()` mutates the canonical comment shape after the builder returns.** `PlaceOpenGroupLeg()` builds a full canonical comment (`ea/FORGE.mq5:17516-17520`) and passes it to `PlaceMarketBatch()` (`ea/FORGE.mq5:17610-17616`, `ea/FORGE.mq5:17627-17633`). The batch helper then appends `|L<n>` (`ea/FORGE.mq5:17306-17313`). Per the comment spec, field 6 is reserved for optional `<SK_DETAIL>` only (`docs/FORGE_ICT_COMMENT_CODES.md:210-220`). On non-SK batch market legs, the parser will see `L1` in the optional SK-detail slot; on SK legs it creates an eighth segment. That is a concrete parser-fragility bug in one migrated comment path.

- **EA migrations intentionally swallow all `ALTER TABLE` failures, including real failures.** Existing-column failures are expected and harmless, but the EA runs every `ALTER TABLE SIGNALS ADD COLUMN ...` without checking `DatabaseExecute()` return status (`ea/FORGE.mq5:10340-10349`). Scribe does a safer pattern: check column presence, execute ALTER, and re-raise non-duplicate errors (`python/scribe.py:1093-1100`). If the MT5 DB is locked or corrupt during an EA migration, the EA can proceed with a missing column until `JournalRecordSignal()` insert fails later (`ea/FORGE.mq5:10835-10838`).

## 3. Minor / cosmetic (improvements, not bugs)

- **The pre-TP1 recovery seed math is conservative but mislabeled.** Pre-TP1 orders use `grp_magic + 30009` (`ea/FORGE.mq5:16845-16860`), so exact group recovery would subtract `30009`; the seed helper subtracts `30000` (`ea/FORGE.mq5:16233-16236`, `ea/FORGE.mq5:16248-16251`). This overestimates group id by 9, which is collision-safe, but the comment says the band is `group_id + 30009` (`ea/FORGE.mq5:16211-16215`) and the math does not spell out the intentional overestimate for recovery the way it does for cascade (`ea/FORGE.mq5:16216-16222`).

- **The docs still contain stale implementation-status text for the comment module.** The live module has the expanded `Forge_BuildScalpComment()` implementation (`ea/include/Forge/IctComment.mqh:148-170`), but the doc still lists helper expansion as pending (`docs/FORGE_ICT_COMMENT_CODES.md:335-344`). That can mislead future parser work, though it does not affect the EA.

- **The Cat 4 comment in `IctScoring.mqh` still says `breaker_present`.** The code correctly uses `g_ict_last_atom_ob_broken` (`ea/include/Forge/IctScoring.mqh:342-348`), but the comment above it says `breaker_present(3)` (`ea/include/Forge/IctScoring.mqh:343-345`). It is cosmetic drift after the v2.7.136 rename.

## 4. What looks correct (specific praise with file:line — confirms audit was thorough)

- **OB displacement gate matches the requested 1.5x ATR body test.** Defaults set `ict_ob_displacement_min_atr = 1.5` (`ea/FORGE.mq5:5315-5319`), JSON loaders wire it (`ea/FORGE.mq5:6076-6080`), and detection requires `MathAbs(close-open) >= displacement_min_atr * atr` (`ea/include/Forge/IctOrderBlock.mqh:110-114`).

- **The OB FVG confirmation uses the canonical three-bar gap around the displacement candle.** For displacement shift `i`, code compares newer bar `i-1` against older bar `i+1`: bullish `low_after > high_before`, bearish `high_after < low_before` (`ea/include/Forge/IctOrderBlock.mqh:126-134`). That matches the existing FVG module’s canonical high-oldest/low-newest rule (`ea/include/Forge/IctStructure.mqh:333-367`, `ea/include/Forge/IctStructure.mqh:381-409`).

- **Broken-state tracking uses closes, not wick pierces.** A bullish OB is marked broken only on close below its low, and bearish only on close above its high (`ea/include/Forge/IctOrderBlock.mqh:161-172`). That matches the module’s own “body close past extreme” contract (`ea/include/Forge/IctOrderBlock.mqh:25-27`, `ea/include/Forge/IctOrderBlock.mqh:153-156`).

- **Breaker retest tolerance is symmetric for BUY and SELL.** Both sides use `MathAbs(mid - level) <= tol` with the same `tol = retest_tolerance_atr * atr`; failed bullish OB sets the SELL retest atom at `OB.low`, failed bearish OB sets the BUY retest atom at `OB.high` (`ea/include/Forge/IctOrderBlock.mqh:182-210`).

- **OB globals are rebuilt before Cat 2 and Cat 4 composite scoring reads them.** `ForgeEvalAtoms()` enables OB rebuild when either OTE or breaker scoring is on (`ea/FORGE.mq5:8293-8305`), populates OB confluence globals (`ea/FORGE.mq5:8306-8310`), and only then calls all four `ComputeCategoryScore()` blocks (`ea/FORGE.mq5:8324-8358`). Cat 1 MSS_CONT does not read OB globals (`ea/include/Forge/IctScoring.mqh:294-313`), so the ordering is sufficient for all four composites.

- **Schema parity count is correct in scribe.** The `forge_signals` INSERT column list has 168 columns, and the placeholder expression is exactly `41 + 24 + 45 + 7 + 5 + 9 + 8 + 19 + 1 + 7 + 2 = 168` (`python/scribe.py:1801-1912`). The v2.7.136 tail columns are present in EA CREATE (`ea/FORGE.mq5:10085-10100`), EA INSERT (`ea/FORGE.mq5:10630-10637`, `ea/FORGE.mq5:10809-10820`), scribe CREATE (`python/scribe.py:281-291`), scribe ALTER (`python/scribe.py:1080-1092`), scribe SELECT (`python/scribe.py:1694-1698`), and scribe INSERT (`python/scribe.py:1883-1888`).

- **The old `atom_breaker_present` rename is handled as an orphan, not a live writer.** EA CREATE and INSERT use `atom_ob_broken` (`ea/FORGE.mq5:10085-10090`, `ea/FORGE.mq5:10809-10812`), scribe uses `atom_ob_broken` (`python/scribe.py:281-283`, `python/scribe.py:1496-1506`), and the EA migration comment explicitly acknowledges old DBs may retain dead `atom_breaker_present` (`ea/FORGE.mq5:10335-10340`).

## 5. Recommended follow-up ships (concrete fixes ranked by leverage)

- **1. Add a hard startup guard for `MagicNumber` changes with open FORGE positions/orders.** Either persist the last magic base and refuse to trade/manage when broker state exists under another base, or scan comments/group IDs independent of magic base before seeding. This closes the only issue here that can directly orphan live positions.

- **2. Change OB detection to retain newest candidates.** Scan from newest to oldest, or collect all candidates then keep the most recent 16. This fixes Cat 2/Cat 4 freshness without changing the atom schema.

- **3. Make §B.8.2 names and code exact.** Decide whether `NY_OPEN_KZ` is the canonical name for NY AM and whether `LONDON_CLOSE_KZ` is a deliberate NY_PM proxy. Then update either `docs/FORGE_SETUP_ICT_MAP.md` or `Atom_KillzoneFavorable()` so future reviews do not have to infer aliases.

- **4. Fix comment-shape post-processing.** Remove `|L<n>` appending in `PlaceMarketBatch()` or make leg identity occupy the existing `<TP_OR_LEG>` field before calling `Forge_BuildScalpComment()`. Add a parser self-test for 6/7 segment counts.

- **5. Replace EA blind ALTERs with checked migrations.** Keep duplicate-column tolerance, but log or abort on lock/corruption/SQL errors so schema parity failures are visible before `JournalRecordSignal()` starts dropping rows.
