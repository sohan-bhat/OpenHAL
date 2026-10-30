import { expect, test, type Browser, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AgentClient, hubState, printAgain, showFrame, signIn } from "../e2e/hub";

const ROUND = process.env.INSPECTOR_ROUND ?? "2";
const OUT = process.env.INSPECTOR_SHOTS ?? fileURLToPath(new URL(`../../docs/design-rounds/inspector-round-${ROUND}/`, import.meta.url));
const SCENARIO = readFileSync(fileURLToPath(new URL("../../docs/demo/scenario.yaml", import.meta.url)), "utf-8");
const WIDTHS = [1440, 390] as const;
const THEMES = ["light", "dark"] as const;

test.describe.configure({ mode: "serial" });

async function reads(device: string, channel: string, wanted: unknown): Promise<void> {
  const state = hubState();
  for (let attempt = 0; attempt < 100; attempt++) {
    const response = await fetch(`${state.url}/v1/devices/${device}`, {
      headers: { Authorization: `Bearer ${state.humanToken}` },
    });
    const view = (await response.json()) as { read: Record<string, { value: unknown }> };
    if (view.read[channel]?.value === wanted) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`${device}.${channel} never read ${String(wanted)}.`);
}

test.beforeAll(async () => {
  test.setTimeout(120_000);
  mkdirSync(OUT, { recursive: true });
  expect(SCENARIO).toContain("extruder_target 300 degC exceeds the limit of 260 degC");
  await printAgain();
  await showFrame("first-layer");
  await reads("printer", "state", "printing");
  const agent = await AgentClient.connect("print-watcher", hubState().printToken);
  const look = { device: "printer-cam", channel: "frame" };
  expect((await agent.call("hal/read", look)).result?.value).toMatchObject({ bytes: 19409 });
  await agent.call("hal/read", { device: "printer", channel: "bed_target" });
  await new Promise((resolve) => setTimeout(resolve, 1100));
  expect((await agent.write("printer", "bed_target", 70, "degC")).result?.status).toBe("done");
  const hot = await agent.write("printer", "extruder_target", 300, "degC");
  expect(hot.error?.message).toBe("extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)");
  await showFrame("come-loose");
  expect((await agent.call("hal/read", look)).result?.value).toMatchObject({ bytes: 23567 });
  expect((await agent.call("hal/action", { device: "printer", action: "pause" })).result?.status).toBe("done");
  expect((await agent.call("hal/action", { device: "printer", action: "cancel" })).result?.status).toBe("pending");
  agent.close();
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
  await page.mouse.move(1, 1);
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
  const first = page.locator('li[data-kind="request"]').filter({ hasText: "printer-cam" }).first();
  if (phone) {
    await scrollTo(page, 'li[data-kind="request"]:has-text("printer-cam")', 90);
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

      await page.goto("/#/devices/printer");
      await expect(page.getByRole("heading", { name: "Klipper 3D printer", level: 1 })).toBeVisible();
      await expect(page.locator("main output").filter({ hasText: "paused" })).toBeVisible();
      await shoot(page, "devices", width, theme);
      await scrollTo(page, "#write-title", header);
      await shoot(page, "devices-controls", width, theme);
      await showLog(page, phone);
      await shoot(page, "log", width, theme);

      await page.goto("/#/devices/printer-cam");
      await expect(page.getByRole("main").getByRole("img", { name: /^Demo frame from Printer camera/ })).toBeVisible();
      if (phone) await scrollTo(page, "#frames-title", header);
      await shoot(page, "camera", width, theme);

      await page.goto("/#/devices/curing-heater");
      await expect(page.getByRole("heading", { name: "Resin curing heater", level: 1 })).toBeVisible();
      await scrollTo(page, "#write-title", header);
      await shoot(page, "device-control-channel", width, theme);

      await page.goto("/#/devices/bench-lamp");
      await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
      await shoot(page, "device-read-only", width, theme);

      await page.goto("/#/confirmations");
      const cancel = page.getByRole("main").getByRole("listitem").filter({ hasText: "sends a request to run cancel" }).first();
      await cancel.getByRole("combobox", { name: /camera/i }).selectOption("printer-cam/frame");
      await expect(cancel.getByRole("img", { name: /^Demo frame from Printer camera/ })).toBeVisible();
      await scrollTo(page, "#pending-title", header);
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
      await expect(page.getByRole("heading", { name: "The hub is unreachable" })).toBeVisible();
      await shoot(page, "offline", width, theme);
      await page.context().close();
    }
  }
});

test("the stopped state and UNLOCK", async ({ browser }) => {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const page = await open(browser, width, theme);
      await page.goto("/#/devices/printer");
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
