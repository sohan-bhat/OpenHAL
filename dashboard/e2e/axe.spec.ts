import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const VIEWS = [
  "#/devices/printer",
  "#/devices/printer-cam",
  "#/devices/plant-waterer",
  "#/devices/curing-heater",
  "#/devices/bench-lamp",
  "#/confirmations",
  "#/audit",
  "#/routines",
  "#/writer",
  "#/settings",
];

async function violations(page: Page, name: string): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(200);
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations.map((violation) => `${name} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

async function queueRequests(): Promise<void> {
  const script = await AgentClient.connect("axe-script", hubState().mediumToken);
  const vent = await script.call("hal/action", {
    device: "curing-heater",
    action: "vent",
    args: { seconds: { value: 5, unit: "s" } },
  });
  script.close();
  expect(vent.result?.status).toBe("pending");
  const watcher = await AgentClient.connect("print-watcher", hubState().printToken);
  const cancel = await watcher.call("hal/action", { device: "printer", action: "cancel" });
  watcher.close();
  expect(cancel.result?.status).toBe("pending");
}

for (const scheme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    test(`every view and state passes axe WCAG 2.1 AA at ${width} px in the ${scheme} theme`, async ({ browser, browserName }) => {
      test.skip(browserName !== "chromium" && width < 800, "the phone pass runs in Chromium");
      test.setTimeout(browserName === "firefox" ? 600_000 : 300_000);
      const context = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 900 }, colorScheme: scheme });
      await signIn(context);
      const page = await context.newPage();
      const agent = await AgentClient.connect("axe-agent", hubState().printToken);
      await agent.write("printer", "extruder_target", 300, "degC");
      await agent.call("hal/read", { device: "printer-cam", channel: "frame" });
      agent.close();
      await queueRequests();
      const problems: string[] = [];

      for (const view of VIEWS) {
        await page.goto(`/${view}`);
        await expect(page.locator("main h1, main h2").first()).toBeVisible();
        if (view === "#/devices/printer-cam") await expect(page.getByRole("main").getByRole("img", { name: /^Demo frame/ })).toBeVisible();
        problems.push(...(await violations(page, view)));
      }

      await page.goto("/#/confirmations");
      const cancel = page.getByRole("main").getByRole("listitem").filter({ hasText: "asks to run cancel" }).first();
      await cancel.getByRole("combobox", { name: "Show a camera" }).selectOption("printer-cam/frame");
      await expect(cancel.getByRole("img", { name: /^Demo frame from Printer camera/ })).toBeVisible();
      problems.push(...(await violations(page, "cancel with its camera")));

      await page.goto("/#/devices/printer");
      await page.locator('li[data-kind="result"]').filter({ hasText: "printer-cam" }).last().getByRole("button", { name: "Show the whole message" }).click();
      problems.push(...(await violations(page, "frame result expanded")));

      await page.goto("/#/routines/water-when-dry");
      await page.getByRole("button", { name: "Dry run" }).click();
      await expect(page.getByRole("heading", { name: "Dry run" })).toBeVisible();
      problems.push(...(await violations(page, "routine dry run")));

      await page.goto("/#/writer");
      await page.getByRole("button", { name: "Start the driver writer" }).click();
      await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible();
      problems.push(...(await violations(page, "writer interview")));

      await page.goto("/#/devices/printer");
      await page.getByRole("button", { name: "Hide the log" }).click();
      problems.push(...(await violations(page, "log hidden")));
      await page.getByRole("button", { name: "Show the log" }).click();

      await page.getByRole("button", { name: /STOP/ }).click();
      await expect(page.getByRole("button", { name: "UNLOCK" })).toBeVisible();
      problems.push(...(await violations(page, "stopped")));
      await page.getByRole("button", { name: "UNLOCK" }).click();
      const dialog = page.getByRole("dialog", { name: "Lift the stop" });
      await expect(dialog).toBeVisible();
      problems.push(...(await violations(page, "unlock dialog")));
      await dialog.getByLabel("Phrase").fill("unlock");
      await dialog.getByRole("button", { name: "Unlock", exact: true }).click();
      await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
      await context.close();

      const stranger = await browser.newContext({ viewport: { width, height: 844 }, colorScheme: scheme });
      const pair = await stranger.newPage();
      await pair.goto("/");
      await expect(pair.getByRole("heading", { level: 1 })).toBeVisible();
      problems.push(...(await violations(pair, "pair")));
      await stranger.close();

      const lost = await browser.newContext({ viewport: { width, height: 844 }, colorScheme: scheme });
      await signIn(lost);
      const offline = await lost.newPage();
      await offline.route("**/v1/whoami", (route) => route.abort());
      await offline.goto("/");
      await expect(offline.getByRole("heading", { name: "The hub does not answer" })).toBeVisible();
      problems.push(...(await violations(offline, "offline")));
      await lost.close();

      expect(problems).toEqual([]);
    });
  }
}
