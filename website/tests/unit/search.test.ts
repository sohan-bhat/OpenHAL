import { describe, expect, it } from "vitest";
import { forIndex } from "../../scripts/search-index.mjs";
import { looksLikeCode, snippetOf } from "../../src/components/search";

describe("search snippets", () => {
  it("tell prose from code and YAML", () => {
    expect(looksLikeCode("The kernel refuses a <mark>300</mark> °C nozzle because the limit is 260 °C.")).toBe(false);
    expect(looksLikeCode("Pair a browser with the one-time code that openhal pair prints.")).toBe(false);
    expect(looksLikeCode("channel: extruder_target unit: degC min: 0 max: 260")).toBe(true);
    expect(looksLikeCode('{ "device": "printer", "channel": "bed_target", "value": 70 }')).toBe(true);
    expect(looksLikeCode("$ git clone https://github.com/sohan-bhat/OpenHAL $ cd OpenHAL $ uv run openhal demo")).toBe(true);
    expect(looksLikeCode("openhal.client.Client.write hal/write extruder_target bed_target")).toBe(true);
  });

  it("show the page's description when the excerpt is code or missing", () => {
    expect(snippetOf("The hub queues the <mark>cancel</mark> for a person.", "Desc.")).toEqual({ html: "The hub queues the <mark>cancel</mark> for a person." });
    expect(snippetOf("device: printer connect: { moonraker: http://printer.local }", " A printer. ")).toEqual({ text: "A printer." });
    expect(snippetOf("", "A printer.")).toEqual({ text: "A printer." });
    expect(snippetOf("max: 260 unit: degC", undefined)).toBeNull();
  });

  it("leave code blocks, YAML and traces out of what the index reads", () => {
    const page =
      '<main data-pagefind-body><p>Prose.</p><figure class="code-block" data-language="yaml"><pre tabindex="0"><code>device: printer</code></pre></figure>' +
      '<figure class="trace-figure"><div class="trace" role="region">hal/write</div></figure><pre class="sig">connect()</pre></main>';
    const indexed = forIndex(page);
    expect(indexed).toContain('<figure data-pagefind-ignore="all" class="code-block"');
    expect(indexed).toContain('<figure data-pagefind-ignore="all" class="trace-figure"');
    expect(indexed).toContain('<div data-pagefind-ignore="all" class="trace"');
    expect(indexed).toContain('<pre data-pagefind-ignore="all" class="sig">');
    expect(indexed).toContain("<p>Prose.</p>");
  });
});
