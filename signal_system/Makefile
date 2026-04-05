# Signal System — Makefile
# Usage: make <command>
# Requires: python3, npm, node in PATH

PYTHON   = python3
ROOT_DIR = $(shell pwd)
SCRIPTS  = $(ROOT_DIR)/scripts

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
	@echo "  make test            Run all tests (API + UI)"
	@echo "  make test-api        Run API tests only"
	@echo "  make test-ui         Run UI tests (headed Chrome)"
	@echo "  make test-ui-silent  Run UI tests headless"
	@echo "  make test-live       Run /api/live tests only"
	@echo "  make test-components Run /api/components tests only"
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
	@echo "  SERVICES"
	@echo "  make start           Start all services"
	@echo "  make stop            Stop all services"
	@echo "  make restart         Restart all services"
	@echo ""
	@echo "  SETUP"
	@echo "  make setup-tests     Install all test dependencies"
	@echo "  make check-tests     Check test deps (no install)"
	@echo ""

# ── Health ────────────────────────────────────────────────────────
.PHONY: health health-watch
health:
	@$(PYTHON) $(SCRIPTS)/health.py

health-watch:
	@$(PYTHON) $(SCRIPTS)/health.py --watch

# ── Status ────────────────────────────────────────────────────────
.PHONY: status
status:
	@$(PYTHON) $(ROOT_DIR)/services/install_services.py --status 2>/dev/null || \
		echo "Services: check ~/Library/LaunchAgents/com.signalsystem.*"

# ── Testing ───────────────────────────────────────────────────────
.PHONY: test test-api test-ui test-ui-silent test-live \
        test-components test-report test-record

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

test-components:
	@$(PYTHON) $(SCRIPTS)/test_api.py --file components

test-report:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --report

test-record:
	@$(PYTHON) $(SCRIPTS)/test_ui.py --record

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
.PHONY: start stop restart

start:
	@$(PYTHON) $(ROOT_DIR)/services/install_services.py

stop:
	@$(PYTHON) $(ROOT_DIR)/services/install_services.py --stop

restart:
	@$(PYTHON) $(ROOT_DIR)/services/install_services.py --restart

# ── Setup ─────────────────────────────────────────────────────────
.PHONY: setup-tests check-tests

setup-tests:
	@$(PYTHON) $(SCRIPTS)/setup_tests.py

check-tests:
	@$(PYTHON) $(SCRIPTS)/setup_tests.py --check
