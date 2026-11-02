import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "./spec-meta.mjs";

const ASSETS = join(REPO_ROOT, "docs", "assets");

function asset(name: string): string {
  return readFileSync(join(ASSETS, name), "utf8");
}

function favicon(): string {
  return asset("favicon.svg");
}

function dimensions(svg: string): { width: number; height: number } {
  return { width: Number(/\swidth="([\d.]+)"/.exec(svg)?.[1] ?? 1), height: Number(/\sheight="([\d.]+)"/.exec(svg)?.[1] ?? 1) };
}

function fit(svg: string, width: number, height: number): string {
  return svg.replace(/\swidth="[\d.]+"/, ` width="${width}"`).replace(/\sheight="[\d.]+"/, ` height="${height}"`);
}

export function markLightSvg(size: number): string {
  const svg = asset("mark-light.svg").trim();
  const { width, height } = dimensions(svg);
  const scale = size / Math.max(width, height);
  return fit(svg, Math.round(width * scale), Math.round(height * scale));
}

export function wordmarkWidth(height: number): number {
  const { width, height: tall } = dimensions(asset("wordmark-light.svg"));
  return Math.round((width * height) / tall);
}

export function faviconSvg(): string {
  return favicon();
}

/**
 * The built wordmark for inline use, such as the home page hero: the same letters as the files, one
 * path each, set in the current text color and hidden from screen readers, which read the heading's
 * own text instead.
 */
export function wordmarkInlineSvg(className: string): string {
  return asset("wordmark-light.svg")
    .trim()
    .replace(/<title[^>]*>.*?<\/title>\s*/s, "")
    .replace(/<desc[^>]*>.*?<\/desc>\s*/s, "")
    .replace(/\s(width|height)="[\d.]+"/g, "")
    .replace(/\srole="img"\saria-labelledby="t d"/, ` class="${className}" aria-hidden="true" focusable="false"`)
    .replace(/<g fill="#[0-9A-Fa-f]{6}"/, '<g fill="currentColor"');
}

export function wordmarkLightSvg(height: number): string {
  return fit(asset("wordmark-light.svg").trim(), wordmarkWidth(height), height);
}
