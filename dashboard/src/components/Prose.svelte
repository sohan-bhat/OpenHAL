<script lang="ts">
  import { keepTogether } from "../lib/units";

  let { text }: { text: string } = $props();

  const segments = $derived(keepTogether(text));
</script>

{#each segments as segment, index (index)}{#if segment.keep}<span class="nobreak">{segment.text}</span>{:else}{segment.text}{/if}{/each}
