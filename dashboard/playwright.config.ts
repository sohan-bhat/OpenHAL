import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { PORT, STATE_PATH } from "./e2e/hub";

const repo = fileURLToPath(new URL("..", import.meta.url));
const python = process.env.UV ?? "uv";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `PYTHONPATH=. ${python} run python dashboard/e2e/print_hub.py --port ${PORT} --state ${STATE_PATH}`,
    cwd: repo,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
