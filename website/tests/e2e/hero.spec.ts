import { expect, test, type Page } from "@playwright/test";
import { PITCH, PRODUCT_NAME } from "../../src/config/brand";
import { SPELLED } from "../../src/lib/story/name";

/** Each label of the hero with the ink box of its letter, in px from the left of the page. */
const labels = (page: Page) =>
  page.evaluate(() => {
    const mark = document.querySelector(".hero-mark")!;
    const text = mark.firstChild!;
    const style = getComputedStyle(mark);
    const context = document.createElement("canvas").getContext("2d")!;
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return [...document.querySelectorAll<HTMLElement>(".hero-spell [data-at]")].map((label) => {
      const at = Number(label.dataset.at);
      const range = document.createRange();
      range.setStart(text, at);
      range.setEnd(text, at + 1);
      const glyph = range.getBoundingClientRect();
      const ink = context.measureText(text.textContent!.charAt(at));
      const box = label.getBoundingClientRect();
      return {
        letter: text.textContent!.charAt(at),
        word: label.textContent!,
        left: box.left,
        right: box.right,
        top: box.top,
        center: box.left + box.width / 2,
        inkLeft: glyph.left - ink.actualBoundingBoxLeft,
        inkRight: glyph.left + ink.actualBoundingBoxRight,
        glyphTop: glyph.top,
        size: parseFloat(getComputedStyle(label).fontSize),
      };
    });
  });

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

  test("shows no diagram and none of the old full-screen letter sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".hero svg, .hero .seq, .hero-demo, .hero-letters, .hero-briefs, .hero-runway, .hero-list, [data-sequence]")).toHaveCount(0);
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
