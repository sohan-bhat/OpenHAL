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

  test("holds its first frame until How it works' inline script has run", async ({ page }) => {
    await page.addInitScript(() => {
      requestAnimationFrame(() => {
        const href = document.querySelector('link[rel="expect"][blocking="render"]')?.getAttribute("href") ?? "";
        Object.assign(window, { firstFrame: { href, parsed: href.startsWith("#") && Boolean(document.getElementById(href.slice(1))) } });
      });
    });
    await page.goto("/", { waitUntil: "load" });
    const { firstFrame, order } = await page.evaluate(() => {
      const href = document.querySelector('link[rel="expect"][blocking="render"]')?.getAttribute("href") ?? "";
      const target = href.startsWith("#") ? document.getElementById(href.slice(1)) : null;
      const inline = [...document.querySelectorAll<HTMLScriptElement>("[data-how] + script:not([src]):not([type])")];
      return {
        firstFrame: (window as unknown as { firstFrame?: { href: string; parsed: boolean } }).firstFrame,
        order: target ? inline.map((script) => Boolean(script.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING)) : [],
      };
    });
    expect(order.length, "How it works keeps an inline script and the head names an element after it").toBeGreaterThan(0);
    expect(order.every(Boolean), "the element the head waits for comes after How it works' inline script").toBe(true);
    expect(firstFrame?.parsed, `the first frame came before ${firstFrame?.href ?? "the expected element"} was parsed`).toBe(true);
  });

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
