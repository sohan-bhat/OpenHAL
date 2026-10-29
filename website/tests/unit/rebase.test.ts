import { describe, expect, it } from "vitest";
import { rebase } from "../../scripts/rebase.mjs";

describe("moving a build under /OpenHAL/", () => {
  it("moves the speculation rules' pattern and leaves their selectors alone", () => {
    const rules = JSON.stringify({
      prerender: [{ source: "document", where: { and: [{ href_matches: "/*" }, { not: { selector_matches: "a[href*='/spec/playground/'], a[href^='#']" } }] }, eagerness: "moderate" }],
    });
    const page = `<script type="speculationrules">${rules}</script>`;
    const moved = rebase(page);
    expect(moved).toContain('"href_matches": "/OpenHAL/*"');
    expect(moved).toContain("a[href*='/spec/playground/'], a[href^='#']");
    expect(rebase(moved)).toBe(moved);
  });

  it("moves where a moved page sends the browser", () => {
    const moved = rebase('<meta http-equiv="refresh" content="0; url=/spec/v0.1/basic/messages/"><a href="/spec/v0.1/basic/messages/" data-moved>');
    expect(moved).toContain('content="0; url=/OpenHAL/spec/v0.1/basic/messages/"');
    expect(moved).toContain('href="/OpenHAL/spec/v0.1/basic/messages/"');
    expect(rebase(moved)).toBe(moved);
  });

  it("moves where Starlight's search loads the index and where its results point", () => {
    const script = "new n({...t,element:`#starlight__search`,baseUrl:`/`,bundlePath:`/`.replace(/\\/$/,``)+`/pagefind/`,showImages:!1})";
    const moved = rebase(script);
    expect(moved).toContain("baseUrl:`/OpenHAL/`");
    expect(moved).toContain("+`/OpenHAL/pagefind/`");
    expect(rebase(moved)).toBe(moved);
    expect(rebase("t=function(e){return`/`+e}")).toBe("t=function(e){return`/OpenHAL/`+e}");
  });

  it("moves the pages the header's pickers open", () => {
    const moved = rebase('<select autocomplete="off"><option value="/spec/v0.1/basic/messages/" selected>v0.1</option><option value="dark">Dark</option></select>');
    expect(moved).toContain('<option value="/OpenHAL/spec/v0.1/basic/messages/" selected>');
    expect(moved).toContain('<option value="dark">');
    expect(rebase(moved)).toBe(moved);
  });

  it("moves every candidate of a crop's srcset", () => {
    const moved = rebase('<source srcset="/captures/inspector-device-dark-843.avif 843w, /captures/inspector-device-dark-992.avif 992w" sizes="(min-width: 1024px) 992px">');
    expect(moved).toContain('srcset="/OpenHAL/captures/inspector-device-dark-843.avif 843w, /OpenHAL/captures/inspector-device-dark-992.avif 992w"');
  });
});
