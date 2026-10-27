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

test.describe("the header and footer", () => {
  for (const width of [1440, 1280, 1024, 390]) {
    test(`line up with the home page's column at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      const column = await inner(page, ".hero");
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
