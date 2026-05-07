#!/usr/bin/env bash
# Compile FORGE.mq5 → FORGE.ex5 using MetaEditor CLI (macOS MetaTrader Wine).
# Requires: MetaTrader 5.app (bundled wine64) and the standard MetaQuotes WINEPREFIX.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="${ROOT}/VERSION"
SRC="${ROOT}/ea/FORGE.mq5"

# ── Stamp version from VERSION file into FORGE.mq5 ──────────────
if [[ -f "${VERSION_FILE}" ]]; then
  VER="$(tr -d '[:space:]' < "${VERSION_FILE}")"
  # MQL5 #property version uses "M.mm" format (e.g. "2.10" for 2.1.0)
  MQL_VER="$(echo "${VER}" | awk -F. '{printf "%d.%02d", $1, $2*10+$3}')"
  # Update const string FORGE_VERSION = "X.Y.Z";
  sed -i '' "s/const string FORGE_VERSION = \"[^\"]*\";/const string FORGE_VERSION = \"${VER}\";/" "${SRC}"
  # Update #property version "M.mm"
  sed -i '' "s/#property version \"[^\"]*\"/#property version \"${MQL_VER}\"/" "${SRC}"
  echo "✓ Stamped FORGE version ${VER} (MQL5: ${MQL_VER}) from VERSION file"
fi
WINE_BASE="${WINEPREFIX:-${HOME}/Library/Application Support/net.metaquotes.wine.metatrader5}"
MT5_DIR="${WINE_BASE}/drive_c/Program Files/MetaTrader 5"
DST_MQ5="${MT5_DIR}/MQL5/Experts/FORGE.mq5"
WINE64="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"

if [[ ! -f "${SRC}" ]]; then
  echo "❌ Missing ${SRC}"
  exit 1
fi
if [[ ! -x "${WINE64}" ]]; then
  echo "❌ wine64 not found at ${WINE64} — install MetaTrader 5 from MetaQuotes."
  exit 1
fi
if [[ ! -f "${MT5_DIR}/MetaEditor64.exe" ]]; then
  echo "❌ MetaTrader 5 not found at:"
  echo "   ${MT5_DIR}"
  exit 1
fi

mkdir -p "$(dirname "${DST_MQ5}")"
cp -f "${SRC}" "${DST_MQ5}"
ORPHAN_JSON="${MT5_DIR}/MQL5/Files/market_data.json"
if [[ -f "${ORPHAN_JSON}" ]]; then
  rm -f "${ORPHAN_JSON}"
  echo "✓ Removed orphan MQL5/Files/market_data.json (live file is Terminal/Common/Files)"
fi
echo "✓ Synced FORGE.mq5 → Wine Experts/"

# Sync scalper_config.json to Common Files so FORGE reads the latest at runtime.
COMMON_FILES="${WINE_BASE}/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
SCALPER_CFG="${ROOT}/config/scalper_config.json"
if [[ -f "${SCALPER_CFG}" ]] && [[ -d "${COMMON_FILES}" ]]; then
  cp -f "${SCALPER_CFG}" "${COMMON_FILES}/scalper_config.json"
  echo "✓ Synced scalper_config.json → Common Files"
elif [[ -f "${SCALPER_CFG}" ]] && [[ -L "${ROOT}/MT5" ]]; then
  cp -f "${SCALPER_CFG}" "${ROOT}/MT5/scalper_config.json"
  echo "✓ Synced scalper_config.json → MT5/ symlink"
fi

export WINEPREFIX="${WINE_BASE}"
export WINEDEBUG=-all
cd "${MT5_DIR}"
# Relative /compile path is required; absolute C:\... often does not run the compiler from CLI.
"${WINE64}" ./MetaEditor64.exe '/compile:MQL5\Experts\FORGE.mq5' /log || true
sleep 2
EX5="${MT5_DIR}/MQL5/Experts/FORGE.ex5"
if [[ -f "${EX5}" ]] && [[ "${EX5}" -nt "${DST_MQ5}" ]]; then
  ls -la "${EX5}"
  echo "✓ FORGE.ex5 built (newer than .mq5)."
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  MT5 must LOAD the new .ex5 — otherwise market_data.json stays on the old forge_version."
  echo "  In MetaTrader: remove FORGE from the chart → drag FORGE from Navigator onto the chart again"
  echo "  (or restart the MetaTrader 5 app). Then:  python3 scripts/poll_mt5_feed.py"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 0
fi

echo "❌ FORGE.ex5 missing or not newer than FORGE.mq5 — open MetaEditor (F4) and press F7, or check:"
echo "   iconv -f UTF-16LE -t UTF-8 \"${MT5_DIR}/logs/metaeditor.log\" | tail -20"
exit 1
