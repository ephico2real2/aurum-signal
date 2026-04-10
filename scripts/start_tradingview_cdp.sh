#!/bin/bash
# start_tradingview_cdp.sh — Launch TradingView Desktop with Chrome DevTools Protocol
# Required by LENS to read live indicator data (RSI, BB, MACD, ADX).
#
# Usage:
#   ./scripts/start_tradingview_cdp.sh          # default port 9222
#   ./scripts/start_tradingview_cdp.sh 9333     # custom port
#
# Called by: make start-tradingview

PORT="${1:-9222}"

# ── Find TradingView ────────────────────────────────────────────
APP=""
for loc in \
  "/Applications/TradingView.app/Contents/MacOS/TradingView" \
  "$HOME/Applications/TradingView.app/Contents/MacOS/TradingView"; do
  if [ -f "$loc" ]; then
    APP="$loc"
    break
  fi
done

if [ -z "$APP" ]; then
  echo "❌ TradingView Desktop not found in /Applications or ~/Applications"
  echo "   Install from: https://www.tradingview.com/desktop/"
  exit 1
fi

# ── Check if already running with CDP ───────────────────────────
if curl -s "http://localhost:$PORT/json/version" > /dev/null 2>&1; then
  echo "✅ TradingView CDP already running on port $PORT"
  curl -s "http://localhost:$PORT/json/version" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'   Browser: {d.get(\"Browser\",\"?\")}')" 2>/dev/null
  exit 0
fi

# ── Kill existing TradingView (no CDP) and relaunch ─────────────
pkill -f "TradingView" 2>/dev/null
sleep 2

echo "Launching TradingView with --remote-debugging-port=$PORT ..."
# Use 'open -a' for proper macOS app launch (handles sandboxing + Electron correctly)
open -a "TradingView" --args --remote-debugging-port=$PORT
echo "  Launched via open -a TradingView"

# ── Wait for CDP to be ready ────────────────────────────────────
echo "  Waiting for CDP (up to 30s)..."
for i in $(seq 1 30); do
  if curl -s "http://localhost:$PORT/json/version" > /dev/null 2>&1; then
    echo "✅ TradingView CDP ready on port $PORT"
    curl -s "http://localhost:$PORT/json/version" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'   Browser: {d.get(\"Browser\",\"?\")}')" 2>/dev/null
    exit 0
  fi
  sleep 1
done

echo "⚠️  CDP not responding after 30s — TradingView may still be loading."
echo "   Check: curl http://localhost:$PORT/json/version"
exit 1
