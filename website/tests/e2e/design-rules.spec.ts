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
    await page.getByRole("dialog", { name: "Search" }).getByRole("combobox").fill("Interlocks");
    await expect(page.locator("[cmdk-item] mark").first()).toBeVisible({ timeout: 15_000 });
    const hrefs = await page.locator("[cmdk-item]").evaluateAll((items) => items.map((item) => item.getAttribute("href")));
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

/**
 * Every place the page paints the magenta accent, read from the computed styles of every element
 * and its ::before and ::after, with the role each place plays: a primary button or the marker of
 * where a person is. Anything else is reported by its tag and class, so a third use fails.
 */
const sparks = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = "var(--spark)";
    document.body.append(probe);
    const spark = getComputedStyle(probe).color;
    probe.remove();
    const roles: string[] = [];
    const strays: string[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("body *")) {
      if (!element.checkVisibility({ visibilityProperty: true })) continue;
      for (const pseudo of [null, "::before", "::after"] as const) {
        const style = getComputedStyle(element, pseudo);
        if (pseudo && (style.content === "none" || style.content === "normal")) continue;
        const border = ["Top", "Right", "Bottom", "Left"].some((side) => parseFloat(style.getPropertyValue(`border-${side.toLowerCase()}-width`)) > 0 && style.getPropertyValue(`border-${side.toLowerCase()}-color`) === spark);
        const text = !pseudo && style.color === spark && [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim());
        const paints = style.backgroundColor === spark || border || text || style.boxShadow.includes(spark) || style.backgroundImage.includes(spark);
        if (!paints) continue;
        const name = `${element.localName}${pseudo ?? ""}.${String(element.className).slice(0, 60)}`;
        if (style.backgroundImage !== "none") strays.push(`${name} draws an image or a gradient`);
        if (text) strays.push(`${name} sets text in the accent`);
        if (element.matches(".button:not(.quiet), [data-slot=button][data-variant=default]") && !pseudo) roles.push("primary button");
        else if (element.matches(".nav-mark") || (pseudo === "::before" && element.matches("li:has(> [aria-current=page]), .oh-menu-sections a[aria-current=page]"))) roles.push("current location");
        else strays.push(name);
      }
    }
    return { spark, roles: [...new Set(roles)].sort(), strays };
  });

test.describe("the magenta accent", () => {
  for (const [scheme, value, least] of [
    ["light", "rgb(204, 20, 117)", 5.2],
    ["dark", "rgb(255, 79, 163)", 6.3],
  ] as const) {
    test(`fills the primary buttons and marks the current location, two uses at most per screen, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize({ width: 1440, height: 900 });
      for (const [path, roles] of [
        ["/", ["current location", "primary button"]],
        ["/docs/quickstart/", ["current location"]],
        ["/spec/v0.1/basic/messages/", ["current location"]],
        ["/drivers/", ["current location"]],
        ["/404.html", []],
      ] as const) {
        await page.goto(path);
        const seen = await sparks(page);
        expect(seen.spark, path).toBe(value);
        expect(seen.strays, `${path} uses the accent only for its two roles`).toEqual([]);
        expect(seen.roles, path).toEqual(roles);
      }
      await page.goto("/spec/playground/");
      await page.locator("summary", { hasText: "Build your own request" }).click();
      const playground = await sparks(page);
      expect(playground.strays).toEqual([]);
      expect(playground.roles.length, "the Playground shows its primary button and the current location, no third use").toBeLessThanOrEqual(2);

      await page.goto("/");
      const colors = await page.getByRole("link", { name: "Get started" }).evaluate((element) => {
        const style = getComputedStyle(element);
        return { background: style.backgroundColor, color: style.color, page: getComputedStyle(document.body).backgroundColor, image: style.backgroundImage };
      });
      expect(colors.background).toBe(value);
      expect(colors.color, "the button's text is the page background").toBe(colors.page);
      expect(colors.image, "no gradient").toBe("none");
      const ratio = await page.evaluate(([one, two]) => {
        const luminance = (color: string) => {
          const [r, g, b] = color.match(/[\d.]+/g)!.slice(0, 3).map((part) => {
            const c = Number(part) / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const [a, b] = [luminance(one), luminance(two)].sort((x, y) => y - x);
        return (a + 0.05) / (b + 0.05);
      }, [colors.background, colors.page]);
      expect(ratio, "the accent against the page, which is also the button's text").toBeGreaterThanOrEqual(least);
    });
  }

  test("puts a 2 px bar on the header's rule under the current section and on the guide line beside the current page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/spec/v0.1/basic/messages/");
    const header = await page.evaluate(() => {
      const mark = document.querySelector(".nav-mark")!.getBoundingClientRect();
      const link = document.querySelector(".oh-sections a[aria-current='page']")!.getBoundingClientRect();
      const bar = document.querySelector("header.header")!.getBoundingClientRect();
      return { height: mark.height, bottom: mark.bottom - bar.bottom, under: mark.left >= link.left && mark.right <= link.right, marks: document.querySelectorAll(".nav-mark").length };
    });
    expect(header).toEqual({ height: 2, bottom: 0, under: true, marks: 1 });
    const side = await page.evaluate(() => {
      const item = document.querySelector("[data-slot=sidebar] li:has(> [aria-current='page'])")!;
      const row = item.querySelector("[aria-current='page']")!.getBoundingClientRect();
      const before = getComputedStyle(item, "::before");
      return {
        width: before.width,
        bar: Math.round(item.getBoundingClientRect().left + parseFloat(before.left)),
        guide: Math.round(item.closest("[data-sidebar=menu-sub]")!.getBoundingClientRect().left),
        tall: Math.round(parseFloat(before.height)) === Math.round(row.height),
      };
    });
    expect(side).toEqual({ width: "2px", bar: side.guide, guide: side.guide, tall: true });
  });
});
