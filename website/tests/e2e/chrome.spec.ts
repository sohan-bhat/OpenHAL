import { expect, test, type Page } from "@playwright/test";

const SPEC = "/spec/v0.1/basic/messages/";
const SECTIONS = ["Overview", "Docs", "Specification", "Playground", "Drivers", "Device Library"];
const REPOSITORY = "https://github.com/sohan-bhat/OpenHAL";

const box = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const rect = el.getBoundingClientRect();
    return [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)];
  });

const picker = (page: Page, kind: "version" | "theme" | "section", scope = "header.header") => page.locator(`${scope} [data-picker='${kind}']`);

const palette = (page: Page) => page.getByRole("dialog", { name: "Search" });
const results = (page: Page) => palette(page).locator("[cmdk-item]");

const header = (page: Page) =>
  page.evaluate(() => {
    const boxes = (selector: string) =>
      [...document.querySelectorAll(selector)]
        .filter((el) => el.getClientRects().length && el.closest("header.header"))
        .map((el) => {
          const rect = el.getBoundingClientRect();
          return [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)];
        });
    return {
      brand: boxes(".oh-brand"),
      sections: boxes(".oh-sections li"),
      picker: boxes("[data-picker='section']"),
      search: boxes("[data-search-trigger]"),
      github: boxes(".oh-social a"),
      version: boxes("[data-picker='version']"),
      theme: boxes("[data-picker='theme']"),
    };
  });

test.describe("the header", () => {
  for (const width of [1440, 1280, 1024, 900]) {
    test(`holds the wordmark, sections, search, GitHub, version and theme in place on every page at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const seen: Record<string, Awaited<ReturnType<typeof header>>> = {};
      for (const path of ["/", "/docs/", SPEC, "/spec/playground/", "/drivers/", "/blog/", "/404.html"]) {
        await page.goto(path);
        await page.evaluate(() => document.fonts.ready);
        seen[path] = await header(page);
        expect(seen[path].brand, path).toHaveLength(1);
        expect(seen[path].search, path).toHaveLength(1);
        expect(seen[path].github, path).toHaveLength(1);
        expect(seen[path].version, path).toHaveLength(1);
        expect(seen[path].theme, path).toHaveLength(1);
        expect(seen[path].sections.length + seen[path].picker.length, path).toBeGreaterThan(0);
      }
      for (const path of Object.keys(seen)) expect(seen[path], path).toEqual(seen["/"]);
    });
  }

  test("lists the six sections after the wordmark and highlights the one a page belongs to", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const [path, current] of [
      ["/", "Overview"],
      ["/docs/quickstart/", "Docs"],
      ["/sdks/", "Docs"],
      ["/inspector/", "Docs"],
      [SPEC, "Specification"],
      ["/spec/errors/", "Specification"],
      ["/spec/playground/", "Playground"],
      ["/drivers/moonraker/", "Drivers"],
      ["/library/", "Device Library"],
    ]) {
      await page.goto(path);
      const nav = page.getByRole("navigation", { name: "Main" });
      await expect(nav.getByRole("link")).toHaveText(SECTIONS);
      await expect(nav.locator("[aria-current='page']"), path).toHaveText(current);
      await expect(nav.locator("[aria-current='page'] .nav-pill"), path).toHaveCount(1);
    }
    await page.goto("/404.html");
    await expect(page.getByRole("navigation", { name: "Main" }).locator("[aria-current]")).toHaveCount(0);
  });

  test("every section link opens its section", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const label of SECTIONS) {
      await page.goto("/404.html");
      await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true }).click();
      await expect(page.getByRole("navigation", { name: "Main" }).locator("[aria-current='page']")).toHaveText(label);
    }
  });

  test("keeps GitHub as a named icon and the wordmark as the way home", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/drivers/");
    await expect(page.locator("header.header").getByRole("link", { name: "GitHub" })).toHaveAttribute("href", REPOSITORY);
    await page.getByRole("link", { name: "OpenHAL overview" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator("h1")).toHaveText("OpenHAL");
  });

  for (const width of [1440, 1280, 1180, 1100, 1024, 900, 800, 390, 360]) {
    test(`fits on one row at ${width} px with nothing overlapping`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(SPEC);
      await page.evaluate(() => document.fonts.ready);
      const parts = await page.evaluate(() => {
        const bar = document.querySelector("header.header")!.getBoundingClientRect();
        const items = [...document.querySelectorAll(".oh-brand, .oh-sections li, [data-search-trigger], .oh-social a, header.header [data-picker], .sl-menu-button")]
          .filter((el) => el.getClientRects().length)
          .map((el) => ({ name: el.tagName.toLowerCase() + "." + el.className, rect: el.getBoundingClientRect() }));
        return { bar: { top: bar.top, bottom: bar.bottom, right: bar.right }, items: items.map(({ name, rect }) => ({ name, left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom })) };
      });
      for (const item of parts.items) {
        expect(item.top, item.name).toBeGreaterThanOrEqual(parts.bar.top);
        expect(item.bottom, item.name).toBeLessThanOrEqual(parts.bar.bottom);
        expect(item.right, item.name).toBeLessThanOrEqual(parts.bar.right);
      }
      const row = [...parts.items].sort((a, b) => a.left - b.left);
      for (let index = 1; index < row.length; index++) expect(row[index].left, `${row[index - 1].name} and ${row[index].name}`).toBeGreaterThanOrEqual(row[index - 1].right - 0.5);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }

  for (const width of [1440, 1280, 1024]) {
    test(`lines the wordmark up with the home column and the sidebar at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      const brand = (await box(page, ".oh-brand"))[0];
      const column = await page.locator("main .home-width").first().evaluate((el) => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft));
      expect(Math.abs(brand - column)).toBeLessThan(1);
      await page.goto(SPEC);
      const pill = await page.locator("[data-slot=sidebar-menu] > li").first().evaluate((el) => el.getBoundingClientRect().left);
      expect(Math.abs((await box(page, ".oh-brand"))[0] - pill)).toBeLessThan(1);
    });
  }

  test("collapses the sections into a picker on a tablet that shows and opens the current section", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/moonraker/");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    const button = picker(page, "section");
    await expect(button).toBeVisible();
    await expect(button).toHaveAccessibleName("Section Drivers");
    await button.click();
    const menu = page.getByRole("menu", { name: "Section" });
    await expect(menu.getByRole("menuitem")).toHaveText(SECTIONS);
    await expect(menu.locator("[aria-current='page']")).toHaveText("Drivers");
    await menu.getByRole("menuitem", { name: "Device Library" }).click();
    await expect(page).toHaveURL(/\/library\/$/);
    await page.goto("/404.html");
    await expect(picker(page, "section")).toHaveAccessibleName("Sections");
  });
});

test.describe("the version label", () => {
  test("sits after GitHub, names itself, shows v0.1 and links to the specification's Versions section", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const path of [SPEC, "/docs/"]) {
      await page.goto(path);
      const label = picker(page, "version");
      await expect(label, path).toHaveAccessibleName("Specification version v0.1");
      await expect(label, path).toHaveAttribute("href", "/spec/v0.1/#versions");
      expect(await label.evaluate((element) => element.localName), "a plain link while one version exists").toBe("a");
      await expect(label.locator("svg")).toHaveCount(0);
      const github = await box(page, ".oh-social a");
      expect((await box(page, "header.header [data-picker='version']"))[0]).toBeGreaterThan(github[0] + github[2]);
    }
    await picker(page, "version").click();
    await expect(page).toHaveURL(/\/spec\/v0\.1\/#versions$/);
    await expect(page.locator("#versions")).toBeInViewport();
  });
});

test.describe("the sidebar", () => {
  test("is shadcn/ui's Sidebar, marks the current page and opens the groups around it", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const sidebar = page.locator("[data-slot=sidebar-content]");
    await expect(page.locator("[data-slot=sidebar-wrapper] [data-slot=sidebar] [data-slot=sidebar-rail]")).toHaveCount(1);
    await expect(sidebar.locator("a[aria-current='page']")).toHaveText("3.3 Messages");
    await expect(sidebar.locator("a[aria-current='page']")).toHaveAttribute("data-active", "true");
    for (const group of ["Specification v0.1", "Specification v0.1 / 3 Base protocol"]) await expect(page.locator(`[data-group='${group}']`)).toHaveAttribute("data-state", "open");
    expect(await page.locator("[data-slot=sidebar-menu] > li[data-group] > button").allInnerTexts()).toEqual(["Specification v0.1", "All versions", "Try the protocol"]);
  });

  test("shows words only, with a chevron on a group and no other icon", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const path of [SPEC, "/docs/quickstart/", "/drivers/"]) {
      await page.goto(path);
      const marks = await page.locator("[data-slot=sidebar]").evaluate((sidebar) => [...sidebar.querySelectorAll("svg, img")].map((mark) => `${mark.parentElement?.localName} ${mark.getAttribute("class")}`));
      expect(marks.length, path).toBeGreaterThan(0);
      for (const mark of marks) expect(mark, path).toMatch(/^button lucide lucide-chevron-right/);
      expect(await page.locator("[data-group] > button").count(), path).toBe(marks.length);
    }
  });

  test("collapses a group, which stays collapsed on the next page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/quickstart/");
    const tutorials = page.locator("[data-group='Tutorials']");
    await expect(tutorials).toHaveAttribute("data-state", "open");
    await tutorials.locator(":scope > button").click();
    await expect(tutorials).toHaveAttribute("data-state", "closed");
    await expect(tutorials.locator(":scope > button")).toHaveAttribute("aria-expanded", "false");
    await expect(tutorials.getByRole("link", { name: "Connect Claude" })).toBeHidden();
    await page.locator("[data-slot=sidebar-content]").getByRole("link", { name: "Install" }).click();
    await expect(page).toHaveURL(/\/docs\/install\/$/);
    await expect(page.locator("[data-group='Tutorials']")).toHaveAttribute("data-state", "closed");
    await expect(page.locator("[data-group='Tutorials']").getByRole("link", { name: "Connect Claude" })).toBeHidden();
  });

  test("is left out on a desktop where a page has no pages of its own, which keep the phone menu", async ({ page }) => {
    for (const path of ["/", "/404.html", "/blog/"]) {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await expect(page.locator("#starlight__sidebar"), path).toBeHidden();
      await expect(page.locator("[data-slot=sidebar]"), path).toHaveCount(0);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.locator(".sl-menu-button").click();
      await expect(page.locator(".oh-menu-sections"), path).toBeVisible();
      await page.keyboard.press("Escape");
    }
  });

  for (const width of [1440, 1280, 1024]) {
    test(`starts every documentation page's title at one left edge at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const edges: Record<string, number> = {};
      for (const path of [SPEC, "/docs/quickstart/", "/inspector/", "/spec/playground/", "/drivers/", "/library/scpi-rigol-dp832/", "/sdks/python/reference/", "/blog/", "/404.html"]) {
        await page.goto(path);
        edges[path] = (await box(page, "main h1"))[0];
      }
      for (const path of Object.keys(edges)) expect(edges[path], path).toBe(edges[SPEC]);
    });
  }
});

test.describe("the sidebar's collapse", () => {
  const state = (page: Page) =>
    page.evaluate(() => ({
      collapsed: document.documentElement.dataset.sidebar === "collapsed",
      state: document.querySelector<HTMLElement>("[data-slot=sidebar]")?.dataset.state,
    }));
  const hydrated = (page: Page) => expect(page.locator("astro-island:has([data-slot=sidebar])")).not.toHaveAttribute("ssr", "");
  const settled = (page: Page) => page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"), undefined, { polling: 25 });
  const rail = (page: Page) => page.locator("[data-slot=sidebar-rail]");
  const container = (page: Page) => page.locator("[data-slot=sidebar-container]");
  const collapse = async (page: Page) => {
    await page.keyboard.press("Control+b");
    await expect.poll(() => state(page)).toEqual({ collapsed: true, state: "collapsed" });
    await settled(page);
  };

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("toggles from the rail on the sidebar's edge, which stays at the window's left edge while the content moves over", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const docked = { title: (await box(page, "main h1"))[0], outline: (await box(page, ".right-sidebar-panel"))[0], edge: (await box(page, "[data-slot=sidebar-container]"))[2] };
    const open = await rail(page).boundingBox();
    expect(Math.abs(open!.x + open!.width / 2 - docked.edge)).toBeLessThan(2);
    await expect(rail(page)).toHaveAttribute("aria-expanded", "true");
    await expect(rail(page)).toHaveAttribute("aria-controls", "oh-sidebar");
    await rail(page).hover();
    expect(await rail(page).evaluate((element) => getComputedStyle(element).cursor)).toBe("w-resize");
    expect(await rail(page).evaluate((element) => getComputedStyle(element, "::after").backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    await rail(page).click();
    await expect.poll(() => state(page)).toEqual({ collapsed: true, state: "collapsed" });
    await settled(page);
    await expect(container(page)).toBeHidden();
    await expect(rail(page)).toHaveAttribute("aria-expanded", "false");
    const hidden = (await rail(page).boundingBox())!;
    expect(hidden.x + hidden.width).toBeGreaterThan(0);
    expect(hidden.x + hidden.width).toBeLessThanOrEqual(8);
    const collapsed = { title: (await box(page, "main h1"))[0], outline: (await box(page, ".right-sidebar-panel"))[0] };
    expect(collapsed.title).toBeLessThan(docked.title);
    expect(collapsed.outline).toBeLessThan(docked.outline);
    await page.mouse.move(3, 450);
    expect(await rail(page).evaluate((element) => getComputedStyle(element).cursor)).toBe("e-resize");
    await page.mouse.click(3, 450);
    await expect.poll(() => state(page)).toEqual({ collapsed: false, state: "expanded" });
    await settled(page);
    await expect(container(page)).toBeVisible();
    expect((await box(page, "main h1"))[0]).toBe(docked.title);
  });

  test("has no button that shows or hides it, and nothing peeks over the content", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const toggles = page.getByRole("button", { name: /sidebar/i });
    await expect(toggles).toHaveCount(1);
    await expect(toggles).toHaveAttribute("data-slot", "sidebar-rail");
    await expect(toggles).toHaveAttribute("tabindex", "-1");
    expect((await toggles.boundingBox())!.width).toBeLessThanOrEqual(16);
    await collapse(page);
    await page.mouse.move(700, 500);
    await page.mouse.move(4, 500);
    await page.waitForTimeout(600);
    await expect(container(page)).toBeHidden();
    expect(await state(page)).toEqual({ collapsed: true, state: "collapsed" });
    await expect(page.getByRole("button", { name: /sidebar/i })).toHaveAttribute("data-slot", "sidebar-rail");
  });

  for (const width of [1440, 1280, 1152, 1024, 900, 800]) {
    test(`never covers the content at ${width} px, shown or hidden`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      for (const stored of ["", "collapsed"]) {
        await page.addInitScript((value) => localStorage.setItem("openhal-sidebar", value), stored);
        for (const path of ["/docs/quickstart/", SPEC, "/drivers/"]) {
          await page.goto(path);
          const right = await page.evaluate(() => {
            const shown = [...document.querySelectorAll<HTMLElement>("[data-slot=sidebar-container], [data-slot=sidebar-rail]")].filter((element) => element.checkVisibility({ visibilityProperty: true }));
            return Math.max(0, ...shown.map((element) => element.getBoundingClientRect().right));
          });
          const content = await page.evaluate(() => {
            const texts = [...document.querySelectorAll("main h1, main p, main li, mobile-starlight-toc summary")].filter((part) => part.checkVisibility());
            return Math.min(
              ...texts.map((part) => {
                const range = document.createRange();
                range.selectNodeContents(part);
                return range.getBoundingClientRect().left;
              }),
            );
          });
          expect(right, `${path} ${stored || "shown"}`).toBeLessThanOrEqual(content);
        }
      }
    });
  }

  test("moves the content from where it stood, both ways, so the title never jumps", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const title = () => box(page, "main h1").then((rect) => rect[0]);
    const firstFrame = () =>
      page.evaluate(async () => {
        const main = document.querySelector("main")!;
        document.querySelector<HTMLElement>("[data-slot=sidebar-rail]")!.click();
        for (let frame = 0; frame < 120 && !main.getAnimations().length; frame++) await new Promise(requestAnimationFrame);
        const animations = main.getAnimations();
        for (const animation of animations) {
          animation.pause();
          animation.currentTime = 0;
        }
        const left = document.querySelector("main h1")!.getBoundingClientRect().left;
        for (const animation of animations) animation.play();
        return { left, moving: animations.length };
      });
    await rail(page).hover();
    await hydrated(page);
    const docked = await title();
    const hiding = await firstFrame();
    expect(hiding.moving).toBeGreaterThan(0);
    expect(Math.abs(hiding.left - docked)).toBeLessThan(2);
    await settled(page);
    const hidden = await title();
    expect(hidden).toBeLessThan(docked);
    const showing = await firstFrame();
    expect(Math.abs(showing.left - hidden)).toBeLessThan(2);
    await settled(page);
    expect(await title()).toBe(docked);
  });

  test("keeps the choice on the next page, hidden from the first frame without a layout shift", async ({ page, browserName }) => {
    await page.goto("/docs/quickstart/");
    await collapse(page);
    expect(await page.evaluate(() => localStorage.getItem("openhal-sidebar"))).toBe("collapsed");
    await page.route(/\/_astro\/.*\.js$/, (route) => route.abort());
    await page.goto(SPEC);
    expect(await state(page), "the head script and the sidebar's inline script alone apply the choice").toEqual({ collapsed: true, state: "collapsed" });
    await expect(container(page)).toBeHidden();
    await expect(rail(page)).toHaveAttribute("aria-expanded", "false");
    await page.unroute(/\/_astro\/.*\.js$/);
    await page.goto(SPEC);
    expect(await state(page)).toEqual({ collapsed: true, state: "collapsed" });
    if (browserName === "chromium") {
      const shift = await page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            let total = 0;
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries() as Array<PerformanceEntry & { value: number; hadRecentInput: boolean }>) if (!entry.hadRecentInput) total += entry.value;
            }).observe({ type: "layout-shift", buffered: true });
            setTimeout(() => resolve(total), 400);
          }),
      );
      expect(shift).toBeLessThan(0.001);
    }
    await page.keyboard.press("Control+b");
    await expect.poll(() => state(page)).toEqual({ collapsed: false, state: "expanded" });
  });

  test("Control or Command and B hides and shows it on the first press, before React loads, but not while typing", async ({ page }) => {
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    await page.goto("/docs/quickstart/");
    await page.waitForTimeout(500);
    expect(fetched.filter((path) => /SidebarNav/.test(path))).toEqual([]);
    await page.keyboard.press("Control+b");
    await expect.poll(() => state(page)).toEqual({ collapsed: true, state: "collapsed" });
    await settled(page);
    await page.keyboard.press("Control+b");
    await expect.poll(() => state(page)).toEqual({ collapsed: false, state: "expanded" });
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    await expect(page.locator("astro-island:has(#pg-text)")).not.toHaveAttribute("ssr", "");
    await page.locator("#pg-text").focus();
    await expect(page.locator("#pg-text")).toBeFocused();
    await page.keyboard.press("Control+b");
    await page.waitForTimeout(300);
    expect(await state(page)).toEqual({ collapsed: false, state: "expanded" });
  });

  test("while hidden, its links leave the tab order and screen readers", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    await collapse(page);
    expect(await container(page).evaluate((element) => getComputedStyle(element).visibility)).toBe("hidden");
    await page.locator("header.header [data-picker='theme']").focus();
    for (let step = 0; step < 3; step++) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => Boolean(document.activeElement?.closest("[data-slot=sidebar]")))).toBe(false);
    }
  });

  test("with reduced motion it switches at once and nothing slides", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/docs/quickstart/");
    await page.keyboard.press("Control+b");
    await expect.poll(() => state(page)).toEqual({ collapsed: true, state: "collapsed" });
    const moving = () => page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === "running" && Number(animation.effect?.getTiming().duration) > 0).length);
    expect(await moving()).toBe(0);
    await expect(container(page)).toBeHidden();
    await page.mouse.click(3, 450);
    await expect.poll(() => state(page)).toEqual({ collapsed: false, state: "expanded" });
    expect(await moving()).toBe(0);
  });

  for (const width of [1440, 1280, 1024]) {
    test(`starts every documentation page's title at one left edge while hidden at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(() => localStorage.setItem("openhal-sidebar", "collapsed"));
      const edges: Record<string, number> = {};
      for (const path of [SPEC, "/docs/", "/docs/quickstart/", "/spec/playground/", "/drivers/", "/library/scpi-rigol-dp832/"]) {
        await page.goto(path);
        edges[path] = (await box(page, "main h1"))[0];
      }
      for (const path of Object.keys(edges)) expect(edges[path], path).toBe(edges[SPEC]);
      const edge = await rail(page).boundingBox();
      expect(edges[SPEC]).toBeGreaterThan(edge!.x + edge!.width + 32);
    });
  }

  test("keeps its links working without JavaScript", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto("/docs/quickstart/");
    await page.locator("[data-slot=sidebar-content]").getByRole("link", { name: "Concepts" }).click();
    await expect(page).toHaveURL(/\/docs\/concepts\/$/);
    await expect(page.locator("[data-slot=sidebar-content] a[aria-current='page']")).toHaveText("Concepts");
    await context.close();
  });

  test("leaves phones and the pages without a sidebar alone", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("openhal-sidebar", "collapsed"));
    for (const path of ["/", "/blog/", "/404.html"]) {
      await page.goto(path);
      await expect(page.locator("[data-slot=sidebar-rail]")).toHaveCount(0);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/docs/quickstart/");
    await expect(rail(page)).toBeHidden();
    await page.locator(".sl-menu-button").click();
    await expect(page.locator("#starlight__sidebar").getByRole("link", { name: "Install" })).toBeVisible();
    await page.keyboard.press("Control+b");
    await page.waitForTimeout(300);
    await expect(page.locator("#starlight__sidebar").getByRole("link", { name: "Install" })).toBeVisible();
  });
});

test.describe("the phone menu", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
  });

  test("lists the sections first, then the section's pages, the version and the theme", async ({ page }) => {
    await page.goto(SPEC);
    await page.locator(".sl-menu-button").click();
    const menu = page.locator("#starlight__sidebar");
    await expect(menu).toBeVisible();
    await expect(menu.locator(".oh-menu-sections a")).toHaveText(SECTIONS);
    await expect(menu.locator(".oh-menu-sections a[aria-current='page']")).toHaveText("Specification");
    await expect(menu.locator(".sidebar-content a[aria-current='page']:not([role='menuitem'])").last()).toHaveText("3.3 Messages");
    await expect(picker(page, "version", ".mobile-preferences")).toHaveAccessibleName("Specification version v0.1");
    await expect(picker(page, "theme", ".mobile-preferences")).toHaveAccessibleName("Theme Auto");
    await picker(page, "theme", ".mobile-preferences").click();
    await expect(menu.getByRole("menu")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu.getByRole("menu")).toHaveCount(0);
    await menu.locator(".oh-menu-sections").getByRole("link", { name: "Device Library" }).click();
    await expect(page).toHaveURL(/\/library\/$/);
  });

  test("closes on Escape and gives focus back to its button", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    const button = page.locator(".sl-menu-button");
    await button.click();
    await expect(page.locator("#starlight__sidebar")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#starlight__sidebar")).toBeHidden();
    await expect(button).toBeFocused();
  });
});

test.describe("the outline and pager", () => {
  test("the outline, heading anchors and pager go somewhere real", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const outline = page.locator("starlight-toc a").nth(2);
    const target = (await outline.getAttribute("href"))!;
    await outline.click();
    await expect(page).toHaveURL(new RegExp(`${target}$`));
    await expect(page.locator(target)).toBeInViewport();
    const anchor = page.locator("h2 a.heading-link").nth(1);
    const hash = (await anchor.getAttribute("href"))!;
    await anchor.click();
    await expect(page).toHaveURL(new RegExp(`${hash}$`));
    const next = page.locator(".pagination-links a[rel='next']");
    const title = (await next.locator(".link-title").textContent())!.trim();
    await next.click();
    await expect(page.locator("h1")).toHaveText(title);
    await page.locator(".pagination-links a[rel='prev']").click();
    await expect(page.locator("h1")).toHaveText("3.3 Messages");
  });

  test("on a phone the outline sits under the header and jumps to a heading", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/docs/quickstart/");
    await page.locator("mobile-starlight-toc summary").click();
    await page.locator("mobile-starlight-toc").getByRole("link", { name: "Stop" }).click();
    await expect(page).toHaveURL(/#stop$/);
  });
});

test.describe("the theme picker", () => {
  test("switches the theme, which the next page keeps", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/docs/");
    await expect(picker(page, "theme")).toHaveAccessibleName("Theme Auto");
    await picker(page, "theme").click();
    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(picker(page, "theme")).toHaveAccessibleName("Theme Dark");
    await expect(picker(page, "theme")).toBeFocused();
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(13, 15, 18)");
    await page.goto(SPEC);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(picker(page, "theme")).toHaveAccessibleName("Theme Dark");
    await picker(page, "theme").click();
    await expect(page.getByRole("menuitemradio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("menuitemradio", { name: "Auto" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    expect(await page.evaluate(() => localStorage.getItem("starlight-theme"))).toBe("");
  });
});

test.describe("site search", () => {
  test("Ctrl K opens the palette before any script ran, which finds an error code and opens a result", async ({ page }) => {
    await page.goto("/drivers/");
    await page.keyboard.press("Control+k");
    await expect(palette(page)).toBeVisible();
    const input = palette(page).getByRole("combobox");
    await expect(input).toBeFocused();
    await input.fill("LIMIT_EXCEEDED");
    await expect(palette(page).locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    expect(await results(page).evaluateAll((items) => items.map((item) => item.getAttribute("href")))).toContain("/spec/errors/");
    const target = (await results(page).first().getAttribute("href"))!;
    await expect(results(page).first()).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`${target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
  });

  test("groups results by the header's sections, marks the matches and moves with the arrow keys", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/");
    await page.keyboard.press("Control+k");
    await palette(page).getByRole("combobox").fill("LIMIT_EXCEEDED");
    await expect(palette(page).locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    const headings = await palette(page).locator("[cmdk-group-heading]").allTextContents();
    expect(headings.length).toBeGreaterThan(1);
    for (const heading of headings) expect(SECTIONS).toContain(heading);
    expect(new Set(headings).size).toBe(headings.length);
    await expect(palette(page).locator("mark").first()).toHaveText(/LIMIT_EXCEEDED/);
    const ids = await results(page).evaluateAll((items) => items.map((item) => item.id));
    await page.keyboard.press("ArrowDown");
    await expect(results(page).nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(palette(page).getByRole("combobox")).toHaveAttribute("aria-activedescendant", ids[1]);
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await expect(results(page).last()).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Tab");
    await expect(palette(page).getByRole("combobox"), "the results are reached with the arrow keys, not Tab").toBeFocused();
    await expect(results(page).last()).toHaveAttribute("aria-selected", "true");
  });

  test("the header field opens the palette, and Escape closes it with focus back on the field", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const field = page.locator("[data-search-trigger]");
    await expect(field).toContainText("Search");
    await expect(field).toHaveAccessibleName(/^Search (Ctrl|⌘) K$/);
    await field.click();
    await expect(palette(page)).toBeVisible();
    await expect(palette(page).getByRole("combobox"), "a field with an id, which Chrome asks of every form field").toHaveAttribute("id", /\S/);
    await palette(page).getByRole("combobox").fill("print babysitter");
    await expect(palette(page).locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Escape");
    await expect(palette(page)).toBeHidden();
    await expect(field).toBeFocused();
  });

  test("a search with no match says so and suggests what to try", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+k");
    await palette(page).getByRole("combobox").fill("qzqzqz");
    await expect(palette(page).locator("[cmdk-empty]")).toHaveText(/No results for qzqzqz\. Try a method such as hal\/write or an error code such as LIMIT_EXCEEDED\./, { timeout: 15_000 });
    await expect(results(page)).toHaveCount(0);
  });

  test("before typing it lists pages to start with, then the searches a person opened", async ({ page }) => {
    await page.goto("/docs/");
    await page.keyboard.press("Control+k");
    await expect(palette(page).locator("[cmdk-group-heading]")).toHaveText(["Start here"]);
    await expect(results(page).first()).toHaveText("Quickstart");
    await expect(results(page).first()).toHaveAttribute("aria-selected", "true");
    await palette(page).getByRole("combobox").fill("Device file");
    await expect(palette(page).locator("[cmdk-item][href*='#']").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Enter");
    await expect(page).not.toHaveURL(/\/docs\/$/);
    await page.keyboard.press("Control+k");
    await expect(palette(page).locator("[cmdk-group-heading]")).toHaveText(["Recent searches", "Start here"]);
    await expect(results(page).first()).toHaveText("Device file");
    await page.keyboard.press("Enter");
    await expect(palette(page).getByRole("combobox")).toHaveValue("Device file");
    await palette(page).getByRole("combobox").fill("");
    await results(page).filter({ hasText: "Clear recent searches" }).click();
    await expect(palette(page).locator("[cmdk-group-heading]")).toHaveText(["Start here"]);
  });

  test("on a phone the field is an icon button that opens the palette full screen with a Cancel button", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: /^Search/ }).click();
    await expect(palette(page)).toBeVisible();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
    expect(await box(page, "[role='dialog']")).toEqual([0, 0, 390, 844]);
    expect((await box(page, "[data-search-trigger]")).slice(2), "the icon button is as easy to tap as the menu button").toEqual([40, 40]);
    await palette(page).getByRole("combobox").fill("print babysitter");
    await expect(palette(page).locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    await palette(page).getByRole("button", { name: "Cancel" }).click();
    await expect(palette(page)).toBeHidden();
  });

  test("results never show code, YAML or a message trace", async ({ page }) => {
    await page.goto("/docs/");
    await page.keyboard.press("Control+k");
    for (const [term, marked] of [
      ["uv run openhal demo", /demo|openhal/i],
      ["provenance", /provenance/i],
      ["babysit", /babysit/i],
      ["hand-written", /hand|written/i],
      ["Klipper", /klipper/i],
    ] as const) {
      await palette(page).getByRole("combobox").fill(term);
      await expect(palette(page).locator("[cmdk-item] mark").filter({ hasText: marked }).first()).toBeVisible({ timeout: 15_000 });
      for (const excerpt of await results(page).allTextContents()) {
        expect(excerpt, `${term}: ${excerpt}`).not.toMatch(/\$ uv run|"jsonrpc"|^\s*device:|provenance: \{|source: hand-written|openhal: "0\.1"|device: Klipper|connect: \{|\{ type: /);
      }
    }
  });
});

test.describe("page turns", () => {
  test("the nav highlight has one view transition name on every page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const path of ["/", "/docs/", SPEC, "/spec/playground/", "/drivers/", "/library/", "/sdks/"]) {
      await page.goto(path);
      const names = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("*")].map((el) => getComputedStyle(el).viewTransitionName).filter((name) => name && name !== "none"),
      );
      expect(names.filter((name) => name === "nav-pill"), path).toHaveLength(1);
      expect(names.filter((name) => name === "site-header"), path).toHaveLength(1);
      expect(new Set(names).size, path).toBe(names.length);
    }
  });

  test.describe("with retries, since a busy Mac can make Chromium drop a view transition between the preview server's uncached pages", () => {
    test.describe.configure({ retries: 2 });

    test("a page turn moves the way the nav goes, and only for section links", async ({ page, browserName }) => {
      test.skip(browserName !== "chromium", "cross-document view transitions are a Chromium feature");
      await page.setViewportSize({ width: 1440, height: 900 });
      const turn = () => page.evaluate(() => document.documentElement.dataset.turn ?? null);
      await page.goto("/drivers/");
      await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Device Library", exact: true }).click();
      await expect(page).toHaveURL(/\/library\/$/);
      expect(await turn()).toBe("forward");
      await page.waitForTimeout(500);
      await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Specification", exact: true }).click();
      await expect(page).toHaveURL(/\/spec\//);
      expect(await turn()).toBe("backward");
      await page.goto("/");
      await page.getByRole("link", { name: "Send the requests in your browser" }).click();
      await expect(page).toHaveURL(/\/spec\/playground\/$/);
      expect(await turn()).toBeNull();
    });
  });

  test("a section in the tablet's Section menu turns the page like the nav's links", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "cross-document view transitions are a Chromium feature");
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/");
    const section = page.locator("header.header [data-picker='section']");
    await section.hover();
    await section.click();
    await page.getByRole("menu").getByRole("menuitem", { name: "Device Library" }).click();
    await expect(page).toHaveURL(/\/library\/$/);
    const asked = () => page.evaluate(() => document.documentElement.dataset.turn ?? sessionStorage.getItem("openhal:page-turn"));
    await expect.poll(asked, "the page left asked for a forward turn, which the preview server's uncached pages can drop at this width").toBe("forward");
  });

  test("no page moves while it loads", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout shift entries are a Chromium API");
    for (const path of ["/docs/quickstart/", SPEC, "/drivers/", "/spec/playground/"]) {
      await page.goto(path);
      await page.waitForTimeout(800);
      const shift = await page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            let total = 0;
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries() as Array<PerformanceEntry & { value: number; hadRecentInput: boolean }>) {
                if (!entry.hadRecentInput) total += entry.value;
              }
            }).observe({ type: "layout-shift", buffered: true });
            setTimeout(() => resolve(total), 400);
          }),
      );
      expect(shift, path).toBeLessThan(0.001);
    }
  });
});

test("the footer links to the repository and says OpenHAL is not affiliated", async ({ page }) => {
  for (const path of ["/", "/docs/quickstart/"]) {
    await page.goto(path);
    await expect(page.locator(".oh-site-footer").getByRole("link", { name: "Source on GitHub" })).toHaveAttribute("href", REPOSITORY);
    await expect(page.locator(".oh-site-footer")).toContainText("not affiliated with Anthropic or MHS");
  }
});

test("a copy button copies its block", async ({ page, browserName, context }) => {
  test.skip(browserName !== "chromium", "clipboard permissions are a Chromium feature here");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/library/scpi-rigol-dp832/");
  const button = page.getByRole("button", { name: "Copy code" }).first();
  await expect(button).toHaveText("Copy", { useInnerText: true });
  await button.click();
  await expect(button).toHaveText("Copied", { useInnerText: true });
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("id: rigol-dp832");
});
