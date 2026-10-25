<script lang="ts">
  let { size = 20 }: { size?: number } = $props();
</script>

<svg class="mark" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <g fill="none" stroke="currentColor" stroke-width="2">
    <path d="M1 4.5h9.5" />
    <path d="M12 1v7" />
    <path d="M15 11.5H5.5" />
  </g>
  <path d="M1 11.5 5.5 8.5v6z" fill="currentColor" />
</svg>

<style>
  .mark {
    color: var(--accent);
    flex: none;
  }
</style>
