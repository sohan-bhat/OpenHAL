import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const PAGES = [
  "/",
  "/spec/latest/",
  "/spec/2026-10-24/basic/messages/",
  "/spec/2026-10-24/architecture/",
  "/spec/glossary/",
  "/spec/playground/",
  "/drivers/",
  "/drivers/mock/",
  "/library/",
  "/sdks/",
  "/sdks/python/",
  "/sdks/python/reference/",
  "/inspector/",
  "/docs/",
  "/docs/quickstart/",
  "/docs/tutorials/build-a-driver/",
  "/docs/architecture/",
  "/blog/",
  "/404/",
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme });
    for (const path of PAGES) {
      test(`${path} has no WCAG AA violations`, async ({ page, browserName }) => {
        test.skip(browserName !== "chromium", "axe runs once, in Chromium");
        test.setTimeout(120_000);
        await page.goto(path);
        await page.evaluate(() => document.fonts.ready);
        const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
        const summary = results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).slice(0, 4).join(", ")}`);
        expect(summary).toEqual([]);
      });
    }
  });
}

test("status never relies on color alone", async ({ page }) => {
  for (const path of ["/", "/drivers/", "/spec/playground/"]) {
    await page.goto(path);
    for (const status of await page.locator(".status").all()) {
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
