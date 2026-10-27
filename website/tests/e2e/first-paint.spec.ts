import { expect, test, type Browser } from "@playwright/test";

async function firstScreen(browser: Browser, viewport: { width: number; height: number }, scheme: "light" | "dark", scripts: boolean): Promise<Buffer> {
  const context = await browser.newContext({ viewport, colorScheme: scheme });
  const page = await context.newPage();
  if (!scripts) await page.route(/\/_astro\/.*\.js$/, (route) => route.abort());
  await page.goto("/", { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const shot = await page.screenshot();
  await context.close();
  return shot;
}

test.describe("the home page", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "one engine is enough to compare a screen with itself");

  for (const viewport of [{ width: 1440, height: 900 }, { width: 412, height: 823 }]) {
    for (const scheme of ["light", "dark"] as const) {
      test(`paints its first screen whole before any module script runs, at ${viewport.width} px in the ${scheme} theme`, async ({ browser }) => {
        const before = await firstScreen(browser, viewport, scheme, false);
        const after = await firstScreen(browser, viewport, scheme, true);
        expect(before.equals(after), "the first screen changed once the module scripts ran").toBe(true);
      });
    }
  }
});
