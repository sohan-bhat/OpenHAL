import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { faviconSvg, markLightSvg, wordmarkLightSvg, wordmarkWidth } from "../../src/lib/brand-mark";

const assets = fileURLToPath(new URL("../../../docs/assets/", import.meta.url));
const asset = (name: string) => readFileSync(`${assets}${name}`, "utf8");
const header = readFileSync(fileURLToPath(new URL("../../src/components/starlight/Header.astro", import.meta.url)), "utf8");

const withoutSize = (svg: string) => svg.trim().replace(/\s(width|height)="[\d.]+"/g, "");

describe("the mark matches docs/assets", () => {
  it("serves the favicon byte for byte", () => {
    expect(faviconSvg()).toBe(asset("favicon.svg"));
  });

  it("draws icons and social images from the mark and wordmark files", () => {
    expect(withoutSize(markLightSvg(40))).toBe(withoutSize(asset("mark-light.svg")));
    expect(withoutSize(wordmarkLightSvg(44))).toBe(withoutSize(asset("wordmark-light.svg")));
  });

  it("shows the wordmark files in the header at their own aspect ratio, one for each theme", () => {
    expect(header).toContain('<img class="dark:sl-hidden" src="/brand/wordmark-light.svg"');
    expect(header).toContain('<img class="light:sl-hidden" src="/brand/wordmark-dark.svg"');
    expect(header).toContain("const width = wordmarkWidth(24);");
    const svg = asset("wordmark-light.svg");
    const width = Number(/\swidth="([\d.]+)"/.exec(svg)![1]);
    const height = Number(/\sheight="([\d.]+)"/.exec(svg)![1]);
    expect(wordmarkWidth(24)).toBe(Math.round((width * 24) / height));
  });
});

describe("status words", () => {
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = join(dir, name);
      return statSync(full).isDirectory() ? files(full) : /\.(css|astro|svelte)$/.test(name) ? [full] : [];
    });
  const source = fileURLToPath(new URL("../../src/", import.meta.url));
  const rules = files(source).flatMap((file) =>
    [...readFileSync(file, "utf8").matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({ file: file.slice(source.length), selector: selector.trim(), body })),
  );
  const TONE = /var\(--(ok|blocked|confirm|confirm-bg|unverified)\)/;
  const CONTROLS = /\.stop\b|\.fill\b/;

  it("have no shape, dot or icon drawn beside them", () => {
    const shaped = rules.filter((rule) => /\.status[^,{]*::(before|after)/.test(rule.selector) && !/content:\s*none/.test(rule.body));
    expect(shaped.map((rule) => `${rule.file} ${rule.selector}`)).toEqual([]);
  });

  it("never sit in a box with a status colored border or tinted background", () => {
    const boxed = rules.filter((rule) => !CONTROLS.test(rule.selector) && /(^|;|\s)(border[a-z-]*|background[a-z-]*|box-shadow|outline)\s*:[^;]*/.test(rule.body)).filter((rule) =>
      rule.body.split(";").some((line) => /^\s*(border[a-z-]*|background[a-z-]*|box-shadow|outline)\s*:/.test(line) && TONE.test(line)),
    );
    expect(boxed.map((rule) => `${rule.file} ${rule.selector}`)).toEqual([]);
  });
});
