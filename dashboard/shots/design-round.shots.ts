import { expect, test, type Browser, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AgentClient, hubState, signIn, tank } from "../e2e/hub";

const ROUND = process.env.INSPECTOR_ROUND ?? "2";
const OUT = process.env.INSPECTOR_SHOTS ?? fileURLToPath(new URL(`../../docs/design-rounds/inspector-round-${ROUND}/`, import.meta.url));
const SCENARIO = readFileSync(fileURLToPath(new URL("../../docs/demo/scenario.yaml", import.meta.url)), "utf-8");
const WIDTHS = [1440, 390] as const;
const THEMES = ["light", "dark"] as const;

test.describe.configure({ mode: "serial" });

const water = (seconds: number) => ({
  device: "plant-waterer",
  action: "water",
  args: { duration: { value: seconds, unit: "s" } },
});

async function soilReads(wanted: number): Promise<void> {
  const state = hubState();
  for (let attempt = 0; attempt < 100; attempt++) {
    const response = await fetch(`${state.url}/v1/devices/plant-waterer`, {
      headers: { Authorization: `Bearer ${state.humanToken}` },
    });
    const view = (await response.json()) as { read: Record<string, { value: unknown }> };
    if (view.read.soil_moisture?.value === wanted) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`soil_moisture never read ${wanted} %.`);
}

async function tankReads(wanted: string): Promise<void> {
  const state = hubState();
  for (let attempt = 0; attempt < 100; attempt++) {
    const response = await fetch(`${state.url}/v1/devices/plant-waterer`, {
      headers: { Authorization: `Bearer ${state.humanToken}` },
    });
    const view = (await response.json()) as { read: Record<string, { value: unknown }> };
    if (view.read.tank?.value === wanted) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`The tank never read ${wanted}.`);
}

test.beforeAll(async () => {
  test.setTimeout(120_000);
  mkdirSync(OUT, { recursive: true });
  expect(SCENARIO).toContain("water duration 120 s exceeds the limit of 30 s");
  await soilReads(31);
  const agent = await AgentClient.connect("bench-agent", hubState().agentToken);
  const tooLong = await agent.call("hal/action", water(120));
  expect(tooLong.error?.message).toBe(
    "water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)",
  );
  await tank("drain");
  await tankReads("empty");
  const empty = await agent.call("hal/action", water(20));
  expect(empty.error?.data?.name).toBe("INTERLOCK_BLOCKED");
  expect(empty.error?.message).toBe("pump can't run while tank is empty");
  await tank("refill");
  await tankReads("ok");
  const watered = await agent.call("hal/action", water(20));
  expect(watered.result?.status).toBe("done");
  agent.close();
  await soilReads(46);
  const script = await AgentClient.connect("lab-script", hubState().mediumToken);
  const pending = await script.call("hal/action", {
    device: "curing-heater",
    action: "vent",
    args: { seconds: { value: 5, unit: "s" } },
  });
  expect(pending.result?.status).toBe("pending");
  script.close();
});

async function open(browser: Browser, width: number, theme: "light" | "dark"): Promise<Page> {
  const context = await browser.newContext({
    viewport: { width, height: width < 800 ? 844 : 900 },
    colorScheme: theme,
    reducedMotion: "reduce",
    deviceScaleFactor: width < 800 ? 2 : 1,
  });
  await signIn(context);
  return context.newPage();
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
}

async function shoot(page: Page, name: string, width: number, theme: string): Promise<void> {
  await settle(page);
  await page.screenshot({ path: `${OUT}${name}-${width}-${theme}.png` });
}

async function scrollTo(page: Page, selector: string, below: number): Promise<void> {
  await page.locator(selector).first().evaluate((element, gap) => {
    window.scrollTo(0, window.scrollY + element.getBoundingClientRect().top - (gap as number));
  }, below);
}

async function showLog(page: Page, phone: boolean): Promise<void> {
  await page.getByRole("button", { name: "Message log", exact: true }).click();
  const first = page.locator('li[data-kind="request"]').filter({ hasText: "plant-waterer" }).first();
  if (phone) {
    await scrollTo(page, 'li[data-kind="request"]:has-text("plant-waterer")', 90);
    return;
  }
  await first.evaluate((row) => {
    const scroller = row.closest(".scroller") as HTMLElement;
    scroller.scrollTop += row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 8;
  });
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`views at ${width} in ${theme}`, async ({ browser }) => {
      const page = await open(browser, width, theme);
      const phone = width < 800;
      const header = phone ? 80 : 140;

      await page.goto("/#/devices/plant-waterer");
      await expect(page.getByRole("heading", { name: "Arduino plant waterer", level: 1 })).toBeVisible();
      await expect(page.locator("main output").filter({ hasText: "46 %" })).toBeVisible();
      await shoot(page, "devices", width, theme);
      await scrollTo(page, "#actions-title", header);
      await shoot(page, "devices-controls", width, theme);
      await showLog(page, phone);
      await shoot(page, "log", width, theme);

      await page.goto("/#/devices/curing-heater");
      await expect(page.getByRole("heading", { name: "Resin curing heater", level: 1 })).toBeVisible();
      await scrollTo(page, "#write-title", header);
      await shoot(page, "device-control-channel", width, theme);

      await page.goto("/#/devices/bench-lamp");
      await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
      await shoot(page, "device-read-only", width, theme);

      await page.goto("/#/confirmations");
      await expect(page.getByText("requested by").first()).toBeVisible();
      await shoot(page, "confirmations", width, theme);

      await page.goto("/#/audit");
      await expect(page.locator("li.entry").first()).toBeVisible();
      await shoot(page, "audit", width, theme);

      await page.goto("/#/routines/water-when-dry");
      await page.getByRole("button", { name: "Dry run" }).click();
      await expect(page.getByRole("heading", { name: "Dry run" })).toBeVisible();
      await shoot(page, "routines", width, theme);

      await page.goto("/#/settings");
      await expect(page.getByRole("heading", { name: "Client tokens" })).toBeVisible();
      await shoot(page, "settings", width, theme);

      await page.goto("/#/writer");
      await expect(page.getByText("Simulated OpenHAL firmware board")).toBeVisible();
      await shoot(page, "writer", width, theme);
      await page.getByRole("button", { name: "Start the driver writer" }).click();
      await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible();
      await scrollTo(page, "#detected-title", header);
      await shoot(page, "writer-detected", width, theme);
      await scrollTo(page, "#interview-title", header);
      await shoot(page, "writer-interview", width, theme);
      for (const button of await page.getByRole("button", { name: /Use suggested value/ }).all()) await button.click();
      await page.getByRole("button", { name: "Confirm these limits" }).click();
      await expect(page.getByText(/added, \d+ removed since the draft/)).toBeVisible();
      await scrollTo(page, ".line.removed", header + 40);
      await shoot(page, "writer-review", width, theme);
      await page.context().close();
    });
  }
}

test("pairing and offline", async ({ browser }) => {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const viewport = { width, height: width < 800 ? 844 : 900 };
      const scale = width < 800 ? 2 : 1;
      const stranger = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "reduce", deviceScaleFactor: scale });
      const pair = await stranger.newPage();
      await pair.goto("/");
      await expect(pair.getByRole("heading", { name: "Pair this browser with the hub" })).toBeVisible();
      await shoot(pair, "pair", width, theme);
      await stranger.close();
      const page = await open(browser, width, theme);
      await page.route("**/v1/whoami", (route) => route.abort());
      await page.goto("/");
      await expect(page.getByText("does not answer")).toBeVisible();
      await shoot(page, "offline", width, theme);
      await page.context().close();
    }
  }
});

test("the stopped state and UNLOCK", async ({ browser }) => {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const page = await open(browser, width, theme);
      await page.goto("/#/devices/plant-waterer");
      await page.getByRole("button", { name: /STOP/ }).click();
      await expect(page.getByRole("button", { name: "UNLOCK" })).toBeVisible();
      await shoot(page, "stopped", width, theme);
      await page.getByRole("button", { name: "UNLOCK" }).click();
      await page.getByRole("dialog").getByLabel("Phrase").fill("unlock");
      await shoot(page, "unlock", width, theme);
      await page.getByRole("dialog").getByRole("button", { name: "Unlock", exact: true }).click();
      await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
      await page.context().close();
    }
  }
});
