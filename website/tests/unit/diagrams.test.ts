import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { fontless, themedDiagram, themeTokens } from "../../src/lib/markdown/diagram-theme.mjs";
import { mermaidHash, redrawManifest } from "../../src/lib/markdown/mermaid.mjs";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const manifest = redrawManifest(root) as Array<{ name: string; source: string; index: number; mermaid: string; title: string }>;

function markdown(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return /^(agents|research|design-rounds|node_modules)$/.test(name) ? [] : markdown(path);
    return path.endsWith(".md") ? [path] : [];
  });
}

const blocks = (path: string) => [...readFileSync(path, "utf8").matchAll(/^```mermaid\n([\s\S]*?)\n```/gm)].map((match) => match[1]);

describe("house-style diagrams", () => {
  it("redraw every Mermaid block the site shows", () => {
    const known = new Set(manifest.map((entry) => entry.mermaid));
    const missing = [...markdown(join(root, "docs")), ...markdown(join(root, "spec"))].flatMap((path) =>
      blocks(path)
        .map((block, index) => ({ where: `${relative(root, path)} block ${index}`, hash: mermaidHash(block) }))
        .filter((block) => !known.has(block.hash))
        .map((block) => block.where),
    );
    expect(missing, "Update the matching docs/diagrams/*.d2 and run scripts/build-diagrams").toEqual([]);
  });

  it("go on a page as one SVG with no fonts, whose colors follow the theme", () => {
    const tokens = themeTokens(root);
    for (const entry of manifest) {
      const light = readFileSync(join(root, "docs", "diagrams", `${entry.name}-light.svg`), "utf8");
      const dark = readFileSync(join(root, "docs", "diagrams", `${entry.name}-dark.svg`), "utf8");
      const svg = themedDiagram(light, dark, tokens);
      expect(svg, entry.name).not.toBeNull();
      expect(svg).not.toMatch(/@font-face|data:|font-family:\s*"?d2-/);
      expect(svg).toContain(`<title id="oh-title">${entry.title}</title>`);
      expect(svg!.length).toBeLessThan(light.length * 0.7);
      for (const name of ["--text", "--text-2", "--surface"]) expect(svg).toContain(`var(${name})`);
      const own = [...svg!.matchAll(/(--d2-\d+):(#[0-9a-f]{3,6})/g)].map((match) => match[1]);
      for (const name of new Set(own)) {
        expect(svg).toContain(`var(${name})`);
        expect(svg).toMatch(new RegExp(`prefers-color-scheme:dark\\)\\{:root:not\\(\\[data-theme="light"\\]\\) \\.d2-\\d+\\{[^}]*${name}:`));
      }
      const darkOnly = [...dark.matchAll(/(?<=\s(?:fill|stroke)=")#[0-9a-f]{6}(?=")/g)].map((match) => match[0]).filter((color) => !light.includes(color));
      for (const color of darkOnly) expect(svg, `${entry.name} keeps the dark ${color} only in its dark rules`).not.toMatch(new RegExp(`(?:fill|stroke)="${color}"`));
    }
  });

  it("draw text with the page's faces at D2's weights and without kerning", () => {
    const light = readFileSync(join(root, "docs", "diagrams", "architecture-command-light.svg"), "utf8");
    const svg = fontless(light);
    expect(svg).not.toContain("@font-face");
    expect(svg).toMatch(/\.text-bold \{?font-family:var\(--font-text\);font-weight:700;font-style:normal;font-kerning:none;/);
    expect(svg).toMatch(/\.text-mono \{?font-family:var\(--font-mono\);font-weight:400;font-style:normal;font-kerning:none;/);
  });

  it("ship light and dark SVGs with a title and nothing executable", () => {
    for (const entry of manifest) {
      for (const theme of ["light", "dark"]) {
        const path = join(root, "docs", "diagrams", `${entry.name}-${theme}.svg`);
        expect(existsSync(path), path).toBe(true);
        const svg = readFileSync(path, "utf8");
        expect(svg).toContain(`<title id="oh-title">${entry.title}</title>`);
        expect(svg).not.toMatch(/<script|<foreignObject|https?:\/\/(?!www\.w3\.org)/);
        expect(svg).not.toMatch(/font-size:(?:[0-9]|1[0-2])(?:\.\d+)?px/);
      }
    }
  });
});
