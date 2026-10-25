<script lang="ts">
  let { size = 20 }: { size?: number } = $props();
</script>

<svg class="mark" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <line x1="11" y1="2" x2="11" y2="14" />
  <line x1="2" y1="5" x2="8.5" y2="5" />
  <line x1="8.5" y1="11" x2="5" y2="11" />
  <polygon points="1.2,11 5.4,7.8 5.4,14.2" />
</svg>

<style>
  .mark {
    flex: none;
    color: var(--accent);
  }

  line {
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
  }

  polygon {
    fill: currentColor;
  }
</style>
