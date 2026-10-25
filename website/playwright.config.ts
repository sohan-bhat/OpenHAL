import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.OPENHAL_PREVIEW_PORT ?? 4322);
if (port === 4000) throw new Error("Port 4000 is reserved. Choose another port.");

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    trace: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], headless: true } },
    { name: "firefox", use: { ...devices["Desktop Firefox"], headless: true } },
    { name: "webkit", use: { ...devices["Desktop Safari"], headless: true } },
  ],
  webServer: {
    command: `pnpm exec astro preview --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
