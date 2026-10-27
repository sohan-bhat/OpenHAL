import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const catalog = JSON.parse(readFileSync(fileURLToPath(new URL("../../../drivers/catalog.json", import.meta.url)), "utf8")) as { drivers: Array<{ name: string; tier: number }> };
const devices = catalog.drivers.filter((driver) => driver.tier !== 0).length;

const PAGES = ["/", "/spec/playground/", "/drivers/", "/library/", "/spec/errors/", "/docs/quickstart/", "/inspector/", "/drivers/moonraker/"];

async function statusProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const probe = document.createElement("span");
    document.body.append(probe);
    const resolve = (name: string) => {
      probe.style.color = root.getPropertyValue(name).trim();
      return getComputedStyle(probe).color;
    };
    const tones = ["--ok", "--blocked", "--confirm", "--unverified"].map(resolve);
    probe.remove();
    const plain = new Set(["rgba(0, 0, 0, 0)", "transparent", resolve("--bg"), resolve("--surface")]);
    const problems: string[] = [];
    const words = document.querySelectorAll<HTMLElement>(".status, .outcome-error, .outcome-result, .verdict-line, .registry-name");
    for (const word of words) {
      if (!word.getClientRects().length) continue;
      const name = `${word.className} "${word.textContent!.trim().slice(0, 40)}"`;
      for (const pseudo of ["::before", "::after"]) {
        const style = getComputedStyle(word, pseudo);
        if (style.content !== "none" && style.content !== "normal" && style.content !== '""') problems.push(`${name} has ${pseudo} ${style.content}`);
        if (style.content === '""' && (parseFloat(style.width) > 0 || style.display !== "inline")) problems.push(`${name} has a ${pseudo} shape`);
      }
      if (word.querySelector("svg, img")) problems.push(`${name} has an icon`);
      let el: HTMLElement | null = word;
      for (let depth = 0; el && depth < 3; depth++, el = el.parentElement) {
        const style = getComputedStyle(el);
        for (const side of ["Top", "Right", "Bottom", "Left"] as const) {
          const width = parseFloat(style.getPropertyValue(`border-${side.toLowerCase()}-width`));
          const color = style.getPropertyValue(`border-${side.toLowerCase()}-color`);
          if (width > 0 && tones.includes(color)) problems.push(`${name} sits in a box with a ${color} border`);
        }
        if (!plain.has(style.backgroundColor) && el.tagName !== "BUTTON") {
          const [r, g, b] = style.backgroundColor.match(/\d+/g)!.map(Number);
          const neutral = Math.max(r, g, b) - Math.min(r, g, b) < 12;
          if (!neutral) problems.push(`${name} sits on a tinted ${style.backgroundColor}`);
        }
      }
    }
    return problems;
  });
}

test.describe("status words", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`stand alone, with no shape, icon or box, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      for (const path of PAGES) {
        await page.goto(path);
        expect(await statusProblems(page), path).toEqual([]);
      }
    });
  }
});

test.describe("the hero", () => {
  for (const width of [1440, 768, 390]) {
    test(`spells HAL out under its own letters at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator(".hero-spell")).toHaveAttribute("data-placed", "");
      await expect(page.locator(".hero-spell")).toHaveAttribute("aria-hidden", "true");
      await expect(page.locator("h1")).toHaveText("OpenHAL");
      const offsets = await page.evaluate(() => {
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
          const center = glyph.left + (ink.actualBoundingBoxRight - ink.actualBoundingBoxLeft) / 2;
          const box = label.getBoundingClientRect();
          return { letter: text.textContent!.charAt(at), word: label.textContent, off: Math.abs(box.left + box.width / 2 - center), size: parseFloat(getComputedStyle(label).fontSize), below: box.top - glyph.top };
        });
      });
      expect(offsets.map((item) => `${item.letter} ${item.word}`)).toEqual(["H hardware", "A agent", "L layer"]);
      for (const item of offsets) {
        expect(item.off).toBeLessThan(1.5);
        expect(item.size).toBe(13);
        expect(item.below).toBeGreaterThan(0);
      }
    });
  }

  test("names the site Open Hardware Agent Layer in its metadata", async ({ page }) => {
    await page.goto("/");
    const site = JSON.parse((await page.locator('script[type="application/ld+json"]').textContent())!);
    expect(site.alternateName).toBe("Open Hardware Agent Layer");
    expect(site.name).toBe("OpenHAL");
  });
});

test.describe("driver counts", () => {
  test("come from drivers/catalog.json and agree on home and the Drivers page", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#works-title ~ .onward")).toContainText(`All ${devices} drivers`);
    await page.goto("/drivers/");
    await expect(page.locator("[data-shown]")).toHaveText(`${devices} drivers.`);
  });
});

test.describe("the search index", () => {
  test("leaves the story's state text out of the home page's entry", async ({ page }) => {
    await page.goto("/drivers/");
    await page.keyboard.press("Control+k");
    await page.locator("#site-search-input").fill("Interlocks");
    await expect(page.locator("[data-search-status]")).toHaveText(/match/);
    const hrefs = await page.locator("a.search-result").evaluateAll((items) => items.map((item) => item.getAttribute("href")));
    expect(hrefs.filter((href) => href === "/" || href?.startsWith("/#"))).toEqual([]);
    const ignored = await page.evaluate(async () => {
      const html = await (await fetch("/")).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const stage = doc.querySelectorAll(".story-scene, .story-snap, .story-trace, .story-notes, .story-count");
      return [...stage].every((el) => el.closest("[data-pagefind-ignore]"));
    });
    expect(ignored).toBe(true);
  });
});
