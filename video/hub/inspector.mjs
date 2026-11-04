import { createRequire } from "node:module";
import { createInterface } from "node:readline";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "..", "dashboard", "package.json"));
const { chromium } = require("@playwright/test");

let browser = null;
let page = null;

const recordClicks = () => {
  window.__openhalClicks = [];
  document.addEventListener(
    "click",
    (event) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      window.__openhalClicks.push({
        event_ms: performance.timeOrigin + event.timeStamp,
        button: button ? button.innerText.trim() : null,
        label: button ? button.getAttribute("aria-label") : null,
      });
    },
    true,
  );
};

const handlers = {
  async open({ url, code, width, height, scale, scheme }) {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: scale,
      colorScheme: scheme,
      reducedMotion: "no-preference",
    });
    await context.addInitScript(recordClicks);
    page = await context.newPage();
    await page.goto(url);
    await page.locator("#pair-code").fill(code);
    await page.getByRole("button", { name: "Pair", exact: true }).click();
    await page.getByRole("button", { name: "STOP every device" }).waitFor({ timeout: 15000 });
    return {};
  },
  async goto({ hash }) {
    await page.evaluate((target) => {
      location.hash = target;
    }, hash);
    await page.waitForTimeout(300);
    return {};
  },
  async wait({ selector, timeout }) {
    await page.locator(selector).first().waitFor({ state: "visible", timeout: timeout ?? 15000 });
    return {};
  },
  async reveal({ selector }) {
    await page.locator(selector).first().scrollIntoViewIfNeeded();
    return {};
  },
  async shot({ file, scheme }) {
    if (scheme) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.waitForTimeout(120);
    }
    const taken_ms = Date.now();
    await page.screenshot({ path: file });
    return { taken_ms };
  },
  async scheme({ scheme }) {
    await page.emulateMedia({ colorScheme: scheme });
    return {};
  },
  async click({ name, exact, selector }) {
    const target = selector ? page.locator(selector).first() : page.getByRole("button", { name, exact: !!exact }).first();
    await target.waitFor({ state: "visible", timeout: 15000 });
    const before = await page.evaluate(() => window.__openhalClicks.length);
    const before_ms = Date.now();
    await target.click();
    const after_ms = Date.now();
    const clicks = await page.evaluate(() => window.__openhalClicks);
    const event = clicks.slice(before).pop() ?? null;
    return { before_ms, after_ms, event };
  },
  async text({ selector }) {
    return { text: await page.locator(selector).first().innerText() };
  },
  async close() {
    if (browser) await browser.close();
    browser = null;
    return {};
  },
};

const lines = createInterface({ input: process.stdin });
for await (const line of lines) {
  if (!line.trim()) continue;
  const request = JSON.parse(line);
  const reply = { id: request.id };
  try {
    Object.assign(reply, { ok: true }, await handlers[request.cmd](request));
  } catch (error) {
    Object.assign(reply, { ok: false, error: String(error && error.message ? error.message : error).slice(0, 800) });
  }
  process.stdout.write(JSON.stringify(reply) + "\n");
  if (request.cmd === "close") break;
}
if (browser) await browser.close();
process.exit(0);
