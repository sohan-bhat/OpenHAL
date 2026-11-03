import { expect, test, type Page } from "@playwright/test";
import { PITCH, PRODUCT_NAME } from "../../src/config/brand";
import { installChannels } from "../../src/lib/install";
import { SPELLED } from "../../src/lib/story/name";

const CHANNELS = installChannels();

/**
 * Makes the page report a system the way a browser on that system does, before any script runs.
 * Playwright's Desktop Chrome and Desktop Firefox send a Windows user agent wherever they run, so
 * every install box test names its system.
 */
const onSystem = (page: Page, system: { platform: string; data: string }) =>
  page.addInitScript((wanted) => {
    Object.defineProperty(Navigator.prototype, "platform", { configurable: true, get: () => wanted.platform });
    Object.defineProperty(Navigator.prototype, "userAgentData", { configurable: true, get: () => ({ platform: wanted.data, brands: [], mobile: false }) });
  }, system);
const MAC = { platform: "MacIntel", data: "macOS" };
const WINDOWS = { platform: "Win32", data: "Windows" };

/** The install box's chosen tab, the command its line shows and the prompt before the command. */
const shown = (page: Page) =>
  page.locator(".hero-install").evaluate((box) => {
    const panel = [...box.querySelectorAll<HTMLElement>("[role=tabpanel]")].find((item) => item.checkVisibility());
    return {
      tab: box.querySelector("[role=tab][aria-selected=true]")?.textContent ?? "",
      command: panel?.querySelector("code")?.textContent ?? "",
      prompt: panel?.querySelector(".install-prompt")?.textContent ?? "",
      panels: [...box.querySelectorAll("[role=tabpanel]")].filter((item) => (item as HTMLElement).checkVisibility()).length,
    };
  });

/** Waits until the install box's island has hydrated and its first press can be replayed. */
const hydrated = (page: Page) => expect(page.locator(".hero-install astro-island")).not.toHaveAttribute("ssr", { timeout: 15_000 });

/** Each label of the hero with the ink box of its letter in the wordmark, in px from the left of the page. */
const labels = (page: Page) =>
  page.evaluate((name) => {
    const word = document.querySelector(".hero-mark svg")!;
    return [...document.querySelectorAll<HTMLElement>(".hero-spell [data-at]")].map((label) => {
      const at = Number(label.dataset.at);
      const glyph = word.querySelector(`[data-at="${at}"]`)!.getBoundingClientRect();
      const box = label.getBoundingClientRect();
      return {
        letter: name.charAt(at),
        word: label.textContent!,
        left: box.left,
        right: box.right,
        top: box.top,
        center: box.left + box.width / 2,
        inkLeft: glyph.left,
        inkRight: glyph.right,
        glyphTop: glyph.top,
        size: parseFloat(getComputedStyle(label).fontSize),
      };
    });
  }, PRODUCT_NAME);

/** The contrast ratio of two CSS colors, as WCAG computes it. */
const contrast = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const channels = (color: string) => color.match(/[\d.]+/g)!.slice(0, 3).map(Number);
    const luminance = (color: string) => {
      const [r, g, b] = channels(color).map((value) => {
        const c = value / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const fore = luminance(getComputedStyle(el).color);
    const back = luminance(getComputedStyle(document.body).backgroundColor);
    return (Math.max(fore, back) + 0.05) / (Math.min(fore, back) + 0.05);
  });

test.describe("the hero", () => {
  test("names the product with no sentence under the name and offers two ways in", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(PRODUCT_NAME);
    await expect(page.locator(".hero-pitch, .hero-lede")).toHaveCount(0);
    await expect(page.locator(".hero")).not.toContainText(PITCH);
    await expect(page.locator(".hero")).not.toContainText("checks each one against limits");
    const links = page.locator(".hero a");
    await expect(links).toHaveText(["Get started", "Read the specification"]);
    await expect(page.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/docs/quickstart/");
    await expect(page.locator(".hero").getByRole("link", { name: "Read the specification" })).toHaveAttribute("href", /^\/spec\/v\d+\.\d+\/$/);
  });

  test("draws the built wordmark, named OpenHAL for screen readers and search", async ({ page, request }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: PRODUCT_NAME })).toBeVisible();
    const file = await (await request.get("/brand/wordmark-light.svg")).text();
    const built = [...file.matchAll(/<path data-at="(\d+)" d="([^"]+)"/g)].map((match) => match[2]);
    const drawn = await page.locator(".hero-mark svg path[data-at]").evaluateAll((paths) => paths.map((path) => path.getAttribute("d")));
    expect(built).toHaveLength(PRODUCT_NAME.length);
    expect(drawn).toEqual(built);
    await expect(page.locator(".hero-mark svg")).toHaveAttribute("aria-hidden", "true");
  });

  test("shows no diagram and none of the old full-screen letter sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".hero svg:not(.hero-word), .hero .seq, .hero-demo, .hero-letters, .hero-briefs, .hero-runway, .hero-list, [data-sequence]")).toHaveCount(0);
    for (const brief of ["The hardware is any device", "A hardware abstraction layer gives every device", "The layer is the hub"]) {
      await expect(page.locator("main")).not.toContainText(brief);
    }
  });

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    test(`fits the first screen with both actions in view at ${viewport.width} by ${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(page.getByRole("link", { name: "Get started" })).toBeInViewport({ ratio: 1 });
      await expect(page.locator(".hero").getByRole("link", { name: "Read the specification" })).toBeInViewport({ ratio: 1 });
      const bottom = await page.locator(".hero").evaluate((el) => el.getBoundingClientRect().bottom);
      expect(bottom).toBeLessThanOrEqual(viewport.height);
    });
  }

  for (const width of [1440, 1280, 1024, 768, 430, 390, 375, 360]) {
    test(`spells HAL out in one row, each label under its own letter, at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator(".hero-spell")).toHaveAttribute("data-placed", "");
      await expect(page.locator(".hero-spell")).toHaveAttribute("aria-hidden", "true");
      const found = await labels(page);
      expect(found.map((item) => `${item.letter} ${item.word}`)).toEqual(SPELLED.map((part) => `${part.letter} ${part.label}`));
      for (const [index, item] of found.entries()) {
        const where = `${width} ${item.word}`;
        expect(item.center, where).toBeGreaterThanOrEqual(item.inkLeft - 1);
        expect(item.center, where).toBeLessThanOrEqual(item.inkRight + 1);
        if (width >= 768) expect(Math.abs(item.center - (item.inkLeft + item.inkRight) / 2), where).toBeLessThan(1.5);
        expect(item.size, where).toBeGreaterThanOrEqual(width >= 1024 ? 14 : 12);
        expect(item.top, where).toBeGreaterThan(item.glyphTop);
        expect(Math.abs(item.top - found[0].top), `${where} shares the row`).toBeLessThan(1);
        expect(item.left, where).toBeGreaterThanOrEqual(0);
        expect(item.right, where).toBeLessThanOrEqual(width);
        if (index > 0) expect(item.left - found[index - 1].right, `${where} clears its neighbor`).toBeGreaterThanOrEqual(6);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }

  for (const scheme of ["light", "dark"] as const) {
    test(`keeps the labels muted and above WCAG AA contrast in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/");
      const muted = await page.evaluate(() => {
        const probe = document.createElement("span");
        probe.style.color = "var(--text-2)";
        document.body.append(probe);
        const color = getComputedStyle(probe).color;
        probe.remove();
        return color;
      });
      await expect(page.locator(".hero-spell span").first()).toHaveCSS("color", muted);
      expect(await contrast(page, ".hero-spell span")).toBeGreaterThanOrEqual(4.5);
    });
  }
});

test.describe("the install box", () => {
  test.beforeEach(async ({ page }) => {
    await onSystem(page, MAC);
  });

  test("sits under the wordmark and above the two actions, with the next step under the line", async ({ page }) => {
    await page.goto("/");
    const top = (selector: string) => page.locator(selector).first().evaluate((el) => el.getBoundingClientRect().top);
    const order = [await top(".hero-spell"), await top(".hero-install"), await top(".hero-next"), await top(".hero-actions")];
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    await expect(page.locator(".hero-next")).toHaveText("Then set up your first device with openhal init, and start OpenHAL with openhal start.");
    await expect(page.getByRole("tablist", { name: `Install ${PRODUCT_NAME}` })).toBeVisible();
  });

  test("offers only the channels that install today, in their order", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("tab")).toHaveText(CHANNELS.map((channel) => channel.label));
    expect(CHANNELS.map((channel) => channel.label).slice(0, 2)).toEqual(["macOS and Linux", "Windows"]);
  });

  test("starts on macOS and Linux off Windows, with the curl command and a $ prompt", async ({ page }) => {
    await page.goto("/");
    expect(await shown(page)).toEqual({ tab: "macOS and Linux", command: CHANNELS[0].command, prompt: "$", panels: 1 });
    expect(CHANNELS[0].command).toMatch(/^curl -LsSf https:\/\/\S+\/install\.sh \| sh$/);
  });

  test("starts on Windows on Windows, before the island loads and after", async ({ page }) => {
    await onSystem(page, WINDOWS);
    await page.goto("/");
    const windows = CHANNELS.find((channel) => channel.platform === "windows")!;
    expect(await shown(page)).toEqual({ tab: "Windows", command: windows.command, prompt: "PS>", panels: 1 });
    await page.getByRole("tab", { name: "Windows" }).hover();
    await hydrated(page);
    expect(await shown(page)).toEqual({ tab: "Windows", command: windows.command, prompt: "PS>", panels: 1 });
    await page.getByRole("tab", { name: "macOS and Linux" }).click();
    expect((await shown(page)).command).toBe(CHANNELS[0].command);
  });

  test("shows each tab's command, from the first click before the island loads", async ({ page }) => {
    await page.goto("/");
    for (const channel of [...CHANNELS.slice(1), CHANNELS[0]]) {
      await page.getByRole("tab", { name: channel.label }).click();
      await expect(page.getByRole("tab", { name: channel.label })).toHaveAttribute("aria-selected", "true");
      expect(await shown(page)).toEqual({ tab: channel.label, command: channel.command, prompt: channel.prompt, panels: 1 });
    }
  });

  test("Copy copies exactly the chosen command, before the island loads and after", async ({ page, context, browserName }) => {
    test.skip(browserName !== "chromium", "clipboard permissions are a Chromium feature here");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    const copy = page.locator(".hero-install").getByRole("button", { name: "Copy the install command" });
    await copy.click();
    await expect(copy).toHaveAttribute("data-copied", "");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(CHANNELS[0].command);
    await expect(page.locator(".hero-install astro-island")).toHaveAttribute("ssr", "");
    for (const channel of CHANNELS.slice(1)) {
      await page.getByRole("tab", { name: channel.label }).click();
      await expect(page.getByRole("tab", { name: channel.label })).toHaveAttribute("aria-selected", "true");
      await copy.click();
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(channel.command);
    }
  });

  test("works by keyboard, from Tab to the arrow keys to Copy", async ({ page, context, browserName }) => {
    await page.goto("/");
    await page.locator(".hero-mark").click();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("tab", { name: CHANNELS[0].label })).toBeFocused();
    await hydrated(page);
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: CHANNELS[1].label })).toBeFocused();
    expect((await shown(page)).command).toBe(CHANNELS[1].command);
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: CHANNELS[0].label })).toBeFocused();
    await page.keyboard.press("End");
    expect((await shown(page)).tab).toBe(CHANNELS[CHANNELS.length - 1].label);
    await page.keyboard.press("Home");
    expect((await shown(page)).tab).toBe(CHANNELS[0].label);
    await page.keyboard.press("Tab");
    await expect(page.locator(".hero-install [role=tabpanel][data-state=active]")).toBeFocused();
    await page.keyboard.press("Tab");
    const copy = page.locator(".hero-install").getByRole("button", { name: "Copy the install command" });
    await expect(copy).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("tab", { name: CHANNELS[0].label })).toBeFocused();
    if (browserName !== "chromium") return;
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(copy).toHaveAttribute("data-copied", "");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(CHANNELS[0].command);
  });

  for (const width of [360, 390, 768, 1440]) {
    test(`fits ${width} px with no sideways page scroll, every tab at least 24 px tall and every command inside its line`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/");
      for (const channel of CHANNELS) {
        await page.getByRole("tab", { name: channel.label }).click();
        const fit = await page.locator(".hero-install").evaluate((box) => {
          const panel = box.querySelector<HTMLElement>("[role=tabpanel][data-state=active]")!;
          const code = panel.querySelector("code")!.getBoundingClientRect();
          const list = box.querySelector<HTMLElement>("[role=tablist]")!;
          const frame = box.getBoundingClientRect();
          const copy = box.querySelector(".copy-button")?.getBoundingClientRect();
          return {
            left: frame.left,
            right: frame.right,
            page: document.documentElement.scrollWidth,
            tabs: [...box.querySelectorAll("[role=tab]")].map((tab) => tab.getBoundingClientRect().height),
            listScrolls: list.scrollWidth > list.clientWidth + 1,
            codeRight: code.right,
            lineRight: panel.getBoundingClientRect().right,
            copyClear: copy ? copy.left >= code.right - 0.5 && copy.right <= frame.right : false,
          };
        });
        expect(fit.left, channel.label).toBeGreaterThanOrEqual(0);
        expect(fit.right, channel.label).toBeLessThanOrEqual(width);
        expect(fit.page, channel.label).toBeLessThanOrEqual(width);
        for (const height of fit.tabs) expect(height, channel.label).toBeGreaterThanOrEqual(24);
        expect(fit.listScrolls, `${channel.label} tabs fit their row`).toBe(false);
        expect(fit.codeRight, channel.label).toBeLessThanOrEqual(fit.lineRight + 0.5);
        expect(fit.copyClear, `${channel.label} Copy sits clear of the command`).toBe(true);
      }
    });
  }

  test("wraps a long command between words and after a slash on a phone, never inside a piece", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto("/");
    const pieces = await page.locator(".hero-install [role=tabpanel][data-state=active] .install-piece").evaluateAll((items) => items.map((item) => item.getClientRects().length));
    expect(pieces.length).toBeGreaterThan(3);
    for (const rects of pieces) expect(rects).toBe(1);
  });

  test("shows the curl command first without JavaScript, keeps every other command readable and draws no dead controls", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.locator(".hero-install [role=tablist]")).toBeHidden();
    await expect(page.locator(".hero-install .copy-button")).toHaveCount(0);
    const panels = await page.locator(".hero-install [role=tabpanel]").evaluateAll((items) =>
      items.map((item) => ({ visible: (item as HTMLElement).checkVisibility(), name: item.querySelector(".install-name")?.textContent, command: item.querySelector("code")?.textContent })),
    );
    expect(panels).toEqual(CHANNELS.map((channel) => ({ visible: true, name: channel.label, command: channel.command })));
    await context.close();
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`draws the box on the site's tokens with no shadow, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/");
      const look = await page.locator(".hero-install").evaluate((box) => {
        const probe = document.createElement("span");
        document.body.append(probe);
        const resolve = (value: string) => {
          probe.style.color = value;
          return getComputedStyle(probe).color;
        };
        const tokens = { surface: resolve("var(--surface)"), border: resolve("var(--border)"), bg: resolve("var(--bg)"), highlight: resolve("var(--highlight)"), text: resolve("var(--text)"), text2: resolve("var(--text-2)") };
        probe.remove();
        const style = (selector: string) => getComputedStyle(box.querySelector(selector) ?? box);
        const all = [box, ...box.querySelectorAll("*")].map((el) => getComputedStyle(el));
        return {
          tokens,
          box: { background: getComputedStyle(box).backgroundColor, border: getComputedStyle(box).borderTopColor, width: getComputedStyle(box).borderTopWidth },
          list: style("[role=tablist]").backgroundColor,
          chosen: { background: style("[role=tab][aria-selected=true]").backgroundColor, color: style("[role=tab][aria-selected=true]").color },
          other: style("[role=tab][aria-selected=false]").color,
          prompt: style("[role=tabpanel][data-state=active] .install-prompt").color,
          command: { color: style("[role=tabpanel][data-state=active] code").color, font: style("[role=tabpanel][data-state=active] code").fontFamily },
          shadows: all.filter((item) => item.boxShadow !== "none" && !item.boxShadow.includes("inset")).length,
        };
      });
      expect(look.box).toEqual({ background: look.tokens.surface, border: look.tokens.border, width: "1px" });
      expect(look.list).toBe(look.tokens.bg);
      expect(look.chosen).toEqual({ background: look.tokens.highlight, color: look.tokens.text });
      expect(look.other).toBe(look.tokens.text2);
      expect(look.prompt).toBe(look.tokens.text2);
      expect(look.command.color).toBe(look.tokens.text);
      expect(look.command.font).toContain("IBM Plex Mono");
      expect(look.shadows, "no shadow or glow").toBe(0);
    });
  }
});
