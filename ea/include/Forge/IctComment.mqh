//+------------------------------------------------------------------+
//| Forge\IctComment.mqh                                              |
//| FORGE v2.7.132 — ICT-canonical broker-comment builder             |
//| Phase 6 of the ICT integration (utility module).                  |
//| See docs/FORGE_ICT_COMMENT_CODES.md for the canonical spec.       |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_COMMENT_MQH__
#define __FORGE_ICT_COMMENT_MQH__

// ─────────────────────────────────────────────────────────────────────────────
// PURPOSE  (Phase 6 — v2.7.132)
//   Single source of truth for the FORGE broker-comment string. Implements
//   the zone-leading scheme defined in docs/FORGE_ICT_COMMENT_CODES.md.
//
//   Canonical comment shape (all trades — primary + cascade + recovery):
//     <ZONE>_<ORDER_TYPE>|<CAT>_<DIR>|G<GROUP_ID>|<TP_OR_LEG>|<KZ_DETAIL>|<CONV>[|<SK_DETAIL>]
//
//   Examples:
//     KZ_MKT|MSS_CONT_B|G5001|TP1|LDN_OPEN_KZ|H
//     SK_MKT|OTE_RETR_S|G5002|TP2|NY_PM_KZ|H|PM_SK
//     OFF_MKT|LIQ_SWEEP_B|G5003|TP1|OFF|L
//     KZ_BUY_STOP_CONT|LIQ_SWEEP_B|G5003|L2|LDN_CL_KZ|H
//
//   Operator decision 2026-05-16: apply to ALL new trades immediately.
//   Legacy SCALP_* family is dead code from this point forward.
//
// CONVENTIONS
//   - Pure-function module. No state. No globals.
//   - All helpers take fully-typed inputs (strings, ints) and return strings.
//     The caller (entry-placement code) reads g_regime.* globals + composite
//     scores + group state and passes them in.
//   - Direction encoded as single char (B / S) per operator preference;
//     direction is also recoverable from the broker deal-type field.
//   - Unknown / off-session inputs degrade to "OFF" / "?" rather than empty
//     string — keeps parser field count stable.
// ─────────────────────────────────────────────────────────────────────────────

//+------------------------------------------------------------------+
//| Forge_ZonePrefix                                                  |
//| Map current killzone + silver-bullet state → 3-code zone prefix.  |
//| Inputs are the canonical labels from g_regime.killzone /          |
//| g_regime.silver_bullet (empty string = inactive).                 |
//| Returns: "SK" (SK implies KZ — checked first) | "KZ" | "OFF".     |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_ZonePrefix(const string kz_label, const string sb_label) {
   if(StringLen(sb_label) > 0) return "SK";
   if(StringLen(kz_label) > 0) return "KZ";
   return "OFF";
}

//+------------------------------------------------------------------+
//| Forge_KillzoneDetailCode                                          |
//| Map the canonical KZ label (from g_regime.killzone) to its        |
//| comment-segment code. Returns "OFF" for empty input.              |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_KillzoneDetailCode(const string canonical_kz) {
   if(canonical_kz == "ASIAN_KZ")         return "ASIA_KZ";
   if(canonical_kz == "LONDON_OPEN_KZ")   return "LDN_OPEN_KZ";
   if(canonical_kz == "NY_OPEN_KZ")       return "NY_OPEN_KZ";
   if(canonical_kz == "LONDON_CLOSE_KZ")  return "LDN_CL_KZ";
   if(canonical_kz == "NY_PM_KZ")         return "NY_PM_KZ";
   return "OFF";
}

//+------------------------------------------------------------------+
//| Forge_SilverKnifeDetailCode                                       |
//| Map the canonical Silver Bullet label (from g_regime.silver_bullet)|
//| to its comment-segment code. Returns "" for empty/inactive — the  |
//| caller skips emitting the optional 7th segment in that case.      |
//| Note: internal canonical name is SILVER_BULLET; operator-preferred|
//| comment vocabulary is SILVER_KNIFE / SK. Both refer to the same   |
//| ICT 60-min hyper-concentrated FVG-entry windows.                  |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_SilverKnifeDetailCode(const string canonical_sb) {
   if(canonical_sb == "LONDON_SB") return "LDN_SK";
   if(canonical_sb == "AM_SB")     return "AM_SK";
   if(canonical_sb == "PM_SB")     return "PM_SK";
   return "";
}

//+------------------------------------------------------------------+
//| Forge_ConvictionLetter                                            |
//| Bucket the category-matched composite score (0-10) into a 1-char  |
//| conviction tag. Pass -1 (or any negative) for "no score" / legacy |
//| setup pre-M9 fold.                                                |
//| Buckets: H ≥ 7  |  M 4-6  |  L 1-3  |  ? <1 or negative.          |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_ConvictionLetter(const int composite_score) {
   if(composite_score >= 7) return "H";
   if(composite_score >= 4) return "M";
   if(composite_score >= 1) return "L";
   return "?";
}

//+------------------------------------------------------------------+
//| Forge_AppendDirectionSuffix                                       |
//| Append _B / _S to a setup-or-category name unless the name        |
//| ALREADY encodes direction (ends in _BUY / _SELL). Handles the     |
//| pre-M7-fold mixed-vocabulary phase where some legacy setup_types  |
//| bake direction (ASIA_CAPITULATION_BUY) and others don't           |
//| (BB_BREAKOUT + direction arg).                                    |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_AppendDirectionSuffix(const string setup_or_cat, const string direction) {
   int len = StringLen(setup_or_cat);
   if(len > 4 && StringSubstr(setup_or_cat, len-4) == "_BUY")  return setup_or_cat;
   if(len > 5 && StringSubstr(setup_or_cat, len-5) == "_SELL") return setup_or_cat;
   string d = direction;
   StringToUpper(d);
   if(d == "BUY")  return setup_or_cat + "_B";
   if(d == "SELL") return setup_or_cat + "_S";
   return setup_or_cat;  // unknown direction — leave bare
}

//+------------------------------------------------------------------+
//| Forge_BuildScalpComment                                           |
//| THE canonical comment builder. Used by ALL 11 order-placement     |
//| sites in FORGE.mq5 (primary entry, limit, cascade, recovery).     |
//|                                                                   |
//| PARAMETERS:                                                       |
//|   order_type_code  — "MKT" / "LIMIT" / "LIMIT_L2" /               |
//|                       "BUY_STOP_CONT" / "SELL_STOP_CONT" /        |
//|                       "BUY_LIMIT_RECOV" / "SELL_LIMIT_RECOV" /    |
//|                       "PRE_TP1_RECOV"                             |
//|   setup_or_cat     — legacy setup_type ("BB_BREAKOUT",            |
//|                       "ASIA_CAPITULATION_BUY", ...) OR ICT short  |
//|                       category code ("MSS_CONT", "LIQ_SWEEP", ...)|
//|   direction        — "BUY" / "SELL" (ignored if setup_or_cat      |
//|                       already ends in _BUY / _SELL)               |
//|   group_id         — FORGE group id (4-digit Gxxxx range)         |
//|   tp_or_leg        — "TP1".."TP4" / "L1".."L4" / "R1".."R3"       |
//|   kz_label         — g_regime.killzone (canonical, e.g.           |
//|                       "LONDON_OPEN_KZ" or empty for off-session)  |
//|   sb_label         — g_regime.silver_bullet (canonical, e.g.      |
//|                       "LONDON_SB" or empty for inactive)          |
//|   composite_score  — 0-10 category-matched composite score for    |
//|                       conviction tag. -1 for legacy/no-score.     |
//|                                                                   |
//| RETURNS:                                                          |
//|   Full pipe-delimited comment per FORGE_ICT_COMMENT_CODES.md §2.1 |
//|                                                                   |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
string Forge_BuildScalpComment(const string order_type_code,
                               const string setup_or_cat,
                               const string direction,
                               const long   group_id,
                               const string tp_or_leg,
                               const string kz_label,
                               const string sb_label,
                               const int    composite_score) {
   string zone     = Forge_ZonePrefix(kz_label, sb_label);
   string cat_dir  = Forge_AppendDirectionSuffix(setup_or_cat, direction);
   string kz_det   = Forge_KillzoneDetailCode(kz_label);
   string conv     = Forge_ConvictionLetter(composite_score);
   string sk_det   = Forge_SilverKnifeDetailCode(sb_label);

   string out = zone + "_" + order_type_code + "|"
              + cat_dir + "|"
              + "G" + IntegerToString(group_id) + "|"
              + tp_or_leg + "|"
              + kz_det + "|"
              + conv;
   if(StringLen(sk_det) > 0) out += "|" + sk_det;
   return out;
}

//+------------------------------------------------------------------+
//| Forge_IctComment_SelfTest                                         |
//| Called once at EA OnInit. Builds 8 canonical sample comments and  |
//| prints them so the operator can visually verify the codes line    |
//| up with the spec. No side effects, no order placement.            |
//| CHANGELOG: v2.7.132 created.                                      |
//+------------------------------------------------------------------+
void Forge_IctComment_SelfTest() {
   Print("FORGE ICT-COMMENT SELF-TEST (v2.7.132) — 8 canonical shapes:");
   PrintFormat("  [1] %s",
      Forge_BuildScalpComment("MKT",            "MSS_CONT",   "BUY",  5001, "TP1", "LONDON_OPEN_KZ", "",          8));
   PrintFormat("  [2] %s",
      Forge_BuildScalpComment("MKT",            "OTE_RETR",   "SELL", 5002, "TP2", "NY_PM_KZ",       "PM_SB",     9));
   PrintFormat("  [3] %s",
      Forge_BuildScalpComment("MKT",            "LIQ_SWEEP",  "BUY",  5003, "TP1", "",               "",          3));
   PrintFormat("  [4] %s",
      Forge_BuildScalpComment("BUY_STOP_CONT",  "LIQ_SWEEP",  "BUY",  5003, "L2",  "LONDON_CLOSE_KZ","",          7));
   PrintFormat("  [5] %s",
      Forge_BuildScalpComment("BUY_LIMIT_RECOV","MSS_CONT",   "BUY",  5001, "R1",  "LONDON_OPEN_KZ", "LONDON_SB", 8));
   PrintFormat("  [6] %s",
      Forge_BuildScalpComment("PRE_TP1_RECOV",  "BRK_RETEST", "SELL", 5004, "R1",  "NY_OPEN_KZ",     "",          5));
   PrintFormat("  [7] %s",
      Forge_BuildScalpComment("LIMIT",          "BB_BREAKOUT","BUY",  5005, "TP1", "",               "",         -1));
   PrintFormat("  [8] %s",
      Forge_BuildScalpComment("MKT","ASIA_CAPITULATION_BUY",  "BUY",  5006, "TP1", "ASIAN_KZ",       "",         -1));
}

#endif // __FORGE_ICT_COMMENT_MQH__
