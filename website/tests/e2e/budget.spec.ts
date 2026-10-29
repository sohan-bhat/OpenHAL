import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { expect, test, type Request } from "@playwright/test";
import { siteCodepoints } from "../../scripts/glyphs.mjs";

const dist = fileURLToPath(new URL("../../dist/", import.meta.url));
const manifest = JSON.parse(readFileSync(fileURLToPath(new URL("../../src/fonts/fonts.json", import.meta.url)), "utf8")) as {
  faces: Array<{ family: string; style: string; file: string; weights: [number, number]; unicodeRange: string; sourceRange: string }>;
};

interface Weight {
  html: number;
  css: number;
  js: number;
  fonts: number;
}

/**
 * The most each template may send on its first load, in bytes. HTML, CSS and JavaScript count
 * gzipped, the way GitHub Pages serves them, and fonts as the WOFF2 files they are. Set from the
 * measured weights of the build in docs/verification/ui.md with about ten percent of headroom.
 */
const BUDGETS: Record<string, { path: string } & Weight> = {
  home: { path: "/", html: 16_100, css: 9_100, js: 7_300, fonts: 29_100 },
  "docs index": { path: "/docs/", html: 6_700, css: 5_600, js: 3_300, fonts: 18_400 },
  "guide page": { path: "/docs/quickstart/", html: 8_200, css: 5_600, js: 3_300, fonts: 35_600 },
  "page with diagrams": { path: "/docs/architecture/", html: 19_200, css: 5_600, js: 3_300, fonts: 29_100 },
  "spec page": { path: "/spec/v0.1/basic/messages/", html: 19_100, css: 5_600, js: 3_300, fonts: 29_100 },
  "schema reference": { path: "/spec/v0.1/schema/", html: 16_700, css: 5_600, js: 3_300, fonts: 29_100 },
  drivers: { path: "/drivers/", html: 12_700, css: 5_600, js: 3_300, fonts: 29_100 },
  "driver page": { path: "/drivers/moonraker/", html: 10_400, css: 5_600, js: 3_300, fonts: 29_100 },
  library: { path: "/library/", html: 8_300, css: 5_600, js: 3_300, fonts: 29_100 },
  "library device": { path: "/library/scpi-rigol-dp832/", html: 8_500, css: 5_600, js: 3_300, fonts: 29_100 },
  playground: { path: "/spec/playground/", html: 16_200, css: 7_700, js: 3_300, fonts: 29_100 },
  "Python reference": { path: "/sdks/python/reference/", html: 14_300, css: 5_600, js: 3_300, fonts: 29_100 },
  "Inspector page": { path: "/inspector/", html: 7_500, css: 5_600, js: 3_300, fonts: 29_100 },
  blog: { path: "/blog/", html: 3_600, css: 4_600, js: 3_300, fonts: 29_100 },
  "not found": { path: "/404.html", html: 4_500, css: 4_600, js: 3_300, fonts: 29_100 },
};

function fileOf(url: string): string {
  const path = decodeURIComponent(new URL(url).pathname);
  const direct = join(dist, path);
  return existsSync(direct) && statSync(direct).isFile() ? direct : join(direct, "index.html");
}

function weigh(requests: Request[]): Weight & { files: string[] } {
  const total = { html: 0, css: 0, js: 0, fonts: 0, files: [] as string[] };
  for (const request of requests) {
    const file = fileOf(request.url());
    if (!existsSync(file)) continue;
    const kind = request.resourceType();
    const gz = () => gzipSync(readFileSync(file)).length;
    if (kind === "document") total.html += gz();
    else if (kind === "stylesheet") total.css += gz();
    else if (kind === "script") total.js += gz();
    else if (kind === "font") {
      total.fonts += statSync(file).size;
      total.files.push(file.slice(dist.length));
    }
  }
  return total;
}

function codepoints(range: string): Set<number> {
  const out = new Set<number>();
  for (const part of range.split(/,\s*/)) {
    const [from, to = from] = part.replace(/^U\+/, "").split("-");
    for (let code = parseInt(from, 16); code <= parseInt(to, 16); code++) out.add(code);
  }
  return out;
}

test.describe("page weight", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "weights are measured once, in Chromium");

  for (const [name, budget] of Object.entries(BUDGETS)) {
    test(`the ${name} stays within its budget`, async ({ page }) => {
      const requests: Request[] = [];
      page.on("requestfinished", (request) => requests.push(request));
      await page.goto(budget.path, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(2500);
      const weight = weigh(requests);
      console.log(`${name} ${budget.path} html ${weight.html} css ${weight.css} js ${weight.js} fonts ${weight.fonts}`);
      for (const kind of ["html", "css", "js", "fonts"] as const) expect(weight[kind], `${name} ${kind}`).toBeLessThanOrEqual(budget[kind]);
      for (const file of weight.files) expect(manifest.faces.map((face) => face.file.replace(/\.woff2$/, "")).some((stem) => file.includes(stem)), `${name} loads ${file}`).toBe(true);
    });
  }

  test("every page uses its faces within the weights the subsets keep", async ({ page }) => {
    test.setTimeout(120_000);
    const used = new Map<string, Set<number>>();
    for (const { path } of Object.values(BUDGETS)) {
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(path);
        const found = await page.evaluate(() => {
          const out: Array<[string, number]> = [];
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const parent = node.parentElement;
            if (!parent || !node.textContent?.trim() || !parent.getClientRects().length) continue;
            const style = getComputedStyle(parent);
            const family = style.fontFamily.split(",")[0].replace(/["']/g, "").trim();
            out.push([`${family} ${style.fontStyle === "normal" ? "normal" : "italic"}`, Number(style.fontWeight)]);
          }
          return out;
        });
        for (const [face, weight] of found) used.set(face, (used.get(face) ?? new Set()).add(weight));
      }
    }
    for (const face of manifest.faces) {
      const weights = [...(used.get(`${face.family} ${face.style}`) ?? [])];
      for (const weight of weights) {
        expect(Math.min(weight, 800), `${face.family} ${face.style} at ${weight}`).toBeGreaterThanOrEqual(face.weights[0]);
        expect(Math.min(weight, 800), `${face.family} ${face.style} at ${weight}`).toBeLessThanOrEqual(face.weights[1]);
      }
    }
  });

  test("every page uses the fonts it preloads", async ({ page }) => {
    test.setTimeout(120_000);
    for (const { path } of Object.values(BUDGETS)) {
      await page.goto(path);
      const { preloads, loaded } = await page.evaluate(async () => {
        await document.fonts.ready;
        return {
          preloads: [...document.querySelectorAll<HTMLLinkElement>('link[rel="preload"][as="font"]')].map((link) => link.getAttribute("href") ?? ""),
          loaded: [...document.fonts].filter((face) => face.status === "loaded").map((face) => `${face.family.replace(/["']/g, "")} ${face.style}`),
        };
      });
      for (const href of preloads) {
        const face = manifest.faces.find((item) => href.includes(item.file.replace(/\.woff2$/, "")));
        expect(face, `${path} preloads ${href}`).toBeDefined();
        expect(loaded, `${path} preloads ${href} but shows no ${face!.family} ${face!.style}`).toContain(`${face!.family} ${face!.style}`);
      }
    }
  });

  test("the font subsets hold every character the build shows that the full faces have", () => {
    const shown = siteCodepoints(dist).map((code: string) => parseInt(code, 16));
    for (const face of manifest.faces) {
      const has = codepoints(face.unicodeRange);
      const could = codepoints(face.sourceRange);
      const missing = shown.filter((code: number) => could.has(code) && !has.has(code)).map((code: number) => `U+${code.toString(16).toUpperCase()}`);
      expect(missing, `${face.file} lacks these. Run node scripts/glyphs.mjs dist, then website/scripts/fonts.py`).toEqual([]);
    }
  });

  test("no page asks for a font the subsets replace", () => {
    const pages = (dir: string): string[] =>
      readdirSync(dir).flatMap((name) => {
        const full = join(dir, name);
        return statSync(full).isDirectory() ? (name === "pagefind" ? [] : pages(full)) : name.endsWith(".html") ? [full] : [];
      });
    for (const file of pages(dist)) {
      const html = readFileSync(file, "utf8");
      for (const match of html.matchAll(/<link rel="preload"[^>]*as="font"[^>]*href="([^"]+)"|<link rel="preload" href="([^"]+)"[^>]*as="font"/g)) {
        const href = match[1] ?? match[2];
        expect(manifest.faces.some((face) => href.includes(face.file.replace(/\.woff2$/, ""))), `${file.slice(dist.length)} preloads ${href}`).toBe(true);
      }
    }
  });
});
