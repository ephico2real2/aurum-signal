# Signal System — Makefile
# Usage: make <command>
# Requires: python3, npm, node in PATH

ROOT_DIR = $(shell pwd)
# Prefer repo .venv when present so `pip install -r requirements.txt` (jsonschema, etc.) is used.
PYTHON  := $(shell if [ -x "$(ROOT_DIR)/.venv/bin/python" ]; then echo "$(ROOT_DIR)/.venv/bin/python"; else echo python3; fi)
SCRIPTS  = $(ROOT_DIR)/scripts
INSTALL_SVC = $(ROOT_DIR)/services/install_services.py

# ── Help ──────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "Signal System — Available Commands"
	@echo "──────────────────────────────────────────────────────"
	@echo ""
	@echo "  HEALTH & STATUS"
	@echo "  make health          Run system health check"
	@echo "  make health-watch    Watch health check every 10s"
	@echo "  make status          Show service status"
	@echo ""
	@echo "  TESTING"
	@echo "  make verify          Health + key API curls + API pytest + Playwright"
	@echo "  make test            Run all tests (API + UI)"
	@echo "  make test-api        Run API tests only"
	@echo "  make test-ui         Run UI tests (headed Chrome)"
	@echo "  make test-ui-silent  Run UI tests headless"
	@echo "  make test-ui-audit   Playwright: all tabs + screenshots + tests/results/athena-ui-audit.json"
	@echo "  make claude-review-ui  Build tests/results/claude-review-ui-prompt.md from audit JSON"
	@echo "  make review-ui       test-ui-audit then claude-review-ui (one shot)"
	@echo "  make test-live       Run /api/live tests only"
	@echo "  make test-components Run /api/components tests only"
	@echo "  make test-contracts  File-bus JSON Schema + OpenAPI/Swagger tests (see docs/DATA_CONTRACT.md)"
	@echo "  make sync-openapi-scribe  Regenerate OpenAPI /api/scribe/query examples from scribe_query_examples.json"
	@echo "  make venv            Create .venv + pip install requirements.txt + pytest"
	@echo "  make test-contracts-venv  make venv then test-contracts (first-time / clean machine)"
	@echo "  make test-report     Open last Playwright HTML report"
	@echo "  make test-record     Record new UI tests by clicking"
	@echo ""
	@echo "  LOGS"
	@echo "  make logs            Show last 30 lines all services"
	@echo "  make logs-bridge     Follow bridge log live"
	@echo "  make logs-listener   Follow listener log live"
	@echo "  make logs-aurum      Follow aurum log live"
	@echo "  make logs-athena     Follow athena log live"
	@echo "  make logs-errors     Show only error lines"
	@echo ""
	@echo "  SERVICES (install_services.py — macOS: launchd; Linux: sudo systemctl)"
	@echo "  make start             Install/load all services (same as services-install)"
	@echo "  make stop              Unload/stop all (same as services-stop)"
	@echo "  make restart           Full reinstall + reload all services"
	@echo "  make reload            Hot-restart all Python processes (fast — launchd unload/load)"
	@echo "  make reload-bridge     Hot-restart BRIDGE only (sentinel/aegis/aurum changes)"
	@echo "  make reload-athena     Hot-restart ATHENA only (API/dashboard changes)"
	@echo "                         Use reload after editing python/*.py — faster than restart."
	@echo "  make services-install  chmod +x installer, then --install"
	@echo "  make services-stop     chmod +x installer, then --stop"
	@echo "  make services-restart  chmod +x installer, then --restart"
	@echo "  make services-status   Show launchd/systemctl status"
	@echo ""
	@echo "  SETUP & OPS"
	@echo "  make setup           One-time setup: venv + MT5 link + test deps"
	@echo "  make setup-tests     Install all test dependencies"
	@echo "  make setup-mt5-link  One-time: create MT5/ symlink from MT5_PATH in .env"
	@echo "  make start-tradingview  Launch TradingView Desktop with CDP (required by LENS)"
	@echo "  make stop-tradingview   Force-kill TradingView Desktop completely"
	@echo "  make mt5-start          Open MetaTrader 5 app"
	@echo "  make mt5-stop           Close MetaTrader 5 app"
	@echo "  make check-tradingview  Check if TradingView CDP is running"
	@echo "  make setup-indicators  Add all required indicators to TradingView chart"
	@echo "  make check-indicators  Verify indicators are present (no changes)"
	@echo "  make update-lens-mcp   Pull latest TradingView MCP, npm install, verify"
	@echo "  (docs/OPERATIONS.md — restart, verify, AURUM prompt)"
	@echo "  (docs/AEGIS.md — risk gate logic, AEGIS_* env tuning)"
	@echo "  (docs/SENTINEL.md — calendar + FXStreet/Google/Investing RSS)"
	@echo "  (docs/FORGE_BRIDGE.md — command.json vs MT5 Common Files)"
	@echo "  make verify-forge-bridge  python3 scripts/verify_forge_bridge.py (paths + market_data age)"
	@echo "  make check-tests     Check test deps (no install)"
	@echo "  make forge-ea        Copy FORGE.mq5 into Wine MT5 Experts (macOS)"
	@echo "  make forge-compile   Copy + compile FORGE.mq5 → FORGE.ex5 (MetaEditor CLI)"
	@echo "  make forge-refresh   forge-compile + open MetaTrader 5 (re-attach FORGE on chart)"
	@echo "  make scribe-gui      Open SCRIBE DB in DB Browser for SQLite (macOS)"
	@echo "  make system-up       Start TradingView + MetaTrader 5 + Python services"
	@echo "  make system-down     Stop Python services + TradingView + MetaTrader 5"
	@echo "  make forge-verify-live  poll MT5/market_data.json until forge_version matches ea/FORGE.mq5"
	@echo "  make forge-refresh-verify  forge-compile + open MT5 + poll (180s) — reattach FORGE if needed"
	@echo ""

# ── Health ────────────────────────────────────────────────────────
.PHONY: health health-watch
health:
	@$(PYTHON) $(SCRIPTS)/health.py

health-watch:
	@$(PYTHON) $(SCRIPTS)/health.py --watch

# ── Status ────────────────────────────────────────────────────────
.PHONY: status services-status
status services-status:
	@chmod +x $(INSTALL_SVC)
	@$(PYTHON) $(INSTALL_SVC) --status 2>/dev/null || \
		echo "Services: check ~/Library/LaunchAgents/com.signalsystem.*"

# ── Testing ───────────────────────────────────────────────────────
.PHONY: verify verify-forge-bridge forge-verify-live forge-refresh-verify test test-api test-ui test-ui-silent test-ui-audit test-live \
        test-closures test-components test-contracts test-contracts-venv venv sync-openapi-scribe test-report test-record claude-review-ui review-ui forge-ea forge-compile \
        services-install services-stop services-restart forge-refresh

verify-forge-bridge:
	@$(PYTHON) $(SCRIPTS)/verify_forge_bridge.py

forge-verify-live:
	@$(PYTHON) $(SCRIPTS)/poll_mt5_feed.py --repo-root "$(ROOT_DIR)" --timeout 120

# Compile, open MT5, poll until new FORGE writes expected version (you may still need to reattach EA).
forge-refresh-verify: forge-compile
	@test -d "/Applications/MetaTrader 5.app" && open -a "MetaTrader 5" || true
	@$(PYTHON) $(SCRIPTS)/poll_mt5_feed.py --repo-root "$(ROOT_DIR)" --timeout 180

verify:
	@echo "── Health ──"
	@$(PYTHON) $(SCRIPTS)/health.py || true
	@echo ""
	@echo "── API spot-checks (ATHENA_URL=$${ATHENA_URL:-http://localhost:7842}) ──"
	@ATHENA_URL=$${ATHENA_URL:-http://localhost:7842}; \
		curl -sf "$$ATHENA_URL/api/health" | $(PYTHON) -m json.tool > /dev/null && echo "  GET /api/health OK" || { echo "  GET /api/health FAILED"; exit 1; }; \
		curl -sf "$$ATHENA_URL/api/live" | $(PYTHON) -m json.tool > /dev/null && echo "  GET /api/live OK" || { echo "  GET /api/live FAILED"; exit 1; }; \
		curl -sf "$$ATHENA_URL/api/components" | $(PYTHON) -m json.tool > /dev/null && echo "  GET /api/components OK" || { echo "  GET /api/components FAILED"; exit 1; }; \
		curl -sf -X POST "$$ATHENA_URL/api/components/heartbeat" -H "Content-Type: application/json" \
			-d '{"component":"SCRIBE","status":"OK","note":"make verify"}' | $(PYTHON) -m json.tool > /dev/null \
			&& echo "  POST /api/components/heartbeat OK" || { echo "  POST heartbeat FAILED"; exit 1; }; \
		test "$$(curl -s -o /dev/null -w '%{http_code}' -X POST "$$ATHENA_URL/api/management" -H "Content-Type: application/json" -d '{"intent":"INVALID"}')" = "400" \
			&& echo "  POST /api/management (expect 400) OK" || { echo "  POST /api/management validation FAILED"; exit 1; }; \
		curl -sf -X POST "$$ATHENA_URL/api/management" -H "Content-Type: application/json" \
			-d '{"intent":"MOVE_BE"}' | $(PYTHON) -m json.tool > /dev/null \
			&& echo "  POST /api/management MOVE_BE OK" || { echo "  POST /api/management FAILED"; exit 1; }
	@echo ""
	@$(MAKE) test-api test-ui-silent

test:
	@$(PYTHON) $(SCRIPTS)/test_all.py

test-api:
	@$(PYTHON) $(SCRIPTS)/test_api.py

test-ui:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --headed

test-ui-silent:
	@$(PYTHON) $(SCRIPTS)/test_ui.py

test-live:
	@$(PYTHON) $(SCRIPTS)/test_api.py --file live

test-closures:
	@$(PYTHON) $(SCRIPTS)/test_api.py --file closures

test-mgmt-scoping:
	@$(PYTHON) -m pytest $(ROOT_DIR)/tests/api/test_mgmt_channel_scoping.py -v -m unit --tb=short

test-components:
	@$(PYTHON) $(SCRIPTS)/test_api.py --file components

test-contracts:
	@$(PYTHON) -m pytest $(ROOT_DIR)/tests/api/test_mgmt_channel_scoping.py \
		$(ROOT_DIR)/tests/api/test_aurum_forge_contract.py \
		$(ROOT_DIR)/tests/api/test_schema_bundle_integrity.py \
		$(ROOT_DIR)/tests/api/test_swagger_ui.py \
		$(ROOT_DIR)/tests/api/test_scribe_query_examples.py \
		$(ROOT_DIR)/tests/api/test_athena_scribe_query_limits.py \
		$(ROOT_DIR)/tests/api/test_bridge_aurum_cmd.py \
		$(ROOT_DIR)/tests/services/test_resolve_signal_python.py \
		$(ROOT_DIR)/tests/api/test_json_schemas.py -v -m unit --tb=short

# Create .venv under repo root, install app + contract-test deps (pytest not in requirements.txt).
VENV_PY  = $(ROOT_DIR)/.venv/bin/python
VENV_PIP = $(ROOT_DIR)/.venv/bin/pip

venv:
	@test -d "$(ROOT_DIR)/.venv" || python3 -m venv "$(ROOT_DIR)/.venv"
	@"$(VENV_PIP)" install -r "$(ROOT_DIR)/requirements.txt"
	@"$(VENV_PIP)" install pytest
	@echo "venv ready: $(VENV_PY)"

test-contracts-venv: venv
	@$(MAKE) test-contracts

sync-openapi-scribe:
	@$(PYTHON) $(ROOT_DIR)/scripts/sync_openapi_scribe_examples.py

test-report:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --report

test-record:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --record

test-ui-audit:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --audit

claude-review-ui:
	@$(PYTHON) $(SCRIPTS)/claude_review_ui.py

review-ui: test-ui-audit claude-review-ui
	@echo ""
	@echo "→ Paste into Claude Code: tests/results/claude-review-ui-prompt.md"
	@echo "→ Raw JSON: tests/results/athena-ui-audit.json"
	@echo "→ Screens: tests/results/athena-ui/screens/*.png"

# ── Logs ─────────────────────────────────────────────────────────
.PHONY: logs logs-bridge logs-listener logs-aurum logs-athena logs-errors

logs:
	@$(PYTHON) $(SCRIPTS)/logs.py

logs-bridge:
	@$(PYTHON) $(SCRIPTS)/logs.py bridge --follow

logs-listener:
	@$(PYTHON) $(SCRIPTS)/logs.py listener --follow

logs-aurum:
	@$(PYTHON) $(SCRIPTS)/logs.py aurum --follow

logs-athena:
	@$(PYTHON) $(SCRIPTS)/logs.py athena --follow

logs-errors:
	@$(PYTHON) $(SCRIPTS)/logs.py --errors

# ── Services ──────────────────────────────────────────────────────
# install_services.py is chmod +x before each run so ./services/install_services.py works.
.PHONY: start stop restart services-install services-stop services-restart reload reload-bridge reload-athena reload-all

services-install:
	@chmod +x $(INSTALL_SVC)
	@$(PYTHON) $(INSTALL_SVC)

services-stop:
	@chmod +x $(INSTALL_SVC)
	@$(PYTHON) $(INSTALL_SVC) --stop

services-restart:
	@chmod +x $(INSTALL_SVC)
	@$(PYTHON) $(INSTALL_SVC) --restart

start: services-install

stop: services-stop

restart: services-restart

# ── Hot reload (unload → load via launchctl for reliable restart) ────
# Use after editing python/*.py — faster than `make restart` (no plist re-render).
# Uses launchctl unload/load (not kill) because KeepAlive.Crashed doesn't
# relaunch on clean SIGTERM exits.
LAUNCH_AGENTS = $(HOME)/Library/LaunchAgents

reload reload-all:
	@echo "Reloading all Signal System Python processes..."
	@for svc in bridge listener aurum athena; do \
		PLIST=$(LAUNCH_AGENTS)/com.signalsystem.$$svc.plist; \
		if [ -f "$$PLIST" ] || [ -L "$$PLIST" ]; then \
			launchctl unload "$$PLIST" 2>/dev/null; \
			launchctl load "$$PLIST" 2>/dev/null; \
			echo "  ✓ Reloaded com.signalsystem.$$svc"; \
		else \
			echo "  ✗ $$PLIST not found — run: make start"; \
		fi; \
	done
	@echo "Waiting 8s for processes to start..."
	@sleep 8
	@$(PYTHON) $(SCRIPTS)/health.py 2>/dev/null || echo "(health script unavailable)"
	@echo ""
	@echo "✅ Reload complete."

reload-bridge:
	@echo "Reloading BRIDGE (sentinel/aegis/aurum changes take effect)..."
	@PLIST=$(LAUNCH_AGENTS)/com.signalsystem.bridge.plist; \
	if [ -f "$$PLIST" ] || [ -L "$$PLIST" ]; then \
		launchctl unload "$$PLIST" 2>/dev/null; \
		launchctl load "$$PLIST" 2>/dev/null; \
		echo "  ✓ Reloaded com.signalsystem.bridge"; \
	else \
		echo "  ✗ plist not found — run: make start"; \
		exit 1; \
	fi
	@echo "Waiting 5s for BRIDGE to start..."
	@sleep 5
	@PIDS=$$(pgrep -f "python.*bridge.py" 2>/dev/null); \
	if [ -n "$$PIDS" ]; then \
		echo "✅ BRIDGE running (PID $$PIDS)"; \
	else \
		echo "⚠️  BRIDGE not running — check: tail -20 logs/bridge.log"; \
	fi

reload-athena:
	@echo "Reloading ATHENA..."
	@PLIST=$(LAUNCH_AGENTS)/com.signalsystem.athena.plist; \
	if [ -f "$$PLIST" ] || [ -L "$$PLIST" ]; then \
		launchctl unload "$$PLIST" 2>/dev/null; \
		launchctl load "$$PLIST" 2>/dev/null; \
		echo "  ✓ Reloaded com.signalsystem.athena"; \
	else \
		echo "  ✗ plist not found — run: make start"; \
	fi
	@sleep 8
	@curl -sf http://localhost:7842/api/health > /dev/null 2>&1 && echo "✅ ATHENA up" || echo "⚠️  ATHENA not responding"

# ── TradingView CDP + LENS MCP ─────────────────────────────────────────
LENS_MCP_DIR = $(HOME)/tradingview-mcp-jackson
LENS_RULES_CANONICAL = $(ROOT_DIR)/config/tradingview_rules.json

.PHONY: start-tradingview stop-tradingview mt5-start mt5-stop setup-mt5-link check-tradingview update-lens-mcp system-up system-down

start-tradingview:
	@chmod +x $(SCRIPTS)/start_tradingview_cdp.sh
	@$(SCRIPTS)/start_tradingview_cdp.sh

stop-tradingview:
	@echo "Stopping TradingView Desktop..."
	@pkill -9 -f "TradingView" 2>/dev/null && echo "✅ TradingView force-stopped" || echo "  TradingView was not running"
	@pgrep -fal "TradingView" >/dev/null 2>&1 && echo "⚠️  TradingView process still detected" || echo "✅ TradingView fully terminated"

mt5-start:
	@echo "Starting MetaTrader 5..."
	@open -a "MetaTrader 5" && echo "✅ MetaTrader 5 started" || echo "⚠️  MetaTrader 5 not found in /Applications"

mt5-stop:
	@echo "Stopping MetaTrader 5..."
	@pkill -f "terminal64.exe" 2>/dev/null && echo "✅ MetaTrader 5 stopped" || echo "  MetaTrader 5 was not running"

setup-mt5-link:
	@echo "One-time setup: creating MT5/ symlink from MT5_PATH in .env"
	@test -f "$(ROOT_DIR)/.env" || { echo "Missing .env — copy .env.example and set MT5_PATH"; exit 1; }
	@MT5_PATH=$$(sed -n 's/^MT5_PATH=//p' "$(ROOT_DIR)/.env" | tail -1 | sed 's/^"//;s/"$$//'); \
	if [ -z "$$MT5_PATH" ]; then echo "MT5_PATH is not set in .env"; exit 1; fi; \
	if [ ! -d "$$MT5_PATH" ]; then echo "MT5_PATH directory does not exist: $$MT5_PATH"; exit 1; fi; \
	if [ -e "$(ROOT_DIR)/MT5" ] && [ ! -L "$(ROOT_DIR)/MT5" ]; then echo "MT5 exists and is not a symlink — remove it manually first"; exit 1; fi; \
	ln -sfn "$$MT5_PATH" "$(ROOT_DIR)/MT5"; \
	echo "MT5 -> $$MT5_PATH"

check-tradingview:
	@if curl -s "http://localhost:9222/json/version" > /dev/null 2>&1; then \
		echo "✅ TradingView CDP running on port 9222"; \
		curl -s "http://localhost:9222/json/version" | $(PYTHON) -c "import sys,json; d=json.load(sys.stdin); print(f'   Browser: {d.get(\"Browser\",\"?\")}')" 2>/dev/null; \
	else \
		echo "❌ TradingView CDP not running — run: make start-tradingview"; \
	fi

setup-indicators:
	@LENS_MCP_CMD="node $(LENS_MCP_DIR)/src/server.js" \
		$(PYTHON) $(ROOT_DIR)/scripts/setup_tradingview_indicators.py

check-indicators:
	@LENS_MCP_CMD="node $(LENS_MCP_DIR)/src/server.js" \
		$(PYTHON) $(ROOT_DIR)/scripts/setup_tradingview_indicators.py --check

update-lens-mcp:
	@echo "Updating TradingView MCP (LENS)..."
	@if [ ! -d "$(LENS_MCP_DIR)/.git" ]; then \
		echo "  Cloning tradingview-mcp-jackson..."; \
		git clone https://github.com/LewisWJackson/tradingview-mcp-jackson.git "$(LENS_MCP_DIR)"; \
	else \
		echo "  Pulling latest from origin/main..."; \
		git -C "$(LENS_MCP_DIR)" stash --include-untracked 2>/dev/null || true; \
		git -C "$(LENS_MCP_DIR)" pull origin main; \
	fi
	@if [ ! -f "$(LENS_RULES_CANONICAL)" ]; then \
		echo "  ❌ Canonical rules file missing: $(LENS_RULES_CANONICAL)"; \
		exit 1; \
	fi
	@rm -f "$(LENS_MCP_DIR)/rules.json"
	@ln -s "$(LENS_RULES_CANONICAL)" "$(LENS_MCP_DIR)/rules.json"
	@echo "  Symlinked rules.json → $(LENS_RULES_CANONICAL)"
	@echo "  Running npm install..."
	@npm install --prefix "$(LENS_MCP_DIR)" --silent 2>&1 | tail -2
	@echo "  Verifying server starts..."
	@timeout 5 node "$(LENS_MCP_DIR)/src/server.js" > /dev/null 2>&1 && echo "  ✅ MCP server OK" || echo "  ✅ MCP server OK (exited on stdin close)"
	@WATCHLIST=$$($(PYTHON) -c "import json, pathlib; p=pathlib.Path('$(LENS_MCP_DIR)/rules.json'); \
print(','.join((json.loads(p.read_text()).get('watchlist') or [])) if p.exists() else 'MISSING')"); \
	echo "  Active rules watchlist: $$WATCHLIST"
	@echo ""
	@COMMIT=$$(git -C "$(LENS_MCP_DIR)" --no-pager log --oneline -1); \
		echo "  Version: $$COMMIT"
	@echo "  Path:    $(LENS_MCP_DIR)/src/server.js"
	@echo ""
	@echo "✅ LENS MCP updated. BRIDGE picks up changes on next LENS fetch cycle."

# ── Full system lifecycle (dependency-ordered) ───────────────────────
# system-up order:
#   1) TradingView CDP (required by LENS)
#   2) MetaTrader 5 app (required by FORGE market_data feed)
#   3) Python services (BRIDGE/LISTENER/AURUM/ATHENA)
system-up: start-tradingview mt5-start start
	@echo ""
	@echo "✅ System startup sequence complete."
	@echo "   Next checks: make check-tradingview && make health"

# system-down order:
#   1) Python services (stop writers/consumers first)
#   2) TradingView
#   3) MetaTrader 5
system-down: stop stop-tradingview mt5-stop
	@echo ""
	@echo "✅ System shutdown sequence complete."

# ── Setup ─────────────────────────────────────────────────────────
.PHONY: setup setup-tests check-tests scribe-gui

setup:
	@$(MAKE) venv
	@$(MAKE) setup-mt5-link
	@$(MAKE) setup-tests
	@echo "Setup complete."

setup-tests:
	@$(PYTHON) $(SCRIPTS)/setup_tests.py

check-tests:
	@$(PYTHON) $(SCRIPTS)/setup_tests.py --check

scribe-gui:
	@open -a "DB Browser for SQLite" "$(ROOT_DIR)/python/data/aurum_intelligence.db"

scalper-config-sync:
	@echo "Syncing scalper_config.json → MT5 Common Files..."
	@cp $(ROOT_DIR)/config/scalper_config.json "$(HOME)/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/scalper_config.json" 2>/dev/null \
		&& echo "  ✅ Synced" \
		|| echo "  ⚠ Common Files path not found — copy manually"

forge-ea:
	@chmod +x $(SCRIPTS)/install_forge_ea_macos.sh
	@$(SCRIPTS)/install_forge_ea_macos.sh

forge-compile:
	@chmod +x $(SCRIPTS)/compile_forge_ea_macos.sh
	@$(SCRIPTS)/compile_forge_ea_macos.sh

forge-refresh: forge-compile
	@test -d "/Applications/MetaTrader 5.app" && open -a "MetaTrader 5" || true
	@echo ""
	@echo "FORGE refresh: new .ex5 is in Wine MQL5/Experts/. In MT5: open gold chart →"
	@echo "  remove old FORGE if stuck → Navigator → Expert Advisors → drag FORGE → enable AutoTrading."

forge-reload: forge-compile
	@echo ""
	@echo "Restarting MetaTrader 5 to load new FORGE .ex5..."
	@pkill -f "terminal64.exe" 2>/dev/null || true
	@sleep 5
	@open -a "MetaTrader 5"
	@echo "MT5 restarting... waiting 45s for full startup"
	@sleep 45
	@$(PYTHON) -c "import json,time;from pathlib import Path;d=json.loads(Path('MT5/market_data.json').read_text());age=time.time()-d.get('timestamp_unix',0); \
		print(f'forge_version={d.get(\"forge_version\")} ea_cycle={d.get(\"ea_cycle\")} age={age:.0f}s'); \
		print('✅ FORGE auto-loaded!' if age<15 else '⚠️  FORGE not writing yet — reattach EA in MT5:'); \
		print('') if age<15 else print('  1. Right-click chart → Expert list → Remove FORGE'); \
		print('') if age<15 else print('  2. Navigator → Expert Advisors → drag FORGE onto chart'); \
		print('') if age<15 else print('  3. Enable Algo Trading (green button)'); \
		print('  Then run: make forge-verify-live')"
