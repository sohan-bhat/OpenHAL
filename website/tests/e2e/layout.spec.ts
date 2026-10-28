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
      version: boxes(".site-header .version-button"),
      label: document.querySelector(".site-header .version-button")?.textContent?.replace(/\s+/g, " ").trim() ?? null,
      footer: boxes(".site-footer .row > *", true),
    };
  });

const SPEC = "/spec/2026-10-24/basic/messages/";

test.describe("the header and footer", () => {
  for (const width of [1440, 1280, 1024]) {
    test(`hold the wordmark, search, nav, version and footer in place across /, /docs/ and a spec page at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const seen: Record<string, Awaited<ReturnType<typeof chrome>>> = {};
      for (const path of ["/", "/docs/", SPEC, "/spec/latest/", "/spec/playground/"]) {
        await page.goto(path);
        await page.evaluate(() => document.fonts.ready);
        seen[path] = await chrome(page);
        expect(seen[path].wordmark, path).toHaveLength(1);
        expect(seen[path].search, path).toHaveLength(1);
        expect(seen[path].nav.length, path).toBeGreaterThan(0);
        expect(seen[path].version, path).toHaveLength(width >= 1180 ? 1 : 0);
        expect(seen[path].footer.length, path).toBeGreaterThan(0);
      }
      for (const path of ["/docs/", SPEC, "/spec/latest/", "/spec/playground/"]) expect(seen[path], path).toEqual(seen["/"]);
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

const rows = (page: Page, selector: string) =>
  page.locator(selector).evaluate((panel) => {
    const style = getComputedStyle(panel);
    const box = panel.getBoundingClientRect();
    const border = parseFloat(style.borderLeftWidth);
    const inner = { left: box.left + border, top: box.top + border, right: box.right - border, bottom: box.bottom - border };
    const innerRadius = Math.max(0, parseFloat(style.borderTopLeftRadius) - border);
    return [...panel.querySelectorAll("a")].map((row) => {
      const at = row.getBoundingClientRect();
      const lines = [...row.children].map((part) => part.getClientRects().length);
      return {
        text: row.textContent!.replace(/\s+/g, " ").trim(),
        current: row.getAttribute("aria-current"),
        background: getComputedStyle(row).backgroundColor,
        color: getComputedStyle(row).color,
        radius: parseFloat(getComputedStyle(row).borderTopLeftRadius),
        inset: Math.min(at.left - inner.left, at.top - inner.top, inner.right - at.right, inner.bottom - at.bottom),
        innerRadius,
        lines,
        height: at.height,
        lineHeight: parseFloat(getComputedStyle(row).lineHeight),
        marks: row.querySelectorAll("svg, img").length,
      };
    });
  });

test.describe("the version picker", () => {
  test("opens from the header after GitHub and lists each version on one line with the current one highlighted like the nav", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const button = page.locator(".version-button");
    await expect(button).toHaveAccessibleName(/^Specification version \d{4}-\d{2}-\d{2}$/);
    await expect(button).toHaveAttribute("aria-expanded", "false");
    const github = (await page.locator(".desktop-nav li").last().boundingBox())!;
    const place = (await button.boundingBox())!;
    expect(place.x).toBeGreaterThan(github.x + github.width);
    await button.click();
    await expect(page.locator("#version-menu")).toBeVisible();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    const pill = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.style.background = "color-mix(in srgb, var(--accent) 10%, var(--bg))";
      probe.style.color = "var(--accent)";
      document.body.append(probe);
      const style = getComputedStyle(probe);
      const colors = [style.backgroundColor, style.color];
      probe.remove();
      return colors;
    });
    const listed = await rows(page, "#version-menu");
    expect(listed.length).toBeGreaterThan(0);
    for (const row of listed) {
      expect(row.lines.every((count) => count === 1), row.text).toBe(true);
      expect(row.height, row.text).toBeLessThan(row.lineHeight * 2);
      expect(row.marks, row.text).toBe(0);
    }
    const current = listed.filter((row) => row.current);
    expect(current).toHaveLength(1);
    expect(current[0].current).toBe("page");
    expect([current[0].background, current[0].color]).toEqual(pill);
    const menu = (await page.locator("#version-menu").boundingBox())!;
    expect(Math.abs(menu.x + menu.width - (place.x + place.width))).toBeLessThan(1);
    expect(menu.y).toBeGreaterThan(place.y + place.height);
  });

  test("keeps every row's background inside the panel's padding, clear of its rounded corners", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/");
    await page.locator(".version-button").click();
    const first = page.locator("#version-menu a").first();
    await first.hover();
    for (const row of await rows(page, "#version-menu")) {
      expect(row.radius, row.text).toBeGreaterThan(0);
      expect(row.inset, row.text).toBeGreaterThanOrEqual(4);
      expect(row.inset + row.radius, row.text).toBeGreaterThanOrEqual(row.innerRadius);
    }
  });

  test("links each version to its spec from other pages and to the same section from a spec page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/");
    const latest = (await page.locator(".version-button .mono").textContent())!.trim();
    await expect(page.locator("#version-menu a[aria-current]")).toHaveAttribute("href", `/spec/${latest}/`);
    await expect(page.locator("#version-menu a[aria-current]")).toHaveAttribute("aria-current", "true");
    await page.goto(SPEC);
    await expect(page.locator("#version-menu a[aria-current]")).toHaveAttribute("href", SPEC);
    await page.locator(".version-button").click();
    await page.locator("#version-menu a").first().click();
    await expect(page).toHaveURL(/\/spec\/\d{4}-\d{2}-\d{2}\/basic\/messages\/$/);
  });

  test("works from the keyboard, closes on Escape and gives focus back to the button", async ({ page, browserName }) => {
    test.skip(browserName === "webkit", "WebKit only tabs to links with the macOS full keyboard setting");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/");
    const button = page.locator(".version-button");
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#version-menu")).toBeVisible();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Tab");
    await expect(page.locator("#version-menu a").first()).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator("#version-menu")).toBeHidden();
    await expect(button).toBeFocused();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Space");
    await expect(page.locator("#version-menu")).toBeVisible();
    await page.mouse.click(700, 600);
    await expect(page.locator("#version-menu")).toBeHidden();
  });

  for (const width of [1024, 390]) {
    test(`sits inside the Menu at ${width} px, one version to a line`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(SPEC);
      await expect(page.locator(".version-button")).toBeHidden();
      await page.locator(".mobile-nav summary").click();
      const list = page.locator(".mobile-nav .versions");
      await expect(list.locator(".legend")).toHaveText("Specification version");
      const listed = await rows(page, ".mobile-nav nav");
      const versions = listed.filter((row) => /^\d{4}-\d{2}-\d{2}/.test(row.text));
      expect(versions.length).toBeGreaterThan(0);
      for (const row of versions) expect(row.lines.every((count) => count === 1), row.text).toBe(true);
      expect(versions.filter((row) => row.current)).toHaveLength(1);
    });
  }
});
