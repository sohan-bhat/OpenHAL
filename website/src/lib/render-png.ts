import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Browser } from "playwright";

const FONTS = join(process.cwd(), "..", "design", "fonts");

let browser: Promise<Browser> | null = null;
let idle: ReturnType<typeof setTimeout> | undefined;

async function launch(): Promise<Browser> {
  if (!browser) {
    browser = import("playwright").then(({ chromium }) => chromium.launch({ headless: true }));
  }
  clearTimeout(idle);
  return browser;
}

function release(): void {
  clearTimeout(idle);
  idle = setTimeout(async () => {
    const open = browser;
    browser = null;
    if (open) await (await open).close();
  }, 1500);
}

function font(file: string): string {
  return readFileSync(join(FONTS, file)).toString("base64");
}

let faces: string | null = null;

export function fontFaces(): string {
  faces ??= [
    ["Sofia Sans Condensed", "sofia-sans-condensed-latin-wght-normal.woff2", "1 1000"],
    ["Atkinson Hyperlegible Next", "atkinson-hyperlegible-next-latin-wght-normal.woff2", "200 800"],
    ["Martian Mono", "martian-mono-latin-wght-normal.woff2", "100 800"],
  ]
    .map(([family, file, weight]) => `@font-face{font-family:"${family}";font-weight:${weight};src:url(data:font/woff2;base64,${font(file)}) format("woff2");}`)
    .join("");
  return faces;
}

export async function renderPng(html: string, width: number, height: number, transparent = false): Promise<Uint8Array> {
  const page = await (await launch()).newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  try {
    await page.setContent(html, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    return new Uint8Array(await page.screenshot({ type: "png", omitBackground: transparent }));
  } finally {
    await page.close();
    release();
  }
}
