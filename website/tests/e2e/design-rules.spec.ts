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

test.describe("Starlight's asides", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`sit in a plain box with no tint, colored rule or icon, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/docs/quickstart/");
      const asides = await page.evaluate(() => {
        const content = document.querySelector(".oh-content")!;
        const probe = document.createElement("span");
        document.body.append(probe);
        const resolve = (name: string) => {
          probe.style.color = `var(${name})`;
          return getComputedStyle(probe).color;
        };
        const border = resolve("--border");
        const text = resolve("--text");
        probe.remove();
        return ["note", "tip", "caution", "danger"].map((kind) => {
          const aside = document.createElement("aside");
          aside.className = `starlight-aside starlight-aside--${kind}`;
          aside.innerHTML = `<p class="starlight-aside__title"><svg class="starlight-aside__icon" viewBox="0 0 24 24" width="16" height="16"></svg>${kind}</p><div class="starlight-aside__content"><p>Read <a href="/docs/">the docs</a>.</p></div>`;
          content.append(aside);
          const style = getComputedStyle(aside);
          const sides = ["top", "right", "bottom", "left"].map((side) => {
            const color = style.getPropertyValue(`border-${side}-color`);
            return `${style.getPropertyValue(`border-${side}-width`)} ${color === border ? "border" : color}`;
          });
          const result = {
            kind,
            background: style.backgroundColor,
            sides,
            title: getComputedStyle(aside.querySelector(".starlight-aside__title")!).color === text,
            icon: aside.querySelector(".starlight-aside__icon")!.getClientRects().length,
          };
          aside.remove();
          return result;
        });
      });
      for (const aside of asides) {
        expect(aside.background, aside.kind).toBe("rgba(0, 0, 0, 0)");
        expect(aside.sides, aside.kind).toEqual(["1px border", "1px border", "1px border", "1px border"]);
        expect(aside.title, aside.kind).toBe(true);
        expect(aside.icon, aside.kind).toBe(0);
      }
    });
  }
});

test.describe("the hero", () => {
  test("names the site Open Hardware Abstraction Layer in its metadata", async ({ page }) => {
    await page.goto("/");
    const site = JSON.parse((await page.locator('script[type="application/ld+json"]').textContent())!);
    expect(site.alternateName).toBe("Open Hardware Abstraction Layer");
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
  test("leaves the diagrams' state text out of the home page's entry", async ({ page }) => {
    await page.goto("/drivers/");
    await page.keyboard.press("Control+k");
    await page.locator("#starlight__search input").fill("Interlocks");
    await expect(page.locator(".pagefind-ui__message")).toHaveText(/result/, { timeout: 15_000 });
    const hrefs = await page.locator(".pagefind-ui__result-link").evaluateAll((items) => items.map((item) => item.getAttribute("href")));
    expect(hrefs.filter((href) => href === "/" || href?.startsWith("/#"))).toEqual([]);
    const ignored = await page.evaluate(async () => {
      const html = await (await fetch("/")).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const stage = doc.querySelectorAll(".how-figure, .how-count");
      return stage.length > 0 && [...stage].every((el) => el.closest("[data-pagefind-ignore]"));
    });
    expect(ignored).toBe(true);
  });
});
