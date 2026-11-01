import { expect, test, type Page } from "@playwright/test";

const THUMB = { light: "rgb(138, 145, 156)", dark: "rgb(90, 98, 109)" } as const;

const bars = (page: Page) =>
  page.evaluate(() => {
    const inner = document.querySelector("[data-slot=sidebar-content]") ?? document.querySelector("main");
    return {
      page: getComputedStyle(document.documentElement).scrollbarColor,
      inner: inner ? getComputedStyle(inner).scrollbarColor : "",
    };
  });

const frame = (page: Page) =>
  page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    gutter: window.innerWidth - document.documentElement.clientWidth,
    overflow: getComputedStyle(document.body).overflowY,
    margin: getComputedStyle(document.body).marginRight,
    header: document.querySelector("header")!.getBoundingClientRect().right,
    scrolls: document.documentElement.scrollHeight > window.innerHeight,
  }));

test.describe("the scrollbar", () => {
  for (const scheme of ["light", "dark"] as const) {
    for (const forced of [false, true]) {
      test(`draws a ${scheme} thumb on a clear track on the page and in every panel, ${forced ? "from the theme picker" : "from the system theme"}`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: forced ? (scheme === "light" ? "dark" : "light") : scheme });
        if (forced) await page.addInitScript((theme) => localStorage.setItem("starlight-theme", theme), scheme);
        await page.goto("/spec/v0.1/basic/messages/");
        await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
        const seen = await bars(page);
        expect(seen.page).toBe(`${THUMB[scheme]} rgba(0, 0, 0, 0)`);
        expect(seen.inner).toBe(seen.page);
        expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(scheme);
      });
    }
  }

  test("stays in place while the search palette floats over the page, and the page never shifts", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/drivers/");
    const before = await frame(page);
    expect(before.scrolls).toBe(true);
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Search" });
    await expect(palette).toBeVisible();
    await expect(page.locator("body")).toHaveAttribute("data-scroll-locked", /.*/);
    const during = await frame(page);
    expect(during.width).toBe(before.width);
    expect(during.gutter).toBe(before.gutter);
    expect(during.overflow).toBe("visible");
    expect(during.margin).toBe("0px");
    expect(during.header).toBe(before.header);
    const top = await page.evaluate(() => window.scrollY);
    await page.mouse.move(80, 800);
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.scrollY), "the wheel over the backdrop leaves the page still").toBe(top);
    await page.keyboard.press("Escape");
    await expect(palette).toHaveCount(0);
    expect((await frame(page)).width).toBe(before.width);
  });
});
