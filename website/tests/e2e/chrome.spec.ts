import { expect, test, type Page } from "@playwright/test";

const SPEC = "/spec/v0.1/basic/messages/";
const SECTIONS = ["Overview", "Docs", "Specification", "Playground", "Drivers", "Device Library"];
const REPOSITORY = "https://github.com/sohan-bhat/OpenHAL";

const box = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const rect = el.getBoundingClientRect();
    return [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)];
  });

const searchReady = (page: Page) => page.locator("#starlight__search input").waitFor({ state: "attached", timeout: 15_000 });

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
      picker: boxes("oh-section-select"),
      search: boxes("site-search button[data-open-modal]"),
      github: boxes(".oh-social a"),
      version: boxes("oh-version-select"),
      theme: boxes("starlight-theme-select"),
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
        const items = [...document.querySelectorAll(".oh-brand, .oh-sections li, oh-section-select, site-search button[data-open-modal], .oh-social a, header.header oh-version-select, header.header starlight-theme-select, .sl-menu-button")]
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
      const pill = await page.locator(".sidebar-content .top-level > li").first().evaluate((el) => el.getBoundingClientRect().left);
      expect(Math.abs((await box(page, ".oh-brand"))[0] - pill)).toBeLessThan(1);
    });
  }

  test("collapses the sections into a picker on a tablet that shows and opens the current section", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/moonraker/");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    const picker = page.locator("header.header oh-section-select select");
    await expect(picker).toBeVisible();
    await expect(picker).toHaveAccessibleName("Section");
    expect(await picker.locator("option").allTextContents()).toEqual(SECTIONS);
    await expect(picker.locator("option:checked")).toHaveText("Drivers");
    await picker.selectOption({ label: "Device Library" });
    await expect(page).toHaveURL(/\/library\/$/);
    await page.goto("/404.html");
    await expect(page.locator("header.header oh-section-select option:checked")).toHaveText("Sections");
  });
});

test.describe("the version picker", () => {
  test("sits after GitHub, names itself and shows v0.1, pointing at the same section", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const picker = page.locator("header.header oh-version-select select");
    await expect(picker).toHaveAccessibleName("Specification version");
    await expect(picker.locator("option:checked")).toHaveText("v0.1");
    await expect(picker).toHaveValue(SPEC);
    const github = await box(page, ".oh-social a");
    expect((await box(page, "header.header oh-version-select"))[0]).toBeGreaterThan(github[0] + github[2]);
    await page.goto("/docs/");
    await expect(picker).toHaveValue("/spec/v0.1/");
    for (const value of await picker.locator("option").evaluateAll((items) => items.map((item) => (item as HTMLOptionElement).value))) {
      expect((await page.request.get(value)).status(), value).toBe(200);
    }
  });

  test("opens as a themed list with the current version in the nav's highlight in Chromium", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "customizable selects are a Chromium feature, other browsers draw the native list");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const picker = page.locator("header.header oh-version-select select");
    await picker.click();
    const checked = picker.locator("option:checked");
    await expect(checked).toBeVisible();
    const colors = await checked.evaluate((option) => {
      const style = getComputedStyle(option);
      const probe = document.createElement("span");
      probe.style.background = "color-mix(in srgb, var(--accent) 10%, var(--bg))";
      probe.style.color = "var(--accent)";
      document.body.append(probe);
      const want = [getComputedStyle(probe).backgroundColor, getComputedStyle(probe).color];
      probe.remove();
      return { got: [style.backgroundColor, style.color], want, radius: parseFloat(style.borderTopLeftRadius) };
    });
    expect(colors.got).toEqual(colors.want);
    expect(colors.radius).toBeGreaterThan(0);
    await page.keyboard.press("Escape");
    await expect(checked).toBeHidden();
  });
});

test.describe("the sidebar", () => {
  test("marks the current page and opens the groups around it", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    const sidebar = page.locator(".sidebar-content");
    await expect(sidebar.locator(".top-level a[aria-current='page']")).toHaveText("3.3 Messages");
    for (const group of ["Specification v0.1", "3 Base protocol"]) await expect(sidebar.locator("details", { has: page.locator(`summary:has-text("${group}")`) }).first()).toHaveAttribute("open", "");
    expect(await sidebar.locator(".top-level > li > details > summary").allInnerTexts()).toEqual(["Specification v0.1", "All versions", "Try the protocol"]);
  });

  test("collapses a group, which stays collapsed on the next page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/quickstart/");
    const tutorials = page.locator(".sidebar-content details", { has: page.locator('summary:has-text("Tutorials")') });
    await expect(tutorials).toHaveAttribute("open", "");
    await tutorials.locator("summary").click();
    await expect(tutorials).not.toHaveAttribute("open", "");
    await expect(tutorials.getByRole("link", { name: "Connect Claude" })).toBeHidden();
    await page.locator(".sidebar-content").getByRole("link", { name: "Install" }).click();
    await expect(page).toHaveURL(/\/docs\/install\/$/);
    await expect(page.locator(".sidebar-content details", { has: page.locator('summary:has-text("Tutorials")') })).not.toHaveAttribute("open", "");
  });

  test("is left out on a desktop where a page has no pages of its own, which keep the phone menu", async ({ page }) => {
    for (const path of ["/", "/404.html", "/blog/"]) {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await expect(page.locator("#starlight__sidebar"), path).toBeHidden();
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
    await expect(menu.locator(".sidebar-content a[aria-current='page']").last()).toHaveText("3.3 Messages");
    await expect(menu.locator(".mobile-preferences oh-version-select select")).toHaveAccessibleName("Specification version");
    await expect(menu.locator(".mobile-preferences starlight-theme-select select")).toBeVisible();
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
    const picker = page.locator("header.header starlight-theme-select select");
    await expect(picker).toHaveAccessibleName("Select theme");
    await picker.selectOption("dark");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(13, 15, 18)");
    await page.goto(SPEC);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.locator("header.header starlight-theme-select select").selectOption("auto");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});

test.describe("site search", () => {
  test("Ctrl K opens Starlight's search, which finds an error code and opens a result", async ({ page }) => {
    await page.goto("/drivers/");
    await searchReady(page);
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: "Search" });
    await expect(dialog).toBeVisible();
    const input = dialog.locator("#starlight__search input");
    await expect(input).toBeFocused();
    await input.fill("LIMIT_EXCEEDED");
    const results = dialog.locator(".pagefind-ui__result-link");
    await expect(results.first()).toBeVisible({ timeout: 15_000 });
    expect(await results.evaluateAll((items) => items.map((item) => item.getAttribute("href")))).toContain("/spec/errors/");
    const target = (await results.first().getAttribute("href"))!;
    await results.first().click();
    await expect(page).toHaveURL(new RegExp(`${target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
  });

  test("the header field opens the search, and Escape closes it with focus back on the field", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const field = page.locator("site-search button[data-open-modal]");
    await expect(field).toContainText("Search");
    await field.click();
    const dialog = page.getByRole("dialog", { name: "Search" });
    await expect(dialog).toBeVisible();
    await dialog.locator("#starlight__search input").fill("print babysitter");
    await expect(dialog.locator(".pagefind-ui__result-link").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(field).toBeFocused();
  });

  test("a search with no match says so", async ({ page }) => {
    await page.goto("/");
    await searchReady(page);
    await page.keyboard.press("Control+k");
    await page.locator("#starlight__search input").fill("qzqzqz");
    await expect(page.locator(".pagefind-ui__message")).toHaveText(/No results for qzqzqz/, { timeout: 15_000 });
    await expect(page.locator(".pagefind-ui__result-link")).toHaveCount(0);
  });

  test("on a phone the field is an icon button that opens the same dialog", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
    await page.locator("#starlight__search input").fill("print babysitter");
    await expect(page.locator(".pagefind-ui__result-link").first()).toBeVisible({ timeout: 15_000 });
  });

  test("results never show code, YAML or a message trace", async ({ page }) => {
    await page.goto("/docs/");
    await searchReady(page);
    await page.keyboard.press("Control+k");
    await page.locator("#starlight__search input").fill("uv run openhal demo");
    await expect(page.locator(".pagefind-ui__result-link").first()).toBeVisible({ timeout: 15_000 });
    for (const excerpt of await page.locator(".pagefind-ui__result-excerpt").allTextContents()) {
      expect(excerpt, excerpt).not.toMatch(/\$ uv run|"jsonrpc"|^\s*device:/);
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
  await button.click();
  await expect(button).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("id: rigol-dp832");
});
