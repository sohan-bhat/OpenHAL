import { join } from "node:path";
import { fromHtml } from "hast-util-from-html";
import { describe, expect, it } from "vitest";
import { errorRegistry, rehypeGlossaryLinks, rehypeSpecSections, rehypeTables, specSectionNumber } from "../../src/lib/markdown/plugins.mjs";
import { REPO_ROOT } from "../../src/lib/spec-meta.mjs";

type Node = { type: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };

const tree = (html: string) => fromHtml(html, { fragment: true }) as unknown as Node;
const file = (path: string) => ({ path: join(REPO_ROOT, path), data: {} });
const all = (node: Node, tag: string): Node[] => [...(node.tagName === tag ? [node] : []), ...(node.children ?? []).flatMap((child) => all(child, tag))];
const text = (node: Node): string => (node.type === "text" ? (node.value ?? "") : (node.children ?? []).map(text).join(""));
const classes = (node: Node) => (node.properties?.className as string[] | undefined) ?? [];

describe("spec section numbers", () => {
  it("follow the sidebar's numbering", () => {
    expect(specSectionNumber("spec/2026-10-24/index.md")).toBe("1");
    expect(specSectionNumber("spec/2026-10-24/basic/messages.md")).toBe("3.3");
    expect(specSectionNumber("docs/guide/quickstart.md")).toBeNull();
  });

  it("number h2 and h3 headings under the page's number", () => {
    const root = tree("<h2>Rules</h2><h3>One</h3><h3>Two</h3><h2>Errors</h2>");
    rehypeSpecSections()(root, file("spec/2026-10-24/basic/messages.md"));
    expect(all(root, "span").filter((node) => classes(node).includes("secno")).map(text)).toEqual(["3.3.1", "3.3.1.1", "3.3.1.2", "3.3.2"]);
  });
});

describe("error registry in tables", () => {
  it("marks the names a kernel check blocks with", () => {
    const { blocked } = errorRegistry();
    for (const name of ["LIMIT_EXCEEDED", "INTERLOCK_BLOCKED", "STOPPED", "RATE_LIMITED"]) expect(blocked.has(name)).toBe(true);
    for (const name of ["PARSE_ERROR", "INTERNAL_ERROR", "DRIVER_ERROR"]) expect(blocked.has(name)).toBe(false);
  });

  it("sets codes and names in mono, blocked names in red with the blocked shape", () => {
    const root = tree(
      "<table><thead><tr><th>Code</th><th>Name</th></tr></thead><tbody><tr><td>-32010</td><td>LIMIT_EXCEEDED</td></tr><tr><td>-32700</td><td>PARSE_ERROR</td></tr><tr><td>-32013</td><td>CONFIRMATION_REQUIRED</td></tr></tbody></table>",
    );
    rehypeTables()(root);
    const names = all(root, "span").filter((node) => classes(node).includes("registry-name"));
    expect(names.map((node) => [text(node), classes(node).join(" ")])).toEqual([
      ["LIMIT_EXCEEDED", "status blocked registry-name"],
      ["PARSE_ERROR", "registry-name"],
      ["CONFIRMATION_REQUIRED", "status confirm registry-name"],
    ]);
    expect(all(root, "span").filter((node) => classes(node).includes("registry-code")).map(text)).toEqual(["-32010", "-32700", "-32013"]);
  });
});

describe("glossary links", () => {
  it("link each defined term once, on its first use, outside code and headings", () => {
    const root = tree("<h2>The Hub</h2><p>A <code>Hub</code> call. The Hub owns every Device File. Hubs and the Hub again.</p>");
    rehypeGlossaryLinks()(root, file("spec/2026-10-24/architecture.md"));
    const links = all(root, "a").map((node) => [text(node), node.properties?.href]);
    expect(links).toEqual([
      ["Hub", "/spec/glossary/#term-hub"],
      ["Device File", "/spec/glossary/#term-device-file"],
    ]);
  });

  it("leave the glossary itself and non-spec pages alone", () => {
    for (const path of ["spec/GLOSSARY.md", "docs/guide/concepts.md"]) {
      const root = tree("<p>The Hub owns every Device.</p>");
      rehypeGlossaryLinks()(root, file(path));
      expect(all(root, "a")).toHaveLength(0);
    }
  });
});
