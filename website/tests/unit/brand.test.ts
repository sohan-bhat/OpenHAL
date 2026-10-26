import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { faviconSvg, markLightSvg, wordmarkLightSvg, wordmarkWidth } from "../../src/lib/brand-mark";

const assets = fileURLToPath(new URL("../../../docs/assets/", import.meta.url));
const asset = (name: string) => readFileSync(`${assets}${name}`, "utf8");
const header = readFileSync(fileURLToPath(new URL("../../src/components/Header.astro", import.meta.url)), "utf8");

const withoutSize = (svg: string) => svg.trim().replace(/\s(width|height)="[\d.]+"/g, "");

describe("the mark matches docs/assets", () => {
  it("serves the favicon byte for byte", () => {
    expect(faviconSvg()).toBe(asset("favicon.svg"));
  });

  it("draws icons and social images from the mark and wordmark files", () => {
    expect(withoutSize(markLightSvg(40))).toBe(withoutSize(asset("mark-light.svg")));
    expect(withoutSize(wordmarkLightSvg(44))).toBe(withoutSize(asset("wordmark-light.svg")));
  });

  it("shows the wordmark files in the header at their own aspect ratio", () => {
    expect(header).toContain('srcset="/brand/wordmark-dark.svg"');
    expect(header).toContain('src="/brand/wordmark-light.svg"');
    expect(header).toContain("width={wordmarkWidth(24)}");
    const svg = asset("wordmark-light.svg");
    const width = Number(/\swidth="([\d.]+)"/.exec(svg)![1]);
    const height = Number(/\sheight="([\d.]+)"/.exec(svg)![1]);
    expect(wordmarkWidth(24)).toBe(Math.round((width * 24) / height));
  });
});

describe("status shapes", () => {
  const css = readFileSync(fileURLToPath(new URL("../../src/styles/global.css", import.meta.url)), "utf8");
  const shaped = [...css.matchAll(/\.status\.([a-z]+)::before\s*\{([^}]*)\}/g)].filter(([, , body]) => !/content:\s*none/.test(body)).map(([, name]) => name);

  it("draws only the shapes DESIGN.md names, and no green dot for ok or granted", () => {
    expect([...new Set(shaped)].sort()).toEqual(["blocked", "confirm", "unverified"]);
  });
});
