import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { mermaidHash, redrawManifest } from "../../src/lib/markdown/mermaid.mjs";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const manifest = redrawManifest(root) as Array<{ name: string; source: string; index: number; mermaid: string; title: string }>;

function markdown(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return /^(agents|research)$/.test(name) ? [] : markdown(path);
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
