import { expect, test, type Page } from "@playwright/test";

const SPEC = "/spec/v0.1/basic/messages/";
const EASE = "cubic-bezier(0.2, 0, 0, 1)";

interface Seen {
  target: string;
  properties: string[];
  duration: number;
  easing: string;
}

const picker = (page: Page, kind: "version" | "theme" | "section", scope = "header.header") => page.locator(`${scope} [data-picker='${kind}']`);
const menu = (page: Page) => page.getByRole("menu");

/**
 * Records each animation the page starts through the Web Animations API, which Motion drives for
 * the islands and Starlight's parts alike. Motion's own check for linear() easing, which has no
 * duration and never shows, is left out.
 */
async function record(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const seen: Seen[] = [];
    Object.assign(window, { seen });
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (this: Element, keyframes, options) {
      const timing: KeyframeAnimationOptions = typeof options === "number" ? { duration: options } : (options ?? {});
      const frames = Array.isArray(keyframes) ? keyframes : [keyframes ?? {}];
      const properties = Array.isArray(keyframes) ? [...new Set(frames.flatMap((frame) => Object.keys(frame ?? {})))] : Object.keys(keyframes ?? {});
      if (timing.duration !== undefined) {
        seen.push({
          target: `${this.localName}${timing.pseudoElement ?? ""} ${typeof this.className === "string" ? this.className : ""}`.trim(),
          properties: properties.filter((key) => !["offset", "easing", "composite"].includes(key)),
          duration: Number(timing.duration),
          easing: String(timing.easing),
        });
      }
      return animate.call(this, keyframes, options);
    };
  });
}

const taken = (page: Page) => page.evaluate(() => (window as unknown as { seen: Seen[] }).seen.splice(0));

/** The scripts of the React islands on the page, which may only load once a person reaches for one. */
const islandScripts = (page: Page) =>
  page.evaluate(() => [...new Set([...document.querySelectorAll("astro-island")].flatMap((island) => [island.getAttribute("component-url") ?? "", island.getAttribute("renderer-url") ?? ""]).filter((url) => url.includes("_astro")))]);

/** Moves the pointer, the first interaction, and waits for the motion code for Starlight's parts to load. */
async function ready(page: Page, motion = true): Promise<void> {
  await page.mouse.move(8, 300);
  await page.waitForFunction(
    (motion) => {
      const loaded = performance.getEntriesByType("resource").map((entry) => entry.name);
      return loaded.some((name) => /\/_astro\/ui\./.test(name)) && (!motion || loaded.some((name) => /\/_astro\/mini\./.test(name)));
    },
    motion,
  );
  await page.waitForTimeout(100);
}

/** Opens a picker and waits until its island answers, the way a person's second look would find it. */
async function open(page: Page, kind: "theme" | "section", scope = "header.header"): Promise<void> {
  await picker(page, kind, scope).hover();
  await picker(page, kind, scope).click();
  await expect(menu(page)).toBeVisible();
}

const settled = (page: Page) => page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running" || animation instanceof CSSAnimation), undefined, { polling: 25 });

function within(seen: Seen[], name: string): void {
  expect(seen.length, `${name} animates`).toBeGreaterThan(0);
  for (const item of seen) {
    const label = `${name}: ${item.target} ${item.properties.join(" ")}`;
    expect(item.duration, label).toBeGreaterThanOrEqual(150);
    expect(item.duration, label).toBeLessThanOrEqual(250);
    expect(item.easing, label).toBe(EASE);
    for (const property of item.properties) expect(["opacity", "transform", "rotate", "height"], label).toContain(property);
    if (item.properties.includes("height")) expect(item.target, label).toMatch(/^(ul|div build-body)/);
  }
}

test.describe("the interactive parts", () => {
  test("load their code and React only once a person reaches for them", async ({ page }) => {
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    await page.waitForTimeout(1500);
    const islands = (await islandScripts(page)).map((url) => new URL(url, page.url()).pathname);
    expect(islands.length).toBeGreaterThan(0);
    expect(fetched.filter((path) => islands.includes(path) || /\/_astro\/(ui|mini)\./.test(path))).toEqual([]);
    await page.mouse.move(700, 600);
    await expect.poll(() => fetched.filter((path) => /\/_astro\/(ui|mini)\./.test(path)).length).toBe(2);
    expect(fetched.filter((path) => islands.includes(path)), "moving over the page loads no island").toEqual([]);
    await picker(page, "theme").hover();
    await expect.poll(() => fetched.some((path) => /ThemeMenu/.test(path))).toBe(true);
    expect(fetched.filter((path) => /SearchPalette|SidebarNav/.test(path)), "only the island a person reached for loads").toEqual([]);
    await page.locator("[data-slot=sidebar-content] a").first().hover();
    await page.waitForTimeout(400);
    expect(fetched.filter((path) => /SidebarNav/.test(path)), "pointing at a sidebar link loads nothing").toEqual([]);
    await page.locator("[data-group] > button").first().hover();
    await expect.poll(() => fetched.some((path) => /SidebarNav/.test(path)), "pointing at a group loads the sidebar").toBe(true);
  });

  test("open and close in 150 to 250 ms on the site's ease, moving only opacity, transforms and a disclosure's height", async ({ page, browserName }) => {
    test.setTimeout(120_000);
    await record(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    await ready(page);
    await open(page, "theme");
    await settled(page);
    await page.keyboard.press("Escape");
    await expect(menu(page)).toHaveCount(0);
    within(await taken(page), "theme picker");

    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
    await settled(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search" })).toBeHidden();
    const search = await taken(page);
    within(search, "search palette");
    expect(search.filter((item) => item.target.includes("bg-(--oh-overlay)") && item.properties.includes("opacity")), "the overlay fades in and out").toHaveLength(2);

    await page.evaluate(() => {
      const container = document.querySelector("[data-slot=sidebar-container]")!;
      const slides: unknown[] = [];
      Object.assign(window, { slides });
      new MutationObserver(() =>
        slides.push(
          container.getAnimations().map((animation) => ({ property: (animation as CSSTransition).transitionProperty, duration: Number(animation.effect?.getTiming().duration), easing: String(animation.effect?.getTiming().easing) })),
        ),
      ).observe(document.querySelector("[data-slot=sidebar]")!, { attributes: true, attributeFilter: ["data-state"] });
    });
    await page.keyboard.press("Control+b");
    await expect(page.locator("[data-slot=sidebar]")).toHaveAttribute("data-state", "collapsed");
    await settled(page);
    await page.keyboard.press("Control+b");
    await expect(page.locator("[data-slot=sidebar]")).toHaveAttribute("data-state", "expanded");
    await settled(page);
    const [out, back] = await page.evaluate(() => (window as unknown as { slides: unknown[] }).slides);
    expect(out, "the sidebar slides out in 150 ms").toContainEqual({ property: "translate", duration: 150, easing: EASE });
    expect(back, "the sidebar slides back in 200 ms").toContainEqual({ property: "translate", duration: 200, easing: EASE });
    const moves = await taken(page);
    within(moves, "the content moving over");
    expect(moves.filter((item) => item.target.startsWith("main")).length, "the content moves over both ways").toBeGreaterThanOrEqual(2);

    await page.goto("/docs/quickstart/");
    await ready(page);
    const group = page.locator("[data-group='Tutorials'] > button");
    await group.hover();
    await expect(page.locator("astro-island:has([data-slot=sidebar])")).not.toHaveAttribute("ssr", "");
    await group.click();
    await settled(page);
    await group.click();
    await settled(page);
    within(await taken(page), "sidebar group");
    if (browserName === "chromium") {
      await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
      await page.getByRole("button", { name: "Copy code" }).first().click();
      await expect(page.getByRole("button", { name: "Copy code" }).first()).toHaveAttribute("data-copied", "");
      await settled(page);
      within(await taken(page), "Copy");
    }

    await page.goto("/spec/playground/");
    await ready(page);
    await page.getByRole("button", { name: "About hazard" }).click();
    await expect(page.getByRole("note")).toBeVisible();
    await settled(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("note")).toBeHidden();
    await page.locator("summary", { hasText: "Build your own request" }).click();
    await settled(page);
    within(await taken(page), "information mark and the builder");

    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/");
    await ready(page);
    await open(page, "section");
    await settled(page);
    await page.keyboard.press("Escape");
    await settled(page);
    within(await taken(page), "section picker");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(SPEC);
    await ready(page);
    await page.locator(".sl-menu-button").click();
    await settled(page);
    await open(page, "theme", ".mobile-preferences");
    await settled(page);
    await page.keyboard.press("Escape");
    await settled(page);
    await page.locator(".sl-menu-button").click();
    await expect(page.locator("#starlight__sidebar")).toBeHidden();
    await page.locator("mobile-starlight-toc summary").click();
    await settled(page);
    await page.keyboard.press("Escape");
    await settled(page);
    within(await taken(page), "phone menu, its theme picker and the outline");
  });

  test("open and close at once with reduced motion", async ({ page }) => {
    await record(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    await ready(page, false);
    await open(page, "theme");
    await expect(menu(page)).toHaveCSS("opacity", "1");
    await page.keyboard.press("Escape");
    await expect(menu(page)).toHaveCount(0);
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Search" })).toHaveCSS("opacity", "1");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search" })).toHaveCount(0);
    await page.locator("[data-group] > button").first().click();
    await expect(page.locator("[data-group]").first()).toHaveAttribute("data-state", "closed");
    await expect(page.locator("[data-group] [data-closing]")).toHaveCount(0);
    await page.keyboard.press("Control+b");
    await expect(page.locator("html")).toHaveAttribute("data-sidebar", "collapsed");
    expect(await page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === "running").length), "nothing slides").toBe(0);
    await page.keyboard.press("Control+b");
    await expect(page.locator("html")).not.toHaveAttribute("data-sidebar", "collapsed");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".sl-menu-button").click();
    await expect(page.locator("#starlight__sidebar")).toHaveCSS("opacity", "1");
    expect((await taken(page)).filter((item) => item.duration > 0)).toEqual([]);
    expect(fetched.filter((path) => /\/_astro\/mini\./.test(path))).toEqual([]);
  });

  test("keep a closing part drawn until its motion ends", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/quickstart/");
    await ready(page);
    await page.locator("[data-group='Tutorials'] > button").hover();
    await expect(page.locator("astro-island:has([data-slot=sidebar])")).not.toHaveAttribute("ssr", "");
    const half = await page.evaluate(async () => {
      const details = document.querySelector<HTMLElement>("[data-group='Tutorials']")!;
      const body = details.querySelector<HTMLElement>(":scope > ul")!;
      const full = body.getBoundingClientRect().height;
      details.querySelector<HTMLElement>(":scope > button")!.click();
      for (let frame = 0; frame < 60 && !body.getAnimations().length; frame++) await new Promise(requestAnimationFrame);
      const animations = body.getAnimations();
      for (const animation of animations) {
        animation.pause();
        animation.currentTime = Number(animation.effect?.getComputedTiming().duration) / 2;
      }
      const result = { full, half: body.getBoundingClientRect().height, open: details.dataset.state === "open", closing: body.hasAttribute("data-closing"), shown: body.checkVisibility() };
      for (const animation of animations) animation.play();
      return result;
    });
    expect(half.open).toBe(false);
    expect(half.closing).toBe(true);
    expect(half.shown).toBe(true);
    expect(half.half).toBeGreaterThan(0);
    expect(half.half).toBeLessThan(half.full);
    await expect(page.locator("[data-group] [data-closing]")).toHaveCount(0);

    await open(page, "theme");
    await settled(page);
    await page.keyboard.press("Escape");
    const leaving = await page.evaluate(async () => {
      let list: HTMLElement | null = null;
      for (let frame = 0; frame < 60; frame++) {
        list = document.querySelector<HTMLElement>("[role='menu']");
        if (list?.getAnimations().length) break;
        await new Promise(requestAnimationFrame);
      }
      if (!list) return { drawn: false, opacity: -1 };
      const animations = list.getAnimations();
      for (const animation of animations) {
        animation.pause();
        animation.currentTime = Number(animation.effect?.getComputedTiming().duration) / 2;
      }
      const result = { drawn: list.isConnected && list.checkVisibility(), opacity: Number(getComputedStyle(list).opacity) };
      for (const animation of animations) animation.play();
      return result;
    });
    expect(leaving.drawn).toBe(true);
    expect(leaving.opacity).toBeGreaterThan(0);
    expect(leaving.opacity).toBeLessThan(1);
    await expect(menu(page)).toHaveCount(0);
  });
});

test.describe("the pickers", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("show their word and a chevron, with no icon, everywhere", async ({ page }) => {
    for (const [width, path, scope] of [
      [1440, SPEC, "header.header"],
      [900, "/drivers/", "header.header"],
      [390, SPEC, ".mobile-preferences"],
    ] as const) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      if (scope === ".mobile-preferences") await page.locator(".sl-menu-button").click();
      const pickers = page.locator(`${scope} button[data-picker]`);
      for (const one of await pickers.all()) {
        if (!(await one.isVisible())) continue;
        const marks = await one.evaluate((element) => [...element.querySelectorAll(":is(svg, img)")].map((mark) => `${mark.localName} ${mark.closest("[aria-hidden='true']") ? "hidden" : "shown"}`));
        expect(marks, `${width} ${scope}`).toEqual(["svg hidden"]);
        await one.hover();
        await one.click();
        await expect(menu(page)).toBeVisible();
        expect(await menu(page).locator(":is(svg, img)").count(), `${width} ${scope} list`).toBe(0);
        await page.keyboard.press("Escape");
        await expect(menu(page)).toHaveCount(0);
      }
      expect(await pickers.count()).toBeGreaterThan(0);
    }
  });

  test("answer Enter, Space, the arrow keys, Home, End, a letter, Escape and Tab", async ({ page }) => {
    await page.goto(SPEC);
    await ready(page);
    const theme = picker(page, "theme");
    const item = (name: string) => menu(page).getByRole("menuitemradio", { name });
    await theme.focus();
    await page.keyboard.press("Enter");
    await expect(menu(page)).toBeVisible();
    await expect(theme).toHaveAttribute("aria-expanded", "true");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(item("Light")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(item("Dark")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(item("Dark")).toBeFocused();
    await page.keyboard.press("Home");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("End");
    await expect(item("Dark")).toBeFocused();
    await page.keyboard.press("l");
    await expect(item("Light")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(menu(page)).toHaveCount(0);
    await expect(theme).toBeFocused();
    await expect(theme).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("ArrowDown");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(item("Light")).toBeFocused();
    await page.keyboard.press(" ");
    await expect(page.locator("html")).toHaveAttribute("data-theme-choice", "light");
    await expect(menu(page)).toHaveCount(0);
    await expect(theme).toBeFocused();
    await expect(theme).toHaveAccessibleName("Theme Light");
    await page.keyboard.press(" ");
    await expect(item("Auto")).toBeFocused();
    await expect(item("Light")).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("Tab");
    await expect(menu(page)).toHaveCount(0);
    await expect(theme).not.toBeFocused();
    await expect(page.locator("[data-slot=sidebar-content] :is(a, button)").first(), "Tab moves on to what follows the picker").toBeFocused();
  });

  test("close on a click outside, and one opening closes another", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/drivers/");
    await ready(page);
    await open(page, "section");
    await expect(menu(page)).toHaveAccessibleName(/^Section/);
    await picker(page, "theme").hover();
    await picker(page, "theme").click();
    await expect(menu(page)).toHaveCount(1);
    await expect(menu(page)).toHaveAccessibleName(/^Theme/);
    await page.mouse.click(450, 600);
    await expect(menu(page)).toHaveCount(0);
    await expect(picker(page, "theme")).toHaveAttribute("aria-expanded", "false");
  });

  test("open below their button, or above it at the foot of the phone menu", async ({ page }) => {
    await page.goto(SPEC);
    await ready(page);
    const placed = async (scope: string) => {
      await open(page, "theme", scope);
      await settled(page);
      const button = await picker(page, "theme", scope).evaluate((element) => element.getBoundingClientRect().toJSON());
      const box = await menu(page).evaluate((element) => element.getBoundingClientRect().toJSON());
      return { gapBelow: box.top - button.bottom, gapAbove: button.top - box.bottom, right: box.right - button.right };
    };
    const header = await placed("header.header");
    expect(Math.abs(header.gapBelow - 4)).toBeLessThan(1);
    expect(Math.abs(header.right)).toBeLessThan(1);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".sl-menu-button").click();
    await page.locator(".mobile-preferences").scrollIntoViewIfNeeded();
    const foot = await placed(".mobile-preferences");
    expect(Math.abs(foot.gapAbove - 4)).toBeLessThan(1);
    expect(Math.abs(foot.right)).toBeLessThan(1);
  });
});

test.describe("control outlines", () => {
  /**
   * How thick a part's outline looks, its border and the inset ring in the border's color. Browsers
   * round a border's width down to whole pixels, so the half pixel is the ring.
   */
  const line = (page: Page, selector: string) =>
    page.locator(selector).first().evaluate((element) => {
      const style = getComputedStyle(element);
      const ring = /^(.+) 0px 0px 0px ([\d.]+)px inset$/.exec(style.boxShadow);
      const sides = new Set([style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth]);
      return { width: parseFloat(style.borderTopWidth) + (ring ? parseFloat(ring[2]) : 0), even: sides.size === 1, matched: ring ? ring[1] === style.borderTopColor : style.boxShadow === "none" };
    });

  const controls = async (page: Page, selectors: string[], width: number) => {
    for (const selector of selectors) expect(await line(page, selector), selector).toEqual({ width, even: true, matched: true });
  };

  test("draw 1.5 px from one token while rules, tables and panels stay 1 px", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/quickstart/");
    const outlined = ["[data-search-trigger]", "[data-search-trigger] kbd", ".copy-button", ".pagination-links a"];
    await controls(page, outlined, 1.5);
    await controls(page, [".code-block"], 1);
    expect(await page.locator("header.header").evaluate((header) => [getComputedStyle(header).borderBottomWidth, getComputedStyle(header).boxShadow])).toEqual(["1px", "none"]);
    await page.evaluate(() => document.documentElement.style.setProperty("--oh-control-line", "3px"));
    await controls(page, outlined, 3);

    await page.goto("/drivers/");
    await controls(page, ["[data-filters] input[name='q']", "[data-filters] select"], 1.5);
    expect(await page.locator("table.drivers td").first().evaluate((cell) => getComputedStyle(cell).borderBottomWidth)).toBe("1px");

    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    await controls(page, ["#pg-text", ".request select", ".button.quiet", ".info"], 1.5);
    await controls(page, [".panel"], 1);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/docs/quickstart/");
    await controls(page, [".sl-menu-button", "mobile-starlight-toc .toggle"], 1.5);
  });
});

test.describe("the theme", () => {
  test("follows the system while Auto is chosen, before any interaction", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/docs/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});
