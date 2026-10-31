import AxeBuilder from "@axe-core/playwright";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const sitemap = fileURLToPath(new URL("../../dist/sitemap-0.xml", import.meta.url));
const PAGES = existsSync(sitemap)
  ? [...readFileSync(sitemap, "utf8").matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname)
  : [];
PAGES.push("/404.html");

/** Waits until no part is still opening or closing, so axe measures colors at full strength. */
async function settled(page: Page): Promise<void> {
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running" || animation instanceof CSSAnimation), undefined, { polling: 25 });
}

async function violations(page: Page): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  await settled(page);
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
      await page.locator(".sl-menu-button").click();
      problems.push(...(await violations(page)).map((item) => `menu ${item}`));

      await page.goto("/spec/v0.1/basic/messages/");
      await page.locator(".sl-menu-button").click();
      problems.push(...(await violations(page)).map((item) => `spec menu ${item}`));
      await page.keyboard.press("Escape");
      await page.locator("mobile-starlight-toc summary").click();
      problems.push(...(await violations(page)).map((item) => `spec outline ${item}`));

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
        const how = document.querySelector<HTMLElement>("[data-how]")!;
        window.scrollTo(0, how.offsetTop + how.offsetHeight / 2);
      });
      await page.waitForTimeout(400);
      problems.push(...(await violations(page)).map((item) => `how it works mid scroll ${item}`));

      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/");
      problems.push(...(await violations(page)).map((item) => `how it works as panels ${item}`));
      await page.emulateMedia({ reducedMotion: "no-preference" });

      await page.goto("/docs/examples/3d-print-watch/");
      await page.getByRole("button", { name: "Next step" }).click();
      await page.getByRole("button", { name: "Next step" }).click();
      await page.waitForTimeout(1500);
      problems.push(...(await violations(page)).map((item) => `example walkthrough ${item}`));

      await page.goto("/");
      await page.getByRole("button", { name: /^Search/ }).click();
      await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `search before typing ${item}`));
      await page.getByRole("dialog", { name: "Search" }).getByRole("combobox").fill("print babysitter");
      await expect(page.locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
      problems.push(...(await violations(page)).map((item) => `search ${item}`));

      expect(problems).toEqual([]);
    });
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`the search palette, before typing, with results and with none, has no WCAG AA violations on a desktop in the ${scheme} theme`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "axe runs once, in Chromium");
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => localStorage.setItem("openhal-recent-searches", JSON.stringify(["hal/write"])));
    await page.goto("/spec/v0.1/basic/messages/");
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Search" });
    await expect(palette.locator("[cmdk-group-heading]").first()).toHaveText("Recent searches");
    const problems = (await violations(page)).map((item) => `before typing ${item}`);
    await palette.getByRole("combobox").fill("LIMIT_EXCEEDED");
    await expect(palette.locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("ArrowDown");
    problems.push(...(await violations(page)).map((item) => `results ${item}`));
    await palette.getByRole("combobox").fill("qzqzqz");
    await expect(palette.locator("[cmdk-empty]")).toBeVisible({ timeout: 15_000 });
    problems.push(...(await violations(page)).map((item) => `no results ${item}`));
    expect(problems).toEqual([]);
  });

  test(`the pickers, open, have no WCAG AA violations on a desktop, a tablet and a phone in the ${scheme} theme`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "axe runs once, in Chromium");
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme: scheme });
    const problems: string[] = [];
    const open = async (scope: string, kind: string) => {
      const button = page.locator(`${scope} button[data-picker='${kind}']`);
      await button.hover();
      await button.click();
      await expect(page.getByRole("menu")).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `${scope} ${kind} ${item}`));
      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu")).toHaveCount(0);
    };
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/spec/v0.1/basic/messages/");
    await open("header.header", "theme");
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/");
    await open("header.header", "section");
    await open("header.header", "theme");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/spec/v0.1/basic/messages/");
    await page.locator(".sl-menu-button").click();
    await open(".mobile-preferences", "theme");
    expect(problems).toEqual([]);
  });

  test(`the sidebar expanded, collapsed and in the phone menu has no WCAG AA violations in the ${scheme} theme`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "axe runs once, in Chromium");
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme: scheme });
    const problems: string[] = [];
    for (const path of ["/docs/quickstart/", "/spec/v0.1/basic/messages/"]) {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await page.locator("[data-group] > button").first().hover();
      await expect(page.locator("astro-island:has([data-slot=sidebar])")).not.toHaveAttribute("ssr", "");
      problems.push(...(await violations(page)).map((item) => `${path} expanded ${item}`));
      await page.keyboard.press("Control+b");
      await expect(page.locator("[data-slot=sidebar]")).toHaveAttribute("data-state", "collapsed");
      await page.mouse.move(3, 450);
      problems.push(...(await violations(page)).map((item) => `${path} collapsed ${item}`));
      await page.goto(path);
      problems.push(...(await violations(page)).map((item) => `${path} collapsed before React ${item}`));
      await page.keyboard.press("Control+b");
      await expect(page.locator("[data-slot=sidebar]")).toHaveAttribute("data-state", "expanded");
      await page.setViewportSize({ width: 390, height: 844 });
      await page.locator(".sl-menu-button").click();
      await expect(page.locator("#starlight__sidebar")).toBeVisible();
      problems.push(...(await violations(page)).map((item) => `${path} phone menu ${item}`));
      await page.keyboard.press("Escape");
    }
    expect(problems).toEqual([]);
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
