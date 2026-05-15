Here is a strong Claude prompt you can copy/paste:

```text
You are an elite MT5/MQL5 automated trading systems architect and ICT/Smart Money Concepts strategy engineer.  Adopt your own standard as yu see fit.

I am deploying an automated trading EA called FORGE for MetaTrader 5. The EA must implement and improve ICT-style logic including:

- MSS: Market Structure Shift
- ChOCh: Change of Character
- FVG: Fair Value Gap
- Valid FVG qualification
- Liquidity Sweep
- Order Blocks
- Breaker Blocks
- Unicorn Model
- Candle Range Theory
- ICT Kill Zones
- Intraday models
- Venom Model
- Bread and Butter setup
- Redelivered/Rebalanced Price Range
- Institutional Order Flow
- Seek and Destroy Friday logic

Your task is not to summarize casually. You must read deeply, extract implementation logic, convert trading ideas into programmable rules, and immediately improve the FORGE EA code.

Research these resources carefully:

1. https://innercircletrader.net/tutorials/what-is-ict-hidden-order-block/
2. https://innercircletrader.net/tutorials/candle-range-theory-crt/
3. https://innercircletrader.net/tutorials/fair-value-gap-trading-strategy/
4. https://innercircletrader.net/tutorials/valid-ict-fair-value-gap/
5. https://innercircletrader.net/tutorials/master-ict-1st-presented-fvg/
6. https://innercircletrader.net/tutorials/powerful-ict-reversal-patterns/
7. https://www.mql5.com/en/articles/18379
   Local file reference: /Users/olasumbo/Downloads/Liquidity_Sweep.mq5
8. https://www.mql5.com/en/articles/22078#para3
9. https://innercircletrader.net/tutorials/ict-redelivered-rebalanced-price-range/
10. https://innercircletrader.net/tutorials/ict-venom-trading-model-2025/
11. https://innercircletrader.net/tutorials/ict-intraday-trading-strategy/
12. https://innercircletrader.net/tutorials/ict-seek-and-destroy-friday/
13. https://innercircletrader.net/tutorials/ict-bread-and-butter/
14. https://innercircletrader.net/tutorials/ict-bread-and-butter-buy-setup/
15. https://innercircletrader.net/tutorials/ict-consolidation-trading/
16. https://innercircletrader.net/tutorials/ict-institutional-order-flow-entry-drill/
17. https://innercircletrader.net/tutorials/master-ict-kill-zones/
18. https://innercircletrader.net/tutorials/ict-unicorn-model/
    Local PDF reference: /Users/olasumbo/Downloads/ICT Unicorn Model PDF Download.pdf
19. https://innercircletrader.net/tutorials/ict-breaker-block-trading/
20. http://innercircletrader.net/tutorials/ict-breaker-block-trading/

You must build a usable trading-engine memory/skill from these sources. Your output must improve FORGE, not just explain theory.

Main objectives:

1. Read all resources in detail.
2. Extract every rule that can be converted into code.
3. Separate subjective ICT language from objective programmable conditions.
4. Convert concepts into reusable MQL5 functions.
5. Update FORGE EA code immediately.
6. Preserve existing working logic unless there is a clear reason to refactor.
7. Avoid vague explanations. Every trading concept must become a rule, enum, function, score, filter, or state-machine transition.
8. Do not waste time asking broad questions. Make best-effort implementation choices and document assumptions.

Implementation focus:

A. Market Structure Shift / MSS

Implement logic to detect bullish and bearish MSS using:

- Prior swing high / swing low
- Displacement candle confirmation
- Break of internal or external structure
- Close beyond structure, not just wick, where appropriate
- Optional body-close confirmation
- ATR-based displacement filter
- Volume/tick-volume optional confirmation if available
- Session filter compatibility

Create functions like:

- DetectSwingHigh()
- DetectSwingLow()
- DetectBullishMSS()
- DetectBearishMSS()
- DetectStructureBreak()
- DetectDisplacementCandle()

B. Change of Character / ChOCh

Implement ChOCh as an early reversal clue, separate from full BOS/MSS.

Rules should consider:

- Previous trend direction
- First violation of minor/internal structure
- Liquidity sweep before reversal
- Break of short-term swing
- Displacement away from swept liquidity
- Optional FVG creation after displacement

Create functions like:

- DetectBullishChOCh()
- DetectBearishChOCh()
- DetectInternalStructureShift()
- DetectExternalStructureShift()

C. Fair Value Gap / FVG

Implement 3-candle FVG logic.

Bullish FVG:
- Candle 1 high < Candle 3 low
- Candle 2 should show displacement
- Gap size must exceed minimum points or ATR fraction

Bearish FVG:
- Candle 1 low > Candle 3 high
- Candle 2 should show displacement
- Gap size must exceed minimum points or ATR fraction

Also implement valid FVG filters:

- Minimum gap size
- Displacement strength
- Not fully mitigated
- Inside premium/discount context
- Created after MSS/ChOCh
- Created during or near kill zone
- Reject weak gaps in chop/consolidation
- Track partial mitigation
- Track full mitigation
- Track midpoint / consequent encroachment

Create structures like:

struct FVGZone {
   datetime time;
   double upper;
   double lower;
   double midpoint;
   bool bullish;
   bool mitigated;
   bool partiallyMitigated;
   int sourceBar;
   double displacementScore;
};

Create functions like:

- DetectBullishFVG()
- DetectBearishFVG()
- IsValidFVG()
- IsFVGMitigated()
- IsFVGPartiallyMitigated()
- GetFVGMidpoint()
- ScoreFVG()

D. Liquidity Sweep

Use the MQL5 article and local Liquidity_Sweep.mq5 as implementation reference.

Detect:

- Buy-side liquidity sweep
- Sell-side liquidity sweep
- Equal highs / equal lows
- Previous session high/low sweep
- Asian range sweep
- London/New York sweep
- Sweep followed by rejection candle
- Sweep followed by ChOCh/MSS
- Sweep followed by FVG

Create functions like:

- DetectBuySideLiquiditySweep()
- DetectSellSideLiquiditySweep()
- DetectEqualHighs()
- DetectEqualLows()
- DetectSweepRejection()
- ScoreLiquiditySweep()

E. Order Blocks and Hidden Order Blocks

Extract rules from ICT hidden order block and MQL5 order block article.

Implement:

- Last opposite candle before displacement
- Bullish order block
- Bearish order block
- Hidden order block logic
- Validity filters
- Mitigation tracking
- Invalidation when price closes beyond OB
- OB strength scoring

Create:

struct OrderBlockZone {
   datetime time;
   double high;
   double low;
   double midpoint;
   bool bullish;
   bool mitigated;
   bool invalidated;
   int sourceBar;
   double strengthScore;
};

Functions:

- DetectBullishOrderBlock()
- DetectBearishOrderBlock()
- DetectHiddenOrderBlock()
- IsOrderBlockMitigated()
- IsOrderBlockInvalidated()
- ScoreOrderBlock()

F. Breaker Block

Implement breaker block logic:

- Failed order block
- Price breaks through prior OB
- Retest of broken OB as breaker
- Bullish/bearish breaker context
- Confirmation with MSS/ChOCh/FVG

Create:

- DetectBullishBreakerBlock()
- DetectBearishBreakerBlock()
- IsValidBreakerBlock()
- ScoreBreakerBlock()

G. Unicorn Model

Implement Unicorn Model logic based on:

- Liquidity sweep
- MSS/ChOCh
- FVG
- Breaker block overlap
- Entry from FVG/breaker confluence
- Kill zone preference
- Risk defined beyond sweep or breaker

Create:

- DetectBullishUnicornSetup()
- DetectBearishUnicornSetup()
- ScoreUnicornSetup()

H. Candle Range Theory / CRT

Extract CRT logic and implement:

- Candle range high/low
- Manipulation outside range
- Reclaim of range
- Expansion away from range
- Session candle range
- Daily/weekly candle range bias

Create:

- DetectCRTRange()
- DetectCRTManipulation()
- DetectCRTReclaim()
- ScoreCRTSetup()

I. Kill Zones and Sessions

Implement kill zone filters:

- Asian session
- London kill zone
- New York AM kill zone
- New York PM session
- Silver Bullet-style windows if relevant
- Broker time offset configurable

Create input parameters:

input bool UseKillZoneFilter = true;
input int BrokerGMTOffset = 0;
input string LondonKillZoneStart = "02:00";
input string LondonKillZoneEnd   = "05:00";
input string NewYorkAMStart      = "08:30";
input string NewYorkAMEnd        = "11:00";

Functions:

- IsInLondonKillZone()
- IsInNewYorkKillZone()
- IsInKillZone()
- GetSessionContext()

J. Premium / Discount and PD Arrays

Implement dealing range logic:

- Recent swing high and swing low
- Equilibrium midpoint
- Discount zone for buys
- Premium zone for sells
- PD array confluence:
  - FVG
  - OB
  - Breaker
  - RDRB
  - Liquidity pool

Create:

- GetDealingRange()
- IsInPremium()
- IsInDiscount()
- GetEquilibrium()
- ScorePDArrayConfluence()

K. Scoring Engine

Do not make every signal binary. Build a scoring layer.

Example scoring:

- Liquidity sweep: 20 points
- MSS/ChOCh confirmation: 25 points
- Valid FVG: 20 points
- Kill zone alignment: 10 points
- Premium/discount alignment: 10 points
- OB/breaker confluence: 15 points

Create:

struct ICTSignalScore {
   double liquidityScore;
   double structureScore;
   double fvgScore;
   double sessionScore;
   double pdArrayScore;
   double orderBlockScore;
   double totalScore;
   bool tradeAllowed;
};

Functions:

- ScoreICTBuySetup()
- ScoreICTSellSetup()
- IsHighProbabilityICTSetup()

L. FORGE Integration

Patch the existing FORGE EA code.

You must:

1. Inspect current FORGE structure.
2. Identify where market regime, setup detector, filter chain, scoring engine, risk engine, and execution logic currently exist.
3. Add ICT logic without breaking existing compile.
4. Prefer modular functions even if FORGE remains one file.
5. Use clear naming.
6. Add input parameters for thresholds.
7. Add debug logging.
8. Add telemetry writes if SCRIBE/SQLite hooks already exist.
9. Add comments explaining trading logic.
10. Ensure code compiles in MetaEditor.

Recommended FORGE module layout if one-file EA is retained:

- Inputs and enums
- Struct definitions
- Utility functions
- Session / time functions
- Swing detection
- Liquidity detection
- Structure detection
- FVG detection
- OB / breaker detection
- Premium-discount logic
- ICT scoring engine
- Risk and execution integration
- Telemetry/SCRIBE integration
- OnInit / OnTick / OnDeinit

M. MQL5 Coding Requirements

Use valid MQL5.

Avoid Python-style syntax.

Use:

- MqlRates rates[]
- CopyRates()
- ArraySetAsSeries()
- SymbolInfoDouble()
- iATR handles where needed
- Proper error handling
- NormalizeDouble()
- _Point
- _Digits
- ENUM_TIMEFRAMES
- input parameters

The code must be practical for MT5.

N. Backtesting Readiness

Add controls for:

- Enable/disable each ICT module
- Minimum score required to trade
- Minimum FVG size
- Swing lookback
- ATR period
- Displacement ATR multiplier
- Kill zone enablement
- Session time offset
- Max spread
- Risk percent
- Stop-loss placement mode:
  - beyond liquidity sweep
  - beyond order block
  - ATR based
  - fixed points
- Take-profit mode:
  - next liquidity pool
  - fixed RR
  - opposite PD array
  - partial TP optional

O. Output Format

First, produce a concise implementation plan.

Then produce code changes.

Then provide:

1. What was added
2. What was changed
3. New input parameters
4. New structs
5. New functions
6. How to compile in MetaEditor
7. What to test in Strategy Tester
8. Any assumptions made
9. Any incomplete parts due to missing local files

Very important:

- Do not hallucinate source content.
- If a page cannot be accessed, say so and continue with available sources.
- If the local file cannot be read, ask me to upload it or paste it.
- Do not just summarize ICT theory.
- Convert everything into code-ready trading logic.
- Start modifying FORGE immediately.
- Prioritize MSS, ChOCh, FVG, Liquidity Sweep, Order Block, Breaker Block, Unicorn Model, and Kill Zone filters first.

The goal is to make FORGE a serious ICT-aware MT5 EA with reusable, testable, and configurable modules.
```
