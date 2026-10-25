import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { faviconSvg, markLightSvg, wordmarkLightSvg } from "../../src/lib/brand-mark";

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

  it("shows the wordmark files in the header", () => {
    expect(header).toContain('srcset="/brand/wordmark-dark.svg"');
    expect(header).toContain('src="/brand/wordmark-light.svg"');
  });
});
