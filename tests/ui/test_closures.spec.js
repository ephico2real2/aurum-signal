// test_closures.spec.js — ATHENA Closures tab tests
const { test, expect } = require('@playwright/test');

const ATHENA_URL = process.env.ATHENA_URL || 'http://localhost:7842';

test.describe('ATHENA Closures Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(ATHENA_URL);
    await page.waitForSelector('#root > div', { timeout: 10000 });
    await page.waitForTimeout(1000); // allow poll
  });

  test('Closures tab is visible in tab bar', async ({ page }) => {
    const closuresTab = page.locator('[data-testid="tab-closures"]');
    await expect(closuresTab).toBeVisible();
  });

  test('Closures tab switches content on click', async ({ page }) => {
    const closuresTab = page.locator('[data-testid="tab-closures"]');
    await closuresTab.click();
    await page.waitForTimeout(500);
    // Should show either closure rows or empty state
    const hasClosures = await page.locator('text=SL_HIT').first().isVisible().catch(() => false) ||
                        await page.locator('text=TP1_HIT').first().isVisible().catch(() => false) ||
                        await page.locator('text=MANUAL_CLOSE').first().isVisible().catch(() => false);
    const hasEmpty = await page.locator('text=No closures recorded yet').isVisible().catch(() => false);
    expect(hasClosures || hasEmpty).toBe(true);
  });

  test('Closures tab shows API help text', async ({ page }) => {
    await page.locator('[data-testid="tab-closures"]').click();
    await page.waitForTimeout(500);
    // Footer help text
    await expect(page.locator('text=Full history').first()).toBeVisible();
  });

  test('Closures stats tiles render when data exists', async ({ page }) => {
    await page.locator('[data-testid="tab-closures"]').click();
    await page.waitForTimeout(500);
    // Stat tiles always present if closure_stats.total > 0
    // If no closures yet, the tiles section won't render — that's expected
    const hasTiles = await page.locator('text=SL Hits').isVisible().catch(() => false);
    const hasEmpty = await page.locator('text=No closures recorded yet').isVisible().catch(() => false);
    // Either tiles or empty state — both are valid
    expect(hasTiles || hasEmpty).toBe(true);
  });

  test('Can switch between Groups and Closures tabs', async ({ page }) => {
    // Start on Groups
    const groupsTab = page.locator('[data-testid="tab-groups"]');
    const closuresTab = page.locator('[data-testid="tab-closures"]');

    await groupsTab.click();
    await page.waitForTimeout(300);

    await closuresTab.click();
    await page.waitForTimeout(300);

    // Switch back to Groups
    await groupsTab.click();
    await page.waitForTimeout(300);

    // Should not crash — verify groups content is back
    const hasGroups = await page.locator('text=No open groups').isVisible().catch(() => false) ||
                      await page.locator('text=BUY').isVisible().catch(() => false) ||
                      await page.locator('text=SELL').isVisible().catch(() => false);
    expect(hasGroups).toBe(true);
  });

});
