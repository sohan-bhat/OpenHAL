<script lang="ts">
  import type { Arrow } from "../lib/trace";

  let { arrow }: { arrow: Arrow } = $props();

  const right = $derived(arrow.startsWith("right"));
  const dashed = $derived(arrow.endsWith("dashed"));
  const label = $derived(
    `${right ? "client to hub" : "hub to client"}${dashed ? ", notification" : ""}`,
  );
</script>

<svg class="arrow" width="22" height="12" viewBox="0 0 22 12" role="img" aria-label={label}>
  {#if right}
    <path d="M1 6h14" stroke="currentColor" stroke-width="1.5" stroke-dasharray={dashed ? "3 2" : undefined} />
    <path d="M21 6 15 2.5v7z" fill="currentColor" />
  {:else}
    <path d="M7 6h14" stroke="currentColor" stroke-width="1.5" stroke-dasharray={dashed ? "3 2" : undefined} />
    <path d="M1 6 7 2.5v7z" fill="currentColor" />
  {/if}
</svg>

<style>
  .arrow {
    color: var(--text);
    flex: none;
    vertical-align: middle;
  }
</style>
