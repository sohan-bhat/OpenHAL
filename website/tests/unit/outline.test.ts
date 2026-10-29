import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import pkg from "../../package.json";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const script = read("../../node_modules/@astrojs/starlight/dist/components-internals/TableOfContents/starlight-toc.js");

/** The selectors Starlight's outline passes to `document.querySelectorAll` to find what it observes. */
function scan(source: string): string[] {
  const start = source.indexOf("const toObserve");
  const end = source.indexOf("].join()", start);
  return [...source.slice(start, end).matchAll(/`([^`]*)`/g)].map((match) => match[1]);
}

describe("Starlight's outline", () => {
  it("is patched for the Starlight version the site installs", () => {
    const version = pkg.dependencies["@astrojs/starlight"];
    expect(Object.keys(pkg.pnpm.patchedDependencies)).toEqual([`@astrojs/starlight@${version}`]);
  });

  it("tests an element for a heading inside it only once the element sits where the outline observes", () => {
    const selectors = scan(script);
    expect(selectors).toHaveLength(4);
    const nested = selectors.filter((selector) => selector.includes(":has("));
    expect(nested).toHaveLength(3);
    for (const selector of nested) expect(selector).toMatch(/^:where\(main [^]*\):not\(:has\(\$\{this\.tocHeadingSelector\}\)\)$/);
  });
});
