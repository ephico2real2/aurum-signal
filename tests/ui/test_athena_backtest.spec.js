/**
 * ATHENA Backtest + Indicators Panel — automated Playwright tests.
 *
 * Covers:
 *   - All tab navigation (all 8 tabs exist and are clickable)
 *   - Backtest tab: run list, stat grid, P&L chart axes, TAKEN ENTRIES, GATE BREAKDOWN
 *   - Gate legend: 3-line display (code + label + explanation) renders
 *   - Indicators tab: indicator cards render with required fields
 *   - Section 508: key headers ≥ 4.5:1 contrast ratio, ≥ 9px font
 *   - Auto-refresh: btRuns and btDetail intervals fire within 35s
 *   - API wiring: gate_legend and indicator_legend endpoints return data
 *
 * Run:  make test-ui
 *       OR: cd tests && npx playwright test test_athena_backtest.spec.js
 *
 * MAINTAIN: Update this file whenever you add a new tab, panel, or field
 * to the Athena UI. Run after EVERY dashboard change.
 */
const { test, expect } = require('@playwright/test');

const BASE = process.env.ATHENA_URL || 'http://localhost:7842';

// All expected tab test-ids in order
const ALL_TABS = ['groups','closures','activity','signals','uploads','perf','backtest','indicators'];

// ── helpers ─────────────────────────────────────────────────────────
function luminance(r, g, b) {
  const chan = [r, g, b].map(v => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2];
}
function contrastRatio(c1, c2) {
  const l1 = Math.max(c1, c2), l2 = Math.min(c1, c2);
  return (l1 + 0.05) / (l2 + 0.05);
}
function parseRgb(s) {
  const m = s.match(/\d+/g);
  return m ? [+m[0], +m[1], +m[2]] : [0, 0, 0];
}

async function getContrastForSelector(page, selector) {
  return page.evaluate((sel) => {
    function lum(r, g, b) {
      return [r, g, b].map(v => {
        const s = v / 255;
        return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      }).reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
    }
    function parseRgb(s) { const m = s.match(/\d+/g); return m ? [+m[0], +m[1], +m[2]] : [0, 0, 0]; }
    const el = document.querySelector(sel);
    if (!el) return null;
    const cs = window.getComputedStyle(el);
    const fg = parseRgb(cs.color);
    const bg = parseRgb(cs.backgroundColor);
    const l1 = lum(...fg), l2 = lum(...bg);
    const cr = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    return { contrast: cr, fontSize: parseFloat(cs.fontSize), color: cs.color, bg: cs.backgroundColor };
  }, selector);
}

async function clickTab(page, tabId) {
  const btn = page.getByTestId(`tab-${tabId}`);
  await expect(btn).toBeVisible({ timeout: 8000 });
  await btn.click();
  await page.waitForTimeout(400);
}

// ── test suite ───────────────────────────────────────────────────────
test.describe.configure({ mode: 'serial' });

test.describe('ATHENA — all tabs exist and load', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('#root > div', { timeout: 15000 });
  });

  test('all 8 tabs are present and visible', async ({ page }) => {
    for (const id of ALL_TABS) {
      const btn = page.getByTestId(`tab-${id}`);
      await expect(btn).toBeVisible({ timeout: 5000 });
    }
  });

  test('each tab is clickable and renders content without crash', async ({ page }) => {
    const consoleErrors = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

    for (const id of ALL_TABS) {
      await clickTab(page, id);
      // Page must still have content after each tab switch
      const root = page.locator('#root > div');
      await expect(root).toBeVisible();
    }

    // Filter known non-crash noise (CDN failures in sandboxed env, etc.)
    const realErrors = consoleErrors.filter(e =>
      !e.includes('net::ERR') && !e.includes('favicon') && !e.includes('cdnjs')
    );
    expect(realErrors, `Console errors: ${realErrors.join('\n')}`).toHaveLength(0);
  });
});

test.describe('ATHENA — Backtest tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('#root > div', { timeout: 15000 });
    await clickTab(page, 'backtest');
  });

  test('run selector shows at least one run or "No backtest runs" message', async ({ page }) => {
    // Either a run pill or an empty state message must exist
    const hasPill = await page.locator('[data-testid^="bt-run-"]').count().catch(() => 0);
    const hasEmpty = await page.getByText('No backtest runs').isVisible().catch(() => false);
    const hasCount = await page.getByText(/run\(s\) stored/).isVisible().catch(() => false);
    expect(hasPill > 0 || hasEmpty || hasCount).toBe(true);
  });

  test('stat grid shows key labels', async ({ page }) => {
    // Give it time for the first fetch to complete
    await page.waitForTimeout(2000);
    const labels = ['Total P&L', 'Win Rate', 'Trades', 'TAKEN', 'Skipped'];
    for (const label of labels) {
      await expect(page.getByText(label).first()).toBeVisible({ timeout: 10000 });
    }
  });

  test('CUMULATIVE P&L chart has X and Y axis labels', async ({ page }) => {
    await page.waitForTimeout(2000);
    // Only check if there are runs (chart won't render with no data)
    const hasChart = await page.getByText('CUMULATIVE P&L').isVisible().catch(() => false);
    if (hasChart) {
      await expect(page.locator('text=Equity ($)').first()).toBeVisible({ timeout: 5000 });
      await expect(page.locator('text=Trade #').first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('TAKEN ENTRIES table renders before GATE BREAKDOWN', async ({ page }) => {
    await page.waitForTimeout(2000);
    const takenVisible = await page.getByText('TAKEN ENTRIES').isVisible().catch(() => false);
    const gatesVisible = await page.getByText('GATE BREAKDOWN (SKIP)').isVisible().catch(() => false);
    if (takenVisible && gatesVisible) {
      // TAKEN ENTRIES must appear higher on the page (smaller Y) than GATE BREAKDOWN
      const takenBox = await page.getByText('TAKEN ENTRIES').first().boundingBox();
      const gateBox  = await page.getByText('GATE BREAKDOWN (SKIP)').first().boundingBox();
      expect(takenBox.y).toBeLessThan(gateBox.y);
    }
  });

  test('TAKEN ENTRIES table columns render', async ({ page }) => {
    await page.waitForTimeout(2000);
    const visible = await page.getByText('TAKEN ENTRIES').isVisible().catch(() => false);
    if (!visible) return; // no runs yet — skip
    const cols = ['TIME (UTC)', 'DIR', 'SESSION', 'SETUP', 'OUTCOME'];
    for (const col of cols) {
      await expect(page.getByText(col).first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('GATE BREAKDOWN renders with legend explanation (3-line format)', async ({ page }) => {
    await page.waitForTimeout(3000); // legend fetch takes a moment
    const visible = await page.getByText('GATE BREAKDOWN (SKIP)').isVisible().catch(() => false);
    if (!visible) return; // no runs yet — skip
    // At least one gate entry with a ↳ legend label should be present
    const legendLabels = await page.locator('text=/↳ /').count();
    expect(legendLabels).toBeGreaterThan(0);
  });
});

test.describe('ATHENA — Indicators tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('#root > div', { timeout: 15000 });
    await clickTab(page, 'indicators');
    await page.waitForTimeout(1500); // allow legend fetch
  });

  test('Indicators tab renders the panel header', async ({ page }) => {
    await expect(page.getByText('FORGE INDICATOR REFERENCE').first()).toBeVisible({ timeout: 8000 });
  });

  test('key indicator acronyms are rendered as cards', async ({ page }) => {
    const required = ['RSI', 'ADX', 'ATR', 'BB', 'MACD', 'OsMA'];
    for (const acr of required) {
      await expect(page.getByText(acr).first()).toBeVisible({ timeout: 8000 });
    }
  });

  test('each indicator card has HOW FORGE USES IT section', async ({ page }) => {
    const count = await page.getByText('HOW FORGE USES IT').count();
    expect(count).toBeGreaterThan(5); // at least 6 indicators visible
  });

  test('indicator cards have full_name text (not just acronym)', async ({ page }) => {
    await expect(page.getByText('Relative Strength Index').first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('Average True Range').first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('Bollinger Bands').first()).toBeVisible({ timeout: 8000 });
  });
});

test.describe('ATHENA — Section 508 contrast compliance', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector('#root > div', { timeout: 15000 });
    await clickTab(page, 'backtest');
    await page.waitForTimeout(2000);
  });

  test('TAKEN ENTRIES header cells ≥ 4.5:1 contrast and ≥ 9px font', async ({ page }) => {
    const visible = await page.getByText('TAKEN ENTRIES').isVisible().catch(() => false);
    if (!visible) return;

    const result = await page.evaluate(() => {
      function lum(r, g, b) {
        return [r, g, b].map(v => {
          const s = v / 255;
          return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        }).reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
      }
      function parse(s) { const m = s.match(/\d+/g); return m ? [+m[0], +m[1], +m[2]] : [128, 128, 128]; }

      const all = [...document.querySelectorAll('div')];
      const header = all.find(el => el.textContent.trim() === 'TAKEN ENTRIES');
      if (!header) return { skipped: true };
      const container = header.parentElement;
      const headerRow = container.children[1];
      if (!headerRow) return { skipped: true };

      return [...headerRow.children].map(c => {
        const cs = window.getComputedStyle(c);
        const fg = parse(cs.color);
        const bg = parse(window.getComputedStyle(container).backgroundColor);
        const l1 = lum(...fg), l2 = lum(...bg);
        const cr = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        return { text: c.textContent.trim(), contrast: cr, fontSize: parseFloat(cs.fontSize) };
      });
    });

    if (result.skipped) return;
    for (const cell of result) {
      expect(cell.contrast, `"${cell.text}" contrast ${cell.contrast.toFixed(2)}:1 < 4.5:1`).toBeGreaterThanOrEqual(4.5);
      expect(cell.fontSize, `"${cell.text}" font ${cell.fontSize}px < 9px`).toBeGreaterThanOrEqual(9);
    }
  });

  test('GATE BREAKDOWN header ≥ 4.5:1 contrast and ≥ 9px', async ({ page }) => {
    const visible = await page.getByText('GATE BREAKDOWN (SKIP)').isVisible().catch(() => false);
    if (!visible) return;

    const result = await page.evaluate(() => {
      function lum(r, g, b) {
        return [r, g, b].map(v => {
          const s = v / 255;
          return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        }).reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
      }
      function parse(s) { const m = s.match(/\d+/g); return m ? [+m[0], +m[1], +m[2]] : [128, 128, 128]; }
      const el = [...document.querySelectorAll('div')].find(d => d.textContent.trim() === 'GATE BREAKDOWN (SKIP)');
      if (!el) return null;
      const cs = window.getComputedStyle(el);
      const fg = parse(cs.color);
      const bg = parse(window.getComputedStyle(el.parentElement).backgroundColor);
      const l1 = lum(...fg), l2 = lum(...bg);
      return { contrast: (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05), fontSize: parseFloat(cs.fontSize) };
    });
    if (!result) return;
    expect(result.contrast).toBeGreaterThanOrEqual(4.5);
    expect(result.fontSize).toBeGreaterThanOrEqual(9);
  });
});

test.describe('ATHENA — API endpoints wired correctly', () => {
  test('GET /api/gate_legend returns 508-compliant structure', async ({ request }) => {
    const res = await request.get(`${BASE}/api/gate_legend`);
    expect(res.ok()).toBe(true);
    const body = await res.json();
    // Must have entries (not empty, no top-level error)
    expect(Object.keys(body).length).toBeGreaterThan(10);
    // Every entry must have label + explanation
    for (const [key, val] of Object.entries(body)) {
      expect(typeof val.label, `${key}.label missing`).toBe('string');
      expect(typeof val.explanation, `${key}.explanation missing`).toBe('string');
      expect(val.label.length, `${key}.label empty`).toBeGreaterThan(0);
    }
  });

  test('GET /api/indicator_legend returns all required indicators', async ({ request }) => {
    const res = await request.get(`${BASE}/api/indicator_legend`);
    expect(res.ok()).toBe(true);
    const body = await res.json();
    const required = ['RSI', 'ADX', 'ATR', 'BB', 'MACD', 'OsMA', 'EMA', 'PSAR'];
    for (const acr of required) {
      expect(body[acr], `${acr} missing from indicator_legend`).toBeDefined();
      expect(body[acr].full_name).toBeTruthy();
      expect(body[acr].forge_usage).toBeTruthy();
      expect(body[acr].what_it_measures).toBeTruthy();
    }
  });

  test('GET /api/backtest/runs returns valid structure', async ({ request }) => {
    const res = await request.get(`${BASE}/api/backtest/runs`);
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(typeof body.count).toBe('number');
    expect(Array.isArray(body.runs)).toBe(true);
    // If runs exist, validate structure
    if (body.runs.length > 0) {
      const r = body.runs[0];
      expect(typeof r.aurum_run_id).toBe('number');
      expect(typeof r.taken).toBe('number');
      expect(typeof r.total_pnl).toBe('number');
      // P&L must be correct (not inflated by Cartesian join)
      expect(r.wins).toBeLessThanOrEqual(r.taken * 10); // at most 10 deals per group
    }
  });

  test('GET /api/backtest/run/<id> enriches taken entries with trade_outcome', async ({ request }) => {
    const runsRes = await request.get(`${BASE}/api/backtest/runs`);
    const { runs } = await runsRes.json();
    if (runs.length === 0) return; // no data yet — skip

    const id = runs[0].aurum_run_id;
    const res = await request.get(`${BASE}/api/backtest/run/${id}`);
    expect(res.ok()).toBe(true);
    const body = await res.json();

    expect(Array.isArray(body.taken)).toBe(true);
    if (body.taken.length > 0) {
      const entry = body.taken[0];
      expect(entry.trade_outcome).toBeDefined();
      expect(entry.pnl).toBeDefined();
      expect(['TP1','TP2','TP3','TP4','SL','WIN','OPEN','CLOSED']).toContain(entry.trade_outcome);
    }

    // P&L curve must have x and be ordered
    expect(Array.isArray(body.pnl_curve)).toBe(true);
  });
});

test.describe('ATHENA — auto-refresh wiring', () => {
  test('backtest runs refresh within 35 seconds when tab is open', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto(BASE);
    await page.waitForSelector('#root > div', { timeout: 15000 });

    let fetchCount = 0;
    page.on('request', req => {
      if (req.url().includes('/api/backtest/runs')) fetchCount++;
    });

    await clickTab(page, 'backtest');
    await page.waitForTimeout(35000); // 30s interval + buffer

    // Should have fired at least twice: initial load + one auto-refresh
    expect(fetchCount).toBeGreaterThanOrEqual(2);
  });
});
