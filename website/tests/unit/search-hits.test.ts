import { describe, expect, it } from "vitest";
import { decode, group, highlight, localPath, marked, sectionOf, terms } from "../../src/components/islands/search/hits";

const sections = [
  { label: "Overview", match: ["/"] },
  { label: "Docs", match: ["/docs/", "/sdks/", "/inspector/"] },
  { label: "Specification", match: ["/spec/"] },
  { label: "Playground", match: ["/spec/playground/"] },
  { label: "Drivers", match: ["/drivers/"] },
  { label: "Device Library", match: ["/library/"] },
];

describe("the search palette's results", () => {
  it("read Pagefind's excerpt as text runs, marked where it matched, with its entities decoded", () => {
    expect(marked("the hub returns <mark>LIMIT_EXCEEDED</mark> &amp; stops &lt;here&gt;")).toEqual([
      { text: "the hub returns ", mark: false },
      { text: "LIMIT_EXCEEDED", mark: true },
      { text: " & stops <here>", mark: false },
    ]);
    expect(decode("&#39;a&#x27; &quot;b&quot; &unknown;")).toBe("'a' \"b\" &unknown;");
  });

  it("mark the query's words in a title whatever their case, longest first", () => {
    expect(terms("hal/write the Hub a")).toEqual(["hal/write", "the", "hub"]);
    expect(highlight("The Hub and its hubs", "hub")).toEqual([
      { text: "The ", mark: false },
      { text: "Hub", mark: true },
      { text: " and its ", mark: false },
      { text: "hub", mark: true },
      { text: "s", mark: false },
    ]);
    expect(highlight("Quickstart", "")).toEqual([{ text: "Quickstart", mark: false }]);
  });

  it("belong to the header section with the longest matching prefix, under the site's base", () => {
    expect(sectionOf("/spec/playground/", sections)).toBe("Playground");
    expect(sectionOf("/spec/errors/", sections)).toBe("Specification");
    expect(sectionOf("/inspector/", sections)).toBe("Docs");
    expect(sectionOf("/", sections)).toBe("Overview");
    expect(sectionOf("/blog/first/", sections)).toBe("Other pages");
    expect(localPath("/OpenHAL/docs/quickstart/#stop", "/OpenHAL/")).toBe("/docs/quickstart/");
    expect(localPath("/docs/quickstart/", "/")).toBe("/docs/quickstart/");
  });

  it("group pages by section in the order their best page ranks, with up to two matching sections under each page", () => {
    const found = group(
      [
        {
          url: "/OpenHAL/spec/errors/",
          excerpt: "a <mark>refusal</mark>",
          meta: { title: "Errors" },
          sub_results: [
            { title: "Errors", url: "/OpenHAL/spec/errors/#_top", excerpt: "a <mark>refusal</mark>" },
            { title: "Registry", url: "/OpenHAL/spec/errors/#registry", excerpt: "the <mark>refusal</mark> codes" },
            { title: "Notes", url: "/OpenHAL/spec/errors/#notes", excerpt: "no match here" },
          ],
        },
        { url: "/OpenHAL/docs/quickstart/", excerpt: "the <mark>refusal</mark>", meta: { title: "Quickstart" }, sub_results: [{ title: "Stop", url: "/OpenHAL/docs/quickstart/#stop", excerpt: "the <mark>refusal</mark>" }] },
        { url: "/OpenHAL/spec/safety/", excerpt: "<mark>refusal</mark>s", meta: { title: "5 Safety &amp; limits" } },
      ],
      sections,
      "/OpenHAL/",
    );
    expect(found.map((item) => item.section)).toEqual(["Specification", "Docs"]);
    expect(found[0].hits.map((hit) => [hit.title, hit.heading ?? ""])).toEqual([
      ["Errors", ""],
      ["Errors", "Registry"],
      ["5 Safety & limits", ""],
    ]);
    expect(found[1].hits.map((hit) => [hit.heading ?? "page", hit.excerpt])).toEqual([
      ["page", ""],
      ["Stop", "the <mark>refusal</mark>"],
    ]);
  });
});
