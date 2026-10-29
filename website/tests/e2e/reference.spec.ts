import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { LAZY_TABLES } from "../../src/lib/markdown/plugins.mjs";

const reference = "/spec/v0.1/schema/";
const drawn = ".prose .table-wrap.lazy { content-visibility: visible !important; }";

const drawAll = (context: BrowserContext) =>
  context.addInitScript((css) => document.addEventListener("DOMContentLoaded", () => document.head.append(Object.assign(document.createElement("style"), { textContent: css }))), drawn);

/** Opens a type's address and returns where its heading settles under the header. */
async function landing(page: Page, id: string): Promise<number> {
  await page.goto(`${reference}#${id}`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
  return page.evaluate((target) => document.getElementById(target)!.getBoundingClientRect().top, id);
}

test.describe("the schema reference", () => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 390, height: 844 }]) {
    test(`renders each table after the first only as the table nears the screen, at ${viewport.width} by ${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(reference);
      const wraps = page.locator(".prose .table-wrap");
      expect(await wraps.count()).toBeGreaterThan(LAZY_TABLES);
      const modes = await wraps.evaluateAll((items) => items.map((item) => getComputedStyle(item).contentVisibility));
      expect(modes[0]).toBe("visible");
      expect(modes.slice(1).every((mode) => mode === "auto")).toBe(true);
      const last = wraps.last();
      const shown = () => last.evaluate((el) => el.querySelector("td")!.checkVisibility({ contentVisibilityAuto: true }));
      expect(await shown()).toBe(false);
      await last.scrollIntoViewIfNeeded();
      await expect.poll(shown).toBe(true);
    });

    test(`lands each type's heading where it lands with every table drawn, at ${viewport.width} by ${viewport.height}`, async ({ browser }) => {
      const lazy = await browser.newContext({ viewport });
      const full = await browser.newContext({ viewport });
      await drawAll(full);
      const page = await lazy.newPage();
      await page.goto(reference);
      const ids = await page.locator(".prose h3[id]").evaluateAll((items) => items.map((item) => item.id));
      const header = await page.locator("header.header").evaluate((el) => el.getBoundingClientRect().bottom);
      const other = await full.newPage();
      for (const id of [0.2, 0.5, 0.8].map((share) => ids[Math.floor(share * ids.length)])) {
        const deferred = await landing(page, id);
        expect(Math.abs(deferred - (await landing(other, id))), id).toBeLessThanOrEqual(2);
        expect(deferred, id).toBeGreaterThan(header);
      }
      await lazy.close();
      await full.close();
    });

    test(`holds about the room its tables need before they render, at ${viewport.width} by ${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(reference);
      await page.evaluate(() => document.fonts.ready);
      const held = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.addStyleTag({ content: drawn });
      const needed = await page.evaluate(() => document.documentElement.scrollHeight);
      expect(Math.abs(held / needed - 1)).toBeLessThan(0.1);
    });
  }

  test("prints every table", async ({ page }) => {
    await page.goto(reference);
    await page.emulateMedia({ media: "print" });
    const modes = await page.locator(".prose .table-wrap").evaluateAll((items) => items.map((item) => getComputedStyle(item).contentVisibility));
    expect(new Set(modes)).toEqual(new Set(["visible"]));
  });

  test("moves nothing on the first screen while the page loads", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout shifts are a Chromium API");
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      await page.goto(reference);
      await page.waitForTimeout(1000);
      const shift = await page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            let total = 0;
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) total += (entry as PerformanceEntry & { value: number }).value;
            }).observe({ type: "layout-shift", buffered: true });
            setTimeout(() => resolve(total), 300);
          }),
      );
      expect(shift).toBe(0);
    }
  });
});
