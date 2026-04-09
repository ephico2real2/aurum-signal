const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir:       './ui',
  testMatch:     '**/*.spec.js',
  fullyParallel: false,
  workers:       1,
  retries:       1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL:           process.env.ATHENA_URL || 'http://localhost:7842',
    ...devices['Desktop Chrome'],
    trace:             'on-first-retry',
    screenshot:        'only-on-failure',
    video:             'on-first-retry',
    actionTimeout:     10000,
    navigationTimeout: 15000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  timeout:  30000,
  outputDir: 'test-results',
});
