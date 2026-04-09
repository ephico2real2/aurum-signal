#!/usr/bin/env bash
# Install FORGE.mq5 into MetaTrader 5 (macOS Wine / MetaQuotes official app).
# After this script: compile in MetaEditor (F7) and attach FORGE to your XAUUSD chart.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/ea/FORGE.mq5"
WINE_BASE="${WINEPREFIX:-${HOME}/Library/Application Support/net.metaquotes.wine.metatrader5}"
WINE_MT5="${WINE_BASE}/drive_c/Program Files/MetaTrader 5"
DST="${WINE_MT5}/MQL5/Experts/FORGE.mq5"

if [[ ! -f "${SRC}" ]]; then
  echo "❌ Missing ${SRC}"
  exit 1
fi
if [[ ! -d "${WINE_MT5}/MQL5" ]]; then
  echo "❌ MetaTrader 5 Wine folder not found:"
  echo "   ${WINE_MT5}"
  echo "   Install MT5 from MetaQuotes or set WINEPREFIX."
  exit 1
fi

mkdir -p "$(dirname "${DST}")"
cp -f "${SRC}" "${DST}"
# FORGE writes JSON to Terminal Common/Files (FILE_COMMON). A stale copy here confuses tools that glob Wine.
ORPHAN_JSON="${WINE_MT5}/MQL5/Files/market_data.json"
if [[ -f "${ORPHAN_JSON}" ]]; then
  rm -f "${ORPHAN_JSON}"
  echo "✓ Removed orphan MQL5/Files/market_data.json (use Common/Files → repo MT5/ symlink)"
fi
echo "✓ Installed FORGE source:"
echo "    ${DST}"
ls -la "${DST}"

# Symlink project MT5 → Terminal Common/Files (JSON bridge)
COMMON_FILES="${WINE_BASE}/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
MT5_LINK="${ROOT}/MT5"
if [[ -d "${COMMON_FILES}" ]]; then
  if [[ -L "${MT5_LINK}" ]]; then
    echo "✓ MT5 symlink already set: ${MT5_LINK} -> $(readlink "${MT5_LINK}")"
  elif [[ ! -e "${MT5_LINK}" ]]; then
    ln -s "${COMMON_FILES}" "${MT5_LINK}"
    echo "✓ Created MT5 symlink -> Common/Files"
  else
    echo "⚠ ${MT5_LINK} exists and is not a symlink — leave as-is (check FORGE FilesPath / FILE_COMMON)"
  fi
else
  echo "⚠ Common Files folder missing (expected after first MT5 login):"
  echo "   ${COMMON_FILES}"
fi

# One canonical MT5 JSON dir at repo root; python/MT5 must not be a separate folder.
PY_MT5="${ROOT}/python/MT5"
if [[ -L "${PY_MT5}" ]]; then
  echo "✓ python/MT5 -> $(readlink "${PY_MT5}")"
elif [[ -d "${PY_MT5}" ]]; then
  echo "⚠ Replacing plain directory python/MT5 with symlink -> ../MT5 (was split-brain with root MT5)"
  rm -rf "${PY_MT5}"
  ln -s ../MT5 "${PY_MT5}"
  echo "✓ python/MT5 -> ../MT5"
elif [[ ! -e "${PY_MT5}" ]]; then
  ln -s ../MT5 "${PY_MT5}"
  echo "✓ Created python/MT5 -> ../MT5"
fi

echo ""
echo "Next steps (required once after MT5 reset):"
echo "  1. Open MetaEditor: in MT5 press F4 (or Tools → MetaEditor)."
echo "  2. Open MQL5 → Experts → FORGE.mq5 → Compile (F7). You need FORGE.ex5."
echo "  3. In MT5: open your gold chart (e.g. XAUUSDm), Navigator → Expert Advisors → FORGE → drag onto chart."
echo "  4. Turn on AutoTrading (toolbar). Inputs: leave FilesPath empty for FILE_COMMON (shared Files)."
echo ""

if [[ -d "/Applications/MetaTrader 5.app" ]]; then
  open -a "MetaTrader 5" || true
  echo "✓ Launched MetaTrader 5"
fi
