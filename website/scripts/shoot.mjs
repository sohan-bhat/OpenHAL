// Take screenshots of site pages with headless Chromium, for design review.
// node scripts/shoot.mjs <out-dir> <path>[,<path>...] [widths] [schemes] [--full]
// Expects the preview server on http://127.0.0.1:4322.

import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const [outDir = "shots", pathList = "/", widthList = "390,768,1024,1440", schemeList = "light,dark", ...flags] = process.argv.slice(2);
const full = !flags.includes("--viewport");
const clipFlag = flags.find((flag) => flag.startsWith("--clip="));
const clip = clipFlag ? (([y, h]) => ({ x: 0, y: Number(y), height: Number(h) }))(clipFlag.slice(7).split(":")) : null;
const base = process.env.OPENHAL_PREVIEW_URL ?? "http://127.0.0.1:4322";
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
for (const scheme of schemeList.split(",")) {
  for (const width of widthList.split(",").map(Number)) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
    const page = await context.newPage();
    for (const path of pathList.split(",")) {
      await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const name = (path.replace(/^\/|\/$/g, "").replaceAll("/", "-") || "home").replaceAll("?", "-").replaceAll("=", "-");
      await page.screenshot({ path: `${outDir}/${name}-${width}-${scheme}${clip ? `-${clip.y}` : ""}.png`, fullPage: full, ...(clip ? { clip: { ...clip, width } } : {}) });
    }
    await context.close();
  }
}
await browser.close();
