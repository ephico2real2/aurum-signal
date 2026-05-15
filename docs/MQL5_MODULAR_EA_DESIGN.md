# MQL5 modular EA design — FORGE convention (v2.7.118+)

**Status**: canonical reference for FORGE's first modular ship (v2.7.118 ICT integration). Defines the include layout, build pipeline, and rules every future module must follow.

## §1 Why modular now

FORGE.mq5 is at 16,598 lines, ~1MB source. The ICT integration (`docs/prompts/ICT_Tradingidea.md`) adds 15+ concepts × ~200-500 LOC each = 3-5k more lines. Monolithic ships:

- compile slowly (the whole file re-tokenizes per build)
- review badly (PRs become unreadable diffs)
- collide on parallel work (one engineer touches MSS, another touches FVG → merge hell)
- make ownership unclear (who owns the ICT layer? the cascade layer?)

Modular `.mqh` includes resolve all four. The `.ex5` artifact stays single-binary (MQL5 has no DLL-style runtime linking — `.mqh` is preprocessor textual inclusion at compile time), so there's no runtime cost.

## §2 MQL5 include mechanics — what to know

### §2.1 Two include forms

| Form | Lookup | When to use |
|---|---|---|
| `#include <Foo\Bar.mqh>` | `MQL5/Include/Foo/Bar.mqh` (canonical) | Standard libs + cross-EA shared modules |
| `#include "Bar.mqh"` | Relative to current source file | Single-EA private helpers (rare in MT5) |

FORGE uses the **angle-bracket form**. Source mirrors Wine path: `ea/include/Forge/IctStructure.mqh` → `MQL5/Include/Forge/IctStructure.mqh`, included as `#include <Forge\IctStructure.mqh>` (note backslash — MQL5 follows Windows conventions even on macOS Wine).

### §2.2 Preprocessor model

`.mqh` is **textual inclusion** (like C `#include`), not module linking:
- Single-pass top-down preprocessing
- Functions / structs / globals declared in `.mqh` become available at every site AFTER the include
- Multiple includes of the same `.mqh` cause **duplicate-symbol errors** without include guards
- Build artifact (`.ex5`) is self-contained — the .mqh source isn't needed at runtime

### §2.3 Include guards — mandatory

Every `.mqh` MUST have:

```mql5
#ifndef __FORGE_ICT_STRUCTURE_MQH__
#define __FORGE_ICT_STRUCTURE_MQH__

// module contents

#endif // __FORGE_ICT_STRUCTURE_MQH__
```

Naming convention: `__FORGE_<MODULE>_MQH__` (uppercase, underscored, leading/trailing double underscores). MQL5 does not auto-generate guards — you write them by hand and FORGE convention is to use the file path.

### §2.4 Property declarations

`#property` directives in `.mqh` are **inert** — they only take effect in the top-level `.mq5`. So `#property version "2.7.118"` belongs in FORGE.mq5, not in any module.

### §2.5 No namespaces in pre-2018 MQL5

Older MQL5 (pre-2018) has no namespaces. Modern MQL5 supports `class` scoping and (loosely) namespace blocks, but the **community convention** is still procedural functions with prefix naming: `Forge_DetectMSS()`, `Forge_DetectFVG()`. We follow that — every public function in a Forge module is prefixed `<module>_<action>` or just keeps the canonical ICT name (e.g., `DetectBullishMSS()`) if the function name itself is unambiguous.

For FORGE, we keep function names **unprefixed** when the name is already domain-specific (`DetectBullishMSS`, `DetectBullishFVG`). Module-private helpers get an underscore prefix (`_ResetFvgRing()`).

## §3 FORGE module layout

```
signal_system/
├── ea/
│   ├── FORGE.mq5                              ← top-level, has OnInit/OnTick/OnDeinit
│   └── include/                               ← source mirror of Wine MQL5/Include/
│       └── Forge/                             ← namespace folder
│           ├── IctStructure.mqh               ← v2.7.118 (swing/MSS/FVG)
│           ├── IctLiquidity.mqh               ← v2.7.119 (ChoCH + liquidity sweep)
│           ├── IctOrderBlock.mqh              ← v2.7.120 (OB + breaker)
│           ├── IctScoring.mqh                 ← v2.7.121 (Unicorn + ICT score)
│           └── IctIntradayModel.mqh           ← v2.7.122 (CRT + Venom + B&B + S&D)
```

Each module has:
- An include guard
- A header docblock (PURPOSE / DEPENDENCIES / EXPORTS / CHANGELOG)
- Module globals (declared `static` if file-private, plain otherwise)
- Module structs (e.g., `FVGZone`, `SwingPoint`, `OrderBlockZone`)
- Module functions (free functions, prefixed only if name would collide)

FORGE.mq5 lists includes near the top after `#property strict`:

```mql5
#include <Trade\Trade.mqh>           // existing
#include <Trade\PositionInfo.mqh>     // existing
#include <Files\FileTxt.mqh>          // existing
#include <Forge\IctStructure.mqh>     // v2.7.118 NEW
```

Wine compile target sees:
```
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/
├── Experts/
│   └── FORGE.mq5                              ← synced by compile_forge_ea_macos.sh
└── Include/
    └── Forge/
        └── IctStructure.mqh                   ← synced by compile_forge_ea_macos.sh (v2.7.118 update)
```

## §4 Dependency rules

1. **One-way dependency graph**. `Forge/IctStructure.mqh` (lower level) can be included by `Forge/IctScoring.mqh` (higher level). Never the reverse.
2. **No mutual includes**. Module A and module B cannot both include each other (even with guards) — the second include is a no-op and you'll get unresolved-symbol errors.
3. **FORGE.mq5 is the top of the graph**. Modules can read `g_sc` (config struct) and other FORGE globals declared in FORGE.mq5 IF the module's include statement appears AFTER the global is declared in FORGE.mq5. Order matters.
4. **Prefer explicit params over hidden globals** in module functions. `DetectBullishMSS(double m5_close, double m5_atr, double recent_swing_high)` is testable; `DetectBullishMSS()` that reads from globals is not.
5. **Module globals stay in the module**. `g_swing_highs[]`, `g_fvg_ring[]` are declared in `Forge/IctStructure.mqh`. FORGE.mq5 references them via the include.

## §5 Globals strategy

Three classes of state:

| Class | Where defined | Example |
|---|---|---|
| **Config** (read-only after init) | FORGE.mq5 (`g_sc` struct) | `g_sc.ict_mss_enabled` |
| **Module-private state** | The module's `.mqh` | `g_fvg_ring[16]`, `g_swing_count` |
| **Shared atom output** | FORGE.mq5 (existing globals) | `g_iss_mss`, `g_iss_fvg`, `g_iss_score` |

The module computes and **writes** to shared atoms (`g_iss_mss = 1`) but **reads** from config (`g_sc.ict_mss_enabled`). This keeps FORGE.mq5 as the source-of-truth for "what the EA decided to do" while delegating heavy lifting to the module.

## §6 Function-signature conventions (FORGE)

Reuse the same header convention as monolithic FORGE (per `.claude/skills/forge-monitor/SKILL.md` "FORGE EA CODE STANDARDS"):

```mql5
// ─────────────────────────────────────────────────────────────────────────────
// DetectBullishMSS — Market Structure Shift, bullish direction
//
// PURPOSE: Detect a body-close break of the most recent M5 swing high with
//   sufficient displacement. Used as the primary "structure-confirmed reversal/
//   continuation" signal for the ICT Phase 1 ISS atom (g_iss_mss).
//
// PARAMETERS:
//   m5_close              — current M5 bar close (NormalizeDouble'd to Digits)
//   m5_open               — current M5 bar open
//   m5_atr                — M5 ATR(14) at current bar
//   recent_swing_high     — most recent confirmed swing high from g_swing_highs[]
//   displacement_atr_mult — minimum body / ATR ratio for "displacement" (e.g. 0.5)
//
// RETURNS: true iff (close > swing_high) AND (|close - open| >= mult * atr)
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship (first modular ICT module).
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBullishMSS(double m5_close, double m5_open, double m5_atr,
                      double recent_swing_high, double displacement_atr_mult)
{
   if(recent_swing_high <= 0.0 || m5_atr <= 0.0) return false;
   if(m5_close <= recent_swing_high) return false;
   double body = MathAbs(m5_close - m5_open);
   return (body >= displacement_atr_mult * m5_atr);
}
```

## §7 Build pipeline (`make forge-compile`)

The Wine sync now copies BOTH the EA AND the include tree:

```bash
# scripts/compile_forge_ea_macos.sh excerpt:
cp -f "${SRC}" "${DST_MQ5}"                           # FORGE.mq5 → Wine Experts/
find "${INCLUDE_SRC_DIR}" -type f -name "*.mqh" | \   # ea/include/**/*.mqh
   while read mqh; do
      rel="${mqh#${INCLUDE_SRC_DIR}/}"
      cp -f "${mqh}" "${INCLUDE_DST_DIR}/${rel}"      # → Wine MQL5/Include/{rel}
   done
```

Source mirrors Wine path 1:1. The MetaEditor CLI compile resolves `#include <Forge\IctStructure.mqh>` against the synced Wine path, produces a single `FORGE.ex5` containing all included module code inline.

### §7.1 Edit + compile loop

1. Edit `ea/include/Forge/IctStructure.mqh` (and/or `ea/FORGE.mq5`)
2. `make forge-compile` → syncs all `.mqh` + the `.mq5`, runs MetaEditor compile
3. Build artifact is `<wine>/MQL5/Experts/FORGE.ex5` (self-contained)

### §7.2 Module-only edits

If you edit ONLY a `.mqh` (no `.mq5` change), `make forge-compile` still works — the script doesn't check what changed, it re-syncs and re-compiles every time. Build is ~5-10 sec.

## §8 Industry references

| Source | Pattern |
|---|---|
| MetaQuotes standard library at `MQL5/Include/` (shipped with every MT5 install) | Subfolder per concern: `Trade/`, `Arrays/`, `Indicators/`, `Math/`, etc. Single-file modules with include guards |
| [MQL5 docs — Custom Includes](https://www.mql5.com/en/docs/basis/preprocessor/include) | "The `#include` command can be put anywhere... The file content is included into the file being compiled at the location of the directive." |
| [Trade\Trade.mqh](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade) | Canonical `CTrade` class wrapper — every FORGE.mq5 already uses this pattern via `#include <Trade\Trade.mqh>` + `g_trade.OrderSend(...)` |
| [mql5.com community — Modular EA design](https://www.mql5.com/en/articles/3651) | "Break your strategy into independently testable, reusable components" |

FORGE convention follows the standard MQL5 library structure: subfolder namespace (`Forge/`), one concern per file, include guards, header docblocks, procedural functions with `class`-free composition.

## §9 Phase 1 module (v2.7.118)

`ea/include/Forge/IctStructure.mqh` will export:

| Export | Type | Used by |
|---|---|---|
| `struct FVGZone` | struct | FORGE.mq5 + later modules (IctScoring) |
| `struct SwingPoint` | struct | FORGE.mq5 + IctLiquidity, IctOrderBlock |
| `g_swing_highs[]`, `g_swing_lows[]` | globals | FORGE.mq5 (read), IctLiquidity (read) |
| `g_fvg_ring[16]`, `g_fvg_ring_count` | globals | FORGE.mq5 (read), IctScoring (read) |
| `DetectSwingHigh(int lookback)` | function | FORGE.mq5 (M5-close tick) |
| `DetectSwingLow(int lookback)` | function | FORGE.mq5 (M5-close tick) |
| `DetectBullishMSS(...)` | function | FORGE.mq5 (setup-trigger fire) |
| `DetectBearishMSS(...)` | function | FORGE.mq5 (setup-trigger fire) |
| `DetectStructureBreak(...)` | function | internal + FORGE.mq5 (chokepoint sweep) |
| `DetectDisplacementCandle(...)` | function | internal helper |
| `DetectBullishFVG(...)` | function | FORGE.mq5 (M5-close tick — appends to ring) |
| `DetectBearishFVG(...)` | function | FORGE.mq5 (M5-close tick) |
| `IsValidFVG(int idx)` | function | FORGE.mq5 |
| `IsFVGMitigated(int idx)` | function | FORGE.mq5 |
| `IsFVGPartiallyMitigated(int idx)` | function | FORGE.mq5 |
| `GetFVGMidpoint(int idx)` | function | FORGE.mq5 |
| `ScoreFVG(int idx, ...)` | function | IctScoring (v2.7.121) |

FORGE.mq5 changes are minimal:
1. Add `#include <Forge\IctStructure.mqh>` near the top
2. Remove the v2.7.112 inline ISS stubs (`g_iss_mss = 0`, `g_iss_fvg = 0`)
3. At the setup-trigger chokepoint, call the new functions to compute the atom values
4. Add 5 new env knobs + struct fields + loader code (in FORGE.mq5, not the module — config is FORGE.mq5's concern)

## §10 Anti-patterns (rejected)

- ❌ **Mutually-recursive includes** — A includes B includes A. Guards prevent the loop but cause unresolved symbols.
- ❌ **Module-defined `#property version`** — only the top-level `.mq5` has it.
- ❌ **Heavy class hierarchies for procedural ICT logic** — `class IctDetector { virtual bool detect() = 0; ... }` is over-engineered for free functions like `DetectBullishMSS()`. Use classes when there's genuine state encapsulation (FVG ring buffer COULD be a class; we keep it procedural for v2.7.118 consistency with current FORGE style, may refactor later).
- ❌ **Module without an include guard** — even if "only used once" now, the first time someone includes it twice transitively, compile breaks.
- ❌ **Implicit dependency on FORGE globals** — `DetectBullishMSS()` reading `g_eval_h4_trend` directly is brittle. Pass it as a parameter.
- ❌ **Hidden side effects** — `DetectBullishFVG()` that secretly mutates `g_iss_fvg` is confusing. Return the value; let FORGE.mq5 assign it explicitly.

## §11 Changelog

- **2026-05-14** — Initial design doc for FORGE's first modular ship (v2.7.118 ICT Phase 1). Codifies the `ea/include/Forge/` source layout, Wine `MQL5/Include/Forge/` mirror target, include-guard naming, function-header convention, and dependency rules. Build pipeline updated at `scripts/compile_forge_ea_macos.sh` (recursive sync of `.mqh` modules to Wine).
