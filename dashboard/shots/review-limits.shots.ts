import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { hubState, signIn } from "../e2e/hub";

const OUT = process.env.SHOTS_DIR ?? fileURLToPath(new URL("../test-results/review-limits/", import.meta.url));

async function resetLamp(): Promise<void> {
  await fetch(`${hubState().url}/_harness/bench-lamp/reset`, { method: "POST" });
}

async function shot(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

for (const scheme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    test(`Review limits at ${width} px in the ${scheme} theme`, async ({ browser }) => {
      await resetLamp();
      const context = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 900 }, colorScheme: scheme });
      await signIn(context);
      const page = await context.newPage();
      const tag = `${width}-${scheme}`;
      await page.goto("/#/devices/bench-lamp");
      await expect(page.getByRole("button", { name: "Review limits" })).toBeVisible();
      await shot(page, `1-device-${tag}`);
      await page.getByRole("button", { name: "Review limits" }).click();
      await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible();
      await shot(page, `2-interview-${tag}`);
      for (const button of await page.getByRole("button", { name: /^Use suggested value for / }).all()) await button.click();
      await page.getByLabel("brightness, in percent. The most an agent may set.").fill("120 %");
      await page.getByLabel("Phrase").fill("confirm");
      await page.getByRole("button", { name: "Confirm the limits" }).click();
      await expect(page.getByText("the most the device reports")).toBeVisible();
      await shot(page, `3-held-${tag}`);
      await page.getByLabel("brightness, in percent. The most an agent may set.").fill("60 %");
      await page.getByRole("button", { name: "Confirm the limits" }).click();
      await expect(page.getByText("is now writable.")).toBeVisible();
      await shot(page, `4-confirmed-${tag}`);
      await page.goto("/#/devices/bench-lamp");
      await expect(page.getByText("takes commands")).toBeVisible();
      await shot(page, `5-writable-${tag}`);
      await context.close();
      await resetLamp();
    });

    test(`Limits and a pending limit change at ${width} px in the ${scheme} theme`, async ({ browser }) => {
      const state = hubState();
      await fetch(`${state.url}/_harness/curing-heater/reset`, { method: "POST" });
      const context = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 900 }, colorScheme: scheme });
      await signIn(context);
      const page = await context.newPage();
      const tag = `${width}-${scheme}`;
      await page.goto("/#/devices/curing-heater");
      const editor = page.getByRole("form", { name: "Limits of power" });
      await editor.getByLabel("Max, in W").fill("65");
      await editor.getByRole("button", { name: "Review the change" }).click();
      await expect(editor.getByLabel("Phrase")).toBeVisible();
      await editor.scrollIntoViewIfNeeded();
      await shot(page, `6-limits-widen-${tag}`);
      await fetch(`${state.url}/v1/limits`, {
        method: "POST",
        headers: { Authorization: `Bearer ${state.mediumToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ device: "curing-heater", channel: "power", max: { value: 70, unit: "W" } }),
      });
      await page.goto("/#/confirmations");
      await expect(page.getByRole("heading", { name: /^Limit changes/ })).toBeVisible();
      await shot(page, `7-limit-change-pending-${tag}`);
      await context.close();
      await fetch(`${state.url}/_harness/curing-heater/reset`, { method: "POST" });
    });
  }
}
