import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("..", import.meta.url));
const port = Number(process.env.INSPECTOR_PORT ?? 7432);
const state = fileURLToPath(new URL("./test-results/shots-hub.json", import.meta.url));
process.env.INSPECTOR_PORT = String(port);
process.env.INSPECTOR_STATE = state;

export default defineConfig({
  testDir: "./shots",
  testMatch: /.*\.shots\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, headless: true, ...devices["Desktop Chrome"] },
  webServer: {
    command: `${process.env.UV ?? "uv"} run python -m tests.inspector.serve --port ${port} --state ${state}`,
    cwd: repo,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
