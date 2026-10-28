import { expect, test, type Page } from "@playwright/test";
import { PRODUCT_NAME } from "../../src/config/brand";
import { AWAY, DIM, DROP, LOW, PARTS, SWAP, TOTAL, stepSpan } from "../../src/lib/story/wordmark";

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

/** A moment in each letter's step after the letter has full strength. */
const settled = (index: number) => stepSpan(index)[0] + (index === 0 ? DIM : SWAP) + 4;

/** The left and right of the home page's column, inside the hero's padding. */
const column = (page: Page) =>
  page.locator(".hero").evaluate((el) => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return { left: box.left + parseFloat(style.paddingLeft), right: box.right - parseFloat(style.paddingRight) };
  });

/** Where each part of the first screen sits and how strongly it shows, counting every ancestor's opacity. */
const firstScreen = (page: Page) =>
  page.evaluate(() =>
    [".hero-mark", ".hero-spell", ".hero-pitch", ".hero-go", ".hero-demo", ".story-meta", ".story-heads", ".story-skip", ".smooth"].map((query) => {
      const el = document.querySelector<HTMLElement>(query)!;
      const box = el.getBoundingClientRect();
      let strength = 1;
      for (let node: HTMLElement | null = el; node; node = node.parentElement) strength *= Number(getComputedStyle(node).opacity);
      return `${query} ${box.x.toFixed(1)} ${box.y.toFixed(1)} ${box.width.toFixed(1)} ${strength.toFixed(3)} ${getComputedStyle(el).visibility}`;
    }),
  );

/** The word's baseline on the page, from the face's own metrics, as the runtime measures it. */
const inkOf = (page: Page) =>
  page.locator(".hero-letters").evaluate((el) => {
    const style = getComputedStyle(el);
    const context = document.createElement("canvas").getContext("2d")!;
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const metrics = context.measureText(el.textContent!);
    const box = el.getBoundingClientRect();
    return { baseline: box.top + (box.height - metrics.fontBoundingBoxAscent - metrics.fontBoundingBoxDescent) / 2 + metrics.fontBoundingBoxAscent };
  });

/** Whether a person pointing at the middle of an element reaches the element, which a clip or a cover would stop. */
const reached = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => {
    const box = el.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + Math.min(24, box.width / 2), box.top + box.height / 2);
    return Boolean(hit && el.contains(hit));
  });

const settle = (page: Page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

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

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 390, height: 844 }]) {
    test(`shows the demo's opening under the hero on the first screen, and its switch works there, at ${viewport.width} by ${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(page.locator("[data-story]")).toHaveAttribute("data-lifted", /^(band|title)$/);
      const go = (await page.getByRole("link", { name: "Get started" }).boundingBox())!;
      const meta = (await page.locator(".story-meta").boundingBox())!;
      const demo = (await page.locator(".hero-demo").boundingBox())!;
      expect(meta.y).toBeGreaterThan(go.y + go.height);
      expect(meta.y + meta.height).toBeLessThanOrEqual(viewport.height);
      await expect(page.locator(".story-count > [data-on]")).toHaveText(/^\d+ steps$/);
      await expect(page.getByRole("link", { name: "Skip the demo" })).toBeInViewport();
      await expect(page.locator(".hero-demo .seq-head").first()).toBeInViewport();
      expect(await reached(page, ".story-skip")).toBe(true);
      expect(await reached(page, ".story-scene .seq-head")).toBe(false);
      if (viewport.width >= 1200) {
        expect(demo.x).toBeGreaterThan(go.x + go.width);
        expect(demo.y + demo.height).toBeLessThan(meta.y);
        await expect(page.locator(".story-title")).toBeInViewport();
        expect(await reached(page, ".story-heads")).toBe(true);
      } else {
        expect(demo.y).toBeGreaterThan(meta.y + meta.height);
        expect(await reached(page, ".story-heads")).toBe(false);
      }
      const toggle = page.getByRole("switch", { name: "Smooth scrolling" });
      await expect(toggle).toBeInViewport();
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "false");
      await toggle.press("Space");
      await expect(toggle).toHaveAttribute("aria-checked", "true");
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
    });
  }

  test("drops the opening away from the first pixel of scroll and brings the first screen back exactly at the top", async ({ page }) => {
    await page.goto("/");
    await settle(page);
    const first = await firstScreen(page);
    const top = (line: string) => Number(line.split(" ")[2]);
    const strength = (line: string) => Number(line.split(" ")[4]);
    await page.evaluate(() => window.scrollTo({ top: 2, behavior: "instant" }));
    await settle(page);
    const nudged = await firstScreen(page);
    expect(top(nudged[4])).toBeGreaterThan(top(first[4]));
    expect(top(nudged[5])).toBeGreaterThan(top(first[5]));
    await heroTime(page, DROP / 2);
    const half = await firstScreen(page);
    for (const index of [4, 5]) {
      expect(strength(half[index])).toBeLessThan(0.6);
      expect(strength(half[index])).toBeGreaterThan(0.2);
    }
    await heroTime(page, DROP);
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-lifted");
    expect(await opacity(page, ".hero-demo")).toBe(0);
    expect(await page.locator(".story-meta").evaluate((el) => el.getBoundingClientRect().top)).toBeGreaterThan(await page.evaluate(() => window.innerHeight));
    await heroTime(page, AWAY + 30);
    await heroTime(page, 0);
    await settle(page);
    expect(await firstScreen(page)).toEqual(first);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });

  test("puts the story's stage back in its place when the page measures again after the drop", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-story]")).toHaveAttribute("data-lifted", /^(band|title)$/);
    await page.evaluate(() => {
      const hero = document.querySelector<HTMLElement>("[data-sequence]")!;
      let y = 0;
      for (let node: HTMLElement | null = hero; node; node = node.offsetParent as HTMLElement | null) y += node.offsetTop;
      window.dispatchEvent(new Event("resize"));
      window.scrollTo({ top: y + hero.querySelector<HTMLElement>(".hero-runway")!.offsetHeight + 300, behavior: "instant" });
    });
    await settle(page);
    await settle(page);
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-lifted");
    expect(await page.locator(".story-stage").evaluate((el) => [el.style.transform, el.style.opacity, el.style.clipPath])).toEqual(["", "", ""]);
    await expect(page.locator(".story-stage")).toBeInViewport();
  });

  test("lands at the top with the whole hero at full strength when the wheel scrolls up past the top", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "wheel timing is checked in one engine");
    await page.goto("/");
    await page.waitForTimeout(2500);
    await settle(page);
    const first = await firstScreen(page);
    await page.mouse.move(700, 450);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(900);
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(250);
    for (let index = 0; index < 8; index++) {
      await page.mouse.wheel(0, -90);
      await page.waitForTimeout(25);
    }
    await page.waitForTimeout(1500);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await settle(page);
    expect(await opacity(page, ".hero-pitch")).toBeGreaterThan(0.99);
    expect(await opacity(page, ".hero-spell")).toBeGreaterThan(0.99);
    expect(await firstScreen(page)).toEqual(first);
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
    expect(await opacity(page, ".hero-demo")).toBe(0);
    expect(await brief(page)).toEqual([]);
  });

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }]) {
    test(`lights one letter at a time with its brief right under the letter, and keeps the whole word in the column, at ${viewport.width} by ${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/");
      const edge = await column(page);
      const resting = await letters(page);
      for (const [index, part] of PARTS.entries()) {
        await heroTime(page, settled(index));
        const shown = await letters(page);
        const at = PRODUCT_NAME.lastIndexOf(part.letter);
        const where = `${viewport.width} ${part.letter}`;
        for (const [position, item] of shown.entries()) expect(item.opacity, `${where} step, ${item.letter}`).toBeCloseTo(position === at ? 1 : LOW, 2);
        for (const [position, item] of shown.entries()) expect(Math.abs(item.left - resting[position].left), `${where} ${item.letter}`).toBeLessThan(1);
        expect(shown[0].left, where).toBeGreaterThanOrEqual(edge.left - 8);
        expect(shown[shown.length - 1].right, where).toBeLessThanOrEqual(edge.right + 1);
        expect(await brief(page)).toEqual([`${part.label} ${part.brief}`]);
        const box = (await page.locator(".hero-brief[data-on]").boundingBox())!;
        const { baseline } = await inkOf(page);
        expect(box.y, where).toBeGreaterThan(baseline + 4);
        expect(box.y - baseline, where).toBeLessThan(48);
        expect(box.x, where).toBeLessThanOrEqual(shown[at].left + 1);
        expect(box.x + box.width, where).toBeGreaterThan(shown[at].right);
        expect(box.x + box.width, where).toBeLessThanOrEqual(edge.right + 1);
        expect(box.y + box.height, where).toBeLessThanOrEqual(viewport.height);
      }
    });
  }

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
            const box = el.getBoundingClientRect();
            const stroke = box.width <= 2.5 || box.height <= 2.5 || (box.width <= 8 && box.height <= 8);
            for (const side of ["top", "right", "bottom", "left"]) if (parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0) out.push(`${el.className} has a border`);
            if (style.boxShadow !== "none") out.push(`${el.className} has a shadow`);
            if (!stroke && style.backgroundColor !== "rgba(0, 0, 0, 0)" && style.backgroundColor !== bg) out.push(`${el.className} has a background`);
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
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-lifted");
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
