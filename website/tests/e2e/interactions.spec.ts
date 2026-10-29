import { expect, test, type Page } from "@playwright/test";

const SPEC = "/spec/v0.1/basic/messages/";
const EASE = "cubic-bezier(0.2, 0, 0, 1)";

interface Seen {
  target: string;
  properties: string[];
  duration: number;
  easing: string;
}

const picker = (page: Page, kind: "version" | "theme" | "section", scope = "header.header") => page.locator(`${scope} oh-picker[data-kind='${kind}'] .oh-picker-button`);
const list = (page: Page, kind: "version" | "theme" | "section", scope = "header.header") => page.locator(`${scope} oh-picker[data-kind='${kind}'] .oh-picker-list`);

/** Records each animation the page starts through the Web Animations API, which Motion drives. */
async function record(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const seen: Seen[] = [];
    Object.assign(window, { seen });
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (this: Element, keyframes, options) {
      const timing: KeyframeAnimationOptions = typeof options === "number" ? { duration: options } : (options ?? {});
      const frames = Array.isArray(keyframes) ? keyframes : [keyframes ?? {}];
      const properties = [...new Set(frames.flatMap((frame) => Object.keys(frame ?? {})))].filter((key) => !["offset", "easing", "composite"].includes(key));
      seen.push({ target: `${this.localName}${timing.pseudoElement ?? ""} ${this.className}`.trim(), properties, duration: Number(timing.duration), easing: String(timing.easing) });
      return animate.call(this, keyframes, options);
    };
  });
}

const taken = (page: Page) => page.evaluate(() => (window as unknown as { seen: Seen[] }).seen.splice(0));

/** Moves the pointer, the first interaction, and waits for the motion code and Motion to load. */
async function ready(page: Page, motion = true): Promise<void> {
  await page.mouse.move(8, 300);
  await page.waitForFunction(
    (motion) => {
      const loaded = performance.getEntriesByType("resource").map((entry) => entry.name);
      return customElements.get("oh-picker") && loaded.some((name) => /\/_astro\/ui\./.test(name)) && (!motion || loaded.some((name) => /\/_astro\/mini\./.test(name)));
    },
    motion,
  );
  await page.waitForTimeout(100);
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
  test("load their code and Motion only once a person interacts", async ({ page }) => {
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    await page.goto(SPEC);
    await page.waitForTimeout(1500);
    expect(fetched.filter((path) => /\/_astro\/(ui|mini|floating-ui)\./.test(path))).toEqual([]);
    await page.mouse.move(400, 300);
    await expect.poll(() => fetched.filter((path) => /\/_astro\/(ui|mini)\./.test(path)).length).toBe(2);
    await picker(page, "version").click();
    await expect(list(page, "version")).toBeVisible();
    expect(fetched.filter((path) => path.includes("floating-ui")), "anchoring places the list without Floating UI").toEqual([]);
  });

  test("open and close in 150 to 250 ms on the site's ease, moving only opacity, transforms and a disclosure's height", async ({ page, browserName }) => {
    test.setTimeout(90_000);
    await record(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    await ready(page);
    for (const kind of ["version", "theme"] as const) {
      await picker(page, kind).click();
      await expect(list(page, kind)).toBeVisible();
      await settled(page);
      await page.keyboard.press("Escape");
      await expect(list(page, kind)).toBeHidden();
      within(await taken(page), `${kind} picker`);
    }
    await page.locator("site-search button[data-open-modal]").click();
    await expect(page.getByRole("dialog", { name: "Search" })).toBeVisible();
    await settled(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search" })).toBeHidden();
    const search = await taken(page);
    within(search, "search dialog");
    expect(search.map((item) => item.target).filter((target) => target.startsWith("dialog::backdrop"))).toHaveLength(2);

    await page.goto("/docs/quickstart/");
    await ready(page);
    const group = page.locator(".sidebar-content summary", { hasText: "Tutorials" });
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
    await picker(page, "section").click();
    await settled(page);
    await page.keyboard.press("Escape");
    await settled(page);
    within(await taken(page), "section picker");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(SPEC);
    await ready(page);
    await page.locator(".sl-menu-button").click();
    await settled(page);
    for (const kind of ["version", "theme"] as const) {
      await picker(page, kind, ".mobile-preferences").click();
      await settled(page);
      await page.keyboard.press("Escape");
      await settled(page);
    }
    await page.locator(".sl-menu-button").click();
    await expect(page.locator("#starlight__sidebar")).toBeHidden();
    await page.locator("mobile-starlight-toc summary").click();
    await settled(page);
    await page.keyboard.press("Escape");
    await settled(page);
    within(await taken(page), "phone menu, its pickers and the outline");
  });

  test("open and close at once with reduced motion, and never load Motion", async ({ page }) => {
    await record(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SPEC);
    await ready(page, false);
    await picker(page, "version").click();
    await expect(list(page, "version")).toHaveCSS("opacity", "1");
    await page.keyboard.press("Escape");
    await expect(list(page, "version")).toBeHidden();
    await page.locator("site-search button[data-open-modal]").click();
    await expect(page.getByRole("dialog", { name: "Search" })).toHaveCSS("opacity", "1");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search" })).toBeHidden();
    await page.locator(".sidebar-content summary").first().click();
    await expect(page.locator(".sidebar-content details[data-closing]")).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".sl-menu-button").click();
    await expect(page.locator("#starlight__sidebar")).toHaveCSS("opacity", "1");
    expect(await taken(page)).toEqual([]);
    expect(fetched.filter((path) => /\/_astro\/mini\./.test(path))).toEqual([]);
  });

  test("keep a closing part drawn until its motion ends", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/docs/quickstart/");
    await ready(page);
    const half = await page.evaluate(async () => {
      const details = [...document.querySelectorAll<HTMLDetailsElement>(".sidebar-content details")].find((item) => item.querySelector("summary")?.textContent?.includes("Tutorials"))!;
      const body = details.querySelector<HTMLElement>(":scope > ul")!;
      const full = body.getBoundingClientRect().height;
      details.querySelector("summary")!.click();
      for (let frame = 0; frame < 60 && !body.getAnimations().length; frame++) await new Promise(requestAnimationFrame);
      const animations = body.getAnimations();
      for (const animation of animations) {
        animation.pause();
        animation.currentTime = Number(animation.effect?.getComputedTiming().duration) / 2;
      }
      const result = { full, half: body.getBoundingClientRect().height, open: details.open, closing: details.hasAttribute("data-closing"), shown: body.checkVisibility() };
      for (const animation of animations) animation.play();
      return result;
    });
    expect(half.open).toBe(false);
    expect(half.closing).toBe(true);
    expect(half.shown).toBe(true);
    expect(half.half).toBeGreaterThan(0);
    expect(half.half).toBeLessThan(half.full);
    await expect(page.locator(".sidebar-content details[data-closing]")).toHaveCount(0);

    await picker(page, "theme").click();
    await expect(list(page, "theme")).toBeVisible();
    await settled(page);
    const leaving = await page.evaluate(async () => {
      const element = document.querySelector<HTMLElement>("header.header oh-picker[data-kind='theme'] .oh-picker-list")!;
      element.hidePopover();
      for (let frame = 0; frame < 60 && !element.getAnimations().length; frame++) await new Promise(requestAnimationFrame);
      const animations = element.getAnimations();
      for (const animation of animations) {
        animation.pause();
        animation.currentTime = Number(animation.effect?.getComputedTiming().duration) / 2;
      }
      const result = { open: element.matches(":popover-open"), closing: element.hasAttribute("data-closing"), shown: element.checkVisibility(), opacity: Number(getComputedStyle(element).opacity) };
      for (const animation of animations) animation.play();
      return result;
    });
    expect(leaving).toEqual({ open: false, closing: true, shown: true, opacity: expect.any(Number) });
    expect(leaving.opacity).toBeGreaterThan(0);
    expect(leaving.opacity).toBeLessThan(1);
    await expect(list(page, "theme")).toBeHidden();
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
      const pickers = page.locator(`${scope} oh-picker`);
      for (const one of await pickers.all()) {
        if (!(await one.isVisible())) continue;
        const marks = await one.evaluate((element) => ({
          inButton: [...element.querySelectorAll(".oh-picker-button :is(svg, img)")].map((mark) => `${mark.localName} ${mark.getAttribute("aria-hidden")}`),
          inList: element.querySelectorAll(".oh-picker-list :is(svg, img)").length,
        }));
        expect(marks.inButton, `${width} ${scope}`).toEqual(["svg true"]);
        expect(marks.inList, `${width} ${scope}`).toBe(0);
      }
      expect(await pickers.count()).toBeGreaterThan(0);
    }
  });

  test("answer Enter, Space, the arrow keys, Home, End, a letter, Escape and Tab", async ({ page }) => {
    await page.goto(SPEC);
    await ready(page);
    const theme = picker(page, "theme");
    const menu = page.getByRole("menu", { name: "Theme" });
    const item = (name: string) => menu.getByRole("menuitemradio", { name });
    await theme.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toBeVisible();
    await expect(theme).toHaveAttribute("aria-expanded", "true");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(item("Light")).toBeFocused();
    await page.keyboard.press("ArrowDown");
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
    await expect(menu).toBeHidden();
    await expect(theme).toBeFocused();
    await expect(theme).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("ArrowDown");
    await expect(item("Auto")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press(" ");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(menu).toBeHidden();
    await expect(theme).toBeFocused();
    await expect(theme).toHaveAccessibleName("Theme Light");
    await page.keyboard.press(" ");
    await expect(item("Light")).toBeFocused();
    await expect(item("Light")).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("Tab");
    await expect(menu).toBeHidden();
    await expect(theme).not.toBeFocused();

    await page.goto("/docs/");
    await ready(page);
    await picker(page, "version").focus();
    await page.keyboard.press("ArrowUp");
    await expect(page.getByRole("menu", { name: "Specification version" }).getByRole("menuitem", { name: "v0.1" })).toBeFocused();
    await page.keyboard.press(" ");
    await expect(page).toHaveURL(/\/spec\/v0\.1\/$/);
  });

  test("close on a click outside, and one opening closes another", async ({ page }) => {
    await page.goto(SPEC);
    await ready(page);
    await picker(page, "version").click();
    await expect(list(page, "version")).toBeVisible();
    await picker(page, "theme").click();
    await expect(list(page, "version")).toBeHidden();
    await expect(list(page, "theme")).toBeVisible();
    await page.mouse.click(700, 500);
    await expect(list(page, "theme")).toBeHidden();
    await expect(picker(page, "theme")).toHaveAttribute("aria-expanded", "false");
  });

  test("open below their button, or above it at the foot of the phone menu", async ({ page }) => {
    await page.goto(SPEC);
    await ready(page);
    const placed = async (scope: string, kind: "version" | "theme") => {
      await picker(page, kind, scope).click();
      await expect(list(page, kind, scope)).toBeVisible();
      await settled(page);
      return page.locator(`${scope} oh-picker[data-kind='${kind}']`).evaluate((element) => {
        const button = element.querySelector(".oh-picker-button")!.getBoundingClientRect();
        const box = element.querySelector(".oh-picker-list")!.getBoundingClientRect();
        return { gapBelow: box.top - button.bottom, gapAbove: button.top - box.bottom, right: box.right - button.right };
      });
    };
    const header = await placed("header.header", "theme");
    expect(Math.abs(header.gapBelow - 4)).toBeLessThan(1);
    expect(Math.abs(header.right)).toBeLessThan(1);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".sl-menu-button").click();
    await page.locator(".mobile-preferences").scrollIntoViewIfNeeded();
    const foot = await placed(".mobile-preferences", "theme");
    expect(Math.abs(foot.gapAbove - 4)).toBeLessThan(1);
    expect(Math.abs(foot.right)).toBeLessThan(1);
  });

  test("place their list with Floating UI in a browser without anchor positioning", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "one browser stands in for one without anchoring");
    await page.addInitScript(() => {
      const supports = CSS.supports.bind(CSS);
      CSS.supports = ((...args: [string, string?]) => (/anchor|position-area/.test(args.join(" ")) ? false : supports(...(args as [string])))) as typeof CSS.supports;
      document.addEventListener("DOMContentLoaded", () => {
        const style = document.createElement("style");
        style.textContent = ".oh-picker-list.oh-picker-list { position-anchor: auto !important; position-area: none !important; position-try-fallbacks: none !important; margin: 0 !important; }";
        document.head.append(style);
      });
    });
    const fetched: string[] = [];
    page.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    for (const [width, path, kind, start] of [
      [1440, SPEC, "theme", false],
      [900, "/drivers/", "section", true],
    ] as const) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await ready(page);
      await picker(page, kind).click();
      await expect(list(page, kind)).toBeVisible();
      await settled(page);
      const box = await page.locator(`header.header oh-picker[data-kind='${kind}']`).evaluate((element, start) => {
        const button = element.querySelector(".oh-picker-button")!.getBoundingClientRect();
        const list = element.querySelector<HTMLElement>(".oh-picker-list")!;
        const rect = list.getBoundingClientRect();
        return { gap: rect.top - button.bottom, edge: start ? rect.left - button.left : rect.right - button.right, left: list.style.left };
      }, start);
      expect(box.left, kind).not.toBe("");
      expect(Math.abs(box.gap - 4), kind).toBeLessThan(1);
      expect(Math.abs(box.edge), kind).toBeLessThan(1);
    }
    expect(new Set(fetched.filter((path) => path.includes("floating-ui"))).size, "one Floating UI file, loaded for the lists").toBe(1);
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
    const outlined = ["site-search button[data-open-modal]", "site-search button > kbd", ".copy-button", ".pagination-links a"];
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
    await page.locator("site-search button[data-open-modal]").click();
    await controls(page, ["#starlight__search .pagefind-ui__search-input"], 1.5);
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
