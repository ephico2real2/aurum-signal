/**
 * ATHENA full UI audit — walks every main tab, screenshots, writes JSON for Claude review.
 * Run: make test-ui-audit   (requires ATHENA up, same as other UI tests)
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'results');
const SCR = path.join(OUT, 'athena-ui', 'screens');
const REPORT = path.join(OUT, 'athena-ui-audit.json');
const TABS = ['groups', 'activity', 'signals', 'perf'];

function summarizeLive(j) {
  if (!j || typeof j !== 'object') return {};
  return {
    mode: j.mode,
    effective_mode: j.effective_mode,
    session: j.session,
    mt5_connected: j.mt5_connected,
    mt5_quote_stale: j.mt5_quote_stale,
    execution_usable: j.execution?.usable,
    execution_symbol: j.execution?.symbol,
    execution_age_sec: j.execution?.age_sec,
    chart_symbol: j.chart_symbol,
    open_groups_count: Array.isArray(j.open_groups) ? j.open_groups.length : null,
    balance: j.account?.balance,
    performance_total: j.performance?.total,
  };
}

test.describe.configure({ mode: 'serial' });

test.describe('ATHENA UI audit', () => {
  test('walk tabs, screenshots, JSON report for Claude', async ({ page, request }) => {
    test.setTimeout(90000);

    fs.mkdirSync(SCR, { recursive: true });

    const liveRes = await request.get('/api/live');
    const liveJson = liveRes.ok() ? await liveRes.json() : { _error: `HTTP ${liveRes.status()}` };

    await page.goto('/');
    await page.waitForSelector('#root > div', { timeout: 20000 });

    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    const tabs = [];
    const mockOrStatic = [];

    for (const id of TABS) {
      const btn = page.getByTestId(`tab-${id}`);
      await expect(btn).toBeVisible({ timeout: 10000 });
      await btn.click();
      await page.waitForTimeout(500);

      const png = path.join(SCR, `${id}.png`);
      await page.screenshot({ path: png, fullPage: true });

      const rootText = await page.locator('#root').innerText();
      const snippet = rootText.length > 6000 ? `${rootText.slice(0, 6000)}\n… [truncated]` : rootText;

      const findings = [];

      if (id === 'signals') {
        if (rootText.includes('G047') && rootText.includes('3181')) {
          findings.push('Likely static Signals demo (G047 / 3181 band) — verify against SCRIBE/API.');
          mockOrStatic.push({
            tab: 'signals',
            issue: 'Hardcoded Received/Executed tiles and row list in dashboard source',
            code: 'dashboard/app.js — tab===\'signals\' block',
          });
        }
      }
      // Perf sparkline is driven by GET /api/pnl_curve; do not flag on section title alone.
      tabs.push({
        id,
        screenshot: `tests/results/athena-ui/screens/${id}.png`,
        body_text_chars: rootText.length,
        text_snippet: snippet,
        findings,
      });
    }

    const noise = (e) =>
      !e.includes('net::') &&
      !e.includes('Failed to load') &&
      !e.includes('fetch') &&
      !e.includes('ResizeObserver');

    const report = {
      generated_at: new Date().toISOString(),
      athena_url: process.env.ATHENA_URL || 'http://localhost:7842',
      api_live_summary: summarizeLive(liveJson),
      console_errors_filtered: consoleErrors.filter(noise),
      tabs,
      mock_or_static_ui: mockOrStatic,
      suggested_next_steps_for_claude: [
        'Replace Signals tab with API-driven rows (e.g. extend athena_api + SCRIBE query for signals_received).',
        'When no data, show explicit "No signals today" instead of demo rows.',
        'Drive Performance sparkline from scribe performance history or hide chart until real series exists.',
        'Add data-testid on major panels if more granular Playwright asserts are needed.',
      ],
    };

    fs.mkdirSync(OUT, { recursive: true });
    fs.writeFileSync(REPORT, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

    expect(tabs).toHaveLength(4);
    expect(fs.existsSync(REPORT)).toBe(true);
    for (const id of TABS) {
      expect(fs.existsSync(path.join(SCR, `${id}.png`))).toBe(true);
    }
  });
});
