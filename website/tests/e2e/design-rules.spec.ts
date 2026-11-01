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
 * Every place the page paints the pink accent or the blue of pending, read from the computed
 * styles of every element and its ::before and ::after, with the role each place plays. Anything
 * else is reported by its tag and class. How it works is left to how.spec.ts.
 */
const accents = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("span");
    document.body.append(probe);
    const resolve = (value: string) => {
      probe.style.color = value;
      return getComputedStyle(probe).color;
    };
    const accent = resolve("var(--accent)");
    const fill = resolve("var(--accent-fill)");
    const confirm = resolve("var(--confirm)");
    const retired = ["#cc1475", "#ff4fa3", "#8a5a00", "#e8b341", "#ffd60a", "#7a5c00", "#ffe14d"].map(resolve);
    probe.remove();
    const roles: string[] = [];
    const strays: string[] = [];
    const large: string[] = [];
    const pending: string[] = [];
    const paints = (style: CSSStyleDeclaration, color: string, pseudo: string | null, element: Element) => {
      const border = ["top", "right", "bottom", "left"].some((side) => parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0 && style.getPropertyValue(`border-${side}-color`) === color);
      const text = !pseudo && style.color === color && [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim());
      return { any: style.backgroundColor === color || border || Boolean(text) || style.boxShadow.includes(color) || style.backgroundImage.includes(color) || style.stroke === color || style.fill === color, back: style.backgroundColor === color };
    };
    for (const element of document.querySelectorAll<HTMLElement | SVGElement>("body *")) {
      if (!element.checkVisibility({ visibilityProperty: true }) || element.closest(".how")) continue;
      for (const pseudo of [null, "::before", "::after"] as const) {
        const style = getComputedStyle(element, pseudo);
        if (pseudo && (style.content === "none" || style.content === "normal")) continue;
        const name = `${element.localName}${pseudo ?? ""}.${String(element.getAttribute("class") ?? "").slice(0, 60)}`;
        for (const old of retired) if (paints(style, old, pseudo, element).any) strays.push(`${name} paints a retired color ${old}`);
        const blue = paints(style, confirm, pseudo, element);
        if (blue.any && !element.closest(".status.confirm, .stroke.held, .stroke.live.confirm")) pending.push(name);
        const pink = paints(style, fill, pseudo, element);
        const mark = accent === fill ? pink : paints(style, accent, pseudo, element);
        if (!pink.any && !mark.any) continue;
        if (style.backgroundImage !== "none" && (style.backgroundImage.includes(fill) || style.backgroundImage.includes(accent))) strays.push(`${name} draws an image or a gradient`);
        if (pink.back) {
          const box = element.getBoundingClientRect();
          if (box.width * box.height > 30_000) large.push(`${name} fills ${Math.round(box.width)} by ${Math.round(box.height)} px`);
        }
        if (!pseudo && element.matches(".button:not(.quiet, .person), [data-slot=button][data-variant=default]")) roles.push("primary button");
        else if (element.matches(".nav-mark") || (pseudo === "::before" && element.matches("li:has(> [aria-current=page]), .oh-menu-sections a[aria-current=page]"))) roles.push("current location");
        else if (!pseudo && element.closest("a[href]") && !pink.back) {
          const link = getComputedStyle(element.closest("a[href]")!);
          if (link.textDecorationLine.includes("underline")) roles.push("link");
          else strays.push(`${name} is a link in the accent without an underline`);
        } else if (!pseudo && element.matches(".story-count, .story-count *")) roles.push("step counter");
        else if (element.closest(".seq .stroke.live:not(.confirm, .ok, .blocked)")) roles.push("request arrow");
        else if (element.closest(".cam .seen")) roles.push("what the agent spots");
        else strays.push(name);
      }
    }
    return { accent, fill, roles: [...new Set(roles)].sort(), strays, large, pending: [...new Set(pending)] };
  });

const luminance = (color: string) => {
  const [r, g, b] = color
    .match(/[\d.]+/g)!
    .slice(0, 3)
    .map((part) => {
      const c = Number(part) / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

const contrast = (one: string, two: string) => {
  const [a, b] = [luminance(one), luminance(two)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
};

test.describe("the pink accent", () => {
  for (const [scheme, accent] of [
    ["light", "rgb(192, 21, 110)"],
    ["dark", "rgb(255, 110, 180)"],
  ] as const) {
    test(`marks only buttons, links, the current location and the walkthrough's step, with blue for pending alone, in the ${scheme} theme`, async ({ page }) => {
      test.slow();
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize({ width: 1440, height: 900 });
      for (const [path, needs] of [
        ["/", ["current location", "primary button"]],
        ["/docs/quickstart/", ["current location", "link"]],
        ["/spec/v0.1/basic/messages/", ["current location", "link"]],
        ["/drivers/", ["current location"]],
        ["/blog/", []],
        ["/docs/examples/3d-print-watch/", ["current location", "step counter"]],
        ["/404.html", []],
      ] as const) {
        await page.goto(path);
        const seen = await accents(page);
        expect(seen.accent, path).toBe(accent);
        expect(seen.fill, path).toBe("rgb(255, 110, 180)");
        expect(seen.strays, `${path} uses the accent only for its roles`).toEqual([]);
        expect(seen.large, `${path} never fills a large area with pink`).toEqual([]);
        expect(seen.pending, `${path} keeps blue for pending`).toEqual([]);
        expect(seen.roles, path).toEqual(expect.arrayContaining([...needs]));
      }
      await page.goto("/spec/playground/");
      await page.getByRole("button", { name: "Build your own request" }).click();
      await expect(page.getByRole("button", { name: /^Send / })).toBeVisible({ timeout: 15_000 });
      const playground = await accents(page);
      expect(playground.strays).toEqual([]);
      expect(playground.pending).toEqual([]);
      expect(playground.roles).toContain("primary button");
    });

    test(`fills Get started with near-black text at weight 600 and a visible edge, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.goto("/");
      const button = page.getByRole("link", { name: "Get started" });
      const look = await button.evaluate((element) => {
        const style = getComputedStyle(element);
        return { background: style.backgroundColor, color: style.color, weight: style.fontWeight, image: style.backgroundImage, shadow: style.boxShadow, edge: style.borderTopColor, page: getComputedStyle(document.body).backgroundColor };
      });
      expect(look.background).toBe("rgb(255, 110, 180)");
      expect(look.color).toBe("rgb(13, 15, 18)");
      expect(look.weight).toBe("600");
      expect(look.image, "no gradient").toBe("none");
      expect(look.shadow.split(/,(?![^(]*\))/).every((part) => part.includes("inset")), "no shadow or glow").toBe(true);
      expect(contrast(look.color, look.background), "text on the fill").toBeGreaterThanOrEqual(4.5);
      expect(contrast(look.edge, look.page), "the edge against the page").toBeGreaterThanOrEqual(3);
    });
  }

  test("brightens Get started and lifts it 1 px on hover, and only brightens it with reduced motion", async ({ page }) => {
    await page.goto("/");
    const button = page.getByRole("link", { name: "Get started" });
    await button.hover();
    await expect.poll(() => button.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe("rgb(255, 142, 197)");
    await expect.poll(() => button.evaluate((element) => getComputedStyle(element).transform)).toBe("matrix(1, 0, 0, 1, 0, -1)");
    await page.mouse.move(0, 0);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.reload();
    await button.hover();
    await expect.poll(() => button.evaluate((element) => getComputedStyle(element).backgroundColor)).toBe("rgb(255, 142, 197)");
    expect(await button.evaluate((element) => getComputedStyle(element).transform)).toBe("none");
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`selects text on the pink fill with near-black text, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/docs/quickstart/");
      const selection = await page.evaluate(() => {
        const rules = [...document.styleSheets].flatMap((sheet) => [...sheet.cssRules]).filter((rule): rule is CSSStyleRule => rule instanceof CSSStyleRule && rule.selectorText === "::selection");
        const probe = document.createElement("span");
        document.body.append(probe);
        const resolve = (value: string) => {
          probe.style.color = value;
          return getComputedStyle(probe).color;
        };
        const found = rules.map((rule) => ({ background: resolve(rule.style.getPropertyValue("background-color") || rule.style.getPropertyValue("background")), color: resolve(rule.style.getPropertyValue("color")) }));
        probe.remove();
        return found;
      });
      expect(selection).toEqual([{ background: "rgb(255, 110, 180)", color: "rgb(13, 15, 18)" }]);
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
