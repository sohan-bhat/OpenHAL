import AxeBuilder from "@axe-core/playwright";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const sitemap = fileURLToPath(new URL("../../dist/sitemap-0.xml", import.meta.url));
const PAGES = existsSync(sitemap)
  ? [...readFileSync(sitemap, "utf8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname)
  : [];
PAGES.push("/spec/latest/", "/404.html");

async function violations(page: Page): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).slice(0, 4).join(", ")}`);
}

test("the sitemap lists every page the axe checks cover", () => {
  expect(PAGES.length).toBeGreaterThan(100);
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme });
    for (const path of PAGES) {
      test(`${path} has no WCAG AA violations`, async ({ page, browserName }) => {
        test.skip(browserName !== "chromium", "axe runs once, in Chromium");
        test.setTimeout(120_000);
        await page.goto(path);
        expect(await violations(page)).toEqual([]);
      });
    }

    test("open menus and interactive states have no WCAG AA violations on a phone", async ({ page, browserName }) => {
      test.skip(browserName !== "chromium", "axe runs once, in Chromium");
      test.setTimeout(180_000);
      await page.setViewportSize({ width: 390, height: 844 });
      const problems: string[] = [];

      await page.goto("/");
      await page.locator(".mobile-nav summary").click();
      problems.push(...(await violations(page)).map((item) => `menu ${item}`));

      await page.goto("/spec/2026-10-24/basic/messages/");
      await page.locator(".side-menu summary").first().click();
      await page.locator(".switcher summary:visible").first().click();
      problems.push(...(await violations(page)).map((item) => `spec menus ${item}`));

      await page.goto("/spec/playground/");
      await page.getByRole("button", { name: "Set the nozzle to 300 °C" }).click();
      await expect(page.locator(".exchanges > li").first()).toBeVisible();
      await page.getByRole("button", { name: "About hazard" }).click();
      await page.locator("summary", { hasText: "Build your own request" }).click();
      problems.push(...(await violations(page)).map((item) => `playground trace ${item}`));

      await page.goto("/drivers/");
      await page.getByLabel("Filter", { exact: true }).fill("no such driver");
      await expect(page.locator("[data-empty]")).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `drivers empty ${item}`));

      await page.goto("/library/");
      await page.getByLabel("Filter", { exact: true }).fill("no such device");
      await expect(page.locator("[data-empty]")).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `library empty ${item}`));

      await page.goto("/");
      await page.evaluate(() => {
        const story = document.querySelector<HTMLElement>("[data-story]")!;
        window.scrollTo(0, story.offsetTop + story.offsetHeight / 2);
      });
      await page.waitForTimeout(300);
      problems.push(...(await violations(page)).map((item) => `story mid scroll ${item}`));

      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/");
      problems.push(...(await violations(page)).map((item) => `story as a list ${item}`));
      await page.emulateMedia({ reducedMotion: "no-preference" });

      await page.goto("/");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      await page.locator("#site-search-input").fill("print babysitter");
      await expect(page.locator("a.search-result").first()).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `search ${item}`));

      expect(problems).toEqual([]);
    });
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`the open search dialog has no WCAG AA violations on a desktop in the ${scheme} theme`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "axe runs once, in Chromium");
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/spec/2026-10-24/basic/messages/");
    await page.keyboard.press("Control+k");
    await page.locator("#site-search-input").fill("LIMIT_EXCEEDED");
    await expect(page.locator("a.search-result").first()).toBeVisible();
    expect(await violations(page)).toEqual([]);
  });
}

test("status never relies on color alone", async ({ page }) => {
  for (const path of ["/", "/drivers/", "/library/", "/library/scpi-rigol-dp832/", "/spec/playground/"]) {
    await page.goto(path);
    for (const status of await page.locator(".status").all()) {
      if (!(await status.isVisible())) continue;
      expect((await status.innerText()).trim().length, path).toBeGreaterThan(0);
    }
  }
});

test("no layout shift while the landing page loads", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "layout shift entries are a Chromium API");
  await page.goto("/");
  await page.waitForTimeout(1500);
  const shift = await page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let total = 0;
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries() as Array<PerformanceEntry & { value: number; hadRecentInput: boolean }>) {
            if (!entry.hadRecentInput) total += entry.value;
          }
        }).observe({ type: "layout-shift", buffered: true });
        setTimeout(() => resolve(total), 500);
      }),
  );
  expect(shift).toBeLessThan(0.02);
});
