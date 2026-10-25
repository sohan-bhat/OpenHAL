import { expect, test, type Browser, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AgentClient, hubState, signIn } from "../e2e/hub";

const OUT = fileURLToPath(new URL("../../docs/design-rounds/inspector-round-1/", import.meta.url));
const WIDTHS = [1440, 390] as const;
const THEMES = ["light", "dark"] as const;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  mkdirSync(OUT, { recursive: true });
  const agent = await AgentClient.connect("bench-agent", hubState().agentToken);
  const blocked = await agent.call("hal/action", {
    device: "plant-waterer",
    action: "water",
    args: { duration: { value: 120, unit: "s" } },
  });
  expect(blocked.error?.data?.name).toBe("LIMIT_EXCEEDED");
  const granted = await agent.call("hal/action", {
    device: "plant-waterer",
    action: "water",
    args: { duration: { value: 20, unit: "s" } },
  });
  expect(granted.result?.status).toBe("done");
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

async function scrollWithin(page: Page, selector: string, container: string, offset: number): Promise<void> {
  await page.locator(selector).first().evaluate(
    (element, [box, gap]) => {
      const scroller = element.closest(box as string) as HTMLElement | null;
      if (!scroller) return;
      scroller.scrollTop += element.getBoundingClientRect().top - scroller.getBoundingClientRect().top - (gap as number);
    },
    [container, offset],
  );
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
}

async function shoot(page: Page, name: string, width: number, theme: string): Promise<void> {
  await settle(page);
  await page.screenshot({ path: `${OUT}${name}-${width}-${theme}.png` });
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`views at ${width} in ${theme}`, async ({ browser }) => {
      const page = await open(browser, width, theme);
      const phone = width < 800;

      await page.goto("/#/devices/plant-waterer");
      await expect(page.locator('li[data-kind="error"]').filter({ hasText: "LIMIT_EXCEEDED" }).first()).toBeAttached();
      if (!phone) {
        await page.waitForTimeout(400);
        await scrollWithin(page, 'li[data-kind="request"]:has-text("\"value\": 120")', ".scroller", 8);
      }
      await shoot(page, "devices", width, theme);
      if (phone) {
        await page.getByRole("heading", { name: "Actions" }).scrollIntoViewIfNeeded();
        await page.evaluate(() => window.scrollBy(0, -90));
        await shoot(page, "devices-controls", width, theme);
        await page.getByRole("heading", { name: "Message log" }).scrollIntoViewIfNeeded();
        await page.locator('li[data-kind="error"]').filter({ hasText: "LIMIT_EXCEEDED" }).last().scrollIntoViewIfNeeded();
        await page.evaluate(() => window.scrollBy(0, 160));
        await shoot(page, "log", width, theme);
      }

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
      await page.getByRole("heading", { name: "Limits interview" }).scrollIntoViewIfNeeded();
      await shoot(page, "writer-interview", width, theme);
      for (const button of await page.getByRole("button", { name: /Use the suggested value/ }).all()) await button.click();
      await page.getByRole("button", { name: "Confirm these limits" }).click();
      await expect(page.getByText(/added, \d+ removed since the draft/)).toBeVisible();
      if (phone) {
        await page.locator(".line.removed").first().evaluate((line) => line.scrollIntoView({ block: "start" }));
        await page.evaluate(() => window.scrollBy(0, -80));
      } else {
        await scrollWithin(page, ".line.removed", "main", 60);
      }
      await shoot(page, "writer-review", width, theme);
      await page.context().close();
    });
  }
}

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
