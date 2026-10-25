<script lang="ts">
  import { tokenizeJson } from "../lib/trace";

  let { value, limit = 4000 }: { value: unknown; limit?: number } = $props();

  const tokens = $derived(tokenizeJson(value, limit));
</script>

<code class="json">{#each tokens as token, index (index)}<span class="t-{token.type}">{token.text}</span>{/each}</code>

<style>
  .json {
    font-family: var(--font-mono);
    font-size: var(--t-mono);
    color: var(--syn-string);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .t-key,
  .t-punct {
    color: var(--syn-key);
  }

  .t-punct {
    color: var(--syn-punct);
  }

  .t-number,
  .t-boolean,
  .t-null {
    color: var(--syn-number);
  }

  .t-more {
    color: var(--syn-comment);
    font-style: italic;
  }
</style>
