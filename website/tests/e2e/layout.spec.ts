import { expect, test, type Page } from "@playwright/test";

const inner = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return { left: box.left + parseFloat(style.paddingLeft), right: box.right - parseFloat(style.paddingRight) };
  });

const reach = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const shown = [...el.children].filter((child) => child.getClientRects().length).map((child) => child.getBoundingClientRect());
    return { left: Math.min(...shown.map((box) => box.left)), right: Math.max(...shown.map((box) => box.right)) };
  });

const chrome = (page: Page) =>
  page.evaluate(() => {
    const boxes = (selector: string, across = false) =>
      [...document.querySelectorAll(selector)]
        .filter((el) => el.getClientRects().length)
        .map((el) => {
          const box = el.getBoundingClientRect();
          const x = [Math.round(box.left), Math.round(box.width)];
          return across ? x : [...x, Math.round(box.top), Math.round(box.height)];
        });
    return {
      wordmark: boxes(".site-header .wordmark img"),
      search: boxes(".site-header .search-field, .site-header .search-button"),
      nav: boxes(".site-header .desktop-nav li, .site-header .mobile-nav summary"),
      footer: boxes(".site-footer .row > *", true),
    };
  });

test.describe("the header and footer", () => {
  for (const width of [1440, 1280, 1024]) {
    test(`hold the wordmark, search, nav and footer in place across /, /docs/ and a spec page at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const seen: Record<string, Awaited<ReturnType<typeof chrome>>> = {};
      for (const path of ["/", "/docs/", "/spec/2026-10-24/basic/messages/"]) {
        await page.goto(path);
        await page.evaluate(() => document.fonts.ready);
        seen[path] = await chrome(page);
        expect(seen[path].wordmark, path).toHaveLength(1);
        expect(seen[path].search, path).toHaveLength(1);
        expect(seen[path].nav.length, path).toBeGreaterThan(0);
        expect(seen[path].footer.length, path).toBeGreaterThan(0);
      }
      expect(seen["/docs/"]).toEqual(seen["/"]);
      expect(seen["/spec/2026-10-24/basic/messages/"]).toEqual(seen["/"]);
    });
  }

  for (const width of [1440, 1280, 1024, 390]) {
    test(`line up with the home page's column at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      const column = await inner(page, "main > .home-width");
      const bar = await reach(page, ".site-header .bar");
      expect(Math.abs(bar.left - column.left)).toBeLessThan(1);
      expect(Math.abs(bar.right - column.right)).toBeLessThan(1);
      const footer = await reach(page, ".site-footer .row");
      expect(Math.abs(footer.left - column.left)).toBeLessThan(1);
      for (const section of await page.locator("main > .home-width").all()) {
        const edge = await section.evaluate((el) => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft));
        expect(Math.abs(edge - column.left)).toBeLessThan(1);
      }
    });
  }

  for (const [width, column] of [
    [1440, 344],
    [1280, 304],
    [1024, 304],
  ] as const) {
    test(`leave the documentation's one left edge at ${column} px at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      for (const path of ["/docs/quickstart/", "/inspector/", "/spec/playground/"]) {
        await page.goto(path);
        expect(Math.round((await page.locator("article.content").boundingBox())!.x), path).toBe(column);
        const sidebar = (await page.locator("aside.sidebar").boundingBox())!.x;
        expect(Math.abs((await reach(page, ".site-header .bar")).left - sidebar), path).toBeLessThan(1);
        expect(Math.abs((await reach(page, ".site-footer .row")).left - sidebar), path).toBeLessThan(1);
      }
    });
  }
});
