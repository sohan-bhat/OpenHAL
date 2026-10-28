import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const SPEC = "/spec/2026-10-24/basic/messages/";
const KEY = "openhal:sidebar";

const left = (page: Page, selector: string) => page.locator(selector).first().evaluate((el) => Math.round(el.getBoundingClientRect().left));

async function hideFirst(page: Page) {
  await page.goto("/404.html");
  await page.evaluate((key) => localStorage.setItem(key, "hidden"), KEY);
}

async function slides(page: Page) {
  await page.addInitScript(() => {
    const runs: string[] = [];
    Object.assign(window, { runs });
    addEventListener("transitionrun", (event) => runs.push(`${(event.target as Element).className} ${event.propertyName}`), true);
  });
}

const runs = (page: Page) => page.evaluate(() => (window as unknown as { runs: string[] }).runs.filter((run) => run.endsWith("translate")));

async function peek(page: Page) {
  await page.mouse.move(700, 500);
  await page.mouse.move(2, 500, { steps: 4 });
  await expect(page.locator("#side-nav")).toBeVisible();
}

test.describe("the sidebar", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("hides and shows from one named button while the content and outline move left by the sidebar's width", async ({ page }) => {
    await page.goto(SPEC);
    const toggle = page.locator(".side-toggle");
    await expect(toggle).toHaveAccessibleName("Hide the sidebar");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAttribute("aria-controls", "side-nav");
    const content = (await page.locator("article.content").boundingBox())!;
    const outline = (await page.locator("aside.outline").boundingBox())!;
    const place = (await toggle.boundingBox())!;

    await toggle.click();
    await expect(toggle).toHaveAccessibleName("Show the sidebar");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#side-nav")).toBeHidden();
    await expect.poll(() => left(page, "article.content")).toBe(Math.round(content.x) - 240);
    await expect.poll(() => left(page, "aside.outline")).toBe(Math.round(outline.x) - 240);
    expect((await page.locator("article.content").boundingBox())!.width).toBe(content.width);
    expect(await toggle.boundingBox()).toEqual(place);

    await toggle.click();
    await expect(toggle).toHaveAccessibleName("Hide the sidebar");
    await expect(page.locator("#side-nav")).toBeVisible();
    await expect.poll(() => left(page, "article.content")).toBe(Math.round(content.x));
    expect(await toggle.boundingBox()).toEqual(place);
  });

  test("slides in about 200 ms and ends exactly where the layout puts the content", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const track = page.evaluate(
      () =>
        new Promise<number[][]>((resolve) => {
          const article = document.querySelector("article.content")!;
          const seen: number[][] = [];
          let start = 0;
          const tick = (now: number) => {
            const x = article.getBoundingClientRect().left;
            if (!start && x !== 344) start = now;
            if (start) seen.push([now - start, x]);
            if (!start || now - start < 600) requestAnimationFrame(tick);
            else resolve(seen);
          };
          requestAnimationFrame(tick);
        }),
    );
    await page.locator(".side-toggle").click();
    const seen = await track;
    const done = seen.find(([, x]) => x === 104)!;
    expect(done[0]).toBeGreaterThan(120);
    expect(done[0]).toBeLessThan(400);
    for (let index = 1; index < seen.length; index++) expect(seen[index][1]).toBeLessThanOrEqual(seen[index - 1][1]);
    expect(seen.at(-1)![1]).toBe(104);
  });

  test("remembers the choice on the next page, which paints hidden at once with no slide and no layout shift", async ({ page, browserName }) => {
    await page.goto("/docs/quickstart/");
    await page.locator(".side-toggle").click();
    expect(await page.evaluate((key) => localStorage.getItem(key), KEY)).toBe("hidden");
    await slides(page);
    await page.addInitScript(() => {
      const frame = () => {
        const article = document.querySelector("article.content");
        if (!article) return requestAnimationFrame(frame);
        Object.assign(window, { born: { state: document.documentElement.dataset.sidebar, shift: getComputedStyle(article).translate } });
      };
      requestAnimationFrame(frame);
    });
    await page.goto(SPEC);
    await page.waitForFunction(() => "born" in window);
    const born = await page.evaluate(() => (window as unknown as { born: { state: string; shift: string } }).born);
    expect(born).toEqual({ state: "hidden", shift: "-240px" });
    await expect(page.locator(".side-toggle")).toHaveAccessibleName("Show the sidebar");
    expect(await left(page, "article.content")).toBe(104);
    await page.waitForTimeout(400);
    expect(await runs(page)).toEqual([]);
    if (browserName === "chromium") {
      const shift = await page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            let total = 0;
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries() as Array<PerformanceEntry & { value: number; hadRecentInput: boolean }>) {
                if (!entry.hadRecentInput) total += entry.value;
              }
            }).observe({ type: "layout-shift", buffered: true });
            setTimeout(() => resolve(total), 300);
          }),
      );
      expect(shift).toBeLessThan(0.001);
    }
  });

  test("slides in over the content when the pointer reaches the window's left edge, and leaves a moment after the pointer leaves", async ({ page }) => {
    await hideFirst(page);
    await page.goto("/docs/quickstart/");
    await page.mouse.move(700, 30);
    await page.mouse.move(2, 30, { steps: 4 });
    await page.waitForTimeout(400);
    await expect(page.locator("#side-nav"), "the header's left edge leaves the sidebar alone").toBeHidden();

    await peek(page);
    expect(await left(page, "article.content")).toBe(104);
    const sheet = await page.locator(".side-sheet").evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        background: style.backgroundColor,
        page: getComputedStyle(document.body).backgroundColor,
        rule: `${style.borderRightWidth} ${style.borderRightStyle}`,
        others: [style.borderTopWidth, style.borderBottomWidth, style.borderLeftWidth],
        shadow: style.boxShadow,
        blur: style.backdropFilter,
        under: document.elementFromPoint(150, 400)!.closest(".sidebar") !== null,
      };
    });
    expect(sheet).toEqual({ background: sheet.page, page: sheet.page, rule: "1px solid", others: ["0px", "0px", "0px"], shadow: "none", blur: "none", under: true });

    await page.mouse.move(160, 400, { steps: 6 });
    await page.waitForTimeout(500);
    await expect(page.locator("#side-nav")).toBeVisible();
    await page.mouse.move(700, 400, { steps: 4 });
    await page.waitForTimeout(120);
    await expect(page.locator("#side-nav"), "it waits a moment").toBeVisible();
    await expect(page.locator("#side-nav")).toBeHidden();
    expect(await page.evaluate((key) => localStorage.getItem(key), KEY)).toBe("hidden");
  });

  test("stays put without flicker when the pointer comes back within the moment", async ({ page }) => {
    await hideFirst(page);
    await slides(page);
    await page.goto("/docs/quickstart/");
    await peek(page);
    await page.waitForTimeout(300);
    const before = (await runs(page)).length;
    await page.mouse.move(700, 400, { steps: 3 });
    await page.waitForTimeout(100);
    await page.mouse.move(150, 400, { steps: 3 });
    await page.waitForTimeout(600);
    await expect(page.locator("#side-nav")).toBeVisible();
    expect((await runs(page)).length).toBe(before);
  });

  test("keeps the sidebar open when the button is pressed while the sidebar shows over the content", async ({ page }) => {
    await hideFirst(page);
    await page.goto("/docs/quickstart/");
    await peek(page);
    const toggle = page.locator(".side-toggle");
    await toggle.hover();
    await toggle.click();
    await page.mouse.move(800, 600, { steps: 4 });
    await page.waitForTimeout(800);
    await expect(page.locator("#side-nav")).toBeVisible();
    await expect(toggle).toHaveAccessibleName("Hide the sidebar");
    expect(await left(page, "article.content")).toBe(344);
    await expect(page.locator(".side-sheet")).toBeHidden();
    expect(await page.evaluate((key) => localStorage.getItem(key), KEY)).toBe("shown");
  });

  test("works from the keyboard, keeps hidden links out of the tab order and shows the sidebar when focus moves in from the button", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const toggle = page.locator(".side-toggle");
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#side-nav")).toBeHidden();
    const link = page.locator("#side-nav a").first();
    expect(await link.evaluate((el: HTMLElement) => (el.focus(), document.activeElement === el)), "a hidden link takes no focus").toBe(false);

    await page.locator("article.content a:visible").first().focus();
    await page.keyboard.press("Shift+Tab");
    await expect(toggle, "going back from the content skips the hidden links").toBeFocused();

    await page.keyboard.press("Tab");
    await expect(link).toBeFocused();
    await expect(page.locator("#side-nav")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#side-nav")).toBeHidden();
    await expect(toggle).toBeFocused();

    await page.keyboard.press("Space");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#side-nav")).toBeVisible();
  });

  test("moving focus out of the sidebar while it shows over the content hides it again", async ({ page }) => {
    await hideFirst(page);
    await page.goto("/docs/quickstart/");
    await page.locator(".side-toggle").focus();
    await page.keyboard.press("Tab");
    await expect(page.locator("#side-nav")).toBeVisible();
    await page.locator("article.content a:visible").first().focus();
    await expect(page.locator("#side-nav")).toBeHidden();
  });

  test("shows and hides without sliding under reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await slides(page);
    await page.goto("/docs/quickstart/");
    await page.locator(".side-toggle").click();
    expect(await left(page, "article.content")).toBe(104);
    await peek(page);
    await page.mouse.move(800, 500, { steps: 3 });
    await expect(page.locator("#side-nav")).toBeHidden();
    await page.locator(".side-toggle").click();
    expect(await left(page, "article.content")).toBe(344);
    expect(await runs(page)).toEqual([]);
  });

  test("follows the theme while it shows over the content", async ({ page }) => {
    await hideFirst(page);
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/docs/quickstart/");
    await peek(page);
    const colors = () => page.locator(".side-sheet").evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el).borderRightColor]);
    expect(await colors()).toEqual(["rgb(252, 252, 253)", "rgb(218, 221, 226)"]);
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await colors()).toEqual(["rgb(13, 15, 18)", "rgb(42, 47, 54)"]);
  });

  test("changes nothing at the widths where the sidebar is a menu", async ({ page }) => {
    for (const width of [390, 768, 1023]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/docs/quickstart/");
      await page.evaluate((key) => localStorage.removeItem(key), KEY);
      await page.reload();
      const shown = await page.locator("article.content").boundingBox();
      await page.evaluate((key) => localStorage.setItem(key, "hidden"), KEY);
      await page.reload();
      await expect(page.locator(".side-toggle"), `${width} px`).toBeHidden();
      await expect(page.locator(".side-menu summary"), `${width} px`).toBeVisible();
      expect(await page.locator("article.content").boundingBox(), `${width} px`).toEqual(shown);
      await page.mouse.move(2, 500, { steps: 3 });
      await page.waitForTimeout(300);
      await expect(page.locator(".side-sheet"), `${width} px`).toBeHidden();
    }
  });

  for (const [width, edge] of [
    [1440, 104],
    [1280, 64],
    [1024, 64],
  ] as const) {
    test(`moves the one left edge to ${edge} px at ${width} px while the sidebar is hidden`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await hideFirst(page);
      for (const path of ["/docs/quickstart/", "/inspector/", "/spec/playground/", SPEC]) {
        await page.goto(path);
        expect(await left(page, "main h1"), path).toBe(edge);
      }
      for (const path of ["/blog/", "/404.html"]) {
        await page.goto(path);
        expect(await page.locator(".column").first().evaluate((el) => Math.round(el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft))), path).toBe(edge);
      }
    });
  }

  test("keeps the page turn, the nav highlight and the search working while the sidebar is hidden", async ({ page, browserName }) => {
    await hideFirst(page);
    await page.goto("/drivers/");
    if (browserName === "chromium") {
      await page.locator(".desktop-nav").getByRole("link", { name: "Device Library", exact: true }).click();
      await expect(page).toHaveURL(/\/library\/$/);
      await expect.poll(() => page.evaluate(() => document.documentElement.dataset.turn ?? null)).toBe("forward");
      expect(await left(page, "main h1")).toBe(104);
    }
    await expect(page.locator(".desktop-nav [aria-current] .nav-pill")).toHaveCount(1);
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Search the site" })).toBeVisible();
    await expect(page.locator("#site-search-input")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search the site" })).toBeHidden();
  });

  test("keeps the button in view to the end of a long page while the sidebar is hidden", async ({ page }) => {
    await hideFirst(page);
    await page.goto(SPEC);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(200);
    const button = (await page.locator(".side-toggle").boundingBox())!;
    expect(button.y).toBe(76);
    await peek(page);
    const nav = (await page.locator("#side-nav").boundingBox())!;
    expect(nav.y).toBe(124);
    expect(nav.y + nav.height).toBeLessThanOrEqual(900);
  });

  test("keeps the outline's links working while the sidebar is hidden", async ({ page }) => {
    await hideFirst(page);
    await page.goto(SPEC);
    const outline = page.locator("aside.outline a").nth(2);
    const target = (await outline.getAttribute("href"))!;
    await outline.click();
    await expect(page).toHaveURL(new RegExp(`${target}$`));
    await expect(page.locator(target)).toBeInViewport();
  });
});

const AXE = ["/docs/", "/docs/quickstart/", "/docs/architecture/", "/spec/latest/", SPEC, "/spec/2026-10-24/schema/", "/spec/errors/", "/spec/playground/", "/drivers/", "/drivers/moonraker/", "/library/", "/library/scpi-rigol-dp832/", "/sdks/", "/sdks/python/reference/", "/inspector/", "/blog/", "/404.html"];

for (const scheme of ["light", "dark"] as const) {
  test(`documentation pages have no WCAG AA violations with the sidebar hidden and while it shows over the content in the ${scheme} theme`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "axe runs once, in Chromium");
    test.setTimeout(240_000);
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1440, height: 900 });
    await hideFirst(page);
    const problems: string[] = [];
    const check = async (label: string) => {
      await page.evaluate(() => document.fonts.ready);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      problems.push(...results.violations.map((violation) => `${label} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).slice(0, 4).join(", ")}`));
    };
    for (const path of AXE) {
      await page.goto(path);
      await check(`${path} hidden`);
    }
    for (const path of ["/docs/quickstart/", SPEC]) {
      await page.goto(path);
      await peek(page);
      await page.waitForTimeout(300);
      await check(`${path} over the content`);
    }
    expect(problems).toEqual([]);
  });
}
