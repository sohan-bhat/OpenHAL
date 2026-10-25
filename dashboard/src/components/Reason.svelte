<script lang="ts">
  import { reasonSegments } from "../lib/units";

  let { text, code = [] }: { text: string; code?: string[] } = $props();

  const segments = $derived(reasonSegments(text, code));
</script>

<span class="reason-text">{#each segments as segment, index (index)}{#if segment.kind === "code"}<code>{segment.text}</code>{:else if segment.kind === "keep"}<span class="nobreak">{segment.text}</span>{:else}{segment.text}{/if}{/each}</span>

<style>
  .reason-text {
    font-family: var(--font-text);
  }

  code {
    white-space: nowrap;
    font-size: 0.95em;
  }
</style>
