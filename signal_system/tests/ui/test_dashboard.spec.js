// test_dashboard.spec.js — ATHENA dashboard load and panel visibility tests
const { test, expect } = require('@playwright/test');

const ATHENA_URL = process.env.ATHENA_URL || 'http://localhost:7842';

test.describe('ATHENA Dashboard', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(ATHENA_URL);
    // Wait for React to mount
    await page.waitForSelector('#root > div', { timeout: 10000 });
  });

  test('dashboard loads without error', async ({ page }) => {
    await expect(page).not.toHaveTitle(/Error/);
    const root = page.locator('#root');
    await expect(root).toBeVisible();
  });

  test('ATHENA header is visible', async ({ page }) => {
    // Look for ATHENA text in header
    const header = page.locator('text=ATHENA').first();
    await expect(header).toBeVisible();
  });

  test('mode badge is visible', async ({ page }) => {
    // Mode badge: OFF, WATCH, SIGNAL, SCALPER, or HYBRID
    const modes = ['OFF', 'WATCH', 'SIGNAL', 'SCALPER', 'HYBRID', 'DISCONNECTED'];
    let found = false;
    for (const mode of modes) {
      const el = page.locator(`text=${mode}`).first();
      if (await el.isVisible().catch(() => false)) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test('left column panels are visible', async ({ page }) => {
    await expect(page.locator('text=Account').first()).toBeVisible();
    await expect(page.locator('text=Mode Control').first()).toBeVisible();
  });

  test('LENS panel is visible', async ({ page }) => {
    await expect(page.locator('text=LENS').first()).toBeVisible();
  });

  test('system health panel is visible', async ({ page }) => {
    await expect(page.locator('text=System Health').first()).toBeVisible();
  });

  test('tab navigation exists', async ({ page }) => {
    // Should have Groups, Activity, Signals, Performance tabs
    await expect(page.locator('text=Groups').first()).toBeVisible();
    await expect(page.locator('text=Activity').first()).toBeVisible();
  });

  test('no JavaScript errors on load', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto(ATHENA_URL);
    await page.waitForTimeout(2000);
    // Filter out network errors for MT5 (expected when not running)
    const realErrors = errors.filter(e =>
      !e.includes('fetch') && !e.includes('net::') && !e.includes('Failed to load')
    );
    expect(realErrors).toHaveLength(0);
  });

});
