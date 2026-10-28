import { expect, test, type Page } from "@playwright/test";
import { PRODUCT_NAME } from "../../src/config/brand";
import { AWAY, DIM, LOW, PARTS, SLIDE, TOTAL, stepSpan } from "../../src/lib/story/wordmark";

async function heroTime(page: Page, t: number): Promise<void> {
  await page.evaluate((time) => {
    const hero = document.querySelector<HTMLElement>("[data-sequence]")!;
    const runway = hero.querySelector<HTMLElement>(".hero-runway")!;
    let y = 0;
    for (let el: HTMLElement | null = hero; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    const pin = document.querySelector<HTMLElement>(".site-header")!.offsetHeight;
    window.scrollTo({ top: y - pin + (time * runway.offsetHeight) / Number(hero.dataset.total), behavior: "instant" });
  }, t);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"), undefined, { polling: 25 });
}

const letters = (page: Page) =>
  page.locator(".hero-letters > span").evaluateAll((items) =>
    items.map((el) => ({ letter: el.textContent!, opacity: Number(getComputedStyle(el).opacity), left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right, bottom: el.getBoundingClientRect().bottom })),
  );

const opacity = (page: Page, selector: string) => page.locator(selector).first().evaluate((el) => Number(getComputedStyle(el).opacity));

const brief = (page: Page) =>
  page.locator(".hero-brief").evaluateAll((items) => items.filter((el) => Number(getComputedStyle(el).opacity) > 0.9).map((el) => el.textContent!.replace(/\s+/g, " ").trim()));

/** A moment in each letter's step after the word has stopped. */
const settled = (index: number) => stepSpan(index)[0] + (index === 0 ? DIM : SLIDE) + 4;

test.describe("the wordmark sequence", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("rests as the hero, and the letters it fades sit exactly on the heading's glyphs", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-sequence]")).toHaveAttribute("data-camera", "");
    await expect(page.locator(".hero-spell")).toHaveAttribute("data-placed", "");
    expect(await opacity(page, ".hero-mark")).toBeGreaterThan(0.99);
    expect(await opacity(page, ".hero-letters")).toBe(0);
    expect(await opacity(page, ".hero-pitch")).toBeGreaterThan(0.99);
    await expect(page.getByRole("link", { name: "Get started" })).toBeVisible();
    const offsets = await page.evaluate(() => {
      const mark = document.querySelector(".hero-mark")!;
      const text = mark.firstChild!;
      const range = document.createRange();
      return [...document.querySelectorAll<HTMLElement>(".hero-letters > span")].map((span, at) => {
        range.setStart(text, at);
        range.setEnd(text, at + 1);
        return Math.abs(span.getBoundingClientRect().left - range.getBoundingClientRect().left) + Math.abs(span.getBoundingClientRect().top - range.getBoundingClientRect().top);
      });
    });
    expect(Math.max(...offsets)).toBeLessThan(0.5);
  });

  test("brings the wordmark down under the header while the description and Get started leave", async ({ page }) => {
    await page.goto("/");
    const rest = await page.locator(".hero-letters").evaluate((el) => el.getBoundingClientRect().top);
    await heroTime(page, AWAY);
    const header = await page.locator(".site-header").evaluate((el) => el.getBoundingClientRect().bottom);
    expect(Math.abs((await page.locator(".hero-stage").boundingBox())!.y - header)).toBeLessThan(1);
    expect(await page.locator(".hero-letters").evaluate((el) => el.getBoundingClientRect().top)).toBeGreaterThan(rest + 40);
    expect(await opacity(page, ".hero-pitch")).toBe(0);
    expect(await opacity(page, ".hero-spell")).toBe(0);
    expect(await opacity(page, ".hero-mark")).toBe(0);
    expect(await opacity(page, ".hero-letters")).toBeGreaterThan(0.99);
    await expect(page.getByRole("link", { name: "Get started" })).toBeHidden();
    expect(await brief(page)).toEqual([]);
  });

  test("lights one letter at a time with its brief, and lands each letter where H stood", async ({ page }) => {
    await page.goto("/");
    let anchor = 0;
    for (const [index, part] of PARTS.entries()) {
      await heroTime(page, settled(index));
      const shown = await letters(page);
      const at = PRODUCT_NAME.lastIndexOf(part.letter);
      for (const [position, item] of shown.entries()) expect(item.opacity, `${part.letter} step, ${item.letter}`).toBeCloseTo(position === at ? 1 : LOW, 2);
      if (index === 0) anchor = shown[at].left;
      expect(Math.abs(shown[at].left - anchor), part.letter).toBeLessThan(1);
      expect(await brief(page)).toEqual([`${part.label} ${part.brief}`]);
      const below = await page.locator(".hero-brief[data-on]").evaluate((el) => el.getBoundingClientRect().top);
      expect(below).toBeGreaterThan(shown[at].bottom);
    }
  });

  test("plays backwards the same way it plays forwards", async ({ page }) => {
    await page.goto("/");
    const forward: string[] = [];
    for (const index of PARTS.keys()) {
      await heroTime(page, settled(index));
      forward.push(JSON.stringify({ letters: await letters(page), brief: await brief(page) }));
    }
    await heroTime(page, TOTAL);
    const backward: string[] = [];
    for (const index of [...PARTS.keys()].reverse()) {
      await heroTime(page, settled(index));
      backward.unshift(JSON.stringify({ letters: await letters(page), brief: await brief(page) }));
    }
    expect(backward).toEqual(forward);
    await heroTime(page, 0);
    expect(await opacity(page, ".hero-mark")).toBeGreaterThan(0.99);
    await expect(page.getByRole("link", { name: "Get started" })).toBeVisible();
  });

  test("keeps the current letter on a phone's screen with the brief under the word", async ({ page }) => {
    for (const viewport of [{ width: 390, height: 844 }, { width: 390, height: 664 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(page.locator("[data-sequence]")).toHaveAttribute("data-camera", "");
      for (const [index, part] of PARTS.entries()) {
        await heroTime(page, settled(index));
        const shown = await letters(page);
        const current = shown[PRODUCT_NAME.lastIndexOf(part.letter)];
        const where = `${viewport.width}x${viewport.height} ${part.letter}`;
        expect(current.left, where).toBeGreaterThanOrEqual(0);
        expect(current.right, where).toBeLessThanOrEqual(viewport.width);
        const box = (await page.locator(".hero-brief[data-on]").boundingBox())!;
        expect(box.y, where).toBeGreaterThan(Math.max(...shown.map((item) => item.bottom)));
        expect(box.x, where).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, where).toBeLessThanOrEqual(viewport.width);
        expect(box.y + box.height, where).toBeLessThanOrEqual(viewport.height);
        expect(await page.evaluate(() => document.documentElement.scrollWidth), where).toBeLessThanOrEqual(viewport.width);
      }
    }
  });

  test("releases the stage after L and the print babysitter story follows", async ({ page }) => {
    await page.goto("/");
    await heroTime(page, TOTAL + 60);
    const header = await page.locator(".site-header").evaluate((el) => el.getBoundingClientRect().bottom);
    expect((await page.locator(".hero-stage").boundingBox())!.y).toBeLessThan(header - 100);
    await expect(page.locator(".story-stage")).toBeInViewport();
  });

  test("changes no layout while it plays", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    await heroTime(page, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    for (let t = 0; t <= TOTAL; t += 4) await heroTime(page, t);
    for (let t = TOTAL; t >= 0; t -= 6) await heroTime(page, t);
    expect(await layouts()).toBe(before);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`draws no box around the word or the briefs, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/");
      for (const index of PARTS.keys()) {
        await heroTime(page, settled(index));
        const boxes = await page.evaluate(() => {
          const out: string[] = [];
          const bg = getComputedStyle(document.body).backgroundColor;
          for (const el of document.querySelectorAll<HTMLElement>(".hero-stage *")) {
            if (el.closest(".hero-go") || !el.getClientRects().length) continue;
            const style = getComputedStyle(el);
            for (const side of ["top", "right", "bottom", "left"]) if (parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0) out.push(`${el.className} has a border`);
            if (style.boxShadow !== "none") out.push(`${el.className} has a shadow`);
            if (style.backgroundColor !== "rgba(0, 0, 0, 0)" && style.backgroundColor !== bg) out.push(`${el.className} has a background`);
          }
          return out;
        });
        expect(boxes).toEqual([]);
      }
    });
  }

  test("with reduced motion it is the hero, still, with the briefs as a list under it", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("[data-sequence]")).not.toHaveAttribute("data-camera", "");
    await expect(page.locator(".hero-letters")).toBeHidden();
    await expect(page.locator(".hero-runway")).toBeHidden();
    await expect(page.locator(".hero-briefs")).toBeHidden();
    await expect(page.locator(".hero-mark")).toBeVisible();
    const items = page.locator(".hero-list > li");
    await expect(items).toHaveCount(PARTS.length);
    for (const [index, part] of PARTS.entries()) {
      await expect(items.nth(index)).toBeVisible();
      await expect(items.nth(index)).toContainText(part.letter);
      await expect(items.nth(index)).toContainText(part.label);
      await expect(items.nth(index)).toContainText(part.brief);
    }
    expect(await page.locator(".hero-list").evaluate((el) => el.getBoundingClientRect().top)).toBeGreaterThan(await page.locator(".hero-mark").evaluate((el) => el.getBoundingClientRect().bottom));
  });

  test("reads the briefs to a screen reader while the stage plays", async ({ page }) => {
    await page.goto("/");
    const list = page.locator(".hero-list");
    for (const part of PARTS) await expect(list).toContainText(part.brief);
    await expect(page.locator(".hero-briefs")).toHaveAttribute("aria-hidden", "true");
    await expect(page.locator(".hero-letters")).toHaveAttribute("aria-hidden", "true");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(PRODUCT_NAME);
  });
});
