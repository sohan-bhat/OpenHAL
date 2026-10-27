import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

async function focusedText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    return (element?.getAttribute("aria-label") || element?.textContent || "").trim();
  });
}

async function hasVisibleFocus(page: Page): Promise<string | true> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return "nothing has focus";
    const style = getComputedStyle(element);
    if (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2) return true;
    return `${element.tagName.toLowerCase()}.${element.className} has no focus outline`;
  });
}

test("the Inspector works from the keyboard with visible focus", async ({ page, browserName }) => {
  await page.goto("/#/devices/printer");
  await expect(page.getByRole("heading", { name: "Klipper 3D printer", level: 1 })).toBeVisible();
  const tab = browserName === "webkit" ? "Alt+Tab" : "Tab";

  await page.keyboard.press(tab);
  expect(await focusedText(page)).toBe("Skip to content");
  expect(await hasVisibleFocus(page)).toBe(true);

  const seen: string[] = [];
  for (let step = 0; step < 12; step++) {
    await page.keyboard.press(tab);
    seen.push(await focusedText(page));
    expect(await hasVisibleFocus(page)).toBe(true);
  }
  expect(seen).toContain("STOP every device");
  expect(seen.some((text) => text.startsWith("Confirmations"))).toBe(true);

  await page.locator("nav.views a", { hasText: "Audit log" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();

  await page.getByRole("link", { name: /Resin curing heater/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Resin curing heater", level: 1 })).toBeVisible();
  const slider = page.getByRole("slider", { name: "power new value" });
  await slider.focus();
  const before = Number(await slider.inputValue());
  await page.keyboard.press(before >= 60 ? "ArrowLeft" : "ArrowRight");
  expect(Number(await slider.inputValue())).not.toBe(before);
  await page.keyboard.press("End");
  expect(await slider.inputValue()).toBe("60");
});

const VIEWS = ["#/devices/printer", "#/devices/printer-cam", "#/devices/plant-waterer", "#/devices/curing-heater", "#/devices/bench-lamp", "#/confirmations", "#/audit", "#/routines", "#/writer", "#/settings"];

test("no view scrolls sideways on a 390 px phone", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const view of VIEWS) {
    await page.goto(`/${view}`);
    await expect(page.locator("main h1, main h2").first()).toBeVisible();
    await page.waitForTimeout(300);
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, view).toBeLessThanOrEqual(390);
  }
});
