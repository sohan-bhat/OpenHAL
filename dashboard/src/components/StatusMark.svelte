<script lang="ts">
  import type { Tone } from "../lib/status";

  let {
    tone,
    label,
    compact = false,
  }: { tone: Tone; label: string; compact?: boolean } = $props();
</script>

<span class="status fade-status {tone}" class:compact data-tone={tone}>{label}</span>

<style>
  .status {
    display: inline;
    max-width: 100%;
    font-size: var(--t-label);
    font-weight: 700;
    line-height: 1.2;
    color: var(--text-2);
  }

  .ok {
    color: var(--ok);
  }

  .confirm {
    color: var(--confirm);
  }

  .blocked {
    color: var(--blocked);
  }

  .unverified {
    color: var(--unverified);
    white-space: nowrap;
  }

  .compact {
    font-weight: 400;
  }
</style>
