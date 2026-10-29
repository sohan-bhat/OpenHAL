import { describe, expect, it } from "vitest";
import { forIndex } from "../../scripts/search-index.mjs";

describe("search snippets", () => {
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
