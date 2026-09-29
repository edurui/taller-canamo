import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 40_000,
  expect: { timeout: 7_000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "reports/e2e/results.json" }],
    ["html", { outputFolder: "reports/e2e/html", open: "never" }],
  ],
  outputDir: "reports/e2e/artifacts",
  use: {
    browserName: "chromium",
    channel: "chromium",
    locale: "es-ES",
    timezoneId: "Europe/Madrid",
    viewport: { width: 1366, height: 768 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
