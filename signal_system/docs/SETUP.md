# SIGNAL SYSTEM — Complete Setup Guide
> macOS · MetaTrader 5 Native · Python 3.11+ · Node.js 18+

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

DEFAULT_MODE=WATCH
AEGIS_RISK_PCT=2.0
AEGIS_NUM_TRADES=8
TP1_CLOSE_PCT=70
MOVE_BE_ON_TP1=true
```

---

## STEP 5 — Install Python dependencies

```bash
cd signal_system
pip3 install -r requirements.txt
# If you get errors:
pip3 install -r requirements.txt --break-system-packages
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

### Install FORGE EA
1. Copy `signal_system/ea/FORGE.mq5` → your MT5 `MQL5/Experts/` folder
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

**AURUM not responding on Telegram:**
```bash
# Verify Chat ID:
curl "https://api.telegram.org/bot{TOKEN}/getUpdates"

# Verify API key:
python3 -c "import anthropic; c=anthropic.Anthropic(); print('API key OK')"
```

---

## STEP 10 — Install as background services (auto-start on login)

Claude Code handles this automatically as part of setup. Or run manually:

```bash
cd signal_system
python3 services/install_services.py
```

This detects macOS vs Linux, installs the right service files,
replaces YOUR_USERNAME with your real username, and starts all 4 services.

### Check everything is running

```bash
python3 services/install_services.py --status
```

### View live logs

```bash
# Follow bridge log in real-time
python3 services/install_services.py --logs bridge

# Or directly on macOS:
tail -f ~/signal_system/logs/bridge.log
```

### Stop / restart

```bash
python3 services/install_services.py --stop
python3 services/install_services.py --restart
```

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
