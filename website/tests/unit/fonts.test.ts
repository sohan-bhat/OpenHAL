import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import manifest from "../../src/fonts/fonts.json";
import glyphs from "../../src/fonts/glyphs.json";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const css = read("../../src/styles/fonts.css");
const tokens = read("../../../design/tokens.css");
const global = read("../../src/styles/global.css");
const base = read("../../src/layouts/Base.astro");

function codepoints(range: string): Set<number> {
  const out = new Set<number>();
  for (const part of range.split(/,\s*/)) {
    const [from, to = from] = part.replace(/^U\+/, "").split("-");
    for (let code = parseInt(from, 16); code <= parseInt(to, 16); code++) out.add(code);
  }
  return out;
}

const faces = (text: string) =>
  [...text.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((match) => {
    const value = (name: string) => match[1].match(new RegExp(`${name}:\\s*([^;]+);`))?.[1].trim().replace(/\s+/g, " ") ?? "";
    return { family: value("font-family"), style: value("font-style"), weight: value("font-weight"), src: value("src"), range: value("unicode-range") };
  });

describe("the website's fonts", () => {
  const subset = faces(css);

  it("have one subset face for each face the site renders, in the manifest", () => {
    expect(subset.map((face) => `${face.family} ${face.style}`)).toEqual(manifest.faces.map((face) => `"${face.family}" ${face.style}`));
    for (const face of manifest.faces) {
      const file = fileURLToPath(new URL(`../../src/fonts/${face.file}`, import.meta.url));
      expect(statSync(file).size, face.file).toBe(face.bytes);
      expect(face.bytes, face.file).toBeLessThan(face.sourceBytes * 0.6);
    }
  });

  it("join the faces in design/tokens.css, so a character a subset lacks falls back to the full face", () => {
    const full = faces(tokens).filter((face) => face.family.startsWith('"Atkinson Hyperlegible'));
    for (const face of subset) {
      const twin = full.find((item) => item.family === face.family && item.style === face.style);
      expect(twin, `${face.family} ${face.style}`).toBeDefined();
      expect(face.weight).toBe(twin!.weight);
    }
    expect(global.indexOf('@import "./fonts.css"')).toBeGreaterThan(global.indexOf("design/tokens.css"));
  });

  it("cover every character the site shows that the full faces have", () => {
    const wanted = new Set([...Array.from({ length: 0x7f - 0x20 }, (_, index) => index + 0x20), ...glyphs.codepoints.map((code) => parseInt(code, 16))]);
    for (const [index, face] of manifest.faces.entries()) {
      const has = codepoints(face.unicodeRange);
      const could = codepoints(face.sourceRange);
      const missing = [...wanted].filter((code) => could.has(code) && !has.has(code)).map((code) => `U+${code.toString(16).toUpperCase()}`);
      expect(missing, face.file).toEqual([]);
      expect(subset[index].range).toBe(face.unicodeRange);
    }
  });

  it("preload the subsets, the mono face only where a page asks for it", () => {
    const preloads = [...base.matchAll(/<link rel="preload"[^>]*as="font"[^>]*>/g)].map((match) => match[0]);
    expect(preloads).toHaveLength(2);
    expect(base).toContain('from "../fonts/atkinson-hyperlegible-next-normal.woff2?url"');
    expect(base).toContain('from "../fonts/atkinson-hyperlegible-mono-normal.woff2?url"');
    expect(base).toContain("{mono && <link rel=\"preload\" href={atkinsonMono}");
  });
});
