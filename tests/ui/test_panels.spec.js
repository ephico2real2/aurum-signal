// test_panels.spec.js — ATHENA panel interaction tests
const { test, expect } = require('@playwright/test');

const ATHENA_URL = process.env.ATHENA_URL || 'http://localhost:7842';

test.describe('ATHENA Panel Interactions', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(ATHENA_URL);
    await page.waitForSelector('#root > div', { timeout: 10000 });
    await page.waitForTimeout(1000); // allow poll to run
  });

  test('right panel shows enhanced TradingView/LENS sections', async ({ page }) => {
    await expect(page.locator('text=TradingView · indicators').first()).toBeVisible();
    await expect(page.locator('text=DMI STUDY').first()).toBeVisible();
    await expect(page.locator('text=ORDER BLOCK DETECTOR').first()).toBeVisible();
    await expect(page.locator('text=TV suggest:').first()).toBeVisible();
  });

  test('right panel keeps required indicator labels', async ({ page }) => {
    for (const label of ['RSI 14', 'MACD', 'BB Rtg', 'ADX', 'EMA20', 'EMA50']) {
      await expect(page.locator(`text=${label}`).first()).toBeVisible();
    }
  });

  test('Activity tab switches content', async ({ page }) => {
    const activityTab = page.locator('text=Activity').first();
    await expect(activityTab).toBeVisible();
    await activityTab.click();
    // Should show activity log area
    await page.waitForTimeout(500);
    // Filter buttons should appear
    await expect(page.locator('text=INFO').first()).toBeVisible();
  });

  test('Activity pause toggles live tail (button + footer)', async ({ page }) => {
    await page.locator('text=Activity').first().click();
    await page.waitForTimeout(400);
    const pauseBtn = page.getByRole('button', { name: '⏸ PAUSE' });
    await expect(pauseBtn).toBeVisible();
    await expect(page.locator('text=LIVE — SCRIBE').first()).toBeVisible();
    await pauseBtn.click();
    await expect(page.getByRole('button', { name: '▶ RESUME' })).toBeVisible();
    await expect(page.locator('text=PAUSED').first()).toBeVisible();
    await page.getByRole('button', { name: '▶ RESUME' }).click();
    await expect(page.getByRole('button', { name: '⏸ PAUSE' })).toBeVisible();
    await expect(page.locator('text=LIVE — SCRIBE').first()).toBeVisible();
  });

  test('Mode control buttons are clickable', async ({ page }) => {
    // Click WATCH mode button
    const watchBtn = page.locator('text=WATCH').first();
    await expect(watchBtn).toBeVisible();
    await watchBtn.click();
    await page.waitForTimeout(500);
    // Should not crash
  });

  test('AURUM chat input is present', async ({ page }) => {
    const chatInput = page.locator('textarea[placeholder*=\"AURUM\"]').first();
    await expect(chatInput).toBeVisible();
    await expect(chatInput).toBeEnabled();
    await expect(page.getByRole('button', { name: 'SEND' })).toBeVisible();
  });

  test('Performance tab shows stats', async ({ page }) => {
    const perfTab = page.locator('text=Performance').first();
    await expect(perfTab).toBeVisible();
    await perfTab.click();
    await page.waitForTimeout(500);
    await expect(page.locator('text=Win Rate').first()).toBeVisible();
  });

  test('Groups tab shows open groups or empty state', async ({ page }) => {
    // Groups is default tab
    const groupsArea = page.locator('text=Groups').first();
    await expect(groupsArea).toBeVisible();
    await groupsArea.click();
    await page.waitForTimeout(500);
    // Either shows groups or "No open groups"
    const hasGroups = await page.locator('text=No open groups').isVisible().catch(() => false);
    const hasGroupCard = await page.locator('text=BUY').isVisible().catch(() => false) ||
                         await page.locator('text=SELL').isVisible().catch(() => false);
    expect(hasGroups || hasGroupCard).toBe(true);
  });

  test('SENTINEL panel shows status', async ({ page }) => {
    const sentinel = page.locator('text=SENTINEL').first();
    await expect(sentinel).toBeVisible();
    // Should show either CLEAR TO TRADE or TRADING PAUSED
    const clear = await page.locator('text=CLEAR TO TRADE').isVisible().catch(() => false);
    const paused = await page.locator('text=TRADING PAUSED').isVisible().catch(() => false);
    expect(clear || paused).toBe(true);
  });

});
