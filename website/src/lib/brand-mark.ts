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

export function markLightSvg(size: number): string {
  return asset("mark-light.svg")
    .trim()
    .replace(/\swidth="\d+"/, ` width="${size}"`)
    .replace(/\sheight="\d+"/, ` height="${size}"`);
}

export function faviconSvg(): string {
  return favicon();
}

export function wordmarkLightSvg(height: number): string {
  const svg = asset("wordmark-light.svg").trim();
  const width = Number(/\swidth="([\d.]+)"/.exec(svg)?.[1] ?? 0);
  const tall = Number(/\sheight="([\d.]+)"/.exec(svg)?.[1] ?? 1);
  return svg.replace(/\swidth="[\d.]+"/, ` width="${Math.round((width * height) / tall)}"`).replace(/\sheight="[\d.]+"/, ` height="${height}"`);
}
