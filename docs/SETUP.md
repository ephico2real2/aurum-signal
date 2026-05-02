# SIGNAL SYSTEM — Complete Setup Guide
> macOS · MetaTrader 5 Native · Python 3.11+ · Node.js 18+
For command-by-command image extraction validation (LISTENER/AURUM + SCRIBE queries), see **[VISION_CLI_RUNBOOK.md](VISION_CLI_RUNBOOK.md)**.

---

## BEFORE YOU START — What you need and why

```
ANTHROPIC API KEY  (one key covers everything)
    ├── AURUM    → AI agent that talks to you via Telegram + ATHENA dashboard
    └── LISTENER → Claude parses every signal message from Telegram

TRADINGVIEW MCP (LewisWJackson/tradingview-mcp-jackson)
    └── LENS → reads live TradingView indicators (RSI, MACD, BB, ADX)

TELEGRAM (two separate things)
    ├── Telethon  → reads your signal channels (uses your personal account)
    └── Bot API   → HERALD sends you alerts, AURUM replies to your messages

METATRADER 5 (macOS native app — no Wine needed)
    └── FORGE EA → executes trades, exports account data via JSON files
```

**One Anthropic API key. One Telegram account. One bot. Everything else is configuration.**

---

## STEP 0 — What the ATHENA dashboard is and how to run it

The dashboard you saw in the mockup works two ways:

**Right now in Claude.ai (what you already saw)**
- The AURUM chat is live Claude API — works immediately
- All other data is mock/demo
- No setup needed

**Locally on your Mac (real live data)**
```bash
# Terminal 1
python3 signal_system/python/bridge.py --mode WATCH

# Terminal 2
python3 signal_system/python/athena_api.py

# Open browser
open http://localhost:7842
```
Now the account balance, positions, LENS indicators, and activity log all show real data from MT5.

---

## STEP 1 — Get your Anthropic API key

Used by AURUM (AI agent) AND LISTENER (signal parser). Same key, both components.

1. Go to https://console.anthropic.com
2. Sign up or log in → **API Keys** → **Create Key**
3. Name: `SignalSystem`
4. Copy the key (starts `sk-ant-api03-...`)
5. Save it — goes into `.env` as `ANTHROPIC_API_KEY`

> Cost estimate: AURUM uses claude-sonnet (~$0.003/query). LISTENER uses
> claude-haiku (~$0.0001/signal). Light trading = a few dollars/month.

---

## STEP 2 — Setup Telegram

### Part A — Telethon credentials (reads signal channels)

1. Go to https://my.telegram.org/auth → enter your phone number
2. Click **API development tools**
3. Create app: name `SignalSystem`, platform `Desktop`
4. Copy **App api_id** (number) and **App api_hash** (string)

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+1234567890
```

### Part B — Find your signal channel IDs

Forward any message from your signal channel to [@userinfobot](https://t.me/userinfobot).
It replies with the ID (e.g. `-1001234567890`).

```
TELEGRAM_CHANNELS=-1001234567890,-1009876543210
```

Comma-separated. Add as many channels as you want.

### Part C — Create your notification bot

1. Telegram → search **@BotFather** → `/newbot`
2. Choose any name and username (must end in `_bot`)
3. Copy the token BotFather gives you

```
TELEGRAM_BOT_TOKEN=1234567890:AABBCCDDEEFFaabbccddeeff
```

### Part D — Get your personal Chat ID

1. Send any message to your new bot
2. Visit in browser: `https://api.telegram.org/bot{TOKEN}/getUpdates`
3. Find `"chat":{"id":XXXXXXX}` in the response

```
TELEGRAM_CHAT_ID=987654321
```

### Part E — Authenticate Telethon (one-time)

```bash
cd signal_system/python
python3 listener.py --test
# Asks for phone + verification code
# Creates config/telegram_session.session
```

Keep `telegram_session.session` safe — it is your auth token.

---

## STEP 3 — Setup TradingView MCP (LENS)

The developer (LewisWJackson) provides a one-command setup via Claude Code.

### Option A: Via Claude Code (recommended — handles everything automatically)

Open Claude Code (install from https://claude.ai/code if you haven't) and paste:

```
Set up TradingView MCP Jackson for me.
Clone https://github.com/LewisWJackson/tradingview-mcp-jackson.git to ~/tradingview-mcp-jackson, run npm install, then add it to my MCP config at ~/.claude/.mcp.json (merge with any existing servers, don't overwrite them).
The config block is: { "mcpServers": { "tradingview": { "command": "node", "args": ["/Users/YOUR_USERNAME/tradingview-mcp-jackson/src/server.js"] } } } — replace YOUR_USERNAME with my actual username.
Then copy rules.example.json to rules.json and open it so I can fill in my trading rules.
Finally restart and verify with tv_health_check.
```

Claude Code clones the repo, runs npm install, edits your MCP config, and verifies it with tv_health_check — all automatically.

### Option B: Manual

```bash
cd ~
git clone https://github.com/LewisWJackson/tradingview-mcp-jackson.git
cd tradingview-mcp-jackson
npm install
cp rules.example.json rules.json
# Edit rules.json with your trading rules if needed

# Test:
node src/server.js
# Should print: TradingView MCP server running
# Ctrl+C to stop
```

### Rules symlink (recommended)

This repo keeps canonical TradingView rules in `signal_system/config/tradingview_rules.json`.
Symlink MCP `rules.json` to that file so all updates stay centralized:

```bash
cd ~/tradingview-mcp-jackson
ln -sf /Users/YOUR_USERNAME/signal_system/config/tradingview_rules.json rules.json
```

Verify the symlink:
```bash
ls -l ~/tradingview-mcp-jackson/rules.json
# should point to .../signal_system/config/tradingview_rules.json
```

### Point LENS at the server

Add to `.env` (replace YOUR_USERNAME with your macOS username — run `whoami` to check):

```bash
LENS_MCP_CMD=node /Users/YOUR_USERNAME/tradingview-mcp-jackson/src/server.js
LENS_SYMBOL=XAUUSD
LENS_EXCHANGE=FX_IDC
LENS_TIMEFRAMES=5m,1h
LENS_CACHE_SEC=300
```

LENS starts and stops the MCP server as a subprocess automatically.
You do not need to keep it running manually.

To expose the full TradingView brief payload in ATHENA:
```bash
curl -s http://localhost:7842/api/brief | python3 -m json.tool
```
If this returns `UNAVAILABLE`, run one LENS cycle (`python3 python/lens.py`) after TradingView CDP is up.

### Launch TradingView Desktop with CDP

**LENS requires TradingView Desktop running with Chrome DevTools Protocol enabled.**
The MCP server connects to TradingView via CDP on `localhost:9222` to read live indicator data.
Without it, LENS returns all zeros.

```bash
make start-tradingview
```

This finds TradingView Desktop, launches it with `--remote-debugging-port=9222`, and waits until CDP is ready. If TradingView is already running with CDP, it skips the relaunch.

**Important**: Open your XAUUSD chart in TradingView after launch so LENS reads the correct symbol.

Other commands:
```bash
make check-tradingview    # check if CDP is running
make stop-tradingview     # kill TradingView
make setup-indicators     # add required indicators (RSI/MACD/BB/ADX+DI/OB/FVG)
make check-indicators     # verify required indicators are present
```

**Startup order**: After login or reboot, run:
```bash
make start-tradingview    # 1. TradingView Desktop with CDP
make start                # 2. Signal System services (BRIDGE, LISTENER, AURUM, ATHENA)
```

Or add TradingView to your macOS **Login Items** (System Settings → General → Login Items) so it launches automatically. Note: Login Items won't pass `--remote-debugging-port`, so prefer `make start-tradingview` or add `scripts/start_tradingview_cdp.sh` as a Login Item script.

### Updating the MCP

The upstream repo receives fixes and new features. To update:

```bash
make update-lens-mcp
```

This pulls the latest code, runs `npm install`, and verifies the server starts. BRIDGE picks up the new version on its next LENS fetch cycle — no restart required.
It also re-links `~/tradingview-mcp-jackson/rules.json` to `signal_system/config/tradingview_rules.json`.

To check your current version:
```bash
git -C ~/tradingview-mcp-jackson log --oneline -1
```

---

## STEP 4 — Configure .env

```bash
cd signal_system
cp .env.example .env
nano .env   # or open in any text editor
```

Minimum required to start:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY

TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=yourhash
TELEGRAM_PHONE=+1234567890
TELEGRAM_CHANNELS=-1001234567890
TELEGRAM_BOT_TOKEN=1234567890:YourToken
TELEGRAM_CHAT_ID=987654321

LENS_MCP_CMD=node /Users/YOUR_USERNAME/tradingview-mcp-jackson/src/server.js

ATHENA_HOST=127.0.0.1       # default; change to 0.0.0.0 only if you need LAN access and have set ATHENA_SECRET
ATHENA_SECRET=              # optional; when set, all state-mutating routes require X-Athena-Token header

DEFAULT_MODE=WATCH
AEGIS_RISK_PCT=2.0
AEGIS_NUM_TRADES=8
TP1_CLOSE_PCT=70
MOVE_BE_ON_TP1=true
BRIDGE_LOOP_SEC=1
BRIDGE_PIN_MODE=HYBRID
# Prefer room IDs (stable if titles change); ACTIVE_SIGNAL_TRADE_ROOMS is an alias.
SIGNAL_TRADE_ROOMS=-1002034822451,-1001959885205
LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT=true
LISTENER_SIGNAL_MEDIA_ARCHIVE_ENABLED=true
LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR=data/signal_media_archive
```

**Risk gate (AEGIS):** `AEGIS_*` variables control min R:R, daily loss cap, max open groups, slippage, and lot scaling. Full decision order, formulas, and defaults are in **[docs/AEGIS.md](AEGIS.md)**. Restart **bridge** (or `make restart`) after changing them.

Regime engine:
```bash
REGIME_HMM_COMPONENTS=3     # default 3; valid range 2-10; controls HMM hidden states for regime inference
```

---

## STEP 5 — Install Python dependencies

```bash
cd signal_system
pip3 install -r requirements.txt
# If you get errors:
pip3 install -r requirements.txt --break-system-packages
```

`requirements.txt` now pins upper bounds on `anthropic`, `telethon`, and `flask`, and explicitly lists `httpx`, `hmmlearn`, `numpy`, and `pytz`. Run `pip install -r requirements.txt` after pulling to pick up the new pins. `pytz` is required by SENTINEL for DST-aware Eastern→UTC conversion of ForexFactory event times (EDT UTC-4 Apr–Nov, EST UTC-5 Nov–Mar).

### Optional: Install SCRIBE DB GUI (macOS)

To inspect SCRIBE data visually, install **DB Browser for SQLite**:

```bash
brew install --cask db-browser-for-sqlite
```

Open the database:

```bash
open -a "DB Browser for SQLite" /Users/YOUR_USERNAME/signal_system/python/data/aurum_intelligence.db
```

Or from repo root:

```bash
make scribe-gui
```

Quick enhancement verification (threshold-hardening fields):

```sql
SELECT id, source, pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points
FROM trade_groups
WHERE source='FORGE_NATIVE_SCALP'
ORDER BY id DESC
LIMIT 10;
```

```sql
SELECT id, source, pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points
FROM market_snapshots
ORDER BY id DESC
LIMIT 10;
```

---

## STEP 6 — Setup MetaTrader 5

### Install MT5
Download from https://www.metatrader5.com/en/download or Mac App Store.
Log in with your FBS account.

### Find your MT5 Files path
In MT5: **File → Open Data Folder** → navigate to `MQL5/Files/`
Copy the full path. It looks like:
`/Users/YOUR_USERNAME/Library/Application Support/MetaQuotes/Terminal/HASH/MQL5/Files/`

**Official MetaTrader 5 for Mac (Wine):** data lives under  
`~/Library/Application Support/net.metaquotes.wine.metatrader5/`.  
Use **Terminal → Common → Files** for JSON when `FilesPath` is left blank (FORGE uses `FILE_COMMON`). From the repo root you can run **`make forge-ea`** to copy `FORGE.mq5` into `MQL5/Experts/` and (re)create the `MT5` symlink to Common/Files when missing.

### Install FORGE EA
1. Copy `signal_system/ea/FORGE.mq5` → your MT5 `MQL5/Experts/` folder (or run **`make forge-ea`** on macOS Wine)
2. MT5: **Tools → MetaEditor** (F4) → open `FORGE.mq5` → **F7** to compile
3. Confirm: `0 errors, 0 warnings`
4. MT5: open XAUUSD chart → Navigator (Ctrl+N) → Expert Advisors → drag **FORGE** onto chart
5. EA settings:
   - `FilesPath` = your MT5 Files path from above
   - ✅ Allow automated trading
   - Click OK

### Create symlink (links project to MT5)

```bash
cd signal_system
ln -s "/Users/YOUR_USERNAME/Library/Application Support/MetaQuotes/Terminal/HASH/MQL5/Files" MT5
```

Verify:
```bash
ls MT5/
# After 10 seconds: market_data.json should appear
```

**Wine gotcha:** MetaTrader may use `…/users/user/…` or `…/users/<mac_username>/…` under the Wine prefix. FORGE must write to the same **Terminal → Common → Files** folder your **`MT5`** symlink points to. If JSON never updates, check both paths under `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/` and repoint the symlink. **`python/MT5`** should be a symlink to **`../MT5`**, not a separate folder (`make forge-ea` fixes that).

---

## STEP 7 — Test components one by one

```bash
cd signal_system/python

# 1. Database
python3 scribe.py
# ✅ "SCRIBE OK — tables created: [system_events, ...]"

# 2. Notifications
python3 herald.py
# ✅ Sends test message to your Telegram bot

# 3. Signal parser
python3 listener.py --test
# ✅ Shows parsed JSON for sample Garry's Signals messages

# 4. Risk manager
python3 aegis.py
# ✅ "approved=True lot=0.02 n=8 rr=1.4"

# 5. News guard
python3 sentinel.py
# ✅ Shows next high-impact USD event

# 6. TradingView data
python3 lens.py
# ✅ Shows RSI, MACD, BB, ADX  OR  "MCP server not running"

# 7. AURUM agent (interactive)
python3 aurum.py
# ✅ Chat prompt — type "what mode am I in?" then 'quit' to exit
```

---

## STEP 8 — Run the system (4 terminals)

**Terminal 1 — BRIDGE**
```bash
cd signal_system/python && python3 bridge.py --mode WATCH
```

**Terminal 2 — ATHENA**
```bash
cd signal_system/python && python3 athena_api.py
# Open: http://localhost:7842
```

**Terminal 3 — LISTENER**
```bash
cd signal_system/python && python3 listener.py
```

**Terminal 4 — AURUM Telegram**
```bash
cd signal_system/python && python3 aurum.py --telegram
```

---

## STEP 9 — Verify

In the ATHENA dashboard at http://localhost:7842:

- [ ] Account balance matches your actual MT5 balance
- [ ] FORGE shows green in System Health
- [ ] All 10 components green
- [ ] HERALD sent a startup message to your Telegram
- [ ] SENTINEL shows next upcoming news event
- [ ] Message your Telegram bot: "hello" → AURUM replies
- [ ] LENS panel shows real RSI/MACD data

---

## Talking to AURUM

**From Telegram** — message your bot directly from your phone:
- *"P&L today?"*
- *"Is G047 worth holding to TP2?"*
- *"Switch to WATCH mode"*
- *"What is LENS showing?"*
- *"Are we clear to trade?"*

**From ATHENA** — use the chat panel bottom-right of the dashboard.

Same AURUM, same live context, both access points.

---

## Mode guide

| Mode | When to use |
|------|-------------|
| WATCH | **Start here.** Records data, zero trades. Run 3+ days first. |
| SIGNAL | Executes Telegram signals only. Switch after WATCH. |
| SCALPER | EA's own LENS-driven entries. No Telegram needed. |
| HYBRID | Both active. Switch when confident. |
| OFF | Complete stop. |

**Spend at least 3 days in WATCH before going live.**

---

## Troubleshooting

**No market_data.json after 30s:**
- MT5 AutoTrading button must be green in toolbar
- Check Expert tab in MT5 for errors
- Verify FilesPath in FORGE matches your actual path

**Telegram session expired:**
```bash
rm signal_system/config/telegram_session.session
python3 listener.py --test
```

**LENS returns zeros:**
```bash
# Test MCP manually:
node ~/tradingview-mcp-jackson/src/server.js
# If fails: cd ~/tradingview-mcp-jackson && npm install

# Try different exchange:
LENS_EXCHANGE=OANDA   # in .env
```
If MCP tooling was newly installed, also run:
```bash
cd ~/tradingview-mcp-jackson && npm link
```

**AURUM not responding on Telegram:**
```bash
# Verify Chat ID:
curl "https://api.telegram.org/bot{TOKEN}/getUpdates"

# Verify API key:
python3 -c "import anthropic; c=anthropic.Anthropic(); print('API key OK')"
```

---

## STEP 10 — Install as background services (auto-start on login)

Day-to-day **restart, health checks, and an AURUM bootstrap prompt** are in [OPERATIONS.md](OPERATIONS.md).

Claude Code handles this automatically as part of setup. Or run manually:

```bash
cd signal_system
make start
# or: python3 services/install_services.py
```

This:
1. Renders plist templates with your `.env` values → `services/macos/rendered/`
2. Creates **symlinks** from `~/Library/LaunchAgents/` → rendered files in the repo
3. Loads all 4 services via `launchctl`

Because LaunchAgents entries are **symlinks** (not copies), changes are always traceable from the source base directory.

### Check everything is running

```bash
make status
# or: python3 services/install_services.py --status
```

Verify symlinks:
```bash
ls -la ~/Library/LaunchAgents/com.signalsystem.*
# Should show -> /path/to/signal_system/services/macos/rendered/*.plist
```

### View live logs

```bash
make logs-bridge      # follow bridge log
make logs-athena      # follow athena log
# Or directly:
tail -f ~/signal_system/logs/bridge.log
```

### Stop / restart / reload

```bash
make stop             # unload all services
make start            # render + symlink + load (full install)
make restart          # stop + start (re-renders plists from .env)
make reload           # hot-restart all Python processes (fast — no plist reinstall)
make reload-bridge    # hot-restart BRIDGE only (picks up sentinel/aegis/aurum changes)
```

**Use `make reload` after editing Python files** — it kills the running processes and launchd relaunches them with fresh code. Much faster than `make restart` (which re-renders plists from scratch).

**Use `make restart` after editing `.env`** — env changes require re-rendering the plists.

After this step your Mac will automatically start all 4 services on every login.
If any service crashes it restarts itself after 10-15 seconds.

---

## Testing

### Install test dependencies (one-time setup)

```bash
# Python test deps
pip3 install pytest pytest-html pytest-cov requests --break-system-packages

# Playwright UI tests
cd ~/signal_system/tests && npm install && npx playwright install chromium

# Verify both
python3 -c "import pytest; print('pytest', pytest.__version__)"
npx playwright --version
```

### API Tests (validates Flask endpoints)

```bash
cd ~/signal_system
python3 -m pytest tests/api/ -v --tb=short

# Skip AURUM test (calls real Claude API — slow)
python3 -m pytest tests/api/ -v --tb=short -m "not slow"

# Specific endpoint
python3 -m pytest tests/api/test_live.py -v
python3 -m pytest tests/api/test_components.py -v
```

### UI Tests (validates ATHENA dashboard in Chrome)

```bash
# Install once:
cd ~/signal_system/tests && npm install && npx playwright install chromium

# Run tests (ATHENA dashboard must be running first):
npx playwright test --headed           # watch Chrome run tests
npx playwright test --debug            # pause at each step
npx playwright show-report             # HTML report in browser

# Record new tests by clicking:
npx playwright codegen http://localhost:7842
```

### What each test covers

API tests (pytest):
- `test_live.py`       — validates all keys in /api/live including components, aegis, broker info, circuit_breaker
- `test_endpoints.py`  — health, sessions, performance, mode, events
- `test_components.py` — /api/components has all 11 components
- `test_aurum.py`      — AURUM chat endpoint (marked slow)

UI tests (Playwright):
- `test_dashboard.spec.js`  — dashboard loads, all panels visible
- `test_panels.spec.js`     — activity log, trade groups, AURUM chat, mode control, LENS panel
