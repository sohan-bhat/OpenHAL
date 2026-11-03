import { describe, expect, it } from "vitest";
import { remarkDescription, summarize } from "../../src/lib/markdown/plugins.mjs";

type Node = { type: string; depth?: number; value?: string; children?: Node[] };

const text = (value: string): Node => ({ type: "text", value });
const paragraph = (...children: Node[]): Node => ({ type: "paragraph", children });
const heading = (depth: number, value: string): Node => ({ type: "heading", depth, children: [text(value)] });

function described(children: Node[], frontmatter: Record<string, unknown> = {}): unknown {
  const file = { data: { astro: { frontmatter } } };
  remarkDescription()({ type: "root", children }, file);
  return file.data.astro.frontmatter.description;
}

describe("a page's description for link previews", () => {
  it("takes whole sentences until the description has enough to say", () => {
    expect(summarize("Short one. A second sentence follows here. A third.", 30)).toBe("Short one. A second sentence follows here.");
    expect(summarize("Python 3.12 or newer runs OpenHAL v0.1 today, on macOS and Linux.", 30)).toBe("Python 3.12 or newer runs OpenHAL v0.1 today, on macOS and Linux.");
    expect(summarize("  Spread\nover   lines.  ")).toBe("Spread over lines.");
  });

  it("comes from the lede paragraph, with link and code text kept", () => {
    const lede = paragraph(text("The "), { type: "link", children: [text("hub")] }, text(" serves MCP to every client through "), { type: "inlineCode", value: "openhal mcp" }, text("."));
    expect(described([lede, heading(2, "Next"), paragraph(text("A later paragraph that is long enough to count."))])).toBe("The hub serves MCP to every client through openhal mcp.");
  });

  it("leaves out generated blocks and short status lines", () => {
    const generated = [{ type: "html", value: "<!-- install:start -->" }, paragraph(text("On macOS and Linux, run this command in a terminal.")), { type: "html", value: "<!-- install:end -->" }];
    const after = paragraph(text("The installer needs nothing installed first, and uv installs Python."));
    expect(described([...generated, after])).toBe("The installer needs nothing installed first, and uv installs Python.");
    expect(described([paragraph(text("Version v0.1. Status draft.")), heading(2, "Introduction"), after])).toBe("The installer needs nothing installed first, and uv installs Python.");
  });

  it("falls back to the first prose paragraph on a page that opens with a section, and keeps a description the page sets", () => {
    const answer = paragraph(text("No, OpenHAL is an open protocol with a versioned specification."));
    expect(described([heading(2, "Is OpenHAL a standard?"), answer])).toBe("No, OpenHAL is an open protocol with a versioned specification.");
    expect(described([heading(2, "Install"), paragraph(text("Too short."))])).toBeUndefined();
    expect(described([answer], { description: "From the front matter." })).toBe("From the front matter.");
  });
});
