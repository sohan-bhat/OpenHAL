<script lang="ts">
  let { size = 20 }: { size?: number } = $props();
</script>

<svg class="mark" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <circle cx="3.4" cy="8" r="2.4" class="ink" />
  <rect x="7.05" y="2" width="2.5" height="12" rx="1.25" class="accent" />
  <rect x="10.8" y="5.9" width="4.2" height="4.2" rx="1" class="ink" />
</svg>

<style>
  .mark {
    flex: none;
  }

  .ink {
    fill: var(--text);
  }

  .accent {
    fill: var(--accent);
  }
</style>
